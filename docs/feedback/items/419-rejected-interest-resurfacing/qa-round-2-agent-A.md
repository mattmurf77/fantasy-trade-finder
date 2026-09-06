# QA round 2 — Agent A — 2026-09-06

## Summary: PASS — no application or wrong-test findings

Fresh, independent full review of feedback 419/420/421 and the approved bounded smaller-player-package presentation, not merely a retest of round-1 F-1. The original F-1 reproduction now passes, including the actual new decision, renewed-source reader, one outcome and idempotent retry. Full backend: **5,645 passed, 1 skipped in 709.94 s**, exit 0. All **95** mobile guard programs, TypeScript, testID lint and **190** web checks passed. The separate 33-file focused backend matrix passed **892 tests in 58.84 s**.

This is a code/mechanical QA verdict, not a physical-device pass, deployed-service health claim or permission to skip exact-head CI/parent validation. There is one documentation-only whitespace observation on the frozen input, recorded below; no runtime fix is requested. All physical checks remain **UNRUN**.

## Exact environment and independence

- Detached, initially clean checkout: `/private/tmp/ftf-feedback-419-421-f1uMyt/qa-round2-a`.
- Tested HEAD: **`7d3e071f92bac3a087ba63da393109b5eae02f68`**. Runtime integration includes `3edf42572e710d212430623f7c6e6b175c2948a8`; comparison baseline is **`4026ebc81eaae50b345b42421641125c5b8d413e`**. No runtime or test edit was made by this reviewer.
- Python **3.12.14**, pytest **9.1.1**, Node **v24.14.1**, npm **11.11.0**, TypeScript **5.9.3**. Interpreter: `/private/tmp/ftf-context-venv/bin/python`. The independently installed mobile dependency tree was present; `test ! -L mobile/node_modules` passed. No dependency symlink was created.
- Full suite used a distinct file-backed synthetic DB, first verified absent: `/private/tmp/ftf-feedback-419-421-f1uMyt/qa-round2-a-full.sqlite`. It is retained. Normal full-suite provider posture was preserved: no global `FTF_DP_VALUES_FILE`, no conftest/default changes. Focused/reproduction imports used the two approved offline provider fixtures below.
- I read the applicable root/backend/tests/mobile/src/api/state/utils/screens and documentation QA instructions; coding guidelines; the feedback skill, lessons and QA reference; design-system/component contracts; all three complete approved PRD/scope/reconciliation sets; their complete build-evidence/code-walk files; adjudicated historical F-1 and `qa-resolution.md`; and the consolidated physical checklist. I independently reviewed the entire runtime and test diff in the 96-file baseline-to-HEAD change set, including modified existing guards, rather than inheriting a previous verdict. The other round-2 agent's report/conclusions were not consulted.
- The feedback skill requires independent QA and negative evidence. The explicitly approved unchanged-baseline alternative was used below. The previously denied source-disabling operation was not retried or bypassed.

## Executed commands and actual results

All commands ran from the checkout above except TypeScript, which ran from its `mobile` directory. Long tests ran in foreground execution sessions, not background monitors.

```sh
test ! -e /private/tmp/ftf-feedback-419-421-f1uMyt/qa-round2-a-full.sqlite
env -u FTF_DP_VALUES_FILE \
  DATABASE_URL=sqlite:////private/tmp/ftf-feedback-419-421-f1uMyt/qa-round2-a-full.sqlite \
  PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/ftf-context-venv/bin/python -m pytest backend/tests -q \
  -p no:cacheprovider --tb=short -ra
```

Result: **5,645 passed / 1 skipped / 0 failed / 0 errors**, exit 0, **709.94 s**. The sole skip is `backend/tests/test_outlook_odds.py:610`: optional offline backtest requiring `FTF_OUTLOOK_BACKTEST=/path/to/captured_2025.json`. It was not supplied and the skipped backtest was not run separately.

The focused command used these environment variables (also used for the original reproduction and supplemental Python check):

```sh
DATABASE_URL=sqlite:///:memory:
PYTHONDONTWRITEBYTECODE=1
FTF_DP_VALUES_FILE=backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv
FTF_DP_PICK_VALUES_FILE=backend/tests/fixtures/dp_values_picks_2026-08-06.csv
```

With that environment:

