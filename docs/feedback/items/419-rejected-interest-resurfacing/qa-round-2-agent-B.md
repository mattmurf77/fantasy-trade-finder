# Feedback 419–421 / smaller-player packages — independent QA round 2, Agent B

2026-09-06. **PASS for the approved bounded implementation at `7d3e071f92bac3a087ba63da393109b5eae02f68`.** No unresolved application defect found. Round-1 F-1 is repaired, including renewed-consent/companion/refinement controls. One minor documentation whitespace observation, D-1 below, is not a runtime finding. This is local source/test QA, not a deployment, activation, Apple-availability or physical-device verdict.

## Identity, independence and method

- Tested detached checkout: `/private/tmp/ftf-feedback-419-421-f1uMyt/qa-round2-b`; exact HEAD above, runtime repair merge `3edf42572e710d212430623f7c6e6b175c2948a8`. Review comparison: `4026ebc81eaae50b345b42421641125c5b8d413e..7d3e071f92bac3a087ba63da393109b5eae02f68`.
- Clean checkout verified before tests and again after all execution, before adding this report. Independent pre-provisioned `mobile/node_modules` is not a symlink. No source/test/guard/config edits, assertion weakening, dependency replacement or production/provider actions. Only this report is authored in the checkout.
- I independently reviewed the complete runtime and test diff, not only the F-1 repair: database chronology/readers/reason writes; server queue/bind/restore/publication/cache/F1 paths; the pure presentation helper and default registries; native transport/auth/session coordinator and all affected screens; both new native suites and every changed backend/mobile test. App metadata changes are the aligned `1.17.1` version bump, not evidence of a built binary.
- Read the applicable root, backend, backend/tests, mobile, mobile/src, API/state/utils/screens, docs/plans/design and QA `CLAUDE.md` instructions; `docs/coding-guidelines.md`; feedback skill, lessons and QA reference; mobile test README; design system/components. The feedback skill requires the explicit contract matrix, real-path evidence, preserved failed-run history and unrun physical checklist recorded here.
- Read all three complete approved `prd.md`, `scope.md`, `reconciliation-log.md` sets, all current build evidence/code walks (including 419 backend/mobile-specific files), `qa-resolution.md`, and the historical round-1 finding evidence. Historical reports were contextual adjudication material, not a substitute for this fresh review or my own test results. I did not inspect or coordinate conclusions with the other round-2 reviewer.
- Source citations below refer to this tested HEAD. Some author documents contain earlier-build line numbers; the current citations below are independently resolved. No claim is made that every prospective sabotage in a PRD was executed.

## Independently executed gates

| Gate | Actual result |
|---|---|
| Entire backend, fresh file-backed SQLite, normal full-suite provider/default posture | **5,645 passed, 1 skipped in 710.20 s**, exit 0 |
| Approved 33-file integrated focused matrix, fixed player and pick fixtures before import | **892 passed in 58.37 s**, exit 0 |
| Separate episode-only route regression | **23 passed, 81 deselected in 2.92 s**, exit 0 |
| Original external round-1 QA-A reason-episode repro, unchanged | Exit 0; actual B module paths, new current pass, resolved renewed source, one outcome and stable retry |
| Every `mobile/tests/check-*.js`, sorted, each in its own Node process, every exit code checked | **95 suites passed, 0 failed** |
| Current disposition/recovery suites rerun after unchanged-baseline RED | **28/28** disposition; **38/38** Win Now recovery; exit 0 |
| `npx tsc --noEmit` in `mobile` | Exit 0 |
| `bash scripts/testid-lint.sh` in `mobile` | Exit 0, `testid-lint OK` |
| `python qa/web/check_web_structure.py` | **190/190**, exit 0 (DS 95, TOK 1, SEO 50, A11Y 38, HYG 6) |
| 5,000-row history/20-card serving diagnostic, actual helpers, isolated SQLite | **1 passed in 2.04 s**; history 1 SELECT / 74.15 ms; serving 1 history SELECT / 144.36 ms |
| Runtime/mobile comparison hygiene | `git diff --check BASE..HEAD -- backend mobile`: exit 0 |
| Entire comparison hygiene | One documentation-only new blank line at EOF, D-1; do not describe this full-range check as green at the tested HEAD |

Versions: Python **3.12.14**, pytest **9.1.1**, Node **v24.14.1**, npm **11.11.0**, TypeScript **5.9.3**. Full regression used a verified initially absent `/private/tmp/ftf-feedback-419-421-f1uMyt/qa-round2-b-full.sqlite`, retained after testing. `FTF_DP_VALUES_FILE` was verified unset for that full command; no global fixture/default or `conftest.py` change was made. The single actual skip is `backend/tests/test_outlook_odds.py:610`: optional offline backtest requiring `FTF_OUTLOOK_BACKTEST=/path/to/captured_2025.json`.

