#!/usr/bin/env python3
"""Measured software baselines on the executing host. Never physical USB/Pi claims."""
import argparse
import binascii
import json
from pathlib import Path
import platform
import resource
import socket
import struct
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'pi'))
from protocol import BinaryFrames,RESPONSE,parse_response,encode
from terminal.lab import parse_bars,train,backtest
from terminal.analytics import cached_features
from terminal.discovery import discover
from terminal.research_store import ResearchStore
from terminal.runtime import Ledger
from terminal.market import summary
from tools.make_fixture import csv_text

def run(out):
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    measured={}
    def timed(name,function):
        start=time.perf_counter();cpu=time.process_time();value=function()
        measured[name]=dict(wall_s=time.perf_counter()-start,cpu_s=time.process_time()-cpu);return value
    raw=RESPONSE.pack(b'PB',3,2,1,1,1,1,1,25,0,1,0);wire=raw+struct.pack('<H',binascii.crc_hqx(raw,0xffff));ascii_=encode('D,3,00000001,1,00000001,1,1,0,25,1,0')
    def binary():
        parser=BinaryFrames()
        for _ in range(20000):
            packets,errors=parser.feed(wire)
            if len(packets)!=1 or errors:raise ValueError('Parser benchmark failed validation')
    def ascii_parse():
        for _ in range(20000):parse_response(ascii_)
    timed('binary_parser_20000',binary);timed('ascii_parser_20000',ascii_parse)
    data=parse_bars(csv_text(900,197),'ITC',60,'simulated','Deterministic software benchmark fixture')
    with tempfile.TemporaryDirectory() as tmp:
        store=ResearchStore(Path(tmp)/'research.sqlite3')
        timed('features_cold_900',lambda:cached_features(store,data));timed('features_cached_900',lambda:cached_features(store,data))
        model=timed('logistic_train_900',lambda:train(data,2))
        timed('backtest_900',lambda:backtest(data,dict(strategy='momentum')))
        timed('discovery_8_candidates_900',lambda:discover(store,data,dict(budget=8),'benchmark'))
        db=Ledger(Path(tmp)/'batch.sqlite3');db.begin('benchmark','simulated','INR')
        payloads=[('benchmark','{}',[],[],[('benchmark',i,0.,'BENCH','fixture')],[]) for i in range(2000)]
        timed('sqlite_2000_audit_rows_batches16',lambda:[db.save_batch(payloads[i:i+16]) for i in range(0,len(payloads),16)]);db.close()
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        start=time.monotonic();log=(Path(tmp)/'server.log').open('w')
        process=subprocess.Popen([sys.executable,'-m','terminal.server','--mode','simulated','--no-hardware','--quiet','--data-dir',str(Path(tmp)/'app'),'--http-port',str(port)],cwd=ROOT,stdout=log,stderr=log)
        url='http://127.0.0.1:'+str(port)+'/api/state'
        try:
            while time.monotonic()-start<15:
                try:
                    with urlopen(url,timeout=1) as r:state=json.load(r)
                    if state.get('total',0)>0:break
                except OSError:pass
                time.sleep(.05)
            else:raise ValueError('Startup did not complete')
            measured['startup_to_first_simulated_tick_s']=time.monotonic()-start
            timings=[];sizes=[]
            for _ in range(30):
                t=time.perf_counter_ns()
                with urlopen(url,timeout=3) as r:body=r.read()
                timings.append((time.perf_counter_ns()-t)/1e6);sizes.append(len(body))
            measured['localhost_api_ms']=summary(timings);measured['localhost_api_bytes']=summary(sizes)
        finally:
            import signal
            stop=time.monotonic();process.send_signal(signal.SIGTERM);process.wait(12);log.close()
            measured['shutdown_s']=time.monotonic()-stop;measured['shutdown_exitcode']=process.returncode
    report=dict(kind='HOST_SOFTWARE_BENCHMARK',host=dict(platform=platform.platform(),machine=platform.machine(),python=sys.version.split()[0]),
                measurements=measured,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                physical_hardware_tested=False,hosted_provider_latency=None,
                limitations=['One execution on the recorded host, not a repeated confidence study or Raspberry Pi result.',
                  'Parser timings include Python calls; no physical transport. Native sketch correctness is tested separately.',
                  'RSS is the benchmark process high-water mark, not the combined workstation footprint.',
                  'SQLite storage reflects this host filesystem, not SD-card durability or throughput.',
                  'API is localhost HTTP response time, not browser rendering or end-to-screen latency.'])
    out.write_text(json.dumps(report,indent=2,allow_nan=False));return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.out),indent=2))
