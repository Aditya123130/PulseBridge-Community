# Troubleshooting

| Symptom | Check / action |
|---|---|
| Firmware refuses compilation | Select the exact supported board profile in `firmware/PulseBridgeESP32/board_config.h` or use the repository's firmware configuration tooling. The default/invalid profile deliberately prevents target guessing. |
| USB device is missing | Use a data-capable USB cable, check the enumerated serial port, confirm Linux `dialout` membership, and close Arduino Serial Monitor or any other reader. |
| Permission denied on serial port | Run `bash setup_pi.sh`; if it adds you to `dialout`, log out and back in before retrying. |
| Port is busy | Close every other serial monitor, terminal, IDE monitor or PulseBridge process using the device. |
| Protocol handshake fails | Confirm the host and firmware are both using Protocol 3, start at the expected base settings, and verify the selected board/profile configuration. |
| CRC or framing errors increase | Check cable quality/connection stability and confirm both sides use the same profile. Preserve the error counts with benchmark results. |
| No physical data | Confirm the ESP32 is flashed with the canonical Community sketch and that the correct serial device is selected. Software simulation is not a substitute for a physical-hardware claim. |
| Software fixture works but hardware does not | Treat this as a hardware/serial-path problem: check firmware, port ownership, permissions, cable, power and board selection. |
| Test import fails | Activate the repository virtual environment and install `requirements.txt`. Confirm Python 3.10+ is being used. |
| Native C++ test fails to build | Install `g++` (or an equivalent supported C++ compiler) and rerun the test. |
| Benchmark results vary | Record host load, power/thermal state, request rate, profile, cable, sample count and raw errors. Repeat controlled runs rather than selecting a favorable result. |
| Timeout/reconnects occur | Inspect physical connection and workload rate. Protocol 3 intentionally performs bounded timeout/recovery and may re-handshake after repeated failures. |

## Useful checks

```bash
python3 --version
.venv/bin/python pi/app.py --list-ports
.venv/bin/python -m unittest discover -s tests -p 'test_community_smoke.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_protocol_v3.py' -v
bash check.sh
```

A successful local software test does not prove ESP32 USB timing, Raspberry Pi SD-card behavior, power quality or thermal health. For physical claims, complete `HARDWARE_VALIDATION_CHECKLIST.md`.