The full run had a long quiet CPU-active interval, then completed. Initial sandbox `ps` inspection was denied; a narrowly escalated read-only process inspection succeeded. It did not restart or alter tests. Non-fatal isolated receipt-worker diagnostics reported absent `receipts_grade_runs`, `deck_impressions` and `user_events` tables; these were not pytest failures and were not used to excuse any failing assertion. The original repro separately emitted a non-fatal global observability missing-`user_events` warning. Neither warning is proof of the unrelated observability sink. The historical in-memory SingletonThreadPool schema-loss run is preserved in round-1 records; this new unchanged file-backed run had no such pytest failures/errors.

### Reproducible commands

All commands below run from the tested checkout unless a `mobile` working directory is stated. Full regression, foreground session 99631:

```sh
test ! -e /private/tmp/ftf-feedback-419-421-f1uMyt/qa-round2-b-full.sqlite
test ! -L mobile/node_modules
test -z "${FTF_DP_VALUES_FILE-}"
DATABASE_URL=sqlite:////private/tmp/ftf-feedback-419-421-f1uMyt/qa-round2-b-full.sqlite \
PYTHONDONTWRITEBYTECODE=1 /private/tmp/ftf-context-venv/bin/python -m pytest \
  backend/tests -q -p no:cacheprovider --tb=short -ra
```

Focused matrix, foreground session 38587:

```sh
DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 \
FTF_DP_VALUES_FILE=backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv \
FTF_DP_PICK_VALUES_FILE=backend/tests/fixtures/dp_values_picks_2026-08-06.csv \
/private/tmp/ftf-context-venv/bin/python -m pytest -q -p no:cacheprovider --tb=short -ra \
  backend/tests/test_small_trade_presentment.py \
  backend/tests/test_trade_interest_disposition.py backend/tests/test_trade_disposition_replay.py \
  backend/tests/test_trade_disposition_restoration.py backend/tests/test_decline_reasons.py \
  backend/tests/test_trade_match_flow.py backend/tests/test_pass_cooldown.py \
  backend/tests/test_awaiting_dismiss.py backend/tests/test_deck_fatigue.py \
  backend/tests/test_trade_decision_idempotency.py backend/tests/test_swipe_reconstruct.py \
  backend/tests/test_bakeoff_serving.py backend/tests/test_calc_trade_queue.py \
  backend/tests/test_deck_replenishment.py backend/tests/test_standing_offers.py \
  backend/tests/test_trade_job_read_amplification.py backend/tests/test_scoring_execution_context.py \
  backend/tests/test_deck_first_session.py backend/tests/test_force_supersedes_running_job.py \
  backend/tests/test_trade_policy.py backend/tests/test_trade_policy_wiring.py \
  backend/tests/test_trade_roster.py backend/tests/test_trade_roster_wiring.py \
  backend/tests/test_bakeoff_arm_a_golden.py backend/tests/test_bakeoff_runner.py \
  backend/tests/test_bakeoff_composition.py backend/tests/test_bakeoff_challenger.py \
  backend/tests/test_engine_quality_golden.py backend/tests/test_session_init_sleeper_calls.py \
  backend/tests/test_verified_sessions.py backend/tests/test_persistent_sessions.py \
  backend/tests/test_win_now_api.py backend/tests/test_win_now_service.py
```

With the same four environment settings as the focused command, separately executed:

```sh
/private/tmp/ftf-context-venv/bin/python -m pytest backend/tests/test_decline_reasons.py \
  -k reason_episode -q -p no:cacheprovider --tb=short -ra
/private/tmp/ftf-context-venv/bin/python -m pytest \
  backend/tests/test_trade_interest_disposition.py::test_batched_5000_row_history_measurement \
  -q -s -p no:cacheprovider --tb=short
PYTHONPATH=. /private/tmp/ftf-context-venv/bin/python \
  /private/tmp/ftf-feedback-419-421-f1uMyt/qa-a-reason-episode-repro.py
```

The original script was read completely before running it. It prints `backend.database.__file__` and `backend.server.__file__`; both resolved under `qa-round2-b/backend/`, not the baseline or another agent's checkout. The last command above also inherited the same fixture variables and `DATABASE_URL=sqlite:///:memory:` explicitly in its actual invocation.

Native all-suite driver, foreground session 15238 (separate process per suite; any nonzero/null status fails the driver):

```sh
node -e 'const fs=require("fs"), cp=require("child_process"); const files=fs.readdirSync("mobile/tests").filter(x=>/^check-.*\.js$/.test(x)).sort(); let fail=0; for(const f of files){ const r=cp.spawnSync(process.execPath,["mobile/tests/"+f],{encoding:"utf8"}); console.log(f+" exit="+r.status+" "+(r.stdout.trim().split("\n").slice(-1)[0]||"")); if(r.status!==0){fail++; console.log(r.stdout,r.stderr,r.error||"");}} console.log(JSON.stringify({suites:files.length,passed:files.length-fail,failed:fail})); process.exitCode=fail?1:0;'
```

Additional commands: `npx tsc --noEmit` and `bash scripts/testid-lint.sh` from `mobile`; `PYTHONDONTWRITEBYTECODE=1 /private/tmp/ftf-context-venv/bin/python qa/web/check_web_structure.py` from root; `node mobile/tests/check-trade-disposition.js && node mobile/tests/check-win-now-recovery.js` after RED. All long tests were foreground execution sessions, polled with bounded waits; none remain running at handoff.

