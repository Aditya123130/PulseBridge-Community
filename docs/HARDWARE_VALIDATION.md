# PulseBridge Physical Hardware Validation

## Overview

PulseBridge Community Edition has been physically validated using an ESP32 connected to a Raspberry Pi/Linux host through USB-UART.

This validation demonstrates real hardware communication using PulseBridge Protocol 3. The market-data movements used during the test were synthetic demonstration data. No live exchange feed or real order execution was involved.

## Test Configuration

| Parameter | Value |
|---|---|
| Protocol | PulseBridge Protocol 3 |
| Hardware | ESP32 + Raspberry Pi |
| Transport | USB Serial / UART 8N1 |
| Baud Rate | 115200 |
| Target Rate | 20 signals/s |
| Test Duration | 60.60 seconds |
| Total Messages | 1,765 |
| Data Source | Synthetic demonstration movements |

## Reliability Results

| Metric | Result |
|---|---:|
| Total Messages | 1,765 |
| CRC Errors | 0 |
| Format Errors | 0 |
| Timeouts | 0 |
| Stale Replies | 0 |
| Duplicate Sequences | 0 |
| I/O Errors | 0 |
| Sequence Gaps | 0 |
| ESP32 Resets | 0 |
| Connections | 1 |

The run completed without a recorded Protocol 3 communication error, sequence gap, or ESP32 reset.

## Request-to-Decision Latency

| Metric | Latency |
|---|---:|
| Minimum | 7.596 ms |
| Average | 8.876 ms |
| P50 | 8.821 ms |
| P95 | 9.561 ms |
| P99 | 9.727 ms |
| Maximum | 10.040 ms |

The latency measurement represents Raspberry Pi request-to-decision latency for this configuration.

## Classification Results

| Classification | Count |
|---|---:|
| BUY | 30 |
| SELL | 30 |
| STAY | 937 |
| WARMUP | 768 |

Total: 1,765 messages.

## Evidence

The machine-readable and supporting evidence for this run is stored in:

`docs/hardware-validation/2026-11-05/`

Included evidence:

- `summary.json` - machine-readable run summary
- `HARDWARE_VALIDATION_RESULTS.txt` - human-readable results
- `system_health.txt` - Raspberry Pi system-health information
- `SHA256SUMS.txt` - hashes for the captured validation artifacts

The complete raw run was also preserved separately during testing.

## System Health Limitation

The Raspberry Pi reported `throttled=0x50005` during the validation session.

Therefore, this run should be treated as successful **functional hardware and protocol validation**, but not as a clean or definitive performance benchmark.

The latency measurements are reported for transparency, but they should not be interpreted as the maximum achievable performance of PulseBridge.

A future benchmark should be performed after eliminating the Raspberry Pi power/undervoltage condition.

## Scope and Interpretation

This validation supports the following claims:

- ESP32-to-Raspberry-Pi physical USB-UART communication works.
- PulseBridge Protocol 3 operates on physical hardware.
- The tested run processed 1,765 messages.
- No CRC, format, timeout, stale-reply, duplicate-sequence, I/O, or sequence-gap errors were recorded.
- Request-to-decision latency was instrumented and recorded.
- Evidence was preserved in machine-readable form.

This validation does **not** demonstrate:

- exchange-grade HFT latency;
- live exchange connectivity;
- profitable trading performance;
- real-money order execution;
- deterministic production latency under all operating conditions.

## Conclusion

The 2026-11-05 validation successfully demonstrated end-to-end PulseBridge Community Edition operation across a physical ESP32 and Raspberry Pi using USB-UART and Protocol 3.

The run provides reproducible evidence of functional communication and protocol reliability. Performance results remain preliminary because the Raspberry Pi reported an undervoltage/throttling condition during testing.
