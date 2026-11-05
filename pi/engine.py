"""Wire protocol, past-only statistics, and thread-safe display state."""
import binascii
import csv
import math
import re
import struct
import threading
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path

from protocol import (SYMBOLS, VERSION, BASE_BAUD, PROFILES, MAGIC, REQUEST, RESPONSE,
                      PacketError, encode, request_packet, binary_request, parse_response,
                      parse_binary, BinaryFrames, Lines)
WINDOW = 128
STALE_SECONDS = 1.5


class RingWindow:
    """Exact integer ppm sums: constant-time mean/variance without floating drift."""
    def __init__(self):
        self.values = deque(maxlen=WINDOW)
        self.total = self.squares = 0

    def __len__(self): return len(self.values)
    def __iter__(self): return (x / 10000 for x in self.values)
    def __getitem__(self, index): return self.values[index] / 10000

    def append(self, value):
        ppm = round(value * 10000)
        if len(self.values) == WINDOW:
            old = self.values[0]
            self.total -= old
            self.squares -= old * old
        self.values.append(ppm)
        self.total += ppm
        self.squares += ppm * ppm

    def statistics(self):
        n = len(self.values)
        mean = self.total / n / 10000 if n else None
        # Compute the subtraction in arbitrary-precision integers BEFORE division.
        variance_numerator = n * self.squares - self.total * self.total
        std = math.sqrt(variance_numerator / (n * (n - 1))) / 10000 if n >= 2 else None
        return mean, std


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Analyzer:
    def __init__(self, threshold=2.0, history=None):
        self.threshold = threshold
        self.windows = {s: RingWindow() for s in SYMBOLS}
        self.source = "Previous ESP32 hardware observations (demo movements)"
        if history:
            self.load(history)

    def load(self, path):
        with open(path, newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            if not {"symbol", "movement_pct", "source"} <= set(reader.fieldnames or []):
                raise ValueError("History requires symbol,movement_pct,source columns")
            sources = set()
            for line, row in enumerate(reader, 2):
                symbol = row["symbol"]
                if symbol not in self.windows:
                    raise ValueError(f"History line {line}: unsupported symbol {symbol!r}")
                try:
                    value = float(row["movement_pct"])
                    source = (row["source"] or "").strip()
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"History line {line}: missing/invalid movement") from exc
                if not math.isfinite(value) or abs(value) > 100 or not source:
                    raise ValueError(f"History line {line}: invalid value/source")
                self.windows[symbol].append(value)
                sources.add(source)
        if any(len(v) < 100 for v in self.windows.values()):
            raise ValueError("History must contain at least 100 past values for EVERY symbol")
        self.source = "Imported: " + "; ".join(sorted(sources))[:300]

    def process(self, symbol, movement):
        window = self.windows[symbol]
        n = len(window)
        # Default startup fills 128. Imported 100+ observations are sufficient.
        ready = n >= (100 if self.source.startswith("Imported:") else WINDOW)
        mean, std = window.statistics()
        z = None
        decision = "WARMUP"
        if ready:
            # Zero/near-zero variation must not create infinity or bogus trades.
            if std is not None and std >= 0.0001:
                z = (movement - mean) / std
                unusual = abs(z) >= self.threshold
                decision = "BUY" if unusual and movement > 0 else (
                    "SELL" if unusual and movement < 0 else "STAY")
            else:
                decision = "STAY"
        result = dict(history_n=n, mean_pct=mean, std_pct=std, z=z, decision=decision,
                      stats_valid=bool(ready and std is not None and std >= 0.0001))
        window.append(movement)  # Deliberately AFTER scoring: no look-ahead.
        return result

    def save(self, path):
        path = Path(path)
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["symbol", "movement_pct", "source"])
            for symbol, window in self.windows.items():
                for value in window:
                    writer.writerow([symbol, f"{value:.4f}", "ESP32 demo rolling window; may include imported seed"])
        temporary.replace(path)


def percentile(sorted_values, quantile):
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * quantile
    low = math.floor(position)
    high = math.ceil(position)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


