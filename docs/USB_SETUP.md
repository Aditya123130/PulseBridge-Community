# USB setup

Use [START_HERE](../START_HERE.md) for the canonical Protocol 3 sketch, installation sequence and explicit board-profile guidance.

The intended Community Edition hardware path is ESP32 ↔ Raspberry Pi/Linux over a **data-capable USB cable**; no UART jumper-wire connection is required for that path.

Before testing:

1. Flash `firmware/PulseBridgeESP32/PulseBridgeESP32.ino` with the correct explicit board profile.
2. Connect the ESP32 with a data-capable USB cable.
3. Close Arduino Serial Monitor and any other process using the serial port.
4. On Linux/Raspberry Pi, confirm serial permissions and list ports with `.venv/bin/python pi/app.py --list-ports`.
5. Record the exact board, host, cable, profile and power/thermal state for physical validation.

Follow [Hardware validation](../HARDWARE_VALIDATION_CHECKLIST.md) before publishing physical latency claims. Until that checklist is completed for a run, software/PTY results must remain clearly labeled as non-physical validation.
