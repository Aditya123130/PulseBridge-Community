# Installation

The core runtime needs Linux (including WSL2), Python 3.10+ and pySerial 3.5. It has no Node, GPU, database-server, NumPy, pandas or local LLM requirement. A browser can run on your laptop while the server runs on the Pi. Windows supports firmware upload; run the workstation in Linux/WSL2 because process isolation and file locking use Linux facilities.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/release_manifest.py verify
.venv/bin/python tools/preflight.py --mode demo --data-dir runs/demo
bash run_workstation.sh --mode demo --no-hardware --data-dir runs/demo
```

Open http://localhost:8080. For a remote Pi, use `ssh -L 8080:localhost:8080 USER@PI` from the laptop. The default loopback binding is deliberate. If binding a LAN address, configure `PB_DASHBOARD_PASSWORD`; use a trusted tunnel or TLS proxy for access outside the machine. The existing `--trusted-lan` option explicitly permits unauthenticated LAN access.

`run_workstation.sh` uses `.venv/bin/python` when present. Install Python venv support using the OS package manager if venv creation fails. `setup_pi.sh` is an optional serial dependency/dialout helper; group membership changes require a new login. For optional external streaming feeds, install `requirements-live.txt`. `requirements-all.txt` installs both pySerial and the pinned WebSocket library for the complete test suite. Initial installation needs a package source; prepare compatible wheels in advance for an offline Pi.

Check `python3 --version` before installation. Creating a venv does not upgrade an older Python interpreter.

## Upgrade and storage

Keep the old source ZIP unchanged. Stop the existing server cleanly and back up its runtime directory before using that data directory with V8. Additive migration 9 preserves earlier schema 7/8 research records, orders, fills, sessions and audit history. New V8 accounts have exact recovery checkpoints. Older V7 sessions without checkpoints remain archived/readable; V8 does not reconstruct unspecified state from incomplete records.

A restarted V8 account restores its cash, cost basis, holdings, orders and fills. Pending orders are cancelled, quotes must become fresh, and new orders/strategies remain paused until explicit resume. New-session actions still archive the prior session. Capture an export before intentionally starting a new account.

Use a separate data directory for each concurrently running instance. SQLite uses WAL and FULL durability, with a bounded writer queue. Clean shutdown checkpoints the WAL. This does not prove sudden-power-loss survival on an SD card; physical fault testing is pending. Stop cleanly before copying all runtime files, or use SQLite's backup interface for a live backup. Use the Linux filesystem for WSL work and measure the actual storage used.

The final release tests and exact environment appear in `FINAL_TEST_REPORT.md`. Full protocol tests need `g++`; release-signature tests also need `openssl`. Browser QA is optional development tooling (`npm ci`, Playwright/Chromium), not a Pi runtime dependency.
