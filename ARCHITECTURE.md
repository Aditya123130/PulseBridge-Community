# V8 architecture

Browser → HTTP/SSE server → separate engine process → PaperBroker/risk → bounded asynchronous SQLite writer. A separate receiver owns Protocol 3 USB acquisition. Heavy research runs in one resource-limited subprocess; hosted AI runs through bounded server-side HTTP requests. The browser never receives provider keys.

`terminal/server.py` owns routing, authentication/origin checks, session-bound commands and SSE. `runtime.py` owns feed/series processing, account lifecycle, persistence and paper deployment commands. `broker.py` owns monetary accounting, order/fill rules and independent risk. `research_service.py` owns validated research actions, job controls, policy scheduling, provider settings and cache invalidation.

`autonomy.py` separates ResearchPlanner, ExperimentScheduler, CandidateEvaluator and StrategyRegistry. `deployment.py` handles paper activation, monitoring and rollback under current policy and risk. `lab.py`, `strategies.py`, `analytics.py` and `regimes.py` own calculations and bounded configurations; no eval or generated production-code execution is used. `ai.py`, `ai_stream.py`, `agent.py` and `offline_analysis.py` separate provider transport, audited application tools and explicitly computed offline explanations.

Schema 9 adds exact account checkpoints, workstation settings, candidate versions and deployment records. Existing sessions, order/fill/audit tables, research records, feature cache, checkpoints and holdout-observation registry are retained. Research and ledger records share SQLite WAL/FULL. Cached summaries bound dashboard transfer size; feature caches retain four datasets; records have archive/body-size limits. Backup and retention planning still belong to the operator.

The frontend retains 14 views and existing chart/indicator code. `v8-ui.js` connects demo/import, policy/registry/deployment, saved strategies, report comparison and provider streaming. `v8.css` adds a compact dark shell and responsive panels. Stable DOM patches avoid rebuilding unchanged tables. Canvas dimensions are reset only when needed. SSE display deltas carry changed fields/bar tails and resynchronize fully on reconnect or account/instrument changes. These deltas do not transport execution/audit commands.

Canonical ESP32 firmware is unchanged: version 7.1.0, Protocol 3. Pi↔ESP32 communication uses its USB connector and onboard bridge/native supported path. Physical latency, SD behavior and the Pi 3 B+ resource envelope remain pending target validation.
