# PulseBridge V8 Community Edition - publication audit

Date: 5 November 2026

Source archive: `PulseBridge_V8_Autonomous_AI_Research_Workstation(20261105-071236).zip`

Source archive SHA-256: `eb2baa2220120ee4f564b147e1ed0ac96a1ffbdef98b8cef98739c03958e54c4`

## Scope

This public candidate is intentionally smaller than the full V8 workstation. It keeps the embedded Protocol 3 / ESP32 / Linux host research path and omits the V8 terminal AI, paper-trading, broker and autonomous-research services, rollback archives, generated datasets and research manuscripts.

The maintainer states that the software project was developed by the maintainer using OpenAI Codex as a coding assistant. Academic manuscripts and other materials with separate authorship are not included in this Community Edition.

## Source integrity

- Full V8 release manifest: PASS, 287 payload files.
- Full V8 archive contains 288 ZIP entries including the manifest/container structure used by the package.
- Source archive's recorded clean-extraction evidence: 190 Python tests passed on Python 3.12.14.
- Historical evidence is retained as evidence from the supplied release, not represented as independently rerun by this audit.

## Independent audit checks

- Python compileall: PASS.
- JSON parse: PASS, 41 JSON files in the full V8 extraction.
- JavaScript/CommonJS syntax: PASS, 9 files.
- Bash syntax: PASS, 5 files.
- Release smoke: PASS, seven checks, Python 3.13.5.
- Native firmware profile compilation: PASS for five explicit profiles; each completed a Protocol 3 synthetic handshake/request check.
- Preliminary credential/private-key scan: no private keys, OpenAI keys, GitHub tokens, AWS access IDs or bearer tokens detected. Six email-like matches were local/system fixture strings in archived documentation, not credentials; archived documentation is excluded from this public candidate.

## Independent test limitations

The audit sandbox could not fetch `pyserial==3.5`. Consequently several serial transport suites could not be fully rerun. Of the Python tests that executed through module-level runs, 131 passed and 7 produced failures/errors; five of those non-passes were directly caused by missing `pyserial` or serial receiver startup. Two research-worker tests remained `RUNNING` in this Python 3.13 sandbox after the child process exited, while the supplied Python 3.12.14 evidence records them as passing. This is treated as a portability/reproduction caveat, not silently converted into a pass.

Browser tests were also not independently rerun because Chromium access to `127.0.0.1` is blocked by this sandbox. The supplied release contains browser reports recording 18 retained workflow groups and 15 V8 workflow groups passing; those remain historical release evidence rather than fresh independent browser certification.

## Secret and privacy review

No obvious live secret was detected by the audit patterns. This is not a formal security certification. Before public release, the maintainer should still review Git history, screenshots, generated data, account identifiers and local configuration outside this candidate.

## Dependency/licensing note

This Community Edition declares `pyserial==3.5`, which is distributed under a BSD license. It is referenced as a dependency and not vendored into this repository. The repository itself is licensed under Apache-2.0.

## Publication conclusion

**Suitable as a GitHub review/release candidate for the focused embedded Community Edition, with explicit limitations.** Do not describe hosted AI, physical USB latency, Pi power/thermal health, live brokerage or trading profitability as independently validated features.