```sh
/private/tmp/ftf-context-venv/bin/python -m pytest -q -p no:cacheprovider --tb=short \
  backend/tests/test_small_trade_presentment.py \
  backend/tests/test_trade_interest_disposition.py \
  backend/tests/test_trade_disposition_replay.py \
  backend/tests/test_trade_disposition_restoration.py \
  backend/tests/test_decline_reasons.py backend/tests/test_trade_match_flow.py \
  backend/tests/test_pass_cooldown.py backend/tests/test_awaiting_dismiss.py \
  backend/tests/test_deck_fatigue.py backend/tests/test_trade_decision_idempotency.py \
  backend/tests/test_swipe_reconstruct.py backend/tests/test_bakeoff_serving.py \
  backend/tests/test_calc_trade_queue.py backend/tests/test_deck_replenishment.py \
  backend/tests/test_standing_offers.py backend/tests/test_trade_job_read_amplification.py \
  backend/tests/test_scoring_execution_context.py backend/tests/test_deck_first_session.py \
  backend/tests/test_force_supersedes_running_job.py backend/tests/test_trade_policy.py \
  backend/tests/test_trade_policy_wiring.py backend/tests/test_trade_roster.py \
  backend/tests/test_trade_roster_wiring.py backend/tests/test_bakeoff_arm_a_golden.py \
  backend/tests/test_bakeoff_runner.py backend/tests/test_bakeoff_composition.py \
  backend/tests/test_bakeoff_challenger.py backend/tests/test_engine_quality_golden.py \
  backend/tests/test_session_init_sleeper_calls.py backend/tests/test_verified_sessions.py \
  backend/tests/test_persistent_sessions.py backend/tests/test_win_now_api.py \
  backend/tests/test_win_now_service.py

PYTHONPATH=. /private/tmp/ftf-context-venv/bin/python \
  /private/tmp/ftf-feedback-419-421-f1uMyt/qa-a-reason-episode-repro.py
```

Focused result: **892 passed in 58.84 s**, exit 0. Reproduction: exit 0. I read the unchanged script before execution and verified that both printed module paths resolve inside **qa-round2-a**, not the baseline or another checkout. Its old pass was `2026-08-01T12:00:00+00:00`, source renewal `2026-09-05T12:00:00+00:00`, and newly written current pass `2026-09-06T16:33:27.756798+00:00`; the route returned `passed:true`, the renewed source became inactive, one pass outcome existed, and retry kept exactly three decision rows.

| Additional command/check | Actual result |
|---|---|
| Enumerate every `mobile/tests/check-*.js`, sort, and `spawnSync(process.execPath, [file])` once per file; inspect every process status and fail the runner if any status is nonzero | **95 programs, 95 exit 0**, no failures. Not a loop that hides failed exit codes. |
| `node mobile/tests/check-trade-disposition.js` (separate repeat) | **28 passed, 0 failed** |
| `node mobile/tests/check-win-now-recovery.js` (separate repeat) | **38 passed, 0 failed** |
| `npx tsc --noEmit` in `mobile` | exit 0 |
| `bash mobile/scripts/testid-lint.sh` | `testid-lint OK`, exit 0 |
| `/private/tmp/ftf-context-venv/bin/python qa/web/check_web_structure.py` | DS 95/95, TOK 1/1, SEO 50/50, A11Y 38/38, HYG 6/6: **190/190**, exit 0 |
| Supplemental inline Python importing the actual `backend.small_trade_presentment` and the existing test helper: identical all-large `3x3` cards at sizes **0, 1, 2, 5, 7, 13**; assert identical occurrence identity/order, unchanged packages, count/indices and idempotence | **6 passed**; production helper path verified inside qa-round2-a. No source file written. |
| `git diff --check 4026ebc8..HEAD` | Nonzero for one documentation-only blank line at EOF; see N-1. No runtime whitespace finding. |

Counts above are independent runs, not additive unique-test counts.

Exact all-guard runner (each guard owns a separate Node process):

```sh
node -e 'const fs=require("fs"),cp=require("child_process");const files=fs.readdirSync("mobile/tests").filter(f=>/^check-.*\.js$/.test(f)).sort();let failed=[];for(const f of files){const r=cp.spawnSync(process.execPath,["mobile/tests/"+f],{encoding:"utf8"});process.stdout.write(f+": exit="+r.status+"\n");if(r.status!==0){failed.push(f);process.stdout.write(r.stdout+r.stderr);}}process.stdout.write(JSON.stringify({programs:files.length,passed:files.length-failed.length,failed})+"\n");process.exitCode=failed.length?1:0;'
```

