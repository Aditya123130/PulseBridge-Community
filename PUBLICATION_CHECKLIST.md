# Publication and maintenance checklist

PulseBridge Community is already public. This checklist now distinguishes completed publication work from validation that remains ongoing.

## Completed for the Community Edition

- [x] Apache License 2.0 is present.
- [x] Public scope is separated from the larger private V8 workstation.
- [x] Public source includes the Community firmware, Linux/Raspberry Pi host code, tests and tooling.
- [x] Preliminary credential/private-key review reported no obvious bundled secret.
- [x] GitHub Actions performs Community verification.
- [x] README states that hosted AI, live brokerage and exchange-grade HFT are not validated Community Edition features.
- [x] Physical hardware claims are separated from software/PTY validation.

## Ongoing release hygiene

- [ ] Re-run Community CI for meaningful source/documentation changes.
- [ ] Review dependency and third-party licensing when dependencies change.
- [ ] Review staged/public changes for credentials and private identifiers before each release.
- [ ] Keep installation, architecture and benchmark documentation synchronized with the files actually shipped.
- [ ] Preserve exact commit/tag information for published benchmark evidence.

## Physical validation still required for physical-performance claims

- [ ] Compile/upload on each specifically claimed ESP32 target.
- [ ] Record Raspberry Pi/Linux host and OS details.
- [ ] Record USB cable/connection path.
- [ ] Record power/undervoltage and thermal/throttling state where available.
- [ ] Record Protocol 3 profile, baud/encoding, workload, sample count and timing boundary.
- [ ] Preserve raw output and error/reconnect counters.
- [ ] Prefer independent reproduction before making strong performance claims.

Publication of source code does not itself complete physical qualification.
