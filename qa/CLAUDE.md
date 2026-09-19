# qa/ — Notes for Claude

**Backend/full-stack QA lives here.** Charter, the four current QA lanes, triage levels,
and the results index: [`README.md`](README.md).

> **Read this before writing any QA plan.** Operator decision **D-056** (2026-08-15,
> Active) retired Maestro and the simulator **entirely** — no flow authoring, no
> execution, no screen captures, in any pipeline. Client-side automated evidence is now
> `mobile/tests/check-*.js` + unit tests; behavior that used to get a sim capture gets a
> written file:line code-walk proof; runtime proof is a manual TestFlight checklist for
> the operator. `testid-lint` stays in CI. **Never generate `qa/sim-runs/last-sim-run.json`**
> — the standing pre-push posture is `FTF_SKIP_SIM_GATE=1`.

## What's tracked here (real code/docs, not scratch)

| Path | Contents |
|---|---|
| `lib/harness.py` | Shared harness — copies `data/trade_finder.db` to a scratch DB, boots a local Flask on it, talks HTTP. **The live DB is never written.** |
| `web/check_web_structure.py` | **Web structural gate** (2026-08-19). Parses shipped `web/` source and asserts design-system, SEO and a11y invariants. Pure stdlib — no browser, no server, no deps. Runs as the `web-structure` CI job. This is the *only* automated coverage `web/` has. |
| `api/`, `db/`, `e2e/`, `eng/`, `perf/`, `sec/` | `tc_*.py` executable test cases; run directly (`python qa/sec/tc_sec_001.py`), each exits non-zero on failure and drops a run JSON in its scratch dir |
| `results/` | 17 `TC-*.md` write-ups — the durable record of each executed case |
| `TEST_CASE_TEMPLATE.md` | Template every new case starts from |
| `accessibility-release-checklist.md` | Per-release mobile a11y regression pass |
| `teardown-remediation-qa.md`, `tiktok-discovery-qa.md` | One-off audit trackers |
| `push_lakeview_to_prod.py`, `seed_test_dispositions.py`, `verify-mfl-send.py` | Prod-support / verification scripts |

## What's gitignored here

- `sim-runs/` — **historical.** Per-machine simulator-gate evidence; last run 2026-08-15 (`sha 44c8bbf`, tier 2, result `fail`). The gate it fed is retired per D-056. Read it as a record, never as an instruction to produce another.
- `**/scratch*/` — throwaway harness DBs, server logs, run JSON. Never commit a DB copy.
- `lib/__pycache__/`.

The root `CLAUDE.md` still lists the sim gate as a required pre-ship artifact (feature-gate
item 4). **That text is stale** — D-056 supersedes it.

## Rules

- Never write to `data/trade_finder.db`. Read-only queries for data-quality audits are fine.
- Pin feature flags and `model_config` explicitly in every case — engine behavior is flag-routed.
- Executed cases go in [`living-memory/TEST_LEDGER.md`](../living-memory/TEST_LEDGER.md); reusable automated cases graduate into `backend/tests/` (which is what CI runs).
- Doc drift (code vs `docs/api-reference.md` / `data-dictionary.md` / `config-reference.md`) is a P2 finding, not a shrug.
