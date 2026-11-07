#!/usr/bin/env python3
"""Local deployment checks. Serial is opened only with explicit --probe."""
import argparse
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['hardware', 'protocol-sim', 'simulated', 'demo', 'replay', 'kraken', 'kite'], default='hardware')
    parser.add_argument('--port', default='auto')
    parser.add_argument('--baud', type=int, choices=[115200,460800,921600])
    parser.add_argument('--protocol',choices=['3','legacy1','legacy2'],default='3')
    parser.add_argument('--profile',choices=['compat','demo','fast','turbo'],default='compat')
    parser.add_argument('--board-profile',type=int,choices=range(1,6))
    parser.add_argument('--kite-session', type=Path)
    parser.add_argument('--http-port', type=int, default=8080)
    parser.add_argument('--data-dir', type=Path, default=ROOT/'runs/workstation')
    parser.add_argument('--probe', action='store_true', help='Send one compatibility request; close all serial readers first')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.kite_session:
        from terminal.kite_gateway import load_session
        try:
            credentials = load_session(args.kite_session)
            os.environ['KITE_API_KEY'] = credentials['api_key']
            os.environ['KITE_ACCESS_TOKEN'] = credentials['access_token']
        except (ValueError,OSError) as exc:
            parser.error(str(exc))
    if not 1 <= args.http_port <= 65535:
        parser.error('HTTP port must be 1..65535')
    checks = []
    def add(level, name, detail):
        checks.append(dict(level=level, name=name, detail=detail))
        print(f'[{level:4s}] {name}: {detail}', flush=True)
    add('PASS' if sys.version_info >= (3, 10) else 'FAIL', 'Python', platform.python_version())
    add('PASS' if sys.platform.startswith('linux') else 'FAIL', 'OS', platform.system()+'; deployment requires Linux')
    for module, required in [('serial', args.mode in ('hardware','protocol-sim')), ('websockets', args.mode in {'kraken', 'kite'})]:
        exists = importlib.util.find_spec(module) is not None
        add('PASS' if exists else 'FAIL' if required else 'WARN', module,
            'available' if exists else 'missing; run setup_pi.sh / setup_live.sh')
    required_files = ['pi/app.py', 'pi/doctor.py', 'pi/protocol.py', 'pi/transport.py',
                      'pi/static/index.html', 'pi/static/app.js', 'pi/static/style.css',
                      'firmware/PulseBridgeESP32/board_config.h']
    missing = [p for p in required_files if not (ROOT/p).is_file()]
    add('FAIL' if missing else 'PASS', 'Project files', ', '.join(missing) if missing else 'Community dashboard and firmware present')
    try:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        space = shutil.disk_usage(args.data_dir).free
        add('PASS' if space > 1024**3 else 'WARN', 'Free storage', f'{space/1024**3:.2f} GiB; prefer at least 1 GiB')
        with tempfile.TemporaryDirectory(prefix='preflight-', dir=args.data_dir) as scratch:
            with closing(sqlite3.connect(Path(scratch)/'check.sqlite3')) as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('PRAGMA synchronous=FULL')
                db.execute('CREATE TABLE check_write(v INTEGER)')
                db.execute('INSERT INTO check_write VALUES (1)')
                db.commit()
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise OSError('Temporary database integrity check failed')
        add('PASS', 'Storage write', 'temporary SQLite WAL transaction committed; existing ledger was not changed')
    except (OSError, sqlite3.Error) as exc:
        add('FAIL', 'Storage write', str(exc))
    try:
        import fcntl
        lock_path = args.data_dir/'workstation.lock'
        if lock_path.exists():
            with lock_path.open('a') as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        add('PASS', 'Workstation lock', 'no running workstation owns this data directory')
    except (OSError, ImportError):
        add('FAIL', 'Workstation lock', 'stop the existing workstation or use a different data directory')
    try:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', args.http_port))
        add('PASS', 'Dashboard port', f'{args.http_port} is available on localhost')
    except OSError as exc:
        add('FAIL', 'Dashboard port', f'{args.http_port}: {exc}; stop the old app or choose --http-port 8081')
    if args.mode=='hardware':
        from pi.protocol import PROFILES
        baud=PROFILES[args.profile][0]
        compatible=args.baud in (None,baud) and (args.protocol!='legacy1' or args.profile=='compat') and (args.protocol!='legacy2' or args.profile!='compat')
        add('PASS' if compatible else 'FAIL','Protocol / profile / baud',f'{args.protocol} / {args.profile} / {args.baud or baud}; no auto downgrade')
        add('PASS' if args.protocol!='3' or args.board_profile else 'FAIL','Board profile',str(args.board_profile or 'Required: inspect actual chip and USB connector'))
        if args.protocol=='3' and args.board_profile:
            header=(ROOT/'firmware/PulseBridgeESP32/board_config.h').read_text()
            import re
            configured=int(re.search(r'#define PB_BOARD_PROFILE (\d+)',header).group(1))
            add('PASS' if configured==args.board_profile else 'WARN','Local firmware configuration',f'Local header {configured}; requested {args.board_profile}. Device identity is verified by --probe, not inferred from this file.')
    selected = None
    if args.mode == 'hardware' or args.probe:
        try:
            sys.path.insert(0, str(ROOT/'pi'))
            from transport import choose_port
            selected = choose_port(args.port)
            allowed = os.access(selected, os.R_OK | os.W_OK)
            add('PASS' if allowed else 'FAIL', 'Serial device', selected + ('; read/write allowed' if allowed else '; fix dialout group and log in again'))
        except (ImportError, OSError, ValueError) as exc:
            add('FAIL', 'Serial device', 'HARDWARE DISCONNECTED / unavailable: '+str(exc))
    if args.mode == 'kite':
        ready = bool(os.environ.get('KITE_API_KEY') and os.environ.get('KITE_ACCESS_TOKEN'))
        add('PASS' if ready else 'FAIL', 'Kite credentials', 'both variables present; validity not tested' if ready else 'set KITE_API_KEY and KITE_ACCESS_TOKEN; never share their values')
    try:
        raw = subprocess.run(['vcgencmd', 'get_throttled'], capture_output=True, text=True, timeout=2, check=True).stdout.strip()
        bits = int(raw.split('=')[1], 16)
        add('FAIL' if bits & 0xf else 'WARN' if bits & 0xf0000 else 'PASS', 'Pi power/thermal', raw + ('; active event' if bits & 0xf else '; past event recorded' if bits & 0xf0000 else '; no recorded throttling flags'))
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        add('WARN', 'Pi power/thermal', 'UNKNOWN; vcgencmd unavailable or unreadable; not evidence of healthy power')
    if args.probe and selected and not any(c['level'] == 'FAIL' for c in checks):
        try:
            run = subprocess.run([sys.executable, str(ROOT/'pi/doctor.py'), '--probe', '--port', selected, '--protocol',args.protocol,'--profile',args.profile]+(['--board-profile',str(args.board_profile)] if args.board_profile else [])+(['--baud',str(args.baud)] if args.baud else []),
                                 capture_output=True, text=True, timeout=8)
            add('PASS' if run.returncode == 0 else 'FAIL', 'Matching protocol probe', run.stdout.strip() or run.stderr.strip())
        except (OSError, subprocess.TimeoutExpired) as exc:
            add('FAIL', 'Matching protocol probe', str(exc))
    result = dict(kind='LOCAL_PREFLIGHT', mode=args.mode, checks=checks,
                  ready=not any(c['level'] == 'FAIL' for c in checks),
                  note='Readiness checks do not prove physical latency, SD-card health, provider connectivity or trading performance.')
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2))
    print('Ready for the selected local setup checks.' if result['ready'] else 'Fix the FAIL items before the demonstration.')
    if args.mode in {'kraken', 'kite'}:
        print('Verify the external feed separately: python tools/live_probe.py --mode '+args.mode+' --seconds 30')
    return 0 if result['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