## Meaningful negative controls and provenance

```sh
FTF_TRADE_DISPOSITION_BASELINE=4026ebc8 \
  node mobile/tests/check-trade-disposition.js

FTF_MOBILE_TEST_ROOT=/private/tmp/ftf-feedback-419-421-f1uMyt/419-provenance-baseline/mobile \
FTF_BASELINE_ONLY=1 node mobile/tests/check-win-now-recovery.js
```

Before the second command, a Node assertion compared each entire file byte-for-byte with `git show 4026ebc8:mobile/<path>`: `src/api/client.ts`, `src/api/auth.ts`, `src/api/winNow.ts`, `src/api/espn.ts`, `src/api/platformLink.ts`, `src/state/useSession.ts`, `src/screens/WinNowScreen.tsx`. **All seven comparisons passed.**

- Trade baseline: **0 passed / 4 failed**, expected exit 1. Real adapter returned boolean rather than structured `passed:false`, omitted edited package context, lost verified-true distinction, and the extracted actual baseline lane projection retained the known passed card. These are behavioral assertions, not missing-file/export failures.
- Win Now baseline: **0 passed / 7 failed**, expected exit 1. Actual transport failed 15.2-second completion, published obsolete verification, kept hosting-diagnosis copy; mounted screen did not repair; foreground duplicate returned before pending init; B dispatched before A acknowledgement; automatic foreground restarted an ambiguous init. These cases execute unchanged baseline modules and existing entry points.
- Current corresponding guards are green as recorded above. Existing backend incident/snapshot/restoration REDs, package-worker REDs and the repair's four original plus known-other-impression RED evidence were read in the build evidence and adjudication. They are **historical builder/root evidence, not newly executed Agent-A REDs**. The original F-1 current-source GREEN was newly executed here.
- The complete menu of prospective source-disabling/sabotage variants in the PRDs was **not** executed in this review. No statement that every proposed mutation was run is intended. The denied operation remained denied; unchanged-baseline execution was the authorized alternative. Green behavioral tests plus the following negative-branch source traces establish the reviewed coverage without claiming nonexistent mutation runs.

## Requirement/test matrix and code-walk proof

References below are file:line anchors in the exact tested HEAD. “PASS” means executed mechanical evidence plus the stated source trace; physical behavior remains in the separate UNRUN checklist. Existing integration harnesses mock provider/generator inputs, not the disposition rule, real route, installed guard, worker publication or lifecycle being asserted.

### 419 — R1 through R4, T1 through T8