class State:
    def __init__(self, rate=20, threshold=2.0):
        self.lock = threading.RLock()
        self.started = time.monotonic()
        self.link = "HARDWARE DISCONNECTED"
        self.reason = "Waiting for an ESP32 USB serial port"
        self.port = None
        self.baud = BASE_BAUD
        self.rate, self.threshold = rate, threshold
        self.total = 0
        self.counts = Counter(BUY=0, SELL=0, STAY=0, WARMUP=0)
        self.errors = Counter(crc_errors=0, format_errors=0, timeouts=0, stale_replies=0,
                              duplicate_sequences=0, io_errors=0)
        self.resets = self.connections = self.sequence_gaps = 0
        self.last_mono = self.last_wall = None
        self.rows, self.latencies, self.rates = deque(maxlen=100), deque(maxlen=2000), deque(maxlen=250000)
        self.chart = deque(maxlen=90)
        self.latency_sum = 0.0
        self.latency_min = self.latency_max = None
        self.last_error = "None"
        self.history = {s: 0 for s in SYMBOLS}
        self.history_source = "Previous ESP32 hardware observations (demo movements)"
        self.health = {"power": "UNKNOWN", "temperature_c": None, "throttled": None}
        self.log_warning = None
        self.profile = "compat"
        self.protocol = "ASCII v3"
        self.requests = self.log_dropped = self.log_written = 0
        self.output_dropped = self.output_sampled = self.log_sampled = 0
        self.output_written = self.protocol_resets = 0
        self.output_queue_us = deque(maxlen=2000)
        self.output_us = deque(maxlen=2000)
        self.device = {}
        self.event_sink = None
        self.event_dropped = self.event_written = 0
        self.health_samples = deque(maxlen=2048)
        self.stale_seconds = STALE_SECONDS
        self.write_sum = self.wait_sum = self.host_sum = self.analysis_sum = 0.0
        self.target_us = 9000.0
        self.over_target = 0
        self.latest_by_symbol = {}
        self.last_unusual = None
        self.first_classified_mono = self.last_classified_mono = None
        self.classified_total = 0
        self.log_mode = "sampled"
        self.serial_description = "Unknown USB bridge"
        self.chart_rate = deque(maxlen=90)

    def status(self, link, reason, port=None):
        with self.lock:
            self.link, self.reason = link, reason
            self.port = port

    def error(self, kind, message, count=1):
        with self.lock:
            self.errors[kind] += count
            self.last_error = message
            if self.event_sink: self.event_sink(kind, message, count)

    def add(self, row, histories):
        with self.lock:
            now = time.monotonic()
            self.total += 1
            row["index"] = self.total
            row["received_at"] = utc_now()
            self.last_mono, self.last_wall = now, row["received_at"]
            self.link, self.reason = "CONNECTED", "CRC-verified ESP32 responses received"
            self.counts[row["decision"]] += 1
            self.rows.appendleft(row)
            latency = row["latency_us"]
            self.latencies.append(latency)
            self.latency_sum += latency
            self.latency_min = latency if self.latency_min is None else min(self.latency_min, latency)
            self.latency_max = latency if self.latency_max is None else max(self.latency_max, latency)
            self.rates.append(now)
            while self.rates and self.rates[0] < now - 10:
                self.rates.popleft()
            self.write_sum += row.get("write_us", 0)
            self.wait_sum += row.get("wait_us", 0)
            self.host_sum += row.get("host_us", row.get("analysis_us", 0))
            self.analysis_sum += row.get("analysis_us", 0)
            self.over_target += int(latency > self.target_us)
            self.latest_by_symbol[row["symbol"]] = row
            if row["decision"] in ("BUY", "SELL"): self.last_unusual = row
            if row["decision"] != "WARMUP":
                if self.first_classified_mono is None: self.first_classified_mono = now
                self.last_classified_mono = now
                self.classified_total += 1
            second = int(time.time())
            if self.chart and self.chart[-1]["t"] == second:
                self.chart[-1]["sum"] += latency
                self.chart[-1]["n"] += 1
            else:
                self.chart.append({"t": second, "sum": latency, "n": 1})
            self.history = histories

    def quick(self):
        with self.lock:
            now = time.monotonic()
            return dict(total=self.total, throughput=len(self.rates) / max(1.0, min(10.0, now - self.started)),
                        error_count=sum(self.errors.values()), counts=dict(self.counts))

    def snapshot(self, include_health_history=False):
        with self.lock:
            now = time.monotonic()
            while self.rates and self.rates[0] < now - 10:
                self.rates.popleft()
            age = None if self.last_mono is None else now - self.last_mono
            status = self.link
            if status == "CONNECTED" and (age is None or age > self.stale_seconds):
                status = "HARDWARE DISCONNECTED"
            values = list(self.latencies)
            result = dict(status=status, reason=self.reason, port=self.port, baud=self.baud,
                transport=("GPIO UART / 3.3V / 8N1" if self.port and any(x in self.port for x in ('ttyAMA', 'ttyS', 'serial0', 'serial1'))
                           and not any(x in self.port for x in ('ttyUSB', 'ttyACM', 'by-id')) else "USB serial / UART 8N1"),
                target_rate=self.rate, threshold=self.threshold,
                total=self.total, counts=dict(self.counts), errors=dict(self.errors),
                error_count=sum(self.errors.values()), last_error=self.last_error,
                sequence_gaps=self.sequence_gaps, resets=self.resets, connections=self.connections,
                throughput=(len(self.rates) / max(1.0, min(10.0, now - self.started))) if status == "CONNECTED" else 0.0,
                last_received=self.last_wall, last_age_s=age, uptime_s=now - self.started,
                latency=dict(avg=self.latency_sum / self.total if self.total else None,
                    min=self.latency_min, max=self.latency_max, window_n=len(values)),
                latest=list(self.rows), chart=[{"t": v["t"], "us": v["sum"] / v["n"], "n":v["n"]} for v in self.chart],
                history=self.history.copy(), history_source=self.history_source,
                health=self.health.copy(), log_warning=self.log_warning,
                profile=self.profile, protocol=self.protocol, requests=self.requests,
                event_dropped=self.event_dropped, event_written=self.event_written,
                protocol_resets=self.protocol_resets, reconnects=max(0,self.connections-1), device=self.device,
                output_dropped=self.output_dropped, output_sampled=self.output_sampled,
                log_sampled=self.log_sampled, output_written=self.output_written,
                output_queue_us=list(self.output_queue_us), output_us=list(self.output_us),
                health_samples=list(self.health_samples) if include_health_history else [],
                log_mode=self.log_mode, log_dropped=self.log_dropped, log_written=self.log_written,
                latest_by_symbol=dict(self.latest_by_symbol), last_unusual=self.last_unusual,
                serial_description=self.serial_description,
                classified_rate=((self.classified_total-1)/(self.last_classified_mono-self.first_classified_mono))
                    if self.classified_total > 1 and self.last_classified_mono > self.first_classified_mono else None,
                target_us=self.target_us, over_target=self.over_target,
                under_target_pct=(100 * (self.total - self.over_target) / self.total) if self.total else None,
                success_pct=(100 * self.total / self.requests) if self.requests else None,
                stages={"write_us":self.write_sum / self.total if self.total else None,
                        "wait_us":self.wait_sum / self.total if self.total else None,
                        "host_us":self.host_sum / self.total if self.total else None,
                        "analysis_us":self.analysis_sum / self.total if self.total else None})
        # Sorting/percentiles are display work; do not hold the receiver's state lock.
        values.sort()
        result["latency"].update(p50=percentile(values,.5),p95=percentile(values,.95),p99=percentile(values,.99))
        for key in ('output_us', 'output_queue_us'):
            data = sorted(result[key])
            result[key] = dict(n=len(data), avg=sum(data)/len(data) if data else None,
                               p50=percentile(data,.5),p95=percentile(data,.95),p99=percentile(data,.99))
        result['connection_kind'] = getattr(self, 'connection_kind', 'physical_usb')
        if result['connection_kind'] == 'software_fixture':
            if result.get('status') == 'CONNECTED': result['status'] = 'SIMULATED'
            result['reason'] = 'Software protocol fixture; no physical ESP32 or USB timing'
            result['history_source'] = 'Synthetic protocol fixture'
        return result
