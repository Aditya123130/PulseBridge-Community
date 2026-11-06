# Reproducing and auditing PulseBridge hardware evidence

This Community Edition reports **functional ESP32–Raspberry Pi USB-UART validation**, not qualified exchange-grade latency. Its 2026-11-05 recording used a synthetic workload, a 115200-baud Protocol 3 link, and a Raspberry Pi that reported `throttled=0x50005`.

## Validate the captured summary

From the repository root, run:

```sh
python3 tools/validate_hardware_evidence.py
python3 -m unittest discover -s tests -p 'test_hardware_evidence.py' -v
```

The validator checks recorded message/decision totals, per-category error accounting, finite ordered latency summaries, and the presence of Raspberry Pi power/throttling flags. It **does not** recalculate latency percentiles from the JSON snapshot, and it never outputs `performance_qualified=true` simply because checks pass. An inconsistent record causes a nonzero exit code.

For another experiment with the same JSON and system-health format, run:

```sh
python3 tools/validate_hardware_evidence.py --evidence-dir path/to/run
```

The `latest` array is a **partial snapshot**, not the complete raw trace. Do not treat those rows as sufficient to reproduce p95/p99. The archived `summary.json` is a historical output, so the validator only checks internal consistency and never re-labels the past run as an independently reproduced experiment.

## Reproducible experimental design

See [BENCHMARK_METHODOLOGY.md](BENCHMARK_METHODOLOGY.md) and [HARDWARE_VALIDATION_CHECKLIST.md](HARDWARE_VALIDATION_CHECKLIST.md) before recording a new result.

1. Fix the hardware, firmware commit, Pi OS, serial configuration, workload, and host timing boundary; retain exact version identifiers.
2. Record boot and end-of-run `vcgencmd get_throttled`, or equivalent platform health information, plus supply and thermal conditions. Resolve power warnings before comparing latency.
3. Preserve every raw request-to-decision sample and error event with units, including timeouts and reconnects. Keep manifests/hashes for the released data.
4. Run multiple randomized/repeated configurations; compare encoding and baud independently where the implementation permits it. If encoding and baud are coupled, report **profile comparisons** only.
5. Publish the analysis script, summary-generation method, sample counts and quantile definition, confidence or uncertainty analysis, and limitations. Cross-check all headline statistics against the raw trace before publishing.
6. Report functional reliability and performance measurements as **different claims**. Passing protocol checks does not certify throughput, tail latency, or trading viability.

## Evidence status

| Material | Status | What it supports |
|---|---|---|
| [`summary.json`](docs/hardware-validation/2026-11-05/summary.json) | Captured | Recorded request counts, error counters, and descriptive latency summaries |
| [`system_health.txt`](docs/hardware-validation/2026-11-05/system_health.txt) | Captured, power warning | The Pi reported undervoltage/throttling flags |
| [`HARDWARE_VALIDATION.md`](docs/HARDWARE_VALIDATION.md) | Documented | Functional link validation and explicit limitations |
| Complete raw samples | Not included in this Community repository | Published p95/p99 cannot be independently recalculated from the snapshot alone |

**Interpretation:** the existing run shows physical protocol operation with no *recorded* errors in that session. It is not a power-qualified performance comparison. A later, controlled study must be evaluated separately.