## Meaningful RED versus GREEN: provenance and limits

I did **not** perform or retry the previously denied source-disabling sabotage. Safe unchanged-baseline alternatives were used without editing runtime:

1. `FTF_TRADE_DISPOSITION_BASELINE=4026ebc8 node mobile/tests/check-trade-disposition.js` reads actual baseline files with `git show`. Actual result: **0 passed, 4 behavioral failures**, exit 1. The baseline collapses a bank response to boolean rather than preserving `passed:false`, lacks actual edited-package echo, does not expose verified true separately from transport failure, and retains the committed package in the extracted real lane projection. These are not missing-module/import failures.
2. Before Win Now RED, verified all seven runtime inputs in `/private/tmp/ftf-feedback-419-421-f1uMyt/419-provenance-baseline/mobile` byte-equal to `4026ebc8`: `src/api/client.ts`, `src/api/auth.ts`, `src/api/winNow.ts`, `src/api/espn.ts`, `src/api/platformLink.ts`, `src/state/useSession.ts`, `src/screens/WinNowScreen.tsx`. Then `FTF_MOBILE_TEST_ROOT=/private/tmp/ftf-feedback-419-421-f1uMyt/419-provenance-baseline/mobile FTF_BASELINE_ONLY=1 node mobile/tests/check-win-now-recovery.js` produced **0 passed, 7 behavioral failures**, exit 1: measured 15.2-second response timeout; stale verification publication; old hosting-diagnosis text; absent real mounted-screen repair; pending revalidation early-return; same-token B dispatch before A ACK; automatic foreground init after ambiguity. The baseline-only branch executes existing APIs rather than failing on a new missing export.
3. Current-source GREEN then returned **28/28** and **38/38**. The 95-suite run was also against current source. AST/source checks in those files remain honestly distinguished from execution of actual transpiled modules, screen handlers and extracted callbacks; neither is physical React Native evidence.

Historical backend RED is **reviewed/attributed**, not newly rerun here: 419's build evidence records incident/read/bind/cache/restoration failures and the F-1 repair's four failures plus the later known-other-impression failure; package build evidence records actual baseline worker/cache/provenance failures and the raw-receive exclusion's two pre-repair failures. Builder fixture/import mistakes are not valid RED and are explicitly identified as such in those documents. This round does not claim separate mutation runs for every lock, comparator, cache branch, retry limit, publication fence or telemetry field. The new green negative controls and full source review complement, not replace, that limit.

## Full requirement and test matrix — 419

| Requirement | Current implementation and independent negative-branch review | Executed evidence |
|---|---|---|
| R1: exact source evidence, no history rewrite | `backend/database.py:5890` normalizes UTC/legacy-naive timestamps; `:5900` builds ordered history with numeric row-ID tie breaking, later own/mirrored-pass barriers and withdrawal barriers. Actionability is independent of discovery amnesty/expiry. Malformed relevant chronology cannot affirm interest; changed actor/league/oriented sets remain distinct. A receiver's re-like cannot revive the older source; a genuinely newer source can be actionable. | `test_trade_interest_disposition.py:49`, `:68`, `:79`, `:95`, `:107`, `:130`, `:165`; real injector with absent/existing organic card and unchanged row snapshots. |
| R2: consistent readers and narrow deliberate queue renewal | `database.py:6017` batches selected history; `:6067` keeps 90-day like semantics, `:6092` retains queue's windowless lookup, `:9093` admits exact/fuzzy candidates before unchanged match math, `:9478` retains Awaiting cap and conservative roster-owner resolution. `save_trade_decision :5736` validates server-derived queue renewal evidence; queue supplies actual counterpart, not client bypass authority. | Real queue/pass/queue at 0/1/2 seconds for either actor in `test_calc_trade_queue.py:418`; real Awaiting/R4 in `test_trade_interest_disposition.py:114`, `:140`, `:154`; matching/withdrawal/idempotency/summary suites in focused/full runs. 5,000-row diagnostic and `:214` query-count guard. |
| R3: verified reason pass; live/serialized/restored state | `database.py:6756` locks the existing reason row, checks account/league/card identity, anchors `created_at`, and commits before returning true. `server.py:15136` passes actual counterpart; `:15142` binds only verified pass, `:15148` gates new outcome/event, `:15175` separates durable Elo claim. `_bind_live_trade_pass :14954` covers all formats plus legacy alias and rejects old-league binding. `_trade_job_public_view :2997` and projection `:3033` use captured owner/league outside global lock; restore `:3096` is shared by interactive/headless builders. | `test_decline_reasons.py:393`–`:653`, original external repro, all 23 episode cases; `test_trade_disposition_replay.py:52` onward real routes and worker; `test_trade_disposition_restoration.py:31`; full idempotency, reconstruction and replenishment suites. |
| R4: locally observed native passes, reversible failure and stable cursor | `mobile/src/utils/tradeDisposition.ts:11` exact account/league/counterpart/oriented-set key; `:31` sticky verified reason/acknowledged swipe settlement; `:52` held-reason-aware source projection; `:72` source coordinate conversion. `TradesScreen.tsx:293` shared scope/epoch bus, `:328` commitment, `:337` strict `passed===true`; actual acted/edited context capture `:1964`, reason target `:5849`; current render `:4037`, held transition `:5868`, browse splice/restore `:6104`/`:6157`. Old callbacks and newer same-ID actions are fenced. | Native 28 checks: adapter `check-trade-disposition.js:64`, exact identity `:102`, stale/new-ID/edited/cursor `:114`–`:141`, bus `:234`, settlement/error callbacks `:245`–`:312`, actual browse methods `:201`/`:211`, wiring/Undo `:321` onward. Existing decline/browse/deck/Undo suites also green. |

