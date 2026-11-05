# Physical validation — HARDWARE PENDING

No ESP32/Pi hardware was attached to the release build environment. Native C++ shims and pseudo-terminal protocol fixtures exercise actual parser/firmware logic but do not measure physical USB latency.

- Record Pi 3 B+ revision, 1 GB RAM, OS/Python, SD model/filesystem, supply, temperature and throttling flags.
- Confirm classic ESP32/CP2102 markings and profile 1; configure and compile the canonical sketch with the exact Espressif Arduino package and board settings. Retain build/upload logs and firmware hash.
- Upload through the board USB data connector, close Serial Monitor and connect Pi USB to ESP32 USB. No GPIO jumper wires are required.
- Enumerate the actual serial port and check permissions; verify Protocol 3 board identity, boot ID, CRC and matching sequence handling at compat/115200.
- Exercise disconnect/reconnect, malformed/stale frames, reset, duplicate replies and acquisition shutdown/drain; confirm no fabricated hardware success or uncounted critical drops.
- Compare supported baud/profile/rate settings with the same seeded workload, logging policy and UI refresh rate. Keep physical request-to-classification timing separate from engine, commit and browser timing.
- Run sustained demo/research/paper workflows on the 1 GB Pi; record CPU/RSS, queues, drops, thermal/power state, API/commit percentiles and sample counts.
- Check the actual SD/filesystem commit distribution and concurrent-write workload to investigate the previously observed high p95. Do not infer its cause from screenshots alone.
- Back up first, then perform an explicitly planned crash/power-loss recovery exercise on nonessential test data. Verify orders, fills, cash, holdings and audit records after restart.

Record PASS/FAIL and the environment for each performed step. Leave unperformed steps HARDWARE PENDING. No hard real-time, physical latency or target-memory guarantee is issued by the software release.
