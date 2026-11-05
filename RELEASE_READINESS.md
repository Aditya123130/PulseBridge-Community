# Release readiness

## Current decision: READY FOR PUBLIC GITHUB AS A LIMITED COMMUNITY EDITION

This decision applies only to the focused embedded/protocol Community Edition, not to the complete PulseBridge V8 Autonomous AI Research Workstation.

| Check | Result |
|---|---|
| Public scope excludes non-working hosted AI claims | PASS |
| Apache-2.0 license present | PASS |
| Preliminary secret/private-key scan | PASS with manual-review caveat |
| Python source syntax | PASS |
| JSON syntax | PASS |
| JavaScript/CommonJS syntax | PASS |
| Shell syntax | PASS |
| Full V8 release manifest | PASS - 287 files |
| Independent V8 release smoke | PASS - 7 checks |
| Native protocol profile builds | PASS - 5 profiles |
| Full 190-test independent rerun | PARTIAL - sandbox cannot fetch pyserial |
| Independent browser rerun | BLOCKED - localhost browser policy |
| Physical ESP32/Raspberry Pi qualification | NOT RUN |
| Hosted language-model provider | NOT RUN / not part of Community Edition |

Publishing this repository is reasonable if the README limitations remain intact. GitHub CI should be allowed to install `pyserial==3.5` and rerun the selected protocol/transport tests on Python 3.12.
