#!/usr/bin/env python3
"""Repeated UART profile experiments. Each run keeps its own trace/percentiles."""
import argparse
from datetime import datetime,timezone
import itertools
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]


def run_statistics(values):
    if not values:return None
    ordered=sorted(values);rng=random.Random(2026)
    means=sorted(statistics.fmean(rng.choices(values,k=len(values))) for _ in range(2000)) if len(values)>1 else None
    return dict(runs=len(values),median=statistics.median(values),min=min(values),max=max(values),
                stdev=statistics.stdev(values) if len(values)>1 else None,
                mean_ci95=[means[49],means[1949]] if means else None,
                note='Exploratory bootstrap CI of mean run statistic, 2000 resamples. Not a packet-pooled percentile.')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',default='auto')
    p.add_argument('--board-profile',type=int,choices=range(1,6),required=True)
    p.add_argument('--profiles',nargs='+',choices=['compat','fast','turbo'],default=['compat','fast'])
    p.add_argument('--repeats',type=int,default=5)
    p.add_argument('--seconds',type=int,default=60)
    p.add_argument('--rate',type=float,default=0)
    p.add_argument('--warmup-seconds',type=float,default=5)
    p.add_argument('--startup-timeout',type=float,default=120)
    p.add_argument('--output-modes',nargs='+',choices=['off','on'],default=['off','on'])
    p.add_argument('--device-seed',type=int,default=42)
    p.add_argument('--out',type=Path,default=ROOT/'runs')
    a=p.parse_args(argv)
    if not 1<=a.repeats<=30 or not 1<=a.seconds<=600 or not 0<=a.rate<=2000:
        p.error('repeats=1..30, seconds=1..600, rate=0..2000')
    folder=a.out/('benchmark_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));folder.mkdir(parents=True)
    schedule=list(itertools.product(range(1,a.repeats+1),a.profiles,a.output_modes));random.Random(2026).shuffle(schedule)
    report=dict(kind='REPEATED_SERIAL_PROFILE_COMPARISON',created_utc=datetime.now(timezone.utc).isoformat(),
                config={k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()},
                physical_measurements_present=False,runs=[],groups={},
                warning='No winner is inferred from baud rate. Failed/unqualified runs remain visible. Native CDC baud labels are not USB speed.')
    def save():(folder/'comparison.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    save()
    print('Close workstation/Serial Monitor first. Actual serial hardware required; no fallback source.',flush=True)
    try:
        for i,(repeat,profile,output) in enumerate(schedule):
            run_dir=folder/f'{i:03d}_{profile}_{output}_r{repeat}'
            cmd=[sys.executable,str(ROOT/'tools/transport_run.py'),'--port',a.port,'--board-profile',str(a.board_profile),'--profile',profile,
                 '--seconds',str(a.seconds),'--rate',str(a.rate),'--output-mode',output,
                 '--device-seed',str(a.device_seed),'--warmup-seconds',str(a.warmup_seconds),
                 '--startup-timeout',str(a.startup_timeout),'--out',str(run_dir)]
            print(f'[{i+1}/{len(schedule)}] {profile}, output={output}, repeat={repeat}',flush=True)
            with (folder/(run_dir.name+'.console.txt')).open('w') as log:
                try:code=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                                        timeout=a.seconds+a.startup_timeout+20).returncode
                except subprocess.TimeoutExpired:code=124
            data=json.loads((run_dir/'summary.json').read_text()) if (run_dir/'summary.json').exists() else dict(eligible=False,reasons=['Missing summary'])
            row=dict(repeat=repeat,profile=profile,output=output,command=cmd,returncode=code,folder=run_dir.name,result=data)
            report['runs'].append(row)
            report['physical_measurements_present'] |= data.get('physical_measurements_present',False)
            save()
    except KeyboardInterrupt:
        report['interrupted']=True;save();return 1
    for profile,output in itertools.product(a.profiles,a.output_modes):
        qualified=[r['result'] for r in report['runs'] if r['profile']==profile and r['output']==output and r['returncode']==0 and r['result']['eligible']]
        report['groups'][profile+'/'+output]=dict(qualified_runs=len(qualified),expected_runs=a.repeats,
            p50_us=run_statistics([r['stages']['latency_us']['p50'] for r in qualified]),
            p95_us=run_statistics([r['stages']['latency_us']['p95'] for r in qualified]),
            p99_us=run_statistics([r['stages']['latency_us']['p99'] for r in qualified]),
            throughput=run_statistics([r['throughput'] for r in qualified]))
    save();print('Saved:',folder/'comparison.json')
    return 0 if all(g['qualified_runs']==a.repeats for g in report['groups'].values()) else 1


if __name__=='__main__':raise SystemExit(main())