| Requirements/tests | Result and positive path | Negative branches/boundaries |
|---|---|---|
| R1 / T1 incident | PASS. `backend/database.py:5901` owns normalized source chronology; `:6067` supplies actionable likes to actual injector `backend/server.py:3627`. `test_trade_interest_disposition.py` and real match-flow suite verify old source resolution and organic unbadged survival. | Source consent does not reuse the discovery/amnesty decision. Old exact own/mirrored pass resolves the source even after expiry; no new source means no synthesis or boost. Different package can remain eligible. |
| R1 / T2 precedence | PASS. `database.py:5891` normalizes UTC/naive stamps; `:5901` uses timestamp plus decision ID, exact side sets and actual actor scope; `:6017` performs bounded-scope history reads. New DB cases exercise orientations, ties, malformed stamps, withdrawal and changed identities. | Retraction cannot fall back; recipient re-like cannot revive another actor's old source. Malformed relevant ordering is conservative, not consent. Old scoped rows deliberately remain available; reads do not rewrite history. |
| R2 / T3 readers | PASS. Exact/fuzzy admission `database.py:9093`, actionable queue probe `:6092`, Awaiting `:9478`; queue's actual target/context `server.py:14758` reaches durable decision logic `database.py:5743`. Real `test_calc_trade_queue.py` t=0/1/2 scenarios, Awaiting/summary, fuzzy and match suites are green. | Server-verified exact intervening pass permits one renewal inside ten seconds; retry adds no second like/Elo/event. Unrelated actor/league/opponent/package and no-pass controls cannot bypass replay. Fuzzy quality math is unchanged. Ambiguous roster ownership cannot invent a waiting partner; known player anchors can support mixed picks. |
| R3 / T4 banking/repair | PASS. `server.py:15130` banks reason then `:15136` verifies/repairs actual-card context using `database.py:6756`; `server.py:14954` binds both live exclusion sets across formats/alias only after a valid pass. `database.py:5605` commits qualified reason Elo and its claim atomically. Real reason-route and reconstruction tests passed. | Contextless or failed persistence stays `passed:false`; a valid later context repairs exactly once, even beyond ten seconds/restart. Edited ID/sides/counterparty are used. Late old-league writes cannot bind the new service. Failed Elo does not erase a durable pass, and failed decision persistence cannot masquerade as success. |
| R3 / T4 repaired F-1 episode | PASS, original reproduction plus 23 current episode cases in `test_decline_reasons.py:507`, `:539`, `:564`, `:592`, `:609`, `:632`, `:653`. `database.py:6777` uses immutable first-bank time; `:6781` validates owned same-league exposure; `:6802` excludes known other exposure; `:6824` checks own/actual-target exact consent barriers. | Arbitrary old same-ID pass is not current episode proof. Earlier swipe companion requires real exposure interval or existing ten-second legacy bridge, without intervening exact positive consent. Equal timestamps use decision IDs. Unknown time is not ordered evidence. Later refinement uses the original bank anchor and does not re-pass a later renewal; a genuine new ordinary swipe still passes it. No legacy-key episode reset is invented. |
| R3 / T5 snapshot/publication | PASS. `server.py:2997` snapshots outside the global lock; `:3033` projects owned history plus conditional batched impression-source links. Generate/status/current cards/final worker/replenishment call it at `:13524`, `:14117`, `:14147`, `:7969`, `:22007`. `test_trade_disposition_replay.py:151`, `:194`, `:236`, `:253`, `:279` cover real routes, known-source replacement rejection, failures, worker hold/drop and lock boundary. | Job/card owner and league, not caller's newly selected league, control filtering. Known source ID cannot borrow fresh same-package evidence; null links stay legacy/unlinked. DB failure fails closed. Survivors retain order and frozen metadata; no mutation of stored prior impressions. |
| R3 / T6 restoration | PASS. Shared restoration `server.py:3097` is called by full init `:20589` and headless replenishment `:21890`; `test_trade_disposition_restoration.py:31` executes both builders. | Day 8/13 and fractional configured pass boundaries, independent seven-day likes, amnesty enabled/disabled and malformed timestamps retain the approved separate windows; this is not a permanent organic ban. |
| R4 / T7 native | PASS. Structured adapter `mobile/src/api/declineReasons.ts`; pure identity/settlement/projection `mobile/src/utils/tradeDisposition.ts:11`, `:31`, `:52`, `:72`; shared bus `TradesScreen.tsx:293`, `:328`, `:337`; actual error handling `:2453`, projection `:4037`, frozen acted reason target `:5849`, Browse restoration `:6157`. All 28 focused cases and existing decline/browse/Undo guards pass. | Only verified true or swipe acknowledgement commits; missing/false evidence and both-write failure remain retryable. One successful sibling survives the other's failure. Held Undo at `:2846` sends nothing; flush `:2832` retains captured identity. Cursor uses source positions, layer 2 stays held, edited identities stay exact. Account/league epoch, deck epoch and newest-action fences prevent stale callbacks/rewinds. Remote-only retained-deck invalidation without a local pass remains excluded. |
| R1–R4 / T8 integration | PASS. New wiring assertions plus full policy/roster/bakeoff/standing/worker suites, especially `test_trade_disposition_replay.py:279` and `:296`, verify public/final cuts and guarded binding. | Active exact passes remain authoritative over organic, interested and standing mirrors and arm-A R4 bypass. Standing/post-match lifecycle, ranking/fairness/fuzzy policy and ordinary swipe's best-effort/D-073 signal contract were not broadened. No safety refill is introduced. |

### 420/421 — R-1 through R-7, T1 through T12

