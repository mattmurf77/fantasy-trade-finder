# MOD-M1 evaluation-tool release preflight

Date: 2026-11-04. Prepared on main `065a1ee6` with exact original #475 head `5c5127307475d2b92a659d06151d659e679b4c05` and stacked #476 head `0f40d087c9e8d9ea0cf5b4f55c91bb38720ed101`, retained as merge ancestors. This is tooling preparation, not the November 10 frozen-candidate evaluation or a model launch verdict.

## Scope and integration

#475 replaces the old direct-generator replay with the real first-deck routes and worker, captures effective config/provenance, and applies the D-055 insult rule to every first-five card. #476 builds the private sixty-card blind audit sheet and scores the operator's marks. No runtime routes, user-facing feature, analytics emitter, schema, source flag, knob, engine or client behavior changes. HLD/LLD/API/data-dictionary changes are inapplicable; scripts/module indexes and this reference document cover the tool contract.

Current main introduced a genuine auth prerequisite: a verified session's users row exists before session init. The old evaluator inserted only an in-memory verified token, so first-init's live-user guard stopped its league-connection daemon and the synthetic SF/TEP case was reported as 1QB. The evaluator and the independent live-flow test now persist that scratch user first, as real `_extension_build_session` does. The production deletion/first-init guard is untouched.

The current page response exposes a served count after disposition/dedup/page-window handling. `deck_size` now uses the actual client's `total_ready`; `generated_deck_size` separately records the stored inventory length. The acceptance test still compares every first-page card to the plain live worker flow, and filter-off proves the generated inventory grows and the page changes.

## Privacy and isolation

- Fresh CLI process, newly created scratch SQLite before backend import, every backend engine resolves to the exact same canonical file. A similarly prefixed filename is rejected; the normal same-file read-only SQLite URI is accepted. No production database or copy is used.
- Remove inherited Anthropic key and Sentry DSN before backend import. Eval errors/league identifiers cannot leave through an inherited production crash-report integration. Public Sleeper GETs remain the only supported real-run network data source; this preflight uses mocked synthetic responses and refuses network connections.
- JSON, markdown report, blind sheet, instructions and private key use exclusive creation, mode0600, in private mode0700 output directories. Tracked in-repo report paths are refused. Existing broad-permission directories are refused without chmod, avoiding accidental permissions changes to operator directories such as `/tmp`.
- The real owned-pick formatter can produce `2027 2nd (from Jared)`. The blind sheet removes only the identifying `(from …)` suffix on PICK assets, preserving year/round/slot/value and the private source run; a regression uses the actual application formatter, including a nested name.
- Default outputs are gitignored `feedback-workspace/deck-eval/`. No real roster, private board, production data, receipt or token was exported or committed. Test artifacts are synthetic.

## Required schedule and remaining evidence

November10 is the planned real run; November11 is the blind sheet delivery, November13 scoring return, November14 model verdict and November17 launch go/no-go. The existing plan authorizes connected Sleeper leagues only, stratified 1QB/SF × TEP on/off ×10/12/14 teams, ideally three leagues per cell. Missing cells are reported, not silently filled from unconnected leagues. A broader public-league sample needs separate operator authorization.

Before the real run, freeze the launch-candidate code and capture the exact live flags/model_config in the approved read-only M3 process. Use `--overrides` with that local private artifact; `--no-overrides` is explicitly not a gate run. Record code SHA, config SHA, RNG seed/PYTHONHASHSEED, ISO week, sample coverage, unpriced assets and latency. Any engine-affecting merge before the November17 verdict requires a rerun. Tool-only changes do not establish that this freeze has happened.

The automated bars remain strict: empty decks <5% of evaluated seats, insult cards <3% of all first-five cards. Errors count as empty; unpriced assets and missing cells must remain visible. The operator's blind audit remains separate: at least three Y cards that the rule passed yields HOLD, not a silently altered numerical threshold.

D-207's B-DK-4..7 zero-violation checks are also required alongside MOD-M1. The existing `backend/eval/bdk_audit.py` is already on main and its synthetic/offline suite is included here. **`deck_eval` does not itself emit those four audit verdicts.** Arrange their evidence against the same frozen first-deck inputs during the actual gate; do not treat the insult-rate report alone as a complete launch quality verdict. This preflight performs no production audit or DB copy.

No additional optional eval PR is required for these two tools: #466 is explicitly a non-gating miss-map cross-check, #458 is non-gating EvalRun bookkeeping for the separate replay/nightly path, and draft #383's 2% owner benchmark readers are a different writer/sampling change. Those are not imported into this narrow batch. Existing `blind_grade`/bakeoff/flip-read tools support their own monitoring and attribution tasks; they do not replace #476's first-deck rule audit. No model graduation or parameter promotion is performed here.

## Evidence

Initial combined original heads:38 passed/1 failed; the failure was the missing minted-user prerequisite. After the mint correction, the first-page card-for-card match passes but the old raw-count comparison exposed the served/generated distinction; that distinction is now explicit. Final focused counts and independent QA are recorded in TEST_LEDGER. Named negative controls remove private-directory enforcement, report file0600, tracked-report rejection and inherited-Sentry removal; each new regression fails independently and source is restored. No full local suite, real connected-league run, paid provider, production data copy or release activation occurred. Exact-head GitHub CI and independent QA remain merge gates for the integration PR.
