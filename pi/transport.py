"""Real serial I/O only. No replay, random fallback, loop:// or network source."""
import glob
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import binascii
import queue
import secrets
import select
import stat
import subprocess
import threading
import time

import serial
from serial.tools import list_ports
from engine import Analyzer, Lines, BinaryFrames, PacketError, parse_response, request_packet, binary_request
from protocol import BASE_BAUD, MAX_READ, IDLE_SECONDS, RECOVERY_SECONDS, handshake, parse_ack


class EvidenceHandler(RotatingFileHandler):
    def handleError(self, record):
        self.failed = True
        self.state.log_warning = "Evidence log write failed; check free space and SD card"


def ports():
    return [dict(device=p.device, description=p.description, hwid=p.hwid)
            for p in list_ports.comports()]


def choose_port(requested):
    if requested != "auto":
        if not requested.startswith("/dev/"):
            raise ValueError("Use a real Linux /dev/ serial port, not a URL or replay file")
        if not stat.S_ISCHR(os.stat(requested).st_mode):
            raise ValueError("Selected path is not a character device")
        return requested
    discovered = [p["device"] for p in ports()
                  if p["device"].startswith(("/dev/ttyUSB", "/dev/ttyACM"))]
    # Deduplicate symlinks to one physical character device; prefer by-id names.
    candidates = {}
    for path in sorted(glob.glob('/dev/serial/by-id/*')) + discovered:
        real = os.path.realpath(path)
        if real.startswith(('/dev/ttyUSB', '/dev/ttyACM')):
            candidates.setdefault(real, path)
    if not candidates:
        raise FileNotFoundError("No USB serial device. Connect the ESP32 with a DATA cable.")
    if len(candidates) > 1:
        raise ValueError("Several USB serial ports found; select --port explicitly: " + ", ".join(candidates.values()))
    return next(iter(candidates.values()))


def open_connection(port, timeout, base_baud=BASE_BAUD):
    try:
        connection = serial.Serial(port=None, baudrate=base_baud, timeout=0,
                                   write_timeout=timeout, exclusive=True)
        connection.dtr = connection.rts = False
        connection.port = port
        connection.open()
        return connection
    except serial.SerialException as exc:
        raise serial.SerialException(f"Cannot open {port}: {exc}. Check dialout permissions and close Serial Monitor/other readers.") from exc



