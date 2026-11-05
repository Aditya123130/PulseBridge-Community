#!/usr/bin/env python3
"""USB port diagnostics. --probe handshakes and sends a genuine protocol-3 poll."""
import argparse
import grp
import json
import os
from pathlib import Path
import select
import sys
import tempfile
import threading
import time
import serial
from app import arguments
from engine import State, Lines, PacketError
from protocol import RECOVERY_SECONDS, parse_stats
from transport import SerialWorker, choose_port, ports, open_connection


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',default='auto')
    p.add_argument('--protocol',choices=['3','legacy1','legacy2'],default='3')
    p.add_argument('--board-profile',type=int,choices=range(1,6))
    p.add_argument('--profile',choices=['compat','fast','turbo'],default='compat')
    p.add_argument('--baud',type=int,choices=[115200,460800,921600])
    p.add_argument('--probe',action='store_true')
    a=p.parse_args(argv)
    if a.protocol=='3' and not a.board_profile:p.error('--board-profile 1..5 required for Protocol 3')
    options=['--protocol',a.protocol,'--profile',a.profile,'--quiet','--log','off','--timeout','.5']
    if a.baud is not None:options+=['--baud',str(a.baud)]
    args=arguments(options);args.board_profile=a.board_profile
    print('PulseBridge 7 USB doctor | Python',sys.version.split()[0],'| pySerial',serial.VERSION)
    print('Groups:',', '.join(grp.getgrgid(g).gr_name for g in os.getgroups()))
    print('Ports:',json.dumps(ports(),indent=2))
    try:
        port=choose_port(a.port)
        if not os.access(port,os.R_OK|os.W_OK): raise PermissionError('Add user to dialout, then log out/in')
        print('Selected:',port)
        if not a.probe:
            print('Close other readers, then rerun with --probe');return 0
        with tempfile.TemporaryDirectory(prefix='pulsebridge-probe-') as temp:
            args.run_dir=Path(temp)
            worker=SerialWorker(State(),args,threading.Event())
            try:
                with open_connection(port,.5,worker.base_baud) as device:
                    time.sleep(RECOVERY_SECONDS)
                    device.reset_input_buffer();device.write(b'\n')
                    worker.negotiate(device)
                    row=worker.exchange(device)
                    if row is None:raise ValueError('No valid matching response before timeout')
                    print('PASS physical serial response; payload is SYNTHETIC:',json.dumps(row,allow_nan=False))
                    print('Selected firmware profile:',json.dumps(worker.state.device))
                    if a.profile=='compat' and a.protocol=='3':
                        device.write(b'STATS\n');lines=Lines();end=time.monotonic()+.5
                        while time.monotonic()<end:
                            if not select.select([device.fileno()],[],[],.05)[0]:continue
                            for line in lines.feed(device.read(max(1,min(4096,device.in_waiting))))[0]:
                                try:print('Device counters:',json.dumps(parse_stats(line)));return 0
                                except PacketError:pass
                    return 0
            finally:
                worker.event_file.close();worker.log_handler.close();worker.logger.removeHandler(worker.log_handler)
    except (OSError,ValueError,serial.SerialException) as exc:
        print('FAIL:',exc);return 1


if __name__=='__main__':raise SystemExit(main())