| PRD test | Concrete pass/negative coverage and limits |
|---|---|
| T1 incident | Real injector cannot synthesize/boost the August source after the August pass although discovery has no current key; independent organic same-package card remains unbadged and score unchanged (`test_trade_interest_disposition.py:49`). |
| T2 precedence | Both actors/orientations, equal timestamp/ID ordering, offsets and legacy naive UTC, malformed barriers, cutoff normalization, withdrawal/no older fallback, reordered/changed package and foreign actor/league controls (`:68`–`:165`; episode same-time controls `test_decline_reasons.py:592`). Reads preserve history. |
| T3 readers | Exact/fuzzy candidate admission, conservative known-owner Awaiting, mixed-pick anchor/contradiction controls, R4/summary, unchanged candidate bounds and ordinary dedupe. Real renewed queue adds exactly one new like/signal/event then remains idempotent. No queue-time match or restored fairness refusal. |
| T4 pass/reason repair | Bank without context gives `passed:false`; failed decision commit does not consume Elo/outcome; valid echoed edited repair after memory loss writes once; false/missing evidence cannot bind. All live formats/alias and late-other-league exclusion checked. Layer-2-first/taxonomy fields, both companion orders, delayed linked companion, Elo failure rollback and later eligible detail are covered (`test_decline_reasons.py:393`–`:653`, `:820`, `:1034` onward). F-1 analysis below. |
| T5 snapshots | Real complete/running generate/status, initial kickoff response, pending cards, passed new ID, switched caller/format with original job owner, old resolved source vs organic control. Known source link cannot be revalidated by a fresh different source; owned provenance batch is account/league scoped; unavailable history/provenance fails closed. Real held worker removes pass before legacy/F1 freeze; frozen rows and survivors stay unchanged (`test_trade_disposition_replay.py:52`–`:291`). |
| T6 restoration | Both real interactive and replenish builders restore day 8/day 13, configured fractional pass boundary, seven-day like boundary, enabled/disabled amnesty, malformed/offset stamps into both appropriate sets (`test_trade_disposition_restoration.py:31`). No new permanent organic ban. |
| T7 native | Actual adapter and bus/callback/handler execution plus pure production helper tests prove strict reason evidence, held Undo no write, reason-success/swipe-failure commitment, total-failure retry, remount scope, A→B→A late callback suppression, edited-only exclusion and no next-card skip. Remote-only invalidation of an already retained append-only deck without local pass is **held, not proved**. |
| T8 wiring/boundaries | AST supplements real consumers: live pass guard `test_trade_disposition_replay.py:296`; global job-lock exclusion and worker-before-writer `:279`; active passes still beat standing mirrors (`:122`) and common final serving path including Arm A. Policy/roster/bakeoff/golden/fatigue/standing suites remain green. Standing/postmatch/fuzzy policy redesign is not included. |

### Independent F-1 adjudication after repair

The original unchanged reproduction executed on B's actual database/server files at 16:35 UTC. Response: `{ok:true, passed:true, reason:"value", detail:"value_giving", switched_from:null, elo_written:true}`. The exact chronology became old pass `2026-08-01T12:00:00+00:00`, renewed source like `2026-09-05T12:00:00+00:00`, and new current pass `2026-09-06T16:35:35.181942+00:00`. The source reader changed from actionable to empty; there was **one** pass outcome. Its retry assertion left three decisions. This independently reverses the concrete round-1 app failure, not just its HTTP field.

The key distinction is now visible at `database.py:6774`: reason identity must match actor, league and actual trade ID. `:6777` uses immutable first-bank time, not mutable detail time. An orderable exact pass at/after that episode is existing committed evidence (`:6808`); a known other impression is rejected first (`:6802`). An earlier pass needs either the owned same-league served interval or the existing ten-second legacy bridge (`:6813`). Exact current actor/counterpart positive barriers, normalized and row-ID ordered, disqualify an old companion (`:6824`–`:6843`); malformed relevant positive time is conservative. Later positives after first bank do not turn a refinement into a new rejection. Otherwise a real new pass is inserted and committed (`:6844`).

