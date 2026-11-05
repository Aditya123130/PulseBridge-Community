#!/usr/bin/env python3
"""One physical serial experiment; no fixture, fallback or provider data source."""
import argparse
from array import array
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import resource
import signal
import sys
import threading
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'pi'))
from app import arguments
from engine import State, percentile
from protocol import VERSION, PROFILES
from transport import SerialWorker, health_loop
from terminal.trace import TraceRecorder

STAGES=('latency_us','write_us','wait_us','read_us','poll_wait_us','validate_us','analysis_us','host_us')


def summarize(values):
    data=sorted(values)
    return dict(n=len(data),avg=sum(data)/len(data) if data else None,min=data[0] if data else None,
                max=data[-1] if data else None,p50=percentile(data,.5),p95=percentile(data,.95),p99=percentile(data,.99))


def analyze_trace(path):
    samples={k:array('d') for k in STAGES}
    count=0
    with path.open() as f:
        for line in f:
            row=json.loads(line)
            if row.get('source')!='SYNTHETIC' or row.get('protocol_version')!=VERSION:
                raise ValueError('Unexpected trace provenance/protocol')
            count+=1
            if count>1_300_000:raise ValueError('Trace exceeds bounded single-run analysis capacity')
            for key in STAGES:samples[key].append(row[key])
    return {k:summarize(v) for k,v in samples.items()}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--board-profile',type=int,choices=range(1,6),required=True)
    p.add_argument('--profile',choices=list(PROFILES),default='compat')
    p.add_argument('--seconds',type=float,default=60)
    p.add_argument('--warmup-seconds',type=float,default=5)
    p.add_argument('--startup-timeout',type=float,default=120)
    p.add_argument('--rate',type=float,default=0)
    p.add_argument('--output-mode',choices=['off','on'],default='off')
    p.add_argument('--device-seed',type=int,default=42)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args(argv)
    if not 1<=a.seconds<=600 or not 0<=a.warmup_seconds<=60 or not 1<=a.startup_timeout<=600:
        p.error('seconds=1..600, warmup=0..60, startup timeout=1..600')
    options=['--board-profile',str(a.board_profile),'--profile',a.profile,'--port',a.port,'--rate',str(a.rate),'--warmup-rate',str(a.rate),
             '--device-seed',str(a.device_seed),'--terminal','tape','--log','sampled' if a.output_mode=='on' else 'off']
    if a.output_mode=='off':options+=['--quiet']
    args=arguments(options);a.out.mkdir(parents=True,exist_ok=False);args.run_dir=a.out
    trace=TraceRecorder(a.out/'measured.jsonl')
    started_utc=datetime.now(timezone.utc).isoformat()
    launched=time.monotonic();duration_ns=int(a.seconds*1e9)
    class MeasuredState(State):
        first_ns=None
        measured=0
        def add(self,row,histories):
            super().add(row,histories)
            if row['decision']=='WARMUP' or min(histories.values())<128 or time.monotonic()-launched<a.warmup_seconds:
                return
            if self.first_ns is None:self.first_ns=row['request_started_ns']
            if row['classified_ns']-self.first_ns<=duration_ns:
                trace.add(dict(row));self.measured+=1
    state=MeasuredState(a.rate);stop=threading.Event();worker=SerialWorker(state,args,stop)
    health=threading.Thread(target=health_loop,args=(state,stop),daemon=True)
    interrupted=False
    def requested(*_):
        nonlocal interrupted
        interrupted=True
    signal.signal(signal.SIGINT,requested);signal.signal(signal.SIGTERM,requested)
    worker.start();health.start();reason=None
    try:
        while not stop.wait(.02):
            if interrupted:reason='Interrupted';break
            if not worker.is_alive():reason='Serial worker exited';break
            if state.first_ns is not None:
                if time.perf_counter_ns()-state.first_ns>=duration_ns:break
            elif time.monotonic()-launched>=a.startup_timeout:
                reason='No fully warmed hardware stream before startup timeout';break
    finally:
        measurement_end_ns=time.perf_counter_ns()
        stop.set();worker.join(6);health.join(2);trace.close()
    snap=state.snapshot(include_health_history=True);trace_info=trace.telemetry()
    reasons=[reason] if reason else []
    if worker.is_alive():reasons.append('Receiver failed to drain')
    if state.measured<200:reasons.append('Fewer than 200 measured packets')
    if snap['error_count'] or snap['sequence_gaps'] or snap['resets'] or snap['reconnects']:
        reasons.append('Transport error/gap/reset/reconnect observed')
    if any(snap.get(k,0) for k in ('log_dropped','output_dropped','event_dropped')) or snap['log_warning']:
        reasons.append('Output/event loss or storage warning')
    if trace_info['dropped'] or trace_info['pending'] or trace_info['error']:
        reasons.append('Incomplete raw trace')
    health_rows=snap['health_samples']
    if not health_rows or any(x.get('power')!='OK' for x in health_rows):
        reasons.append('Power/thermal status not confirmed OK for every recorded health sample')
    try:stages=analyze_trace(trace.path)
    except (OSError,ValueError,KeyError) as exc:stages={};reasons.append('Trace analysis failed: '+str(exc))
    if stages and stages['latency_us']['n']!=state.measured:reasons.append('Measured/trace count mismatch')
    usage=resource.getrusage(resource.RUSAGE_SELF)
    total_elapsed=time.monotonic()-launched
    measured_duration=(min(a.seconds,max(0,(measurement_end_ns-state.first_ns)/1e9))
                       if state.first_ns is not None else 0)
    report=dict(kind='PHYSICAL_SERIAL_EXPERIMENT',physical_measurements_present=state.measured>0,
                data_provenance='SYNTHETIC ESP32 movements',protocol=VERSION,eligible=not reasons,reasons=reasons,
                config={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()},
                command=sys.argv,platform=platform.platform(),python=sys.version,
                started_utc=started_utc,finished_utc=datetime.now(timezone.utc).isoformat(),
                stages=stages,measured_packets=state.measured,
                throughput=state.measured/measured_duration if measured_duration else 0,
                measured_duration_s=measured_duration,run_elapsed_s=total_elapsed,
                process_cpu_s=usage.ru_utime+usage.ru_stime,max_rss_kib=usage.ru_maxrss,
                trace=trace_info,hardware=snap,
                notes=['Per-run exact sample percentiles; no pooling across runs.',
                       'Successful request-to-classification latency excludes startup, warmup, output and persistence.',
                       'Every selected sample is traced asynchronously in BOTH output modes; trace observer cost is shared.',
                       'wait_us includes serial read time; poll_wait_us + read_us = wait_us.',
                       'Output timings are a last-2000 selected-output window; no physical screen timing is measured.',
                       'A Linux character device does not independently authenticate physical provenance.'])
    (a.out/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print('Report:',a.out/'summary.json','QUALIFIED' if not reasons else 'NOT QUALIFIED: '+'; '.join(reasons))
    return 0 if not reasons else 1


if __name__=='__main__':raise SystemExit(main())
