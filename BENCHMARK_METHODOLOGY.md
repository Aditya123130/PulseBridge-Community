# Benchmark methodology

PulseBridge Community separates software profiling from physical ESP32-to-host measurements. Results are meaningful only when the timing boundary, transport, workload, environment and validation state are reported together.

## What may be benchmarked

The repository includes Community tooling under `tools/` and `pi/benchmark.py` for software/transport experiments. Use the tools that match the experiment being reported; do not describe a PTY/software-fixture result as physical USB latency.

The historical V8 research archive reported host request-to-classification measurements for controlled synthetic workloads. Those historical results are context, not a guarantee of performance on another board, Pi, cable, OS, power supply or workload.

## Required experiment record

For a reproducible physical run, record at minimum:

- ESP32 model and selected board profile;
- firmware commit SHA;
- host/Raspberry Pi model and OS;
- Python version and dependency versions;
- USB cable/connection path;
- selected Protocol 3 profile, encoding and baud;
- warmup and steady request rates;
- sample count/run duration;
- exact timing boundary and units;
- power/undervoltage state when available;
- thermal/throttling state when available;
- errors, reconnects, CRC failures, sequence gaps and rejected samples;
- whether the run is physical hardware, software fixture or simulation.

Use `HARDWARE_VALIDATION_CHECKLIST.md` for physical qualification.

## Controlled comparisons

Change one independent variable at a time whenever causal attribution is intended. In particular, do not attribute a latency difference to binary versus ASCII encoding if baud rate also changes in the same comparison.

A stronger encoding/baud study is a controlled 2×2 design where the supported configuration permits it. If a protocol profile couples encoding and baud, report the result as a **profile comparison**, not as an encoding-only effect.

## Statistics

Keep raw samples where practical. Report sample count and at least median/p50 plus appropriate tail summaries such as p95/p99 when the sample size supports them. Very small samples should be described as descriptive observations rather than reliable extreme-quantile estimates.

Do not remove failed samples silently. Report timeout, reconnect, parser, CRC and sequence/error counts alongside latency summaries.

## Timing interpretation

Host request-to-classification timing includes the host/device path defined by the benchmark implementation. It is not:

- exchange round-trip latency;
- broker/order execution latency;
- Internet/network latency;
- a profitability measurement;
- an ESP-to-Pi one-way timestamp derived from unsynchronized clocks.

The ESP timestamp in Protocol 3 is metadata. No unsynchronized ESP/Pi timestamp subtraction should be presented as latency.

## Software fixtures

Linux PTY or other software-fixture runs are useful for parser, transport and regression testing. Label them clearly as software results. They cannot validate USB cable behavior, ESP32 target timing, Raspberry Pi power/thermal health, or physical serial performance.

## Before publishing a number

Run the relevant automated tests, record the exact commit, preserve raw output, complete the hardware checklist for physical measurements, and state all limitations. Reproduction by an independent machine or contributor is preferred before making strong performance claims.