I independently checked and executed the adversarial controls: same-ID old pass both far outside and inside the ten-second bridge; actual renewal by either orientation; mixed offsets; same-time positive before/after pass with both actors; unrelated actor/league/package/direction; malformed pass/positive/served/episode clocks; a known other exposure; real linked swipe-first delayed by an hour; both companion orders; service loss and context echo; retry/refinement after later source renewal. That later renewal survives the old reason refinement, then an actual new ordinary swipe rejects it (`test_decline_reasons.py:564`). The immutable local surrogate still cannot identify a genuinely new reason episode versus a very late retry of the same key. There is **no time-based/new-like reset**, no new lifecycle field, and no claim that this held identity ambiguity was solved.

## Full requirement and test matrix — 420/421

| Requirement | Current implementation and negative branches | Executed evidence |
|---|---|---|
| R-1 recovery | `useSession.ts:728` creates one foreground deadline, joins readiness (`:746`), issues one initial read, catches only typed exact 409 (`:756`), forces once and performs one nonrecursive replay (`:758`). `leagueSession.ts:80` checks pending before ready/throttle. Failed work never becomes ready. | Recovery suite `:208`, `:256`, `:268`, `:281`; real mounted screen, available/unavailable replay, second refusal terminal, pending shared join. |
| R-2 identity/lifecycle | `leagueSession.ts:45` captures intent/generation before token wait; `:41` fences actor/token revision; `:83` token-lane predecessor; `:89` cancels only undispatched obsolete preparation; `:105` ambiguous accepted-send failure latches; `:75` allows only later explicit authorization. `useSession.ts:705`/`:737` guard terminal errors as well as data. | Recovery `:290`, `:301`, `:311`, `:320`, `:327`, `:354`, `:418`, `:431`, `:485`, `:513`, `:540`; no server cancellation/final-writer guarantee after ambiguous accepted POST. |
| R-3 budgets | `client.ts:332` exact normalized GET pathname, 30 s; ordinary requests retain 15 s and existing slow POSTs 30 s. `:454` computes logical deadline before token preparation; `runWithDeadline :298` rechecks before work, result and error. Fetch `:535`, body `:590`, and coordinator own deadline `leagueSession.ts:84` forbid late dispatch/publication. `useSession.ts:729` captures total 90 s before the chain. | Recovery `:182`, `:347`, `:369`, `:385`, `:396`, `:405`, `:524`, `:555`; 15.2 s succeeds, exact 30 s deadline, query/absolute URL yes, lookalike/prefix/POST no, token/body/backoff/suspended-runtime and near-deadline repair cases. |
| R-4 truthful error/existing UI | `client.ts:287` exact neutral timeout; caller abort wins `:309`/`:327`. `WinNowScreen.tsx:91` effect owns request, existing data/error/loading fields, Refresh cause and cleanup; typed source messages are not fabricated standings. Current 401 receipt `client.ts:212`, created after owned clear at `:614`, preserves original current-session error through guards; replacement-token 401 stays silent. | Recovery `:200`, `:445`, `:454`, `:462`, `:471`, `:485`, `:494`; existing `check-win-now.js`. Physical loading/VoiceOver remains unrun. |
| R-5 backend/safety | No 420 backend runtime/API change. Real persistent-token restoration still gets exact initialized-session 409 before any forecast call; authorized init unlocks actual typed unavailable; foreign league still forbidden (`test_verified_sessions.py:538`). Existing source/forecast/expiry/authorization semantics untouched. | Full Win Now, forecast/outlook, persistent/verified-session tests; focused verified/API/service gates; current/refused native matrix. |
| R-6 observability/privacy | Existing wrapper emits once per logical failure (`client.ts:457`); superseded consumer abort `useSession.ts:740` is silent; no lane-only fake HTTP event. `client.ts:639` checks sent/current token, revision, deadline and caller/context fence **before** verification callback. No new analytics schema, raw keys or identifier-bearing coordination logs. | Recovery `:418`, `:431`, `:626`, `:636`; normalized route/query stripped, background latency omitted, allowed event fields exact. |
| R-7 bounded integration | State instantiates single owner `useSession.ts:694`; API init requires control `auth.ts:258`; all affected writers share it. Revalidate `useSession.ts:358`, switch `:444`, Connect `:592`, picker `LeaguePickerScreen.tsx:410`, resync `LeagueScreen.tsx:144` guard seeds/persistence/navigation. Connect reserves original gesture authorization/deadline before target discovery. No new Context/store/worker, API upward import, search/evaluate/decision recovery, model/policy changes or web edits for 420. | Recovery `:504`, `:534`, `:540`, `:555`, `:567`, `:581`, `:592`, `:606`, `:636`; all 95 suites, typecheck and existing seed/ownership/Win Now guards. |