class SerialWorker(threading.Thread):
    def __init__(self, state, args, stop, analyzer=None):
        super().__init__(daemon=True, name="esp32-receiver")
        self.state, self.args, self.stop = state, args, stop
        self.analyzer = analyzer or Analyzer(args.threshold, args.history)
        self.state.history_source = self.analyzer.source
        self.state.history = {s: len(w) for s, w in self.analyzer.windows.items()}
        self.state.baud = args.baud
        self.protocol = getattr(args,"protocol","3")
        import protocol as v3
        import legacy
        self.wire = v3 if self.protocol=="3" else legacy
        self.base_baud = 230400 if self.protocol=="legacy2" else 115200
        self.idle_seconds = IDLE_SECONDS if self.protocol=="3" else 1.5 if self.protocol=="legacy2" else float("inf")
        self.binary = getattr(args, "profile", "compat") != "compat"
        self.state.profile = getattr(args, "profile", "compat")
        self.state.protocol = ("Binary " if self.binary else "ASCII ") + self.protocol
        self.state.log_mode = getattr(args, "log", "sampled")
        self.state.target_us = getattr(args, "target_us", 9000)
        self.nonce = secrets.randbits(32)
        self.request_id = 0
        self.boot = self.sequence = None
        self.expected_boot = None
        self.last_exchange = None
        self.state.stale_seconds = max(1.5, 2 / args.rate) if args.rate > 0 else 1.5
        self.event_queue = queue.Queue(512)
        self.event_file = (args.run_dir / 'events.jsonl').open('x', encoding='utf-8')
        self.state.event_sink = self.enqueue_event
        self.console_ok = not args.quiet
        self.last_notice = None
        self.last_notice_time = 0
        self.lines = self.wire.Lines()
        self.frames = self.wire.BinaryFrames()
        self.output_queue = queue.Queue(maxsize=4096)
        self.output_done = threading.Event()
        self.output_thread = None
        self.last_print = self.last_log = 0
        self.logger = logging.getLogger("pulsebridge.run." + args.run_dir.name)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        handler = EvidenceHandler(args.run_dir / "signals.jsonl", maxBytes=5_000_000,
                                  backupCount=3, encoding="utf-8")
        handler.state = state
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)
        self.log_handler = handler

    def enqueue_event(self, kind, message, count=1, printing=False):
        try:
            self.event_queue.put_nowait(dict(t_ns=time.perf_counter_ns(), kind=kind,
                                            message=str(message)[:1000], count=count, printing=printing))
        except queue.Full:
            self.state.event_dropped += 1

    def negotiate(self, connection):
        """Both modes establish a fresh session at 115200 before any data poll."""
        if self.protocol=='legacy1':return
        if self.protocol=='legacy2':
            self.wire.negotiate(self,connection)
            self.last_exchange=time.monotonic()
            return
        wire = handshake(self.nonce, self.binary, self.args.baud, getattr(self.args, 'device_seed', 0))
        if connection.write(wire) != len(wire):
            raise serial.SerialException('Incomplete handshake write')
        deadline = time.monotonic() + 1.0
        lines = Lines()
        while time.monotonic() < deadline and not self.stop.is_set():
            if not select.select([connection.fileno()], [], [], .05)[0]: continue
            chunk = connection.read(max(1, min(MAX_READ, connection.in_waiting)))
            if not chunk: raise serial.SerialException("USB closed during handshake")
            for line in lines.feed(chunk)[0]:
                try: device = parse_ack(line, self.nonce, self.binary, self.args.baud)
                except PacketError: continue
                expected_profile=getattr(self.args,'board_profile',None)
                if expected_profile and device['board_profile']!=expected_profile:
                    raise serial.SerialException('Device board profile mismatch; no data accepted')
                self.expected_boot = device['boot_id']
                if self.boot is not None and self.boot != self.expected_boot:
                    with self.state.lock: self.state.resets += 1
                self.boot, self.sequence = self.expected_boot, None
                self.state.device = device
                if self.binary:
                    connection.baudrate = self.args.baud
                    if self.stop.wait(.08): return
                connection.reset_input_buffer()
                self.frames, self.lines = self.wire.BinaryFrames(), self.wire.Lines()
                self.last_exchange = time.monotonic()
                self.notice(f"[LINK] Protocol 3 {'binary' if self.binary else 'ASCII'} / {self.args.baud} / SYNTHETIC")
                return
        if not self.stop.is_set():
            self.state.error('handshake_errors', 'No valid protocol 3 acknowledgement')
            raise serial.SerialException("Protocol 3 handshake failed at 115200. Flash firmware/PulseBridgeESP32/PulseBridgeESP32.ino; verify chip/USB profile and cable.")

    def notice(self, message):
        now = time.monotonic()
        if message != self.last_notice or now-self.last_notice_time > 5:
            self.enqueue_event('link', message, printing=self.console_ok)
            self.last_notice, self.last_notice_time = message, now

    def exchange(self, connection):
        # Low controlled rates can exceed device idle expiry. Re-handshake outside
        # the timed sample, with a fresh nonce and measured recovery counters.
        if self.last_exchange is not None and time.monotonic()-self.last_exchange >= self.idle_seconds-.15:
            self.stop.wait(max(0, RECOVERY_SECONDS-(time.monotonic()-self.last_exchange)))
            if self.stop.is_set(): return None
            connection.baudrate = self.base_baud
            connection.reset_input_buffer()
            connection.write(b'\n')
            self.nonce, self.request_id = secrets.randbits(32), 0
            self.state.protocol_resets += 1
            self.negotiate(connection)
        self.request_id = (self.request_id + 1) & 0xFFFFFFFF
        wire = (self.wire.binary_request if self.binary else self.wire.request_packet)(self.nonce, self.request_id)
        with self.state.lock:
            self.state.requests += 1
        start_ns = time.perf_counter_ns()  # BEFORE write; includes both transport legs.
        if connection.write(wire) != len(wire):
            raise serial.SerialException("Incomplete serial write")
        written_ns = time.perf_counter_ns()
        deadline = time.monotonic() + self.args.timeout
        read_total_ns = 0
        while not self.stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            readable, _, _ = select.select([connection.fileno()], [], [], min(remaining, .05))
            if not readable:
                continue
            read_start_ns = time.perf_counter_ns()
            chunk = connection.read(max(1, min(MAX_READ, connection.in_waiting)))
            received_ns = time.perf_counter_ns()
            read_total_ns += received_ns-read_start_ns
            if not chunk:
                raise serial.SerialException("USB serial endpoint closed")
            if self.binary:
                packets, errors = self.frames.feed(chunk)
                for kind, count in errors.items(): self.state.error(kind, "Binary framing/CRC rejection", count)
            else:
                lines, overflows = self.lines.feed(chunk)
                if overflows: self.state.error("format_errors", "Oversized input discarded", overflows)
                packets = []
                for line in lines:
                    if line.startswith(b"#"): continue
                    try: packets.append(self.wire.parse_response(line))
                    except PacketError as exc: self.state.error(exc.kind, str(exc))
            for packet in packets:
                if packet["nonce"] != self.nonce or packet["request_id"] != self.request_id:
                    self.state.error("stale_replies", "Discarded response for a different request")
                    continue
                if self.expected_boot is not None and packet['boot_id'] != self.expected_boot:
                    self.state.error('stale_replies', 'Boot identity differs from handshake; re-negotiate')
                    continue
                if self.boot == packet["boot_id"] and self.sequence is not None:
                    difference = (packet["sequence"] - self.sequence) & 0xFFFFFFFF
                    if difference == 0 or difference >= 0x80000000:
                        self.state.error("duplicate_sequences", "Duplicate/out-of-order sequence rejected")
                        continue
                    if difference > 1:
                        with self.state.lock:
                            self.state.sequence_gaps += difference - 1
                elif self.boot is not None and self.boot != packet["boot_id"]:
                    with self.state.lock:
                        self.state.resets += 1
                self.boot, self.sequence = packet["boot_id"], packet["sequence"]
                score_start = time.perf_counter_ns()
                analysis = self.analyzer.process(packet["symbol"], packet["movement_pct"])
                finish_ns = time.perf_counter_ns()
                packet.update(analysis)
                packet["latency_us"] = (finish_ns - start_ns) / 1000
                packet["analysis_us"] = (finish_ns - score_start) / 1000
                packet["write_us"] = (written_ns - start_ns) / 1000
                packet["wait_us"] = (received_ns - written_ns) / 1000
                packet["host_us"] = (finish_ns - received_ns) / 1000
                packet['read_us'] = read_total_ns / 1000
                packet['poll_wait_us'] = max(0, (received_ns-written_ns-read_total_ns)/1000)
                packet['validate_us'] = (score_start-received_ns)/1000
                self.last_exchange = time.monotonic()
                # Same-host monotonic clock for optional cross-process workstation timing.
                packet["request_started_ns"] = start_ns
                packet["received_ns"] = received_ns
                packet["classified_ns"] = finish_ns
                return packet
        if not self.stop.is_set():
            self.state.error("timeouts", "No valid matching response before timeout")
            self.frames, self.lines = self.wire.BinaryFrames(), self.wire.Lines()
            self.state.protocol_resets += 1
        return None

    def output(self, row):
        # Never synchronously print, sort percentiles, or write disk in acquisition.
        now = time.monotonic()
        mode = getattr(self.args, "terminal", "tape")
        interval = 1 if mode == "summary" else .1
        printing = self.console_ok and (mode == "all" or now - self.last_print >= interval)
        logging_mode = getattr(self.args, "log", "sampled")
        logging = logging_mode == "all" or (logging_mode == "sampled" and now - self.last_log >= .1)
        if not printing: self.state.output_sampled += 1
        if not logging: self.state.log_sampled += 1
        if not printing and not logging: return
        if printing: self.last_print = now
        if logging: self.last_log = now
        try: self.output_queue.put_nowait((row, printing, logging, time.perf_counter_ns()))
        except queue.Full:
            with self.state.lock:
                self.state.log_dropped += int(logging)
                self.state.output_dropped += int(printing)
            self.state.log_warning = "Output queue full; acquisition continues, selected log/display rows dropped"

    def consume_output(self):
        background = getattr(self.args, 'background_cpus', [])
        if background and hasattr(os, 'sched_setaffinity'):
            try:
                os.sched_setaffinity(0, set(background))
            except OSError:
                self.state.log_warning = 'Could not place output thread on housekeeping CPUs'
        while not self.output_done.is_set() or not self.output_queue.empty() or not self.event_queue.empty():
            for _ in range(64):
                try: event = self.event_queue.get_nowait()
                except queue.Empty: break
                try:
                    self.event_file.write(json.dumps(event, allow_nan=False)+'\n')
                    self.event_file.flush()
                    self.state.event_written += 1
                    if event.pop('printing', False) and self.console_ok: print(event['message'], flush=True)
                except (OSError, BrokenPipeError):
                    self.state.event_dropped += 1
                    self.state.log_warning = 'Event output failed; inspect disk/terminal'
                finally: self.event_queue.task_done()
            try: row, printing, logging, queued_ns = self.output_queue.get(timeout=.05)
            except queue.Empty: continue
            output_start_ns = time.perf_counter_ns()
            with self.state.lock:
                self.state.output_queue_us.append((output_start_ns-queued_ns)/1000)
            if logging:
                self.log_handler.failed = False
                self.logger.info(json.dumps(row, separators=(",", ":"), allow_nan=False))
                with self.state.lock:
                    self.state.log_written += int(not self.log_handler.failed)
                    self.state.log_dropped += int(self.log_handler.failed)
            if not printing or not self.console_ok:
                with self.state.lock: self.state.output_us.append((time.perf_counter_ns()-output_start_ns)/1000)
                self.output_queue.task_done()
                continue
            snapshot = self.state.quick()
            z = "n/a" if row["z"] is None else f"{row['z']:+.2f}"
            message = (f"[{row['index']:06d}] {row['symbol']:<8} movement={row['movement_pct']:+.2f}% "
                       f"z={z:>6} decision={row['decision']:<6} latency={row['latency_us']:.0f}us "
                       f"analysis={row['analysis_us']:.1f}us "
                       f"throughput={snapshot['throughput']:.1f} sig/s errors={snapshot['error_count']} "
                       f"history={row['history_n']} seq={row['sequence']}")
            if getattr(self.args, "terminal", "tape") == "summary":
                c = snapshot["counts"]
                message = (f"[LIVE] total={snapshot['total']} BUY={c['BUY']} SELL={c['SELL']} STAY={c['STAY']} "
                           f"rate={snapshot['throughput']:.1f}/s errors={snapshot['error_count']} | " + message)
            try:
                print(message, flush=True)
                self.state.output_written += 1
            except (BrokenPipeError, OSError):
                self.console_ok = False
                self.state.log_warning = "Terminal output closed; hardware processing continues"
                self.state.output_dropped += 1
            finally:
                with self.state.lock: self.state.output_us.append((time.perf_counter_ns()-output_start_ns)/1000)
                self.output_queue.task_done()

    def run(self):
        self.output_thread = threading.Thread(target=self.consume_output, daemon=True, name="output-writer")
        self.output_thread.start()
        retry_delay=1.0
        try:
            while not self.stop.is_set():
                connection = None
                port = None
                try:
                    port = choose_port(self.args.port)
                    self.state.status("CONNECTING", "Opening serial port; waiting for ESP32 boot", port)
                    connection = open_connection(port, self.args.timeout, self.base_baud)
                    # A disconnected ESP32 may still be at the last negotiated speed.
                    # Silence longer than idle expiry, always reopen the BASE baud.
                    if self.stop.wait(max(RECOVERY_SECONDS, self.args.boot_wait)): break
                    connection.reset_input_buffer()
                    connection.write(b"\n")
                    self.nonce, self.request_id = secrets.randbits(32), 0
                    self.lines, self.frames = self.wire.Lines(), self.wire.BinaryFrames()
                    self.state.protocol_resets += 1
                    self.negotiate(connection)
                    details = [p for p in ports() if p["device"] == os.path.realpath(port)]
                    if details:
                        self.state.serial_description = details[0]["description"]
                    with self.state.lock:
                        self.state.connections += 1
                    failures = 0
                    while not self.stop.is_set():
                        cycle = time.monotonic()
                        row = self.exchange(connection)
                        if row is None:
                            failures += 1
                            self.state.status("NO VALID DATA", "No matching CRC-valid response; retrying", port)
                            self.notice("[LINK] NO VALID DATA — check firmware, baud rate, and USB cable")
                            if failures >= 3:
                                raise serial.SerialException("Three consecutive response timeouts")
                        else:
                            failures = 0
                            retry_delay=1.0
                            histories = {s: len(w) for s, w in self.analyzer.windows.items()}
                            self.state.add(row, histories)
                            self.output(row)
                        warming = any(len(w) < 128 for w in self.analyzer.windows.values())
                        rate = self.args.warmup_rate if warming else self.args.rate
                        if rate > 0: self.stop.wait(max(0, cycle + 1 / rate - time.monotonic()))
                except (OSError, serial.SerialException, ValueError) as exc:
                    # Missing ports aren't counted as a fresh packet error on each scan.
                    if connection is not None and connection.is_open:
                        self.state.error("io_errors", str(exc))
                    self.state.status("HARDWARE DISCONNECTED", str(exc), port)
                    self.notice("[LINK] HARDWARE DISCONNECTED — " + str(exc))
                finally:
                    if connection is not None:
                        connection.close()
                self.stop.wait(retry_delay)
                retry_delay=min(16.,retry_delay*2)
        except Exception as exc:
            self.state.error("io_errors", "Receiver stopped: " + repr(exc))
            self.state.status("HARDWARE DISCONNECTED", "Receiver stopped: " + repr(exc))
            self.notice("[FATAL] Receiver stopped; restart after fixing: " + repr(exc))
        finally:
            self.output_done.set()
            if self.output_thread: self.output_thread.join(timeout=3)
            try:
                self.analyzer.save(self.args.run_dir / "history.csv")
            except OSError as exc:
                self.state.log_warning = "History could not be saved: " + str(exc)
            if not self.output_thread or not self.output_thread.is_alive():
                self.event_file.close()
                self.state.event_sink = None
                self.log_handler.close()
                self.logger.removeHandler(self.log_handler)
            else:
                self.state.log_warning = "Output writer did not drain before shutdown; inspect saved evidence"


def health_loop(state, stop):
    while not stop.is_set():
        health = {"power": "UNKNOWN", "temperature_c": None, "throttled": None}
        try:
            raw = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True,
                                 timeout=1, check=True).stdout.strip()
            value = int(raw.split("=")[1], 16)
            health["throttled"] = raw
            health["power"] = ("UNDERVOLTAGE NOW" if value & 1 else
                               "THROTTLING NOW" if value & 0xE else
                               "PAST POWER/THERMAL EVENT" if value & 0xF0000 else "OK")
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as file:
                health["temperature_c"] = round(int(file.read()) / 1000, 1)
        except (OSError, ValueError):
            pass
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            health['process_cpu_seconds'] = usage.ru_utime + usage.ru_stime
            health['process_max_rss_kib'] = usage.ru_maxrss
        except (ImportError, OSError): pass
        health['sampled_monotonic_ns'] = time.perf_counter_ns()
        with state.lock:
            state.health = health
            state.health_samples.append(health.copy())
        stop.wait(5)
