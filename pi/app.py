#!/usr/bin/env python3
"""PulseBridge: one command runs real hardware reception and a local dashboard."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import signal
import sys
import threading
import time
from datetime import datetime, timezone

try:
    import serial
except ImportError:
    raise SystemExit("Missing pySerial. On the Pi run: sudo apt-get install python3-serial")

from engine import Analyzer, State
from protocol import BASE_BAUD, PROFILES
from transport import SerialWorker, health_loop, ports

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"


def handler_for(state):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def do_GET(self):
            route = self.path.split("?", 1)[0]
            try:
                if route in ("/api/state", "/api/export"):
                    data = json.dumps(state.snapshot(), allow_nan=False).encode()
                    mime = "application/json; charset=utf-8"
                elif route in ("/", "/index.html", "/app.js", "/style.css"):
                    name = "index.html" if route == "/" else route[1:]
                    data = (STATIC / name).read_bytes()
                    mime = {"html": "text/html", "js": "application/javascript", "css": "text/css"}[name.split(".")[-1]]
                    mime += "; charset=utf-8"
                elif route == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                    return
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
                if route == "/api/export":
                    self.send_header("Content-Disposition", 'attachment; filename="pulsebridge-snapshot.json"')
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass

        def log_message(self, *_):
            pass
    return Handler


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="auto", help="auto, /dev/ttyUSB0, or /dev/serial/by-id/...")
    parser.add_argument("--protocol",choices=["3","legacy1","legacy2"],default="3")
    parser.add_argument("--board-profile",type=int,choices=range(1,6))
    parser.add_argument("--profile", choices=["compat", "demo", "fast", "turbo"], default="compat",
                        help="compat: ASCII v3/115200; demo: binary 460800/100Hz; fast: binary 460800/unpaced; turbo: 921600/experimental")
    parser.add_argument("--baud", type=int, choices=[115200, 460800, 921600], default=None)
    parser.add_argument("--rate", type=float, default=None, help="target signals/sec; 0 = no deliberate pacing")
    parser.add_argument("--warmup-rate", type=float, default=None, help="startup target; 0 = no deliberate pacing")
    parser.add_argument("--threshold", type=float, default=2.0, help="absolute z-score threshold (0.5..10)")
    parser.add_argument("--timeout", type=float, default=.25, help="response timeout seconds (0.05..2)")
    parser.add_argument("--boot-wait", type=float, default=1.8, help="wait after serial open, seconds (0..5)")
    parser.add_argument("--history", type=Path, help="optional sourced historical movement CSV; no implicit fallback")
    parser.add_argument("--host", default="127.0.0.1", help="localhost default; 0.0.0.0 only for an explicitly trusted LAN")
    parser.add_argument("--device-seed", type=int, default=0, help="uint32 demo seed; 0 uses device entropy")
    parser.add_argument("--http-port", type=int, default=8080)
    parser.add_argument("--out", type=Path, default=ROOT / "runs")
    parser.add_argument("--seconds", type=float, default=0, help="0 runs until Ctrl+C")
    parser.add_argument("--quiet", action="store_true", help="suppress per-signal terminal lines")
    parser.add_argument("--terminal", choices=["tape", "summary", "all"], default="tape",
                        help="tape: max 10 printed rows/s; summary: 1/s; all: every row subject to bounded output queue")
    parser.add_argument("--log", choices=["sampled", "all", "off"], default="sampled",
                        help="raw evidence: max 10 rows/s, all accepted rows, or none; full-run metrics always retained")
    parser.add_argument("--target-us", type=float, default=9000, help="display latency budget, never changes measurements")
    parser.add_argument("--list-ports", action="store_true")
    args = parser.parse_args(argv)
    defaults = PROFILES[args.profile]
    for name, value in zip(("baud", "rate", "warmup_rate"), defaults):
        if getattr(args, name) is None: setattr(args, name, value)
    if args.protocol=="legacy1" and args.profile!="compat":parser.error("legacy1 requires compat")
    if args.protocol=="legacy2" and args.profile=="compat":parser.error("legacy2 requires binary profile")
    if args.baud != defaults[0]:
        parser.error('Use the matching profile: compat=115200, demo/fast=460800, turbo=921600')
    if not 0 <= args.device_seed <= 0xFFFFFFFF: parser.error('--device-seed must be uint32')
    for name, lo, hi in [("rate", 0, 2000), ("warmup_rate", 0, 2000), ("threshold", .5, 10),
                         ("target_us", 1, 1_000_000),
                         ("timeout", .05, 2), ("boot_wait", 0, 5), ("http_port", 1, 65535), ("seconds", 0, 86400)]:
        if not lo <= getattr(args, name) <= hi:
            parser.error(f"--{name.replace('_', '-')} must be between {lo} and {hi}")
    return args


def main():
    args = arguments()
    if args.list_ports:
        found = ports()
        print(json.dumps(found, indent=2) if found else "No serial ports detected")
        return 0
    if args.protocol=="3" and not args.board_profile:raise SystemExit("--board-profile 1..5 required")
    try:
        analyzer = Analyzer(args.threshold, args.history)
        args.run_dir = args.out / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        args.run_dir.mkdir(parents=True, exist_ok=False)
    except (OSError, ValueError) as exc:
        print("Startup error:", exc, file=sys.stderr)
        return 2
    state = State(args.rate, args.threshold)
    stop = threading.Event()
    try:
        server = ThreadingHTTPServer((args.host, args.http_port), handler_for(state))
    except OSError as exc:
        print(f"Dashboard could not bind: {exc}. Try --http-port 8081", file=sys.stderr)
        return 2
    server.daemon_threads = True
    try:
        worker = SerialWorker(state, args, stop, analyzer)
    except OSError as exc:
        server.server_close()
        print("Cannot open run log:", exc, file=sys.stderr)
        return 2
    signal_requested = False
    def request_stop(*_):
        nonlocal signal_requested
        signal_requested = True
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    threading.Thread(target=server.serve_forever, daemon=True, name="dashboard").start()
    threading.Thread(target=health_loop, args=(state, stop), daemon=True, name="pi-health").start()
    print("PULSEBRIDGE 7 | physical ESP32 input | SYNTHETIC demo movements")
    print(f"Profile: {args.profile} | baud: {args.baud} | steady rate: {args.rate or 'UNPACED'} | logs: {args.log}")
    print(f"Terminal: {args.terminal}; readable display sampling never changes acquisition counters")
    print("Latency = Pi request-to-decision, including outbound request; display/logging excluded")
    print("History = " + analyzer.source + "; rolling 128 values per symbol")
    print(f"Dashboard: http://localhost:{args.http_port} or http://<PI-IP>:{args.http_port}")
    print(f"Run evidence: {args.run_dir}\nCtrl+C stops cleanly. No hardware = no generated rows.", flush=True)
    worker.start()
    started = time.monotonic()
    exit_code = 0
    try:
        while not stop.wait(.2):
            if signal_requested:
                break
            if args.seconds and time.monotonic() - started >= args.seconds:
                stop.set()
            if not worker.is_alive():
                print("Receiver exited. See last error in run summary.", file=sys.stderr)
                exit_code = 1
                stop.set()
    finally:
        stop.set()
        worker.join(timeout=6)
        if not state.total or worker.is_alive():exit_code=1
        state.status("STOPPED", "Application stopped; all displayed data is historical")
        server.shutdown()
        server.server_close()
        try:
            (args.run_dir / "summary.json").write_text(json.dumps(state.snapshot(include_health_history=True), indent=2, allow_nan=False))
        except OSError as exc:
            print("Could not save summary:", exc, file=sys.stderr)
        print("Stopped. Run logs, history, and summary:", args.run_dir)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
