# PulseBridge V8 Community Edition

PulseBridge V8 Community Edition is a focused open-source research toolkit for ESP32-to-Linux USB-serial communication, Protocol 3 framing, CRC-16 validation, deterministic synthetic market-data movement generation, host-side rolling analysis, latency instrumentation, and reproducible protocol testing.

> **Scope:** educational and research software. It is not an exchange-grade HFT system, not a live trading product, and does not claim trading profitability.

## Why this Community Edition exists

The full PulseBridge V8 workstation contains broader research, paper-trading and optional hosted-AI workflows. This public edition deliberately focuses on the embedded USB/UART and protocol toolchain so that it can be installed, tested and understood independently. Hosted AI functionality is not advertised as a working feature here.

## Included

- `firmware/PulseBridgeESP32/` - Protocol 3 ESP32 firmware and explicit board-profile configuration
- `pi/` - Linux/Raspberry Pi protocol, transport, simulator, analysis and benchmarking code
- `tests/` - protocol, transport and native firmware test fixtures selected from V8
- `tools/` - configuration, preflight and benchmark utilities
- protocol, architecture, installation, benchmark and hardware-validation documentation

## Quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_community_smoke.py' -v
```

For physical hardware, read `INSTALLATION.md`, `docs/USB_SETUP.md`, `PROTOCOL_SPEC.md`, and `HARDWARE_VALIDATION_CHECKLIST.md` first. Configure the exact ESP32 target in `firmware/PulseBridgeESP32/board_config.h` before compiling.

## Release snapshot note

The published `v8.0.0-community` tag records the initial public release point, which predates the later upload of the complete Community Edition source tree and documentation-alignment commits. The tag is intentionally preserved rather than moved after publication. For the complete current Community Edition source, use the `main` branch. See `CHANGELOG.md` for details.

## Verification status

The source V8 archive's strict manifest verified successfully at **287 payload files**. Its bundled validation evidence records **190 Python tests passing on Python 3.12.14**, but that historical evidence is distinguished from the independent checks performed during this Community Edition audit.

Independent checks performed on 5 November 2026 include:

- all included Python source compiles successfully under Python 3.13.5;
- all JSON files in the full V8 source parse successfully;
- all JavaScript/CommonJS files in the full V8 source pass `node --check`;
- all shell scripts in the full V8 source pass `bash -n`;
- the full V8 release manifest verifies at 287 files;
- V8 release smoke flow passes seven software checks;
- all five native ESP32 firmware profiles compile with `g++ -Wall -Wextra -Werror` and complete a synthetic Protocol 3 handshake/request check;
- V8-specific Python tests pass (16 tests); several broader transport tests could not be fully reproduced in the audit sandbox because `pyserial` could not be downloaded there;
- browser automation could not be independently reproduced because the sandbox blocks Chromium access to localhost.

See `PUBLICATION_AUDIT.md` and `RELEASE_READINESS.md` for exact limitations.

## Hardware and AI claims

Physical ESP32 upload, real USB/Pi latency, power/thermal qualification, live broker integration and hosted language-model connectivity are **not independently validated by this Community Edition audit**. The bundled simulator is software evidence only.

## Development

The project is maintained by its developer with coding assistance from OpenAI Codex. AI assistance does not replace testing, review, licensing or release responsibility.

## License

Licensed under the Apache License, Version 2.0. See `LICENSE`.