| Requirements/tests | Result and positive path | Negative branches/boundaries |
|---|---|---|
| R-1 / T1 | PASS. `useSession.ts:728` joins init, then exact typed 409 at `:756` permits one force and one GET replay; mounted `WinNowScreen.tsx:99` uses this owner. Real installed backend guard test at `test_verified_sessions.py:568` validates authorized recovery. | Second 409 is outside the repair catch and terminates. Available/unavailable source payloads are preserved. Logical replay is not a promise of only two transport attempts: existing bounded transport retries remain. |
| R-1 / T2 | PASS. `leagueSession.ts:80` joins pending work before using ready timestamps; `useSession.ts:746` awaits it before read. Native deferred tests run two foreground callers and projection together. | No busy boolean/foreground throttle marks pending work ready; one waiter cannot force an early GET or duplicate same-generation initialization. |
| R-1/R-4 / T3 | PASS. Lifecycle `:115` publishes readiness only after current accepted init, not failure; captured auth control preserves the existing one player-cache retry. Native failure/second-refusal/explicit-Refresh cases are green. | Failure does not poison success throttle; cache retry is bounded and keeps the same context/deadline. No recursion or background success fiction; current terminal error releases loading. |
| R-2 / T4 | PASS. `leagueSession.ts:38`, `:45` capture intent/generation before waits; `:83`, `:97`, `:105` serialize accepted same-token writers. Actual revalidate/switch deferred cases prove B waits for A ACK and obsolete prepared A never dispatches. | Pending preparation is cancellable; already-dispatched POST is not asserted canceled. A cannot seed B or later A after an intervening generation. Writer order after ambiguous accepted completion is expressly not guaranteed. |
| R-2/R-6 / T5 | PASS. `leagueSession.ts:41`, `:129`, `:136`; `useSession.ts:734`–`:744`; screen effect's abort cleanup fences readers on identity/intent/unmount. Native shared-consumer/sign-out/stale callback checks plus code walk. | One caller detaches without canceling another's shared init. Replacement token/account, new league intent and AbortError cannot publish old results or timeout telemetry. Actual blur/flag-kill/device suspension coverage is in the UNRUN physical supplement, not claimed as device execution. |
| R-5 / T6 | PASS. Real persistent-session restoration test in `test_verified_sessions.py` restores a verified bare token through the installed guard, observes exact 409 and zero forecasts, performs actual authorized init, then gets typed unavailable and rejects foreign league. Full verified/persistent-session suites passed. | No fake ready session replaces guard coverage; unverified, invalid membership and signed-out safety tests remain green. Backend runtime/wire contract for this Win Now correction is unchanged. |
| R-3 / T7 | PASS. `client.ts:332` compares normalized exact path plus GET; `:454` captures min caller/route deadline; `:298` covers preparation/transport/body/return. Fake-clock tests verify 15.2-second success, 30-second failure, query/absolute forms, retries/backoff and resumed-JS late checks. | Prefix/suffix/lookalike/POST does not acquire projection allowance. Ordinary GET remains 15 seconds, existing slow POSTs 30. Transport retries and body consumption do not reset deadline. Neither the 30-second route cap nor 90-second attempt is a backend throughput SLA. |
| R-2/R-4/R-5 / T8 | PASS. `client.ts:212` identifies only the current request's own expiry receipt; its 401/403 branches check sent token, synchronous revision, signal/deadline and caller fence. `leagueSession.ts:41` and `useSession.ts:704` allow the genuine current-401 error through that one clear, not arbitrary replacement. Mounted screen, actual picker/resync, replacement-401 and delayed verification/deletion tests passed. | Current 401 clears and remains a truthful sign-in error; it is not hidden as cancellation. Old 401 cannot clear replacement login; late deletion callback cannot expire it. Exact unrelated 409/verification denial/source unavailable/503/offline/timeouts are not repair authorization. Already-dispatched native storage is not unconditionally cancellable/ordered by these guards. |
| R-5/R-7 / T9 | PASS. Existing `WinNowScreen.tsx:113`, `:117`, `:133`, `:169`, `:177`, `:244` retain baseline/result expiry, no-search-on-unavailable/stale gates, edit invalidation and source/title conditions. Complete existing forecast/Win Now tests and all mobile guards passed. | No fabricated zero standings, expired-success fallback, title bypass, altered server order or dynasty-decision replay. Search/evaluation/decision paths retain separate existing epochs and budget, not the new projection recovery. |
| R-1/R-2/R-3 / T10 | PASS. `useSession.ts:729` captures one 90-second attempt before token/context; `leagueSession.ts:84` takes the minimum, `:91` latches ambiguous dispatch and `:99` rejects previously queued authorization. Explicit sequence is captured before Connect target await at `useSession.ts:604`, using `leagueSession.ts:135`. | No automatic mount/refocus/foreground/throttle release of uncertainty. Old Connect gesture cannot become new permission. Late response does not publish readiness; repeated ambiguity relatches. Fresh later explicit action or replacement token permits a bounded retry. Near-deadline repair cannot dispatch after the original cap. |
| R-2/R-7 / T11 | PASS. Sole owner/seed at `useSession.ts:694`; revalidation, switch `:464`, Connect, picker and ESPN resync use begin/complete context, with accepted init before selected-league publication/Main. Actual handler tests and changed seeding/ownership guards preserve the behavior, not just old text shape. | Imported ESPN/MFL/Fleaflicker account-only real leagues retain platform builders; sentinel/demo/no league performs no projection read. Token/preparation/current-401 failures release picker/resync busy states; stale work cannot navigate. |
| R-6/R-7 / T12 | PASS. Existing client request-failure hook remains bounded and route-normalized; native event spy checks allowed keys, one exhausted logical-request event, no query identity, abort silence and background duration omission. Recovery at `useSession.ts:727` is GET-only and state-owned. | Lane-only deadline does not emit fabricated HTTP telemetry. No new token/coordination persistence/event fields, no API→coordinator/cache import, no search/evaluate/decision replay. Group #420 introduces no backend runtime, schema, flags, model or web change; separate authorized #419/package backend changes are not misattributed to it. |