| PRD test | Executed concrete boundary / limitation |
|---|---|
| T1 | Actual mounted Win Now repairs a lost initialized context; real current helper separately preserves typed unavailable after repair. No fake-ready-only proof. |
| T2 | Revalidate plus two consumers share pending preparation beyond old 1.6 s; no early GET or second init; one cache seed (`check-win-now-recovery.js:268`). |
| T3 | Exact second 409 terminates; explicit Refresh succeeds; player-cache recognized denial retries once and repeat denial ends (`:281`, `:504`); current picker/resync failures release busy state. |
| T4 | Both obsolete preparation and already dispatched acknowledged A→B paths execute (`:290`, `:301`). The same owner registers intent before waits and prevents old-generation seed/selection. Rapid-generation semantics also reviewed at `leagueSession.ts:38`–`:70`; no independent physical rapid-tap claim. |
| T5 | Caller detach leaves shared consumer alive; sign-out before dispatch writes/seeds nothing; replacement token and same-token selection silence old results/errors (`:311`, `:320`, `:431`, `:485`). Screen cleanup and season flag lifecycle covered by existing Win Now guards; not a device result. |
| T6 | Real restored persisted-session route guard `test_verified_sessions.py:538`: exact 409 and zero forecast calls before init, actual authorized init, preserved unavailable body and foreign 403. |
| T7 | Actual transport allows 15.2 s, exact method/path rules, finite one-request budget through token/body/retry, and post-suspension guard (`:182`, `:369`–`:405`). Existing two network plus two typed-init retry counters imply at most five physical GETs per logical read, ten across repair; no additional POST replay policy. |
| T8 | Available/unavailable, exact/unrelated 409, 400/403/404, neutral timeout, current/replaced 401 and stale verification callback execute against production parser/orchestrator. Full 95-suite transport/Win Now guards retain 503/network/body behavior. Current401 owns its one-step clear receipt; delayed secure deletion cannot publish expiry over replacement (`:462`–`:494`). |
| T9 | Existing full backend source/forecast/Win Now suites and `check-win-now.js` preserve live-week/unsupported-source/freshness/cache/title/feature guards, server order, expired recommendations and search's independent budget/epochs. No missing-as-zero or stale-success fallback added. |
| T10 | 90 s starts before token/readiness, includes lane/preparation/transport/body/repair; delayed preparation never later dispatches. Ambiguity survives queued B, auto picker, re-entry/foreground/throttle expiry and late response; only fresh explicit authorization or new token can reconcile. A second ambiguous retry relatches (`:327`, `:347`, `:354`, `:524`, `:540`, `:555`, `:581`). |
| T11 | Actual helper/store and extracted real picker/resync handlers execute all writer paths; init-before-navigation, guarded seeds, merged platform list, current-failure busy cleanup. Account-only real ESPN/MFL/Fleaflicker builders stay supported; `no_league` does no projection request (`:606`). Structural census supplements these real calls. |
| T12 | Actual event spy proves one bounded failure report, no abort event, normalized route and allowed keys, background duration omitted; census forbids API→state/cache import and write recovery (`:626`, `:636`). No identifiers were added to tracked QA evidence. |

## Full requirement and test matrix — smaller-player presentation

| Requirement | Current implementation, negative branches and tests |
|---|---|
| R1 eligibility | `server.py:7852` requires captured mode, live successfully evaluated policy, no raw presentation exemption, no explicit pins/opponent, no demo/active ghost/dark served arm. `test_small_trade_presentment.py:416` runs real worker on give/receive/raw ignored receive/opponent/demo/ghost/shadow/dark/policy failure controls and compares off/on cards/impressions. Raw receive intent survives targeting-off normalization at `server.py:13528`; real completed/running route controls `test_small_trade_presentment.py:480`. |
| R2 permutation | `small_trade_presentment.py:94` creates occurrence records, `:119` uses absolute six-position windows and class-local stable sort by max-side then total players. No generation, valuation, truncation, duplicate collapse or input mutation. T1 `test_small_trade_presentment.py:100` moves the actual A/B/C worker deck; multi-window/holes/17-card/duplicate-object invariant checks at `:136` preserve every original occurrence and slot class with ≤5 displacement before later filtering. |
| R3 classification/source fidelity | `small_trade_presentment.py:25` uses actual player metadata plus existing generic/owned pick parsing and canonical pseudo-asset predicate; unknown/conflicting/malformed sides produce null, not guessed zero. `:57` locks missing policy or required actual arm/group metadata; card lane/basis and policy lane remain class components. Tests `:167`, `:174`, `:188`, `:209`, `:218` cover special positions, mixed/pure picks, real RB/PICK generic assets, unknown/conflicting ownership and absent attribution/group. Picks are not players and not a tie-break penalty. |
| R4 captured configuration/reuse | `server.py:3119` captures mode/version/base once; `:3127` checks mode compatibility; generation `:13524`, kickoff `:8234`/`:8284`, pregen `:21159`, replenish `:21964` carry it through reuse and worker. Tests `:296`, `:322`, `:354`, `:372`, `:395` cover 0→1/1→0, missing metadata/default0, complete/running/pregen/replenish, actual kickoff and mid-worker flips. Old-ID polling does not rerank. |
| R5 one publication | Helper runs once after final policy and before evaluated first snapshot (`server.py:7852`–`:7879`). Final #419 cut at `:7969` removes only authoritative dispositions; final republish `:7988` does not depend on F1 logging. Held actual worker `test_small_trade_presentment.py:237` asserts first published shape, one helper invocation, then newly passed card removed and survivor order retained with both signal/telemetry settings. |
| R6 occurrence-aligned provenance | `small_trade_presentment.py:134` advances identity-plus-occurrence records through the ordered survivor subsequence. `server.py:4891` freezes `final_index` from writer enumeration; `:4982` uses separately captured serving suffix, `:5022` retains existing arm suffix. Final legacy/F1 writers `:8020`/`:8054` consume the same survivor order. Tests `:237` include duplicate-shaped distinct objects and repeated same-object occurrences, original indices `[3,5,4,2,1,6,7]`, final/card indices 0–6, later poll deletion leaving frozen rows unchanged, signal/telemetry combinations; `:456` locks unknown/unattributed first row with uniform nullable provenance. |
| R7 one default-off knob/safety | Only `simple_player_presentment=0.0` is added to both default registries (`database.py:2942`, `trade_service.py:1293`); exact finite numeric1 enables (`small_trade_presentment.py:18`). Boolean/string/NaN/infinite/other values stay off. No arm-profile, fairness/value/roster/policy/generator math change. Full goldens and arm config census green; #419 final removal is never refilled/reranked. |

