"""Software tests only: fixtures never enter the normal application data path."""
import binascii
import csv
import json
import os
from pathlib import Path
import pty
import select
import socket
import statistics
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pi"))
import serial
from engine import Analyzer, Lines, PacketError, State, SYMBOLS, encode, parse_response, percentile, request_packet
from transport import SerialWorker, choose_port
from app import handler_for, ThreadingHTTPServer


def response(nonce=0xABCDEF01, request=1, sequence=1, boot="12345678", symbol="TCS", ppm=-4500):
    return encode(f"D,3,{nonce:08X},{request},{boot},{sequence},50000,{SYMBOLS.index(symbol)},{ppm},1,0")


class ProtocolTests(unittest.TestCase):
    def test_crc_independent_known_vector(self):
        self.assertEqual(binascii.crc_hqx(b"123456789", 0xFFFF), 0x29B1)

    def test_response_units_and_ids(self):
        item = parse_response(response())
        self.assertEqual(item["movement_pct"], -.45)
        self.assertEqual(item["nonce"], 0xABCDEF01)
        self.assertEqual(item["sequence"], 1)

    def test_crc_corruption(self):
        wire = response().replace(b"50000", b"60000")
        with self.assertRaises(PacketError) as error:
            parse_response(wire)
        self.assertEqual(error.exception.kind, "crc_errors")

    def test_semantic_rejections(self):
        for body in ["D,2,ABCDEF01,1,12345678,1,3,1,0,1,0",
                     "D,3,ABCDEF01,-1,12345678,1,3,1,0,1,0",
                     "D,3,ABCDEF01,4294967296,12345678,1,3,1,0,1,0",
                     "D,3,ABCDEF01,1,12345678,1,3,9,0,1,0",
                     "D,3,ABCDEF01,1,12345678,1,3,1,nan,1,0",
                     "D,3,ABCDEF01,1,12345678,1,3,1,1000001,1,0"]:
            with self.subTest(body=body), self.assertRaises(PacketError):
                parse_response(encode(body))

    def test_fragments_and_combined_packets(self):
        lines = Lines()
        data = response() + response(sequence=2)
        output=[]
        for byte in data:
            output.extend(lines.feed(bytes([byte]))[0])
        self.assertEqual([parse_response(x)["sequence"] for x in output], [1, 2])

    def test_overflow_discards_tail_and_resynchronizes(self):
        lines = Lines()
        found, errors = lines.feed(b"x" * 500 + response() + response(sequence=2))
        self.assertEqual(errors, 1)
        self.assertEqual(len(found), 1)
        self.assertEqual(parse_response(found[0])["sequence"], 2)

    def test_request_crc(self):
        packet = request_packet(0x12345678, 77)
        self.assertTrue(packet.startswith(b"P,3,12345678,77*"))
        body, crc = packet.rstrip().split(b"*")
        self.assertEqual(int(crc, 16), binascii.crc_hqx(body, 0xFFFF))


