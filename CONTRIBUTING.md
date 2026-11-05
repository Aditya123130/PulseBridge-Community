# Contributing

Thank you for helping improve PulseBridge Community Edition.

Contributions are welcome for reproducible protocol, ESP32 firmware, Linux/Raspberry Pi host, simulator, benchmarking, testing and documentation improvements.

## Before you start

- Search existing issues and pull requests before opening a duplicate.
- Keep Community Edition changes focused on the public source tree.
- Keep synthetic/software results clearly separated from physical hardware claims.
- Do not add live-order execution, brokerage credentials, private datasets or private-workstation components.
- Never commit API keys, tokens, account identifiers or other secrets.

For substantial behavior or protocol changes, open an issue first so the scope and validation plan can be discussed.

## Development setup

Follow `INSTALLATION.md` and `START_HERE.md` for environment setup.

Before submitting a pull request, run the public verification suite:

```bash
python -m compileall -q pi tools tests
python -m unittest discover -s tests -p 'test_*.py' -v
```

If your change affects native protocol helpers or other checks documented by the repository, run those checks as well.

## Pull requests

A useful pull request should:

1. explain the problem and the proposed change;
2. stay focused on one coherent improvement;
3. add or update tests when behavior changes;
4. document any user-visible change;
5. report the exact validation performed;
6. avoid unsupported performance, hardware or trading claims.

Do not split one small change into several pull requests merely to create activity.

## Reproducibility and benchmark contributions

When reporting a reproduction or benchmark, include enough context for another person to understand the result:

- hardware and board model;
- operating system and version;
- Python version;
- connection type and baud/profile;
- exact command used;
- run duration/sample count where applicable;
- relevant output or logs;
- whether the result is software-only, simulated, or physical hardware.

A failed reproduction is also useful when the environment and failure are documented clearly.

## Hardware claims

Physical ESP32/Raspberry Pi results must come from an actual hardware run. Photos, terminal logs or other evidence are encouraged when they help establish the setup. Do not relabel simulator or PTY results as physical measurements.

## Security

For vulnerabilities or sensitive security concerns, follow `SECURITY.md` rather than posting secrets in a public issue.

## License

By submitting a contribution, you agree that your contribution may be distributed under the repository's Apache-2.0 license.