| PRD test | Executed coverage |
|---|---|
| T1 meaningful movement | Actual composed/uncomposed A/B/C worker × both `1qb_ppr`/`sf_tep` × F1 on/off: `3x3,1x4,2x3,1x1,1x2,1x1` → `1x1,1x2,1x1,3x3,1x4,2x3`, first-three load 16→7; total supply unchanged and larger cards still present. Credit A/B/C/A/B/C remains; original arm/group ranks travel. |
| T2 properties | 17-card absolute-window fixture, locked hole, short last window, lane/basis/policy class positions, stable/idempotent output, unchanged objects/attributes, complete occurrence multiset, repeated same-object controls (`:136`). Compaction after a pass is explicitly outside the ≤5 permutation displacement promise. |
| T3 exclusions/classification | Every listed worker exclusion plus pure-helper unknown/special/source locks executes; literal raw receive with targeting flag off is not reinterpreted as organic. Mode0 unchanged control remains valid. Explicit/manual/Win Now routes do not acquire a helper call. |
| T4 first publication | Actual held worker first/final boundary with logging on/off proves helper before evaluated publication and final pass filter before writers. Route/cache/kickoff fixtures separately cover fresh/forced, normal/pregen/replenish plumbing; they are not falsely described as all doing end-to-end generation. |
| T5 mode/rollback | Supported/unsupported values, missing capture, complete/running cache compatibility, both mode transitions, pregen/replenishment and retained old-ID snapshot; capture is not re-read after upstream policy fixture flips it. |
| T6 F1/legacy | Actual writers verify original occurrence record, enumerated final index, unchanged actual arm/group ranks and valuation variant, locked first-row nulls, captured base/suffix, no fabricated arm/propensity, no F1 row with signal disabled, no candidate logging accidentally enabled by suffix. Polls do not mutate frozen rows. |
| T7 supply/goldens | Full generator/Arm A golden files and bakeoff drafting/accounting unchanged; zero/default/exempt controls preserve cards/order/features; pure permutation keeps larger packages. Existing test fixture repair merely supplies the real mirror like required by the injector, keeping its old ordering assertions intact. |
| T8 integration | The 892 tests selected across 33 files include current disposition, worker/cache, standing offers, policy, roster, scoring context, queue/matching and arm accounting. All 5,645 full backend tests, 95 native suites, typecheck, testID and web structure gates passed. No source or control changed to obtain green. |

The anonymous served-shape diagnostic in the builder evidence is **reviewed, not newly rerun**: two anonymous jobs / 78 occurrences; reported movement 13/40 and 14/38; first-three 14→12 each; first-six unchanged26; max movement5/4; no-op windows2/7 each. It is conditional on organic eligibility with modeled ungrouped attribution because historical pins/dark/fatigue context is unavailable. It is **not** an actual-runtime counterfactual, new player-supply measurement, acceptance gain or causal experiment. The independent synthetic T1 movement and invariants above are directly executed, not inferred from that corpus.

## Documentation, design and findings

Current synchronized contracts were checked against source: `docs/api-reference.md:264` and `:283` separate bank acknowledgement from verified pass, source-specific actionability, queue renewal and snapshot cuts; `docs/architecture.md:235`/`:237` cover batched projection and post-policy presentation; `:335` records native lifecycle/deadline/uncertainty limits. `docs/data-dictionary.md:413` describes existing JSON occurrence provenance without a migration or acceptance claim; `docs/config-reference.md:656` records exactly one default-off setting and fresh-generation rollback; `docs/cross-client-invariants.md:271` no longer claims resolved one-sided likes must occupy a bucket. Native API/state/utils README changes match producer/coordinator ownership and durable-reason semantics. No concrete new contract mismatch was found in these changed references.

The three approved reconciliations are followed: no new public response field, source history reset, postmatch redesign, extra package knob, fourth arm, global timeout increase, server async endpoint or UI redesign. Existing native panels/controls remain. The shared neutral timeout and the bounded uncertainty message use the existing error area. Design/token/code review plus typecheck/testID/web structure are not visual/device accessibility proof. The test README's older stated suite count is not the actual runner census: all **95** globbed files ran; I did not change unrelated index documentation.