class StatisticsTests(unittest.TestCase):
    def ready(self):
        engine = Analyzer()
        for _ in range(64):
            engine.process("TCS", -.2)
            engine.process("TCS", .2)
        return engine

    def test_warmup_never_masquerades_as_stay(self):
        engine=Analyzer()
        for i in range(128):
            row=engine.process("TCS", i % 2)
            self.assertEqual(row["decision"], "WARMUP")
            self.assertEqual(row["history_n"], i)
        self.assertNotEqual(engine.process("TCS", .5)["decision"], "WARMUP")

    def test_positive_negative_normal(self):
        for movement, expected in [(2,"BUY"),(-2,"SELL"),(0,"STAY")]:
            row=self.ready().process("TCS",movement)
            self.assertEqual(row["decision"],expected)

    def test_no_lookahead_and_sample_std(self):
        engine=self.ready()
        prior=list(engine.windows["TCS"])
        row=engine.process("TCS",10)
        self.assertAlmostEqual(row["mean_pct"], statistics.mean(prior))
        self.assertAlmostEqual(row["std_pct"], statistics.stdev(prior))
        self.assertAlmostEqual(row["z"], 10/statistics.stdev(prior))
        self.assertEqual(engine.windows["TCS"][-1],10)
        self.assertEqual(len(engine.windows["TCS"]),128)

    def test_zero_variance_safe_json(self):
        engine=Analyzer()
        for _ in range(128): engine.process("TCS",0)
        row=engine.process("TCS",5)
        self.assertEqual(row["decision"],"STAY")
        self.assertIsNone(row["z"])
        self.assertFalse(row["stats_valid"])
        json.dumps(row,allow_nan=False)

    def test_symbol_windows_independent(self):
        engine=self.ready()
        self.assertEqual(engine.process("INFY",3)["decision"],"WARMUP")

    def test_csv_validation_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"history.csv"
            path.write_text("symbol,movement_pct,source\nTCS,1,TEST\n")
            with self.assertRaises(ValueError): Analyzer(history=path)
            engine=Analyzer()
            for symbol in SYMBOLS:
                for i in range(128): engine.process(symbol,(-1)**i*.2)
            engine.save(path)
            loaded=Analyzer(history=path)
            self.assertEqual(loaded.process("TCS",2)["decision"],"BUY")
            self.assertEqual(len(loaded.windows["TCS"]),128)

    def test_import_nonfinite_or_missing_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"history.csv"
            for row in ["TCS,nan,TEST", "TCS,inf,TEST", "TCS,1,"]:
                path.write_text("symbol,movement_pct,source\n"+row+"\n")
                with self.assertRaises(ValueError): Analyzer(history=path)

    def test_percentile_interpolation(self):
        self.assertEqual(percentile([10,20,30,40],.5),25)
        self.assertAlmostEqual(percentile([10,20,30,40],.95),38.5)
        self.assertIsNone(percentile([],.5))


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.args=SimpleNamespace(run_dir=Path(self.tmp.name),threshold=2.,history=None,baud=115200,
            quiet=True,timeout=.15,port="auto",boot_wait=0,rate=200,warmup_rate=200)
        self.state=State()
        self.stop=threading.Event()
        self.worker=SerialWorker(self.state,self.args,self.stop)

    def tearDown(self):
        self.stop.set()
        if self.worker.is_alive():self.worker.join(3)
        self.worker.event_file.close()
        self.worker.log_handler.close()
        self.worker.logger.removeHandler(self.worker.log_handler)
        self.tmp.cleanup()

    def transact(self,make_replies):
        master,slave=pty.openpty()
        connection=serial.Serial(os.ttyname(slave),115200,timeout=0,write_timeout=.2)
        def remote():
            line=b""
            while b"\n" not in line:
                line+=os.read(master,256)
            fields=line.split(b"*")[0].decode().split(",")
            for item in make_replies(int(fields[2],16),int(fields[3])):
                os.write(master,item)
        responder=threading.Thread(target=remote,daemon=True)
        responder.start()
        try:return self.worker.exchange(connection)
        finally:
            responder.join(1)
            connection.close();os.close(master);os.close(slave)

    def test_real_serial_api_handles_crc_stale_fragment_and_recovers(self):
        def replies(nonce,request):
            wire=response(nonce,request,sequence=3)
            return [response(nonce,request).replace(b"50000",b"60000"),
                    response(nonce,request-1),wire[:9],wire[9:]]
        row=self.transact(replies)
        self.assertEqual(row["sequence"],3)
        self.assertGreater(row["latency_us"],0)
        self.assertEqual(self.state.errors["crc_errors"],1)
        self.assertEqual(self.state.errors["stale_replies"],1)
        self.assertEqual(len(self.worker.analyzer.windows["TCS"]),1)

    def test_timeout_does_not_generate_signal(self):
        row=self.transact(lambda n,r:[])
        self.assertIsNone(row)
        self.assertEqual(self.state.total,0)
        self.assertEqual(len(self.worker.analyzer.windows["TCS"]),0)
        self.assertEqual(self.state.errors["timeouts"],1)

    def test_sequence_duplicate_gap_wrap_reset(self):
        self.worker.boot="12345678";self.worker.sequence=1
        row=self.transact(lambda n,r:[response(n,r,sequence=1),response(n,r,sequence=4)])
        self.assertEqual(row["sequence"],4)
        self.assertEqual(self.state.errors["duplicate_sequences"],1)
        self.assertEqual(self.state.sequence_gaps,2)
        self.worker.sequence=0xFFFFFFFF
        row=self.transact(lambda n,r:[response(n,r,sequence=0)])
        self.assertEqual(row["sequence"],0)
        row=self.transact(lambda n,r:[response(n,r,sequence=1,boot="87654321")])
        self.assertEqual(self.state.resets,1)

    def test_missing_device_worker_stays_empty(self):
        with patch("transport.choose_port",side_effect=FileNotFoundError("TEST absent device")):
            self.worker.start()
            time.sleep(.06)
            self.stop.set();self.worker.join(2)
        snapshot=self.state.snapshot()
        self.assertEqual(snapshot["status"],"HARDWARE DISCONNECTED")
        self.assertEqual(snapshot["total"],0)
        self.assertEqual(snapshot["throughput"],0)
        self.assertEqual(snapshot["latest"],[])

    def test_worker_disconnect_and_reconnect(self):
        # PTYs exercise Linux serial I/O and recovery; they are TEST fixtures only.
        fixture = {"port": None}
        handles, remote_threads, remote_stops = [], [], []
        def select_fixture(_):
            if fixture["port"] is None: raise FileNotFoundError("TEST unplugged")
            return fixture["port"]
        def attach(boot):
            master, slave = pty.openpty()
            handles.extend([master, slave])
            remote_stop = threading.Event(); remote_stops.append(remote_stop)
            def respond():
                buffer=b""; sequence=0
                while not remote_stop.is_set():
                    try:
                        if not select.select([master],[],[],.03)[0]: continue
                        buffer+=os.read(master,4096)
                        while b"\n" in buffer:
                            line,buffer=buffer.split(b"\n",1)
                            if line.startswith(b'H,3,'):
                                fields=line.split(b'*')[0].decode().split(',')
                                os.write(master,encode(f'A,3,{fields[2]},A,115200,{boot},1'))
                                continue
                            if not line.startswith(b"P,3,"):continue
                            fields=line.split(b"*")[0].decode().split(",")
                            sequence+=1
                            os.write(master,response(int(fields[2],16),int(fields[3]),sequence=sequence,boot=boot))
                    except OSError:return
            thread=threading.Thread(target=respond,daemon=True);remote_threads.append(thread);thread.start()
            fixture["port"]=os.ttyname(slave)
            return master,slave,remote_stop
        def until(predicate,seconds=6):
            deadline=time.monotonic()+seconds
            while not predicate() and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue(predicate())
        try:
            with patch("transport.choose_port",side_effect=select_fixture):
                master,slave,remote_stop=attach("11111111")
                self.worker.start()
                until(lambda:self.state.total>=5)
                fixture["port"]=None;remote_stop.set();remote_threads[-1].join(1)
                os.close(master);os.close(slave);handles.remove(master);handles.remove(slave)
                until(lambda:self.state.snapshot()["status"]=="HARDWARE DISCONNECTED")
                count=self.state.total;time.sleep(.05)
                self.assertEqual(self.state.total,count)
                attach("22222222")
                until(lambda:self.state.total>=count+5)
                self.assertGreaterEqual(self.state.connections,2)
                self.assertEqual(self.state.resets,1)
                self.stop.set();self.worker.join(2)
        finally:
            self.stop.set()
            for event in remote_stops:event.set()
            for thread in remote_threads:thread.join(1)
            for handle in handles:os.close(handle)

    def test_disconnected_state_freezes_count_and_zeroes_rate(self):
        row=self.transact(lambda n,r:[response(n,r)])
        self.state.add(row,{s:0 for s in SYMBOLS})
        self.state.status("HARDWARE DISCONNECTED","TEST removed")
        snapshot=self.state.snapshot()
        self.assertEqual(snapshot["total"],1)
        self.assertEqual(snapshot["throughput"],0)
        self.assertEqual(len(snapshot["latest"]),1)

    def test_port_ambiguity_and_no_url_backdoor(self):
        with patch("transport.ports",return_value=[{"device":"/dev/ttyUSB0"},{"device":"/dev/ttyUSB1"}]):
            with self.assertRaises(ValueError):choose_port("auto")
        for name in ["loop://","socket://localhost:4000","fixture.json"]:
            with self.assertRaises(ValueError):choose_port(name)

    def test_dashboard_api_on_disconnected_system(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),handler_for(self.state))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base="http://127.0.0.1:"+str(server.server_port)
            with urlopen(base+"/api/state",timeout=2) as reply: data=json.load(reply)
            self.assertEqual(data["total"],0)
            self.assertIsNone(data["latency"]["avg"])
            with urlopen(base,timeout=2) as reply:self.assertIn(b"PulseBridge",reply.read())
        finally:server.shutdown();server.server_close();thread.join(1)


if __name__=="__main__":unittest.main()
