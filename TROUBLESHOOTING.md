# Troubleshooting

| Symptom | Check / action |
|---|---|
| Firmware refuses compilation | Set the verified explicit board profile using `tools/configure_firmware.py`; profile 0 deliberately refuses a target guess. For the stated classic CP2102 ESP32 use profile 1. |
| USB device missing | Use a data-capable USB cable, check enumerated ports/dialout membership, close Arduino Serial Monitor and other readers, then run the matching Protocol 3 probe. |
| No live hardware data | Hardware mode does not silently generate prices when the device is absent. Use demo or protocol-sim explicitly for a software demonstration. |
| Restored account refuses orders | Review restored holdings and resume in Risk Management. Wait for a fresh quote; deployments need their own explicit resume. |
| Accepted order stays open | Inspect its type/trigger, quote freshness, configured delay, modeled liquidity, risk rejection note and whether the finite demo has ended. |
| CSV preview fails | Verify six distinct mapped columns, timestamp unit/timezone, strict ordering, OHLC consistency, positive prices and source provenance. Invalid imports never substitute a demo. |
| Research rejects final holdout | Those observations were already used by another recorded experiment. New labels/formatting do not create independent observations; use genuinely new data. |
| Research accepted but no deployment | Check enabled/unpaused promotion policy, whitelist, synthetic mode, symbol, interval, costs, sizing and independent account risk. Inspect the promotion audit/report. |
| Resume refuses a checkpoint | Restore its original research policy/budgets. Exhausted time/evaluation limits are not reset by resume. |
| AI configured but not verified | Run Settings → Test provider connection. Check server key, exact model ID/URL, token-limit field, quota and provider compatibility. No browser key field exists. |
| Chat requests too fast | Wait two seconds; provider failures and incomplete streams are visible and not added to completed history. |
| Dashboard delayed | Check Performance Lab queue/drop counters, API/display/commit timing separately. Reduce `--ui-hz` to 2 or 1, inspect actual storage and CPU, and record a comparable profile before drawing conclusions. |
| Data-directory lock failure | Stop its existing server or use a different `--data-dir`. Do not delete a lock to run two writers on one account. |

Use clean shutdown and backup before upgrades. Unexpected storage failure must be investigated rather than bypassed. A successful local software test does not prove USB cable, SD-card, power supply or thermal health.
