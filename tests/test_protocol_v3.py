"""Cross-language/fault tests use the ACTUAL sketch with explicit native shims.
PTY/native results are software evidence, never physical board latency.
"""
import binascii
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pi'))
from protocol import (BASE_BAUD, PROFILES, VERSION, BinaryFrames, PacketError, RESPONSE,
                      binary_request, encode, handshake, parse_ack, parse_binary, parse_response, parse_stats)
from app import arguments
from engine import State
from transport import SerialWorker, choose_port
ROOT=Path(__file__).resolve().parents[1]
NONCE=0xABCDEF01


class NativeAgreementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('g++'):raise unittest.SkipTest('Native g++ unavailable; target compile is separate')
        cls.temp=tempfile.TemporaryDirectory()
        cls.bin=Path(cls.temp.name)/'native'
        cls.flags=['g++','-std=c++17','-Wall','-Wextra','-Werror','-Itests/native',
                   '-DPB_BOARD_PROFILE=1','-DCONFIG_IDF_TARGET_ESP32=1',
                   'tests/native_protocol.cpp','-o',str(cls.bin)]
        subprocess.run(cls.flags,cwd=ROOT,check=True,capture_output=True,text=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def run_device(self,commands):
        text='\n'.join(c.hex() if isinstance(c,bytes) else c for c in commands)+'\n'
        result=subprocess.run([str(self.bin)],input=text,capture_output=True,text=True,timeout=5,check=True)
        return [json.loads(x) for x in result.stdout.splitlines()]
    def begin(self,binary=True,seed=42):return handshake(NONCE,binary,460800 if binary else BASE_BAUD,seed)
    def test_fragmented_concatenated_corrupt_stale_cache_and_idle(self):
        first=binary_request(NONCE,1);bad=bytearray(binary_request(NONCE,2));bad[-1]^=1
        commands=[self.begin(),*map(lambda x:bytes([x]),first),first,
                  bytes(bad)+binary_request(NONCE^1,2)+binary_request(NONCE,2)+binary_request(NONCE,3),
                  binary_request(NONCE,2), '@2001',self.begin(False),encode(f'P,3,{NONCE:08X},1'),b'STATS\n']
        out=self.run_device(commands)
        parse_ack(bytes.fromhex(out[0]['hex']),NONCE,True,460800)
        self.assertTrue(all(x['hex']=='' for x in out[1:14]))
        frame=bytes.fromhex(out[14]['hex']);a=parse_binary(frame)
        self.assertEqual(a['source'],'SYNTHETIC');self.assertEqual(a['sequence'],1)
        self.assertEqual(out[14]['hex'],out[15]['hex'])
        packets,errs=BinaryFrames().feed(bytes.fromhex(out[16]['hex']))
        self.assertEqual([x['request_id'] for x in packets],[2,3]);self.assertFalse(errs)
        self.assertEqual(out[16]['crc'],1);self.assertEqual(out[16]['rejected'],1)
        self.assertEqual(out[17]['hex'],'');self.assertEqual(out[17]['rejected'],2)
        self.assertEqual(out[18]['baud'],115200);self.assertFalse(out[18]['session'])
        response=parse_response(bytes.fromhex(out[20]['hex']))
        self.assertEqual(response['movement_pct'],a['movement_pct'])
        stats=parse_stats(bytes.fromhex(out[21]['hex']))
        self.assertEqual(stats['duplicates'],1);self.assertEqual(stats['rejected_requests'],2)
    def test_seed_cross_encoding_and_vectors(self):
        binary=self.run_device([self.begin(),binary_request(NONCE,1)])
        ascii_=self.run_device([self.begin(False),encode(f'P,3,{NONCE:08X},1')])
        b=parse_binary(bytes.fromhex(binary[1]['hex']));a=parse_response(bytes.fromhex(ascii_[1]['hex']))
        self.assertEqual(a,b)
        self.assertEqual(binary_request(0x12345678,1).hex(),'504203017856341201000000472a')
    def test_python_fixture_matches_actual_sketch_seed_and_outliers(self):
        from simulator import ProtocolSimulator
        fixture=ProtocolSimulator(threading.Event())
        try:
            fixture.text(self.begin())
            rows=self.run_device([self.begin()]+[binary_request(NONCE,i) for i in range(1,220)])
            for i,row in enumerate(rows[1:],1):
                native=parse_binary(bytes.fromhex(row['hex']));python=parse_binary(fixture.reply(NONCE,i))
                for field in ('symbol','movement_pct','sequence','request_id','source'):self.assertEqual(native[field],python[field])
        finally:os.close(fixture.master);os.close(fixture.slave)
    def test_boot_session_required_and_handshake_replay_cannot_reset_cache(self):
        out=self.run_device([encode(f'P,3,{NONCE:08X},1'),self.begin(False),
                             encode(f'P,3,{NONCE:08X},1'),self.begin(False),
                             encode(f'P,3,{NONCE:08X},1'),encode(f'P,3,{NONCE^1:08X},2')])
        self.assertFalse(out[0]['hex']);self.assertEqual(out[0]['rejected'],1)
        self.assertEqual(out[2]['hex'],out[4]['hex']);self.assertEqual(out[-1]['rejected'],3)
    def test_long_noise_bounded_and_recovers_after_truncation(self):
        rng=random.Random(27);noise=bytes(rng.randrange(256) for _ in range(8000))
        request=binary_request(NONCE,9)
        out=self.run_device([self.begin(),noise+request[:8]+request])[-1]
        packets,_=BinaryFrames().feed(bytes.fromhex(out['hex']))
        self.assertEqual([x['request_id'] for x in packets],[9]);self.assertLess(out['ring_length'],14)
    def test_ascii_bounds_and_idle_counter_wrap(self):
        out=self.run_device([b'x'*1000+b'\n',self.begin(False),encode(f'P,3,{NONCE:08X},4294967295'),
                             encode(f'P,3,{NONCE:08X},0'),encode(f'P,3,{NONCE:08X},4294967295'),
                             '@4294967290','@20'])
        self.assertGreater(out[0]['framing'],0)
        self.assertEqual(parse_response(bytes.fromhex(out[3]['hex']))['request_id'],0)
        self.assertEqual(out[4]['hex'],'');self.assertFalse(out[-1]['session'])
    def test_all_explicit_profiles_native_shim_build(self):
        for profile,chip in [(2,'ESP32S3'),(3,'ESP32C3'),(4,'ESP32S3'),(5,'ESP32C3')]:
            flags=['g++','-std=c++17','-Wall','-Wextra','-Werror','-Itests/native',
                   f'-DPB_BOARD_PROFILE={profile}',f'-DCONFIG_IDF_TARGET_{chip}=1']
            if profile>=4:flags+=['-DARDUINO_USB_CDC_ON_BOOT=1','-DARDUINO_USB_MODE=1']
            target=Path(self.temp.name)/f'native{profile}'
            subprocess.run(flags+['tests/native_protocol.cpp','-o',str(target)],cwd=ROOT,check=True,capture_output=True)
            cmd=handshake(NONCE,True,460800,42).hex()+'\n'+binary_request(NONCE,1).hex()+'\n'
            rows=subprocess.run([str(target)],input=cmd,capture_output=True,text=True,timeout=5,check=True).stdout.splitlines()
            self.assertEqual(parse_binary(bytes.fromhex(json.loads(rows[-1])['hex']))['source'],'SYNTHETIC')
    def test_missing_and_mismatched_target_are_compile_errors(self):
        for flags in [[],['-DPB_BOARD_PROFILE=1','-DCONFIG_IDF_TARGET_ESP32C3=1'],
                      ['-DPB_BOARD_PROFILE=4','-DCONFIG_IDF_TARGET_ESP32S3=1']]:
            cmd=['g++','-std=c++17','-Itests/native',*flags,'tests/native_protocol.cpp','-o',str(Path(self.temp.name)/'reject')]
            r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0);self.assertIn('error:',r.stderr)


