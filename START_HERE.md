# Start here

PulseBridge Community is the focused public ESP32-to-Linux/Raspberry Pi edition of PulseBridge. Start with software verification before making physical-performance claims.

## 1. Install and test

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -p 'test_community_smoke.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_protocol_v3.py' -v
```

For more detail, see `INSTALLATION.md` and `QUICKSTART.md`.

## 2. Canonical firmware

Use:

```text
firmware/PulseBridgeESP32/PulseBridgeESP32.ino
```

Board configuration is explicit in:

```text
firmware/PulseBridgeESP32/board_config.h
```

Do not guess a board profile. Select the profile matching the target supported by the firmware configuration. The host validates the board profile reported by the Protocol 3 handshake.

## 3. Connect the hardware

Use a data-capable USB cable between the ESP32 and Raspberry Pi/Linux host. No UART jumper-wire connection is required for the intended USB-serial path.

On Linux/Raspberry Pi:

```bash
bash setup_pi.sh
.venv/bin/python pi/app.py --list-ports
```

If `setup_pi.sh` changes `dialout` membership, log out and back in.

Close Arduino Serial Monitor and other programs that may already own the serial port.

## 4. Understand Protocol 3

Read `PROTOCOL_SPEC.md` before changing transport settings or interpreting benchmark results. Protocol 3 uses CRC-16/CCITT-FALSE, explicit little-endian binary serialization, session nonces, request IDs, sequence validation and bounded recovery behavior.

## 5. Validate before benchmarking

Software/PTY simulation validates software behavior; it does not establish physical ESP32-to-Pi USB latency.

Before publishing physical results, complete `HARDWARE_VALIDATION_CHECKLIST.md` and follow `BENCHMARK_METHODOLOGY.md`.

## Scope

PulseBridge Community is educational/research software. It is not an exchange-grade HFT platform, does not claim trading profitability, and does not include the larger private V8 workstation's brokerage, autonomous deployment or hosted-AI subsystems.