### Smaller packages — R1 through R7, T1 through T8

| Requirements/tests | Result and positive path | Negative branches/boundaries |
|---|---|---|
| R1/R2/R5 / T1 | PASS. `server.py:7853` requires eligible captured live-policy organic work, then `:7857` calls pure helper before first evaluated publication. `test_small_trade_presentment.py:100` executes actual three-arm worker, both formats, grouped and group-size-zero cases with F1 on/off: six shapes move first-three total **16→7**, first-six total **23** unchanged, original A/B/C slots maintained. | No generator/profile/draft pre-sort; old rank is not a sort class that silently makes the helper a no-op. Cards and larger supply survive; this is presentation, not acceptance evidence. |
| R2/R3 / T2 | PASS. `small_trade_presentment.py:57` defines actual arm/group/lane/basis/policy classes; `:118` uses disjoint absolute six-slot windows, stable `(max players, total players)` order. Tests `:136` plus supplemental 0/1/2/5/7/13 all-large cases cover occurrences, locks, >12/short windows, bounds, ties and idempotence. | No cross-window or cross-class move, max displacement five before later removals; no dedupe/drop/value change. Holes are not compacted before windows. Equal keys preserve order and no-small-supply stays honest. |
| R1/R3/R7 / T3 | PASS. `small_trade_presentment.py:25` classifies real players versus generic/owned/pseudo picks, `:112` locks special/unknown/pure-pick cards; `server.py:7853` enforces worker exclusions. Actual raw receive request is captured at `:13528` independently of target flag; tests `:480` exercise completed/running route hits. | Picks add zero and do not break player ties. Unknown/conflicting/malformed metadata is not guessed as attractive zero or fabricated organic provenance. Explicit give/receive/opponent, demo, ghost, shadow/dark/single-arm validation remain exempt, including literal receive pins while targeting flag is off. Manual/Win Now routes do not call helper. |
| R4/R5/R7 / T4 | PASS. Worker `server.py:7857` precedes first evaluated snapshot, then final `:7969` cuts current dispositions and `:7972` retains occurrence records without another sort. Held real worker test `test_small_trade_presentment.py:237` asserts helper count one and final publication with/without F1. | Pass after first publication wins; survivors preserve order, are never refilled, and a passed card does not get an impression. Logging is not required for final safety cut. Polls do not reapply presentation. |
| R4 / T5 | PASS. `server.py:3119` captures mode/version, `:3127` checks compatibility; generation `:13524`, kickoff `:8234`, init-pregen `:21158`, replenish `:21963` use it. Tests `:296`, `:322`, `:354`, `:372`, `:395` cover both flips, completed/running hits and real kickoff capture. | Mid-job knob mutation cannot recapture order/version. Old-ID polling remains old order. Incompatible fresh completed/running/pregen/replenishment cache hits are rejected; same-mode compatible hit remains usable. Missing/invalid values are off. |
| R6 / T6 | PASS. `small_trade_presentment.py:103` records each original occurrence; `:133` walks ordered survivor occurrences rather than identity dictionary; actual writers `server.py:4694`, `:4891`, `:4982`, `:5022` enumerate final positions. Tests `:237`, `:456` inspect real frozen rows, duplicate-shaped objects and repeated object occurrences. | No stale parallel zip, collapsed occurrence, rebuilt original index or second sort. Removed occurrence gets no row; final index equals actual F1 card index; later poll cut does not rewrite frozen rows. Unknown first-row counts stay null with uniform fields. Arm/group rank, actual propensity, attribution/agreement and valuation variant remain distinct from `/pp:simple-player-v1` serving version. |
| R1/R7 / T7 | PASS. Exact finite numeric one only (`small_trade_presentment.py:18`); default **0.0** in `database.py:2942` and `trade_service.py:1293`. Worker exemption parity cases `test_small_trade_presentment.py:416`, arm-A goldens and bakeoff/engine regression passed. | Boolean/string/nonfinite/unsupported mode is off. No flag, arm profile, fairness, ranking or floor change; only the one new setting. Off/exempt yields baseline payload/order/features, no presentation stamp or implied telemetry activation. Default seed does not overwrite saved config. |
| R1–R7 / T8 | PASS. Full policy/roster/worker/cache/standing/lifecycle tests and full backend/mobile gates above. The final disposition cut is after presentation and before both writers. | #419 safety never yields to a simpler-card preference. No permanent cap, supply fabrication, post-match redesign or literal-selection override. Anonymous corpus examples are conditional shape diagnostics only, not runtime counterfactuals, production quality or acceptance-rate proof. |