class HostV3Tests(unittest.TestCase):
    def test_profile_contract(self):
        for name,(baud,_,_) in PROFILES.items():self.assertEqual(arguments(['--profile',name]).baud,baud)
        for options in [['--profile','fast','--baud','115200'],['--profile','compat','--baud','460800']]:
            with self.assertRaises(SystemExit):arguments(options)
    def test_flags_reserved_and_version_strict(self):
        for version,flag,reserved in [(2,1,0),(3,0,0),(3,3,0),(3,1,1)]:
            body=RESPONSE.pack(b'PB',version,2,NONCE,1,123,1,10,10,0,flag,reserved)
            with self.assertRaises(PacketError):parse_binary(body+struct.pack('<H',binascii.crc_hqx(body,0xFFFF)))
    def test_by_id_preferred_and_aliases_deduplicated(self):
        with patch('transport.ports',return_value=[dict(device='/dev/ttyUSB0')]), \
             patch('transport.glob.glob',return_value=['/dev/serial/by-id/test']), \
             patch('transport.os.path.realpath',return_value='/dev/ttyUSB0'):
            self.assertEqual(choose_port('auto'),'/dev/serial/by-id/test')
    def test_bounded_input_overflow_is_explicit(self):
        parser=BinaryFrames();packets,errors=parser.feed(b'P'*100000)
        self.assertFalse(packets);self.assertEqual(errors['parser_overflows'],1);self.assertLess(len(parser.buffer),34)
    def test_error_queue_pressure_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=arguments(['--quiet','--log','off']);args.run_dir=Path(tmp)
            w=SerialWorker(State(),args,threading.Event())
            try:
                for _ in range(520):w.state.error('crc_errors','fixture')
                self.assertEqual(w.state.event_dropped,8);self.assertEqual(w.state.errors['crc_errors'],520)
            finally:w.event_file.close();w.log_handler.close();w.logger.removeHandler(w.log_handler)
    def test_wrong_board_ack_rejected_before_data(self):
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as tmp:
            args=arguments(['--quiet','--board-profile','1']);args.run_dir=Path(tmp)
            w=SerialWorker(State(),args,threading.Event());connection=MagicMock()
            connection.write.side_effect=lambda raw:len(raw)
            connection.in_waiting=100;connection.read.return_value=encode(f'A,3,{w.nonce:08X},A,115200,12345678,2')
            try:
                with patch('transport.select.select',return_value=([1],[],[])):
                    with self.assertRaisesRegex(Exception,'board profile mismatch'):w.negotiate(connection)
                self.assertIsNone(w.expected_boot);self.assertEqual(w.state.total,0)
            finally:w.event_file.close();w.log_handler.close();w.logger.removeHandler(w.log_handler)
    def test_permission_denied_remains_disconnected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=arguments(['--quiet','--log','off']);args.run_dir=Path(tmp)
            stop=threading.Event();state=State();w=SerialWorker(state,args,stop)
            def denied(*args):stop.set();raise PermissionError('Permission denied: test device')
            with patch('transport.choose_port',return_value='/dev/PB_FIXTURE'),patch('transport.open_connection',side_effect=denied):w.run()
            self.assertEqual(state.link,'HARDWARE DISCONNECTED');self.assertIn('Permission denied',state.reason);self.assertEqual(state.total,0)

if __name__=='__main__':unittest.main()
