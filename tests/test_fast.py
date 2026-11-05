"""v2 transport and exact running statistics; test fixtures only."""
import binascii
from collections import deque
import math
import os
from pathlib import Path
import pty
import random
import select
import statistics
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pi"))
import serial
from engine import Analyzer, BinaryFrames, RingWindow, State, RESPONSE, binary_request, parse_binary, PacketError, encode
from transport import SerialWorker
from app import arguments

def reply(nonce,request,seq=1,ppm=12345,symbol=0):
    body=RESPONSE.pack(b"PB",3,2,nonce,request,123,seq,1000,ppm,symbol,1,0)
    return body+struct.pack("<H",binascii.crc_hqx(body,0xFFFF))

class FastProtocolTests(unittest.TestCase):
    def test_sizes_fields_signed_crc(self):
        self.assertEqual(len(binary_request(123,456)),14)
        frame=reply(123,456,7,-20000,2)
        self.assertEqual(len(frame),34)
        value=parse_binary(frame)
        self.assertEqual((value['nonce'],value['request_id'],value['symbol'],value['movement_pct']), (123,456,'INFY',-2))

    def test_noise_corruption_missing_byte_recovery(self):
        parser=BinaryFrames();bad=bytearray(reply(1,1));bad[15]^=1
        data=b'boot noise'+bytes(bad)+reply(1,2)[:15]+reply(1,3)
        packets=[];errors={}
        for byte in data:
            out,err=parser.feed(bytes([byte]));packets.extend(out)
            for k,v in err.items():errors[k]=errors.get(k,0)+v
        self.assertEqual([x['request_id'] for x in packets],[3])
        self.assertGreater(errors['crc_errors'],0)
        self.assertLess(len(parser.buffer),34)

    def test_combined_frames_and_unknown_symbol(self):
        parser=BinaryFrames();frames,_=parser.feed(reply(1,1)+reply(1,2))
        self.assertEqual(len(frames),2)
        with self.assertRaises(PacketError):parse_binary(reply(1,1,symbol=250))

    def test_random_noise_memory_bounded(self):
        parser=BinaryFrames()
        for _ in range(100):parser.feed(b'x'*10000)
        self.assertLessEqual(len(parser.buffer),1)

    def test_profiles_and_unpaced(self):
        self.assertEqual(arguments(['--profile','turbo']).baud,921600)
        self.assertEqual(arguments(['--profile','turbo']).rate,0)
        self.assertEqual(arguments(['--profile','compat']).baud,115200)
        self.assertEqual(arguments([]).profile,'compat')

class ExactStatisticsTests(unittest.TestCase):
    def test_matches_reference_for_long_stream(self):
        rng=random.Random(7);window=RingWindow();reference=deque(maxlen=128)
        for i in range(20000):
            value=rng.randrange(-1_000_000,1_000_001)/10000
            window.append(value);reference.append(value)
            if i%113==0 and len(reference)>1:
                mean,std=window.statistics()
                self.assertAlmostEqual(mean,statistics.mean(reference),places=11)
                self.assertAlmostEqual(std,statistics.stdev(reference),places=11)

    def test_large_offset_tiny_variance_no_cancellation(self):
        window=RingWindow()
        for i in range(128):window.append(99.9999 if i%2 else 100)
        _,std=window.statistics()
        self.assertGreater(std,0)
        self.assertAlmostEqual(std,statistics.stdev(list(window)),places=12)

    def test_rounding_precision_contract(self):
        window=RingWindow();window.append(.1234567)
        self.assertEqual(window[0],.1235)

class BinaryIntegrationTests(unittest.TestCase):
    def test_negotiate_exchange_stages_and_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=arguments(['--profile','turbo','--quiet','--log','off'])
            args.run_dir=Path(tmp);args.timeout=.1
            state=State();stop=threading.Event();worker=SerialWorker(state,args,stop)
            master,slave=pty.openpty();connection=serial.Serial(os.ttyname(slave),115200,timeout=0,write_timeout=.2)
            def device():
                text=b''
                while not text.endswith(b'\n'):text+=os.read(master,1)
                fields=text.split(b'*')[0].decode().split(',')
                nonce=int(fields[2],16)
                os.write(master,encode(f'A,3,{nonce:08X},B,921600,0000007B,1'))
                data=b''
                while len(data)<14:data+=os.read(master,14-len(data))
                self.assertEqual(binascii.crc_hqx(data[:-2],0xFFFF),int.from_bytes(data[-2:],'little'))
                _,_,_,nonce,request=struct.unpack('<2sBBII',data[:-2])
                wire=reply(nonce,request)
                os.write(master,wire[:7]);os.write(master,wire[7:])
            thread=threading.Thread(target=device,daemon=True);thread.start()
            try:
                worker.negotiate(connection)
                self.assertEqual(connection.baudrate,921600)
                row=worker.exchange(connection)
                self.assertIsNotNone(row)
                self.assertAlmostEqual(row['latency_us'],row['write_us']+row['wait_us']+row['host_us'],places=6)
                self.assertGreaterEqual(row['host_us'],row['analysis_us'])
                state.add(row,{s:len(w) for s,w in worker.analyzer.windows.items()})
                self.assertEqual(state.snapshot()['success_pct'],100)
                self.assertIsNone(worker.exchange(connection))
                self.assertEqual(state.total,1)
            finally:
                stop.set();thread.join(2);connection.close();os.close(master);os.close(slave)
                worker.event_file.close();worker.log_handler.close();worker.logger.removeHandler(worker.log_handler)

    def test_output_queue_pressure_does_not_change_decision_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=arguments(['--profile','turbo','--quiet','--log','all']);args.run_dir=Path(tmp)
            state=State();worker=SerialWorker(state,args,threading.Event())
            try:
                for i in range(4100):worker.output({'index':i})
                self.assertEqual(state.log_dropped,4)
                self.assertEqual(state.total,0)
                self.assertEqual(worker.output_queue.qsize(),4096)
            finally:worker.event_file.close();worker.log_handler.close();worker.logger.removeHandler(worker.log_handler)

if __name__=='__main__':unittest.main()
