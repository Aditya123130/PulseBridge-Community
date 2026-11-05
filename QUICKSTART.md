# Quickstart

1. On Linux/WSL2/Raspberry Pi install Python 3.10+ and `g++` for native firmware tests.
2. Run `python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`.
3. Run ` .venv/bin/python -m unittest discover -s tests -p 'test_protocol_v3.py' -v`.
4. For physical hardware, select your exact ESP32 board profile in `firmware/PulseBridgeESP32/board_config.h`, compile/upload with the appropriate ESP32 Arduino core, and follow `docs/USB_SETUP.md`.
5. Before publishing latency numbers, follow `BENCHMARK_METHODOLOGY.md` and `HARDWARE_VALIDATION_CHECKLIST.md`.

Software simulation via Linux PTY is not a measurement of physical ESP32 USB latency.
