# Installation

PulseBridge Community targets Linux, WSL2, and Raspberry Pi OS/Linux with Python 3.10+. Physical serial use requires pySerial 3.5 from `requirements.txt`. Native protocol checks also require a C++ compiler such as `g++`.

## Standard setup

```bash
git clone https://github.com/Aditya123130/PulseBridge-Community.git
cd PulseBridge-Community
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Run the Community smoke test:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_community_smoke.py' -v
```

Run the Protocol 3 test module:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_protocol_v3.py' -v
```

For the repository's broader local verification, run:

```bash
bash check.sh
```

## Raspberry Pi helper

`setup_pi.sh` creates `.venv` when needed, installs `requirements.txt`, checks `dialout` membership and lists serial ports:

```bash
bash setup_pi.sh
```

If the script adds your user to `dialout`, log out and back in before retrying serial access.

## Physical ESP32 setup

The canonical firmware is:

```text
firmware/PulseBridgeESP32/PulseBridgeESP32.ino
```

Select the exact supported board profile in `firmware/PulseBridgeESP32/board_config.h`; do not guess a target. Compile/upload using an appropriate ESP32 Arduino environment, then follow `START_HERE.md` and `docs/USB_SETUP.md`.

A data-capable USB cable is required. Close Arduino Serial Monitor or any other process that already owns the serial port before running PulseBridge.

## Software-only validation

You can inspect the host software and run tests without claiming physical hardware performance. The included simulator/PTY paths exercise software and protocol behavior; they do **not** establish ESP32-to-Pi USB latency.

Useful tools under `tools/` include environment inspection, preflight checks, software benchmarks, queue benchmarks, transport runs, core-isolation helpers and firmware configuration.

## Scope

This repository is the focused Community Edition. It does not require or include the private V8 workstation server, brokerage runtime, hosted AI provider, autonomous deployment system, or its browser QA stack.

Before publishing physical benchmark numbers, follow `BENCHMARK_METHODOLOGY.md` and `HARDWARE_VALIDATION_CHECKLIST.md`.