## Contract, scope and UI audit

The reviewed API reference now separates reason storage (`ok`) from verified exact disposition (`passed`), including true on committed retries; it documents source-specific interest, queue renewal, Awaiting and frozen/public projection. Architecture/data dictionary/config reference/LLD and native API/state/utils documentation agree with the implemented division. The immutable episode/legacy identity limit is explicit in the repaired code walk and LLD. No new wire field, table or migration implements these fixes; presentation uses existing JSON/version columns. The single knob defaults off, all three arms and their actual source/group positions remain attributable, and raw receive selection exemption is literal even with targeting disabled.

Modified native JSX retains the existing reason panel, Back/loading/error/Refresh and search controls; no new visual system, badge, modal or valuation UI was introduced. The source-index projection and retry remount affect behavior, not design tokens. Design-system/component rules were reviewed, all existing guards/typechecks/testIDs passed, and the required runtime/a11y checks are still physical-only. Version metadata is consistently changed to 1.17.1 in the reviewed native/Expo files; that is source metadata, not evidence that Apple has processed or users can install it.

The held boundaries remain held: remote-only retained local deck invalidation without a local pass; standing-offer/post-match lifecycle redesign; unconditional ordinary-swipe durability; server cancellation/final-writer order after an ambiguous accepted init; unconditional ordering/cancellation of native storage already dispatched; new legacy reason-key episode identity; anonymous-corpus counterfactual or acceptance claims.

## Findings and environment classification

**Application defects: none found. Wrong tests: none found.** F-1 is resolved on this tested runtime by actual behavior, not merely a changed expected response. The existing seeding/shop/ownership guard edits match the new real lifecycle and account boundary; they do not suppress an observed application failure.

**N-1 — nonblocking documentation whitespace.** `git diff --check 4026ebc8..HEAD` reports `docs/research/2026-09-06-trade-package-shapes.md:124: new blank line at EOF.` This exists on the frozen tested input. It is not a contract or runtime defect. I made no edit. Parent subsequently reported removing only that EOF blank line in its integration working tree and a clean whole-range diff check; that downstream cleanup is parent evidence, not a change to the source tested here.

