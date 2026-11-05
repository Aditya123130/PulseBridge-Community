#!/usr/bin/env python3
"""Read-only system inventory for a reproducible Pi deployment."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess


def read(path):
    try:return Path(path).read_text().replace('\x00','').strip()
    except OSError:return None


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pid',type=int);p.add_argument('--out',type=Path);a=p.parse_args()
    result=dict(model=read('/proc/device-tree/model'),platform=platform.platform(),python=platform.python_version(),
                clock=vars(__import__('time').get_clock_info('perf_counter')),cpus=os.cpu_count(),
                allowed_cpus=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
                isolated=read('/sys/devices/system/cpu/isolated'),cmdline=read('/proc/cmdline'),
                governors={x.parent.parent.name:x.read_text().strip() for x in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_governor')})
    try:result['power']=subprocess.run(['vcgencmd','get_throttled'],capture_output=True,text=True,timeout=2,check=True).stdout.strip()
    except (OSError,subprocess.SubprocessError):result['power']='UNKNOWN'
    if a.pid:
        result['threads']=[]
        for task in Path(f'/proc/{a.pid}/task').glob('*'):
            values=read(task/'status') or ''
            result['threads'].append(dict(tid=task.name,placement=[x for x in values.splitlines() if x.startswith(('Name:','Cpus_allowed_list:'))]))
    text=json.dumps(result,indent=2)
    if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text)
    print(text)


if __name__=='__main__':main()