### D-1 — minor documentation hygiene, not an application defect

At the exact tested HEAD, `git diff --check 4026ebc81eaae50b345b42421641125c5b8d413e..HEAD` reports `docs/research/2026-09-06-trade-package-shapes.md:124: new blank line at EOF.` Runtime/mobile diff check passes. No code/test correction is indicated. Forwarded to root without editing this file. Root subsequently reported a documentation-only EOF cleanup in the integration working tree and a passing full-range check; I have not relabeled this frozen B checkout as containing that cleanup. Release owner should include/verify the cleanup on its final docs commit. This is the sole new observation, **minor/non-runtime**, not a wrong test or environment assertion failure.

## Manual coverage audit — all UNRUN

Read the entire consolidated `testflight-checklist.md` (17 steps). Its 419 steps1–6 cover old-source/organic controls, local lane/edited/browse replay, held worker and restoration, Undo/failures/strict reason evidence, deliberate source renewal and distinct reason episode. Steps7–13 cover both Win Now entries, staging rollover, selection/token uncertainty, deadline/error/current401 matrix, contention measurement and every writer/imported-platform regression. Steps14–17 cover real organic package order/picks/exemptions and retained capture/rollback. These align with the three approved PRDs. None was physically performed.

Add the following explicit substeps to the operator run, without treating this report as permission to mutate production:

18. **Shared consumer detach:** under authorized staging delayed initialization, open a second legitimate same-context consumer, then leave Win Now. Confirm the surviving consumer completes with one init, while the departed screen emits no late error; repeat cancellation on the exact deadline runtime turn. Automated equivalent: recovery suite `:311`, `:626`.
19. **Reason refinement after new consent:** after one successfully committed reason episode, create a later authorized synthetic source renewal, then deliver a delayed layer-2 refinement/retry for the old episode. It must not write a new pass or resolve the later renewal. A genuinely new ordinary pass can subsequently reject it. Repeat old pass linked to a known different impression, which must not serve as the new episode's companion (`test_decline_reasons.py:564`, `:653`).
20. **Rapid intent reversal and same-card retry:** exercise same-token A→B→A selection with slow preparation/ACK, plus a failed older pass callback arriving after a newer action on the same raw card. No stale busy cleanup, seed, toast, cursor rewind or banner may override the newest intent. Use only controlled fixture identities.
21. **Literal raw receive exclusion:** on staging mode1 with the pre-existing receive-targeting flag off, repeat a nonempty explicit GET selection against both completed and running organic cache entries. The request must not borrow/relabel the organic presentation; empty receive remains the ordinary control. Mode0 retains original normalization/fairness behavior.
22. **Frozen occurrence audit:** in a controlled duplicate-occurrence fixture, pause after the first evaluated package snapshot, add an exact pass, release the worker, then inspect sanitized served/F1 evidence. The pass is absent, helper ran once, each survivor retains original index/count record, and written final index equals F1 card index; repeat F1/suggestion-telemetry combinations and a later poll removal. This is a staging artifact check paired with native observation, not a physical-only claim.

Record installed version/build, device/OS, backend exact SHA and controlled fixture revision for each actual result. No Apple processing/availability result or previous upload can substitute for these checks.

## Explicit unrun/held items and release boundary

- Physical TestFlight steps1–22, real-device touch/gesture/Back/Dynamic Type/VoiceOver, actual slow-network UI and staging rollover/contended backend measurement: **UNRUN**. No simulator, Maestro or screen capture was used.
- Optional captured-2025 offline backtest: **SKIPPED** for absent configured artifact, as pytest reports. No provider/network data collection or private snapshot retrieval was attempted.
- Fresh PostgreSQL concurrency/lock/load benchmark: **UNRUN** in this SQLite QA environment. The reason transaction's deployed single-worker semantics and `FOR UPDATE` source were reviewed; SQLite green is not a newly measured PostgreSQL race proof or latency SLO.
- Backend baseline/repair RED and anonymous corpus diagnostic: reviewed with attribution, **not rerun** this round. All other individually prospective source-disable, retry-limit, callback, classification or cache sabotages: **not claimed run**. Previously denied sabotage was not retried/bypassed.
- Remote-only invalidation into a retained append-only native deck without a local pass, standing/postmatch lifecycle/fuzzy policy redesign, legacy-surrogate new-episode ambiguity, server cancellation/final-writer guarantees after ambiguous accepted init, and unconditional ordering/cancellation of already dispatched native storage: **held scope**, not silently solved or tested as guarantees.
- Production quality/acceptance, knob activation, provider proposals, feedback closure, deploy/CI/EAS/build/submission/TestFlight availability: **not performed or established by this agent**. Parent owns exact-final-head validation, other independent QA, release gates and authorized normal shipping; no express waiver is inferred. A runtime/test code change after this frozen review requires another full independent review.

All commanded foreground test sessions completed. This report is the only authored checkout change. Its report-only commit must have tested `7d3e071f92bac3a087ba63da393109b5eae02f68` as parent; report commit identity and post-commit clean status are provided in the handoff rather than self-embedding a changing commit hash here.