**E-1 — diagnostic limitations, not hidden pytest failures.** The full suite logged asynchronous isolated receipt-worker missing-table diagnostics for `receipts_grade_runs`, `deck_impressions` and `user_events`; pytest nevertheless completed with the actual zero failure/error result above. The original synthetic reproduction also logged an uninitialized global observability `user_events` sink: its real decision/reader/outcome assertions passed, but it is not an independent successful observability-sink proof. I did not edit fixtures/expectations or retry a failed full suite. The historical round-1 five-failure/28-error in-memory run was reviewed as adjudicated isolation history, not relabeled as this run. A read-only process listing attempted during a quiet test interval was sandbox-denied (`operation not permitted: ps`); it was not retried/escalated and tests subsequently completed normally.

## Physical TestFlight checklist — all UNRUN

I audited the existing consolidated **17-step** [physical checklist](testflight-checklist.md): steps 1–6 cover rejection/progressive reasons/snapshots/Undo/requeue/new impression episodes; 7–13 cover both Win Now entry routes, rollover, sequencing, uncertainty, deadlines, error/a11y/throughput measurement, picker/Connect/resync and existing controls; 14–17 cover the presentation fixture, picks, explicit flows, retained order and rollback. Preserve every step and its required device/OS, version/build, backend SHA and controlled-fixture identity. Do not interpret source assertions, EAS upload or Apple processing as a device pass.

Add the following explicit supplements to avoid relying on implications inside those broad steps (numbering continues after 17):

18. **Trades → a committed reason episode → partner renews → late layer-2/detail retry.** With authorized staging fixtures, complete the original reason, create a newer exact partner like, then release a delayed refinement of the old episode. Expect no new decision/outcome and no rejection of that newer interest merely from refinement. A subsequent genuine ordinary pass must create the current rejection. Repeat both actor orientations, and separately preserve swipe-before-reason companion coalescing. A reused unlinked legacy key does not pretend to identify a new episode.
19. **Win Now and Trades → rapid A→B→A, sign-out/replacement login, blur/unmount and season flag disabled while waiting.** Repeat during token preparation, init preparation and projection body completion. Only the latest legitimate context can show data/error, advance cursor, seed state or navigate. One surviving Win Now consumer must finish when another leaves. Re-enable only in staging and use a fresh deliberate Refresh after uncertainty. Caller cancellation must stay silent; record any device-suspension timing without asserting JavaScript ran while suspended.
20. **Win Now/picker/resync → current 401 versus replacement login during delayed secure storage.** Current expiry must stop loading/busy state and preserve the actual sign-in error. A delayed older response/callback must not clear the replacement login or publish its error. Record the actual native-storage outcome separately: the implementation does not promise cancellation/order of a write/delete already dispatched before replacement.
21. **Organic Find a Trade → held-worker pass with F1 logging both on and off.** With the six-card staged package fixture plus a duplicate occurrence, verify the first evaluated order, then pass before final publication and release. Surviving order stays unchanged, no refill occurs, and staged server readback of existing F1 rows has per-occurrence original indices and actual final indices; post-freeze polling must not rewrite them. This supplements the device check with authorized sanitized staging evidence, not real-user impression writes.

## Blocked, unrun and handoff limits

- All 17 consolidated physical steps and the four supplements are **UNRUN**; no physical device, Apple availability, TestFlight installability or a11y runtime result was claimed.
- Optional captured-2025 offline outlook backtest was skipped as declared above. No fixture was fabricated to clear it.
- Prospective sabotage variants beyond the explicitly executed unchanged-baseline controls were **not run**. Historical RED evidence is attributed, never presented as newly executed. Denied source-disabling work was not attempted again.
- No source/config/test fix, production/secrets/provider network operation, real-user action, proposal/message, deployment, push, EAS build, upload, simulator, Maestro, capture or live knob activation was performed. No web runtime source changed, so no local-browser/Flask visual exercise was performed; the web structural gate passed.
- Production latency/concurrency, package acceptance/causal quality, physical storage ordering and server final-writer behavior after an ambiguous init remain unmeasured/out of this gate. The read-only `ps` diagnostic was blocked as recorded above and no longer needed.
- Parent owns report reconciliation, TEST_LEDGER/release documentation, exact-head CI and final pre-push validation. Any subsequent **runtime code change requires a fresh full QA round**; this report does not certify an altered runtime. The only file authored by Agent A is this report, committed separately with the tested HEAD as its parent.
