# Reproducible software profiling

Run `tools/profile_dashboard.cjs` sequentially against unmodified V7 and V8 on the same host, with fresh data directories and no other QA/research jobs running. Use the same Python, Chromium, viewport, seed, simulated market workload and 4 Hz display setting. Optional Playwright belongs on a development machine.

```bash
PYTHON=/path/to/python PB_CHROMIUM=/path/to/chromium \
  node tools/profile_dashboard.cjs /path/to/V7 /path/to/output-v7
PYTHON=/path/to/python PB_CHROMIUM=/path/to/chromium \
  node tools/profile_dashboard.cjs /path/to/V8 /path/to/output-v8
```

The script starts/stops each real server and records raw samples, versions, host characteristics, workload, errors and units. It measures 20 explicit renders on each of 14 views, render-to-next-frame and navigation timings, 80 HTTP state requests, 20 steady-state SSE update sizes, live Market renders and 120 alternating baseline configuration commands. Each configuration command records an actual audit event through the durable writer; the exported ledger must contain all 120. Paper automation remains off. Rendering unchanged state deliberately measures redundant DOM work; live SSE render samples are reported separately.

Backend commit/queue timings come from the actual writer. HTTP command acknowledgement includes transport, command scheduling and commit; it is not database latency alone. CPU is a process-tree delta in one-core percentage units. Namespace PIDs are mapped to host `/proc` identities; summed RSS includes shared pages and is not unique physical memory. Timing summaries retain p50/p95/p99, sample counts and raw values. Low-sample navigation/live-render tails are descriptive, not reliable extreme-quantile estimates.

The final report uses the audited V7/V8 runs in `docs/v8/validation/profile-v7.json` and `profile-v8.json`. Earlier short preliminary runs varied, including a navigation regression; there is no claim that every run or every metric improves. The final database commit tail increased with V8's added checkpoint writes. WAL/FULL and durable acknowledgement remain enabled.

The requested approximately 67 ms commit p95 cannot be causally diagnosed from a screenshot alone. It was not reproduced on this host. A meaningful target diagnosis needs the original workload/sample count, queue and lock waits, filesystem/SD latency, competing writers, Pi power/thermal status and raw traces. V7 already used an asynchronous bounded WAL writer; V8 does not claim to have invented that architecture or fixed the target SD card. Repeat these measurements on the actual Pi 3 B+ and keep physical USB request/classification latency separate from software API, processing, persistence and browser timings.
