# PulseBridge Community architecture

PulseBridge Community is a focused ESP32-to-Linux/Raspberry Pi research toolkit for USB/UART communication, Protocol 3 validation, synthetic market-data movement generation, latency instrumentation, and reproducible software/hardware experiments.

## System path

```text
ESP32 firmware
    ↕ USB serial / UART
pi/transport.py
    ↓
pi/protocol.py
    ↓
pi/engine.py
    ↓
pi/app.py / pi/benchmark.py / pi/doctor.py
    ↓
browser dashboard or recorded benchmark output
```

The public Community Edition intentionally excludes the larger private V8 workstation's brokerage, autonomous research, deployment, hosted-AI, and account-management subsystems.

## Firmware

The canonical sketch is `firmware/PulseBridgeESP32/PulseBridgeESP32.ino` with explicit board configuration in `board_config.h`. Firmware implements Protocol 3 framing, CRC-16/CCITT-FALSE, session negotiation, request/replay handling, bounded parsing, deterministic seeded synthetic workloads, and diagnostic counters.

Board/profile selection is explicit rather than guessed. See `START_HERE.md` and `PROTOCOL_SPEC.md`.

## Host

- `pi/transport.py` owns serial/PTY transport behavior and bounded reads.
- `pi/protocol.py` owns Protocol 3 framing, CRC validation, parsing, identity checks, and protocol semantics.
- `pi/engine.py` owns the host-side processing path and rolling analysis.
- `pi/app.py` provides the small Community dashboard/runtime.
- `pi/benchmark.py` provides benchmark execution.
- `pi/doctor.py` provides environment/device diagnostics.
- `pi/simulator.py` provides a software fixture for protocol testing.
- `pi/legacy.py` contains explicit legacy compatibility paths; Protocol 3 does not silently downgrade.

The browser assets used by the Community dashboard are under `pi/static/`.

## Validation layers

PulseBridge deliberately separates four kinds of evidence:

1. **Software validation** — Python/native tests and CI.
2. **Protocol validation** — framing, CRC, replay/session, corruption, timeout and parser behavior.
3. **Software-fixture validation** — Linux PTY simulation through the real host parser.
4. **Physical validation** — ESP32, USB cable, Raspberry Pi/Linux host, power/thermal state and measured physical transport.

Passing software or PTY tests does not prove physical USB latency.

## Timing boundary

Benchmark results must state the exact timing boundary being measured. Host request-to-classification timing is not exchange latency, network latency, order-execution latency, or unsynchronized ESP-to-Pi timestamp subtraction. The ESP `micros()` value is metadata only.

## Persistence and scope

This Community Edition is not the full PulseBridge V8 workstation and does not expose its private trading, brokerage, autonomous deployment, research-database, or hosted-AI architecture. Documentation in this repository describes only components that are present here.

See `BENCHMARK_METHODOLOGY.md`, `HARDWARE_VALIDATION_CHECKLIST.md`, and `PROTOCOL_SPEC.md` before publishing performance claims.
