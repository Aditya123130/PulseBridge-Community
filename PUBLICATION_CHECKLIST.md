# Publication approval checklist

- [ ] All original authors/rights holders have approved the specific public code and license.
- [ ] Confirm third-party source and dependencies are redistributable; preserve notices.
- [ ] Independently review every included file for credentials, private identifiers, and sensitive historical content.
- [ ] Choose and add an approved LICENSE file.
- [ ] Verify README commands on a clean Linux/WSL2 environment.
- [ ] Run full selected tests and inspect failures/skips; ensure native `g++` availability.
- [ ] Compile and test firmware on each claimed supported ESP32 board, or clearly mark unverified.
- [ ] Document exact hardware, supply, temperature, USB cable, baud, and timing boundaries for any physical benchmark.
- [ ] Confirm Git history contains no secrets (use a new empty repository).
- [ ] Review the complete staged Git diff and CI workflow before public push.
- [ ] Obtain final explicit approval before publishing.
