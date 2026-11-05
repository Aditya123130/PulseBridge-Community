#!/usr/bin/env python3
"""Synthetic queue scheduling comparison. NOT a hardware/network benchmark."""
import argparse
import json
from pathlib import Path
import platform
import queue
import sys
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terminal.market import summary


def trial(style, count, interval):
    channel = queue.Queue(maxsize=4096)
    ready = threading.Event()
    def producer():
        ready.wait()
        for _ in range(count):
            channel.put(time.perf_counter_ns())
            time.sleep(interval)
    thread = threading.Thread(target=producer)
    thread.start()
    values=[]
    ready.set()
    while len(values) < count:
        if style == "v3_periodic_poll":
            for _ in range(256):
                try: stamp=channel.get_nowait()
                except queue.Empty: break
                values.append((time.perf_counter_ns()-stamp)/1000)
            time.sleep(.001)
        else:
            stamp=channel.get(timeout=2)
            values.append((time.perf_counter_ns()-stamp)/1000)
    thread.join()
    return summary(values)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples",type=int,default=2000)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if not 100<=args.samples<=20000:parser.error("samples must be 100..20000")
    result=dict(kind="SYNTHETIC QUEUE BENCHMARK ONLY",host=platform.machine(),
                boundary="Producer enqueue timestamp to consumer handling, microseconds",
                v3_periodic_poll=trial("v3_periodic_poll",args.samples,.0005),
                v4_blocking_receive=trial("v4_blocking_receive",args.samples,.0005),
                limitations="Single-process thread queue; excludes USB, IPC, strategy, disk, network and browser. Compare on your own Pi.")
    text=json.dumps(result,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text)
    print(text)


if __name__=="__main__":main()
