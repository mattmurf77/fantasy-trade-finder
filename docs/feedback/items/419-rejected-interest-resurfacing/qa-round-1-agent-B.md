# QA round 1 — agent B — 2026-09-06

## Summary: FAIL (one major application finding)

F-1 violates #419 R3: a new reason episode can reuse an old same-ID pass that predates renewed partner interest. The endpoint reports `passed:true` without recording the new pass; the renewed source remains actionable. Existing focused tests pass but miss this chronology. Return to build and then perform a new independent full QA round on the repaired integrated SHA.

The initial full regression also failed because the in-memory SQLite startup schema disappeared. This is recorded separately as E-1, not mislabeled as a provider failure or an application regression. Its failing cases pass in a fresh process, and both affected files pass against a new file-backed SQLite database. A second full run is recorded below. No other application defect was confirmed in the reviewed Win Now or bounded-presentation changes. Native/operator checks remain UNRUN, not implicitly passed.

## Environment and scope

- Tested parent SHA: `aa4637899a9233a4afffca22f3f90847fca76a62`, detached, initially clean; runtime equivalent to `71b2b496`. Sole review checkout: `/private/tmp/ftf-feedback-419-421-f1uMyt/qa-b`.
- Review baseline: `4026ebc81eaae50b345b42421641125c5b8d413e`. Reviewed runtime/test diffs, relevant unchanged callers, version metadata, and synchronized API/config/data/architecture/cross-client reference changes. Marketing version is consistently `1.17.1` in Expo and both native configurations.
- Node `24.14.1`; Python `3.12.14`, executable `/private/tmp/ftf-context-venv/bin/python`. Independently installed `mobile/node_modules`, never symlinked or altered.
- Read repository/backend/mobile CLAUDE routing, coding guidelines, mobile design-system guidance, the feedback skill plus lessons and QA-phase instructions, and all three complete PRD/scope/reconciliation/build/code-walk evidence sets. Build evidence is not a QA verdict. Source instructions required static/code-walk tests plus an operator checklist, not retired simulator evidence.
- Full regression uses the normal provider posture: no global `FTF_DP_VALUES_FILE`, no conftest/default/fixture edits. The existing conftest pins only the pick curve. Focused imports use the two authorized checked-in player/pick snapshots.
- No source/test fix, private database/secret access, production action, network/provider workflow, external user/session mutation, flag activation, deployment, EAS, simulator, Maestro, or capture was performed. Synthetic Flask fixtures are local only. Parent specifically authorized fresh disposable file-backed test databases after E-1; these were validated nonexistent and are retained, not deleted.
- This report is the only repository file authored by QA-B. Its eventual report-only commit has the tested SHA above as its parent; the commit hash is supplied in the completion handoff.

## Executed results

| Check | Result | Evidence |
|---|---|---|
| Full backend, initial requested in-memory posture | FAIL: 5 failed, 5,589 passed, 1 skipped, 28 errors; 465.83 s | Session 22002; E-1 below preserves failure names and first traceback. Not replaced by another agent's count. |
| Six discriminating original failures in fresh unchanged in-memory process | PASS: 6 passed; 2.48 s | Both roster tests, first mock setup contract, and three direct mock CRUD tests; session 10749. |
| Both affected files, new file-backed database | PASS: 149 passed; 223.72 s | Session 66453, `/private/tmp/ftf-feedback-419-421-f1uMyt/qa-b-isolated.sqlite`. |
| Full backend, separately new file-backed database | PASS: 5,622 passed, 1 skipped; 367.26 s | Session 67242, `/private/tmp/ftf-feedback-419-421-f1uMyt/qa-b-full.sqlite`; same source, expectations and normal provider posture. |
| Combined 33-file focused backend contract/regression run | PASS: 869 passed; 24.88 s | Session 95033; all listed files below, including actual installed session guard, actual worker, source/reason/restoration and policy/roster suites. |
| Every mobile `check-*.js`, each in its own Node process | PASS: 95 scripts, 0 failed | Includes 28 new disposition assertions, 38 recovery assertions, and existing 28 Win Now checks. |
| Mobile `npx tsc --noEmit` | PASS, exit 0 | Session 76954. |
| `bash mobile/scripts/testid-lint.sh` | PASS, exit 0 | `testid-lint OK`; session 96225. No Maestro execution. |
| `python qa/web/check_web_structure.py` | PASS: 190/190 | DS 95, TOK 1, SEO 50, A11Y 38, HYG 6; no web UI runtime diff. |
| Unchanged #419 mobile baseline | Expected behavioral RED: 0 passed, 4 failed | Actual `git show 4026ebc8` modules; structured false/true evidence, edited echo, retained old lane. |
| Unchanged Win Now baseline | Expected behavioral RED: 0 passed, 7 failed | All seven loaded baseline module files first compared byte-for-byte with `4026ebc8`; no missing import/export counted. |
| Independent real endpoint F-1 chronology probe | DEFECT REPRODUCED | HTTP 200/`passed:true`, exactly two old decision rows remain, fresh source still actionable. Full executable repro below. |
| Diff/cleanliness check after report | PASS | `git diff --check`; only this report is untracked before staging. No application/test changes. |
| Physical device, native accessibility/visual behavior, TestFlight availability, CI/deployment | UNRUN | Explicit operator checklist below; neither build docs nor prior uploaded binary prove these. |

Commands, from the sole review checkout unless `mobile/` is stated:

```sh
DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/ftf-context-venv/bin/python -m pytest backend/tests -q -p no:cacheprovider --tb=short

DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/ftf-context-venv/bin/python -m pytest -q -p no:cacheprovider --tb=short \
  backend/tests/test_launch_qa_fixes.py::test_rosters_sleeper_404_maps_to_404_no_leak \
  backend/tests/test_launch_qa_fixes.py::test_rosters_sleeper_5xx_maps_to_503 \
  backend/tests/test_mock_draft.py::test_295_02_the_route_fixture_is_production_shaped \
  backend/tests/test_mock_draft.py::test_w2_11_only_one_active_mock_survives_per_user_and_league \
  backend/tests/test_mock_draft.py::test_292_01_abandoning_a_completed_mock_clears_the_whole_backlog \
  backend/tests/test_mock_draft.py::test_292_04_a_second_mock_creates_after_a_completed_one

test ! -e /private/tmp/ftf-feedback-419-421-f1uMyt/qa-b-isolated.sqlite && \
  DATABASE_URL=sqlite:////private/tmp/ftf-feedback-419-421-f1uMyt/qa-b-isolated.sqlite \
  PYTHONDONTWRITEBYTECODE=1 /private/tmp/ftf-context-venv/bin/python -m pytest -q -p no:cacheprovider --tb=short \
  backend/tests/test_launch_qa_fixes.py backend/tests/test_mock_draft.py

test ! -e /private/tmp/ftf-feedback-419-421-f1uMyt/qa-b-full.sqlite && \
  DATABASE_URL=sqlite:////private/tmp/ftf-feedback-419-421-f1uMyt/qa-b-full.sqlite \
  PYTHONDONTWRITEBYTECODE=1 /private/tmp/ftf-context-venv/bin/python -m pytest backend/tests -q -p no:cacheprovider --tb=short

env DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 \
  FTF_DP_VALUES_FILE=backend/tests/fixtures/outlook-hypotheses/dp-values-players-2026-08-09.csv \
  FTF_DP_PICK_VALUES_FILE=backend/tests/fixtures/dp_values_picks_2026-08-06.csv \
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

node -e 'const fs=require("fs"),cp=require("child_process");const files=fs.readdirSync("mobile/tests").filter(f=>/^check-.*\.js$/.test(f)).sort();let failures=[];for(const f of files){const r=cp.spawnSync(process.execPath,["mobile/tests/"+f],{encoding:"utf8"});process.stdout.write(f+": exit="+r.status+"\n"+(r.stdout||"").trim().split("\n").slice(-2).join("\n")+"\n");if(r.status!==0){failures.push(f);process.stdout.write(r.stderr||"");}}console.log(JSON.stringify({scripts:files.length,passed:files.length-failures.length,failures}));process.exitCode=failures.length?1:0;'

# In mobile/:
npx tsc --noEmit
# Back in the review root:
bash mobile/scripts/testid-lint.sh
/private/tmp/ftf-context-venv/bin/python qa/web/check_web_structure.py

FTF_TRADE_DISPOSITION_BASELINE=4026ebc8 node mobile/tests/check-trade-disposition.js
for f in src/api/client.ts src/api/auth.ts src/api/espn.ts src/api/platformLink.ts src/api/winNow.ts src/state/useSession.ts src/screens/WinNowScreen.tsx; do
  git show "4026ebc8:mobile/$f" | cmp - "/private/tmp/ftf-feedback-419-421-f1uMyt/419-provenance-baseline/mobile/$f" || exit 1
done
FTF_MOBILE_TEST_ROOT=/private/tmp/ftf-feedback-419-421-f1uMyt/419-provenance-baseline/mobile \
  FTF_BASELINE_ONLY=1 node mobile/tests/check-win-now-recovery.js
```

## Requirement / test code-walk

References below are at the exact tested parent SHA, not the builder's earlier line numbers. PASS means the indicated mechanical assertions and cited control flow satisfy that bounded requirement; native execution and prospective sabotage limits remain separately labeled.

### #419

| Contract/test | Verdict | Executed proof and production path |
|---|---|---|
| R1 / T1 incident | PASS | `test_trade_interest_disposition.py:49` executes the real injector with the August like/pass history and no concept evidence. `database.py:5891` normalizes UTC; `:5942` keys league/actor/oriented sets; `:5972` checks a later own or actual receiver's mirrored pass. `server.py:3583`'s injector consumes `load_recent_league_likes`, not stale raw likes. Expired/amnestied discovery does not resurrect the source. |
| R1 / T2 chronology/negative cases | PASS | `test_trade_interest_disposition.py:68`, `:79`, `:95`, `:107`, `:130`, `:165` cover immutable history, renewed source versus receiver re-like, actor/league/package/orientation controls, offset/naive/tied/malformed time and no fallback after withdrawal. `database.py:5915` normalizes before cutoff; unknown chronology is a conservative barrier; `:5931` uses normalized time plus row ID; `:5983` rejects retracted/resolved sources. No history writer is called by these readers. |
| R2 / T3 readers and queue | PASS | `database.py:6017` batches scoped history; `:6067` recent-like consumer, `:9040` exact/fuzzy mirror and `:9425` Awaiting use actionable evidence. `test_trade_interest_disposition.py:114`, `:140`, `:154` cover R4/summary inputs and known mixed player/pick anchors without inventing ambiguous owners. Queue's `server.py:14758` probe and `:14808` narrow renewal write use `database.py:5992` actual orderable intervening pass; test_calc_trade_queue covers t=0/1/2 and repeated queue with one genuine renewal signal. `test_trade_interest_disposition.py:173`, `:214` and read-amplification regressions execute batched workload/query assertions. |
| R3 / T4 exact current reason episode | FAIL → F-1 | Ordinary contextless-bank/repair, persistence-failure, edited package, replay, layer-2 and signal tests pass. However, `database.py:6776` queries same actor/league/raw trade ID only, then `:6785` accepts matching assets regardless of reason/source chronology. A new reason is falsely certified by an old episode. `server.py:15155` also consumes its Elo claim as though the old pass were the companion swipe. The missing renewed-source test is independently reproduced below. |
| R3 / T4 live binding and duplicate side effects | PASS except F-1 premise | `server.py:14954` binds exact pass keys across format services and alias; ordinary swipe calls it at `:14322`, reason calls it only after verified result at `:15142`. New pass ancillary work is gated by `wrote_pass` at `:15147`; DB transaction/claim seams at `database.py:5609`, `:6756`, `:6800` preserve existing once-only signal/outcome rules. These guards cannot compensate for F-1's false verification. |
| R3 / T5 snapshots and T8 serve wiring | PASS except F-1 missing current row | Public view `server.py:2997` projects with the captured job key (`:3028`); `:3033` batches history and owned source links, active pass keys win at `:3077`, and known source ID must remain actionable at `:3081`. A fresh same-package like cannot validate a known old source. Cache/running generate (`:13539`, `:13555`), old-ID status (`:14117`), pending cards (`:14147`), worker final cut (`:7970`) and replenishment count (`:22004`) use this boundary. Copies are taken under job lock and DB work occurs after release. `test_trade_disposition_replay.py:52`, `:84`, `:96`, `:151`, `:184`, `:194`, `:223`, `:253`, `:279` assert source/actor isolation, held worker, frozen rows and lock/placement. |
| R3 / T6 restoration | PASS | `server.py:3096` owns restoration; full init (`:20591`) and headless replenishment builder (`:21892`) use it. `database.py:5947` applies separate fractional pass/like windows and pass-only amnesty to the same normalized history, returning mixed and pass-only sets. `test_trade_disposition_restoration.py:31`, `:63` executes both builders, including day 8/day 13, fractional boundaries, seven-day likes, malformed time and amnesty controls. No permanent organic ban. |
| R4 / T7 actual identity and commitment | PASS | `tradeDisposition.ts:11` keys account/league/counterparty and separate sorted sets, not raw ID. `TradesScreen.tsx:1964` freezes the acted card; `:5849` echoes that card's actual ID and complete package. The structured adapter and `:337` observer accept only `passed === true`; `tradeDisposition.ts:31`, `:38` make successful sibling evidence sticky while keeping acknowledged ordinary swipe semantics distinct. Guard cases at `check-trade-disposition.js:64`, `:122`, `:161`, `:245`, `:290` execute these seams. Backend F-1 is a false-positive input to this otherwise correct client contract. |
| R4 / T7 panel, retry, browse and cursor | PASS | Projection `tradeDisposition.ts:52` retains held reason card and tracks original source positions; `:72` maps visible moves back. `TradesScreen.tsx:4037` applies it each render; `:5868` clears the banked marker before the single transition. `:2453` detaches failure settlement and waits for independent reason evidence, fences account/deck/latest action, then re-arms retry rather than rewinding a newer card. Browse `:6104` retains a removal receipt; `:6157` restores one failed removal in order. `:2832` flushes captured held action, `:2846` Undo writes/commits nothing. `:3659`/`:3702` retain source cursor across single-pin restoration. All 28 disposition cases plus existing browse/Undo/failure guards pass. |
| R4 / T7 scope and T8 boundaries | PASS | Module scope/epoch `TradesScreen.tsx:293`, subscription `:303`, `currentPassContext :325`, screen action fence `:1970` and newer-action map `:2480` stop A→B→A or superseded callbacks changing replacement UI. Stale failure cases `check-trade-disposition.js:297`, `:306`, `:312` execute actual onError. No persistent local ban, new flag, quality math, acceptance redesign or remote-only retained-deck claim. |

### #420–421

| Contract/test | Verdict | Executed proof and production path |
|---|---|---|
| R-1 / T1, T2, T3 repair/join | PASS | `useSession.ts:728` captures one whole attempt; `leagueSession.ts:80` joins pending work before readiness. `useSession.ts:756` matches only exact 409 error, `:758` forces one shared reconciliation and `:759` one logical GET replay, without recursion or mutation replay. `check-win-now-recovery.js:208`, `:256`, `:268`, `:281`, `:504` exercise mounted loss, pending consumers, terminal second refusal, fresh Refresh and exactly one cache-missing init retry. Physical GET retries remain the existing bounded transport behavior, not extra logical repairs. |
| R-2 / T4 normal same-token ordering | PASS | `leagueSession.ts:45` registers intent before token wait, `:41` fences account/generation/revision, `:83` captures prior lane tail, `:97` awaits acknowledgement, `:105` owns every submitted init, and `:115` guards seed/readiness. Superseded pre-dispatch work aborts at `:89`; accepted POST is not called canceled. `check-win-now-recovery.js:290`, `:301` execute both preparation and acknowledged-order cases with only B seeds. |
| R-2 / T5, T10 uncertainty/explicit authorization | PASS | `leagueSession.ts:91`, `:108`, `:120` latch unacknowledged dispatch failure; `:62`, `:75`, `:101` prevent automatic/queued continuation. Authorization is sequenced at gesture capture `:56` / Connect reservation `:135`, not when delayed target lookup resolves. `useSession.ts:653` carries that original ticket/deadline. `check-win-now-recovery.js:327`, `:354`, `:540`, `:555`, `:581` exercise repeated automatic re-entry, explicit relatch, replacement token, old Connect and picker. Shared consumer detach (`leagueSession.ts:129`) does not abort another legitimate consumer; preparation/late mirror/sign-out cases execute at guard `:311`, `:320`, `:513`. |
| R-3 / T7, T10 budgets | PASS | `client.ts:332` uses exact method/path matching; `:451` fixes a logical request deadline before preparation, `:298` bounds uncancelable waits, `:535`/`:590` recheck before dispatch/publication. `useSession.ts:729` fixes 90 s once; `leagueSession.ts:84` takes minimum captured context/caller/own deadlines. `check-win-now-recovery.js:182`, `:369`, `:385`, `:396`, `:405`, `:347`, `:524`, `:555` cover 15.2 s success, exact 30 s limit, lookalike/method exclusions, header/body/backoff, suspended JS and composed 90 s expiry. Ordinary 15 s and existing slow POST 30 s controls pass. |
| R-4 / T3, T8 current failure versus stale failure | PASS | Exact neutral timeout text `client.ts:287`, typed status 0/timeout error, and silent caller abort in `:298`. Current 401 gets only its own from→to revision receipt (`:209`, `:607`); `useSession.ts:768` preserves that error without admitting unrelated replacement. Stale 403 is fenced before shared callback `client.ts:633`, not merely after screen rejection. `WinNowScreen.tsx:90` owns existing loading/error/Refresh and cleanup. Actual mounted/picker/resync/current/stale401, secure-delete replacement and 403 tests `:418`, `:431`, `:445`, `:454`, `:462`, `:471`, `:485`, `:494` pass. |
| R-5 / T6, T8, T9 server/native safety | PASS | `test_verified_sessions.py:538` uses the installed real restoration/initialized-session guard, asserts exact 409 before init and zero forecast calls, then authorized initialized result. Persistent sessions and Win Now API/service suites run, not only a ready-session fake. `WinNowScreen.tsx:111`, `:125`, `:128`, `:132`, `:169`, `:176` retain title/source expiry/search/decision gates and operation epochs. Existing Win Now guard passes all 28 checks. No backend Win Now protocol or model diff. |
| R-6 / T5, T8, T12 observability/privacy | PASS | Outer `client.ts:451` reports once per logical request; request guard/consumer abort ensures obsolete failures are silent. `useSession.ts:744` subscribes to supersession. `check-win-now-recovery.js:431`, `:626` execute no stale failure event, caller-abort exclusion, normalized route, omitted background duration and exact bounded fields. No token/coordination/private ranking values are persisted or emitted by the new lifecycle. |
| R-7 / T11, T12 integration | PASS | `useSession.ts:694` is the one owner. Foreground, switch and Connect call it; picker (`LeaguePickerScreen.tsx:436`) awaits context/init before selecting/Main, resync (`LeagueScreen.tsx:156`) coordinates only its existing init leg and fences messages/busy/refetch. `auth.ts:258` requires control, `:268` submits through it, `:311`/`:333` fence late verification; imported branches (`:421`, `:449`) precede account-only Sleeper refusal. Real imported ESPN/MFL/Fleaflicker builders and sentinel refusal execute at guard `:606`; picker/resync and writer census at `:567`, `:592`, `:636`. API→state upward import remains absent; no layout/navigation route, feature flag, backend Win Now runtime, schema or source contract changed. |

### Bounded smaller-player packages

| Contract/test | Verdict | Executed proof and production path |
|---|---|---|
| R1 / T1, T3 eligible-only | PASS | `server.py:7852` requires captured mode, successful live market policy, no explicit exemption/ghost/pins/opponent and no served single arm. `small_trade_presentment.py:57` requires eligible result and valid actual source/group metadata. Tests `test_small_trade_presentment.py:100`, `:218`, `:416` exercise real grouped and group-size-zero workers, both formats, F1 on/off and every exclusion. T1 moves early player total 16→7 while preserving A/B/C slots and all six packages. |
| R2 / T1, T2 fixed permutation | PASS | Helper `:119` walks disjoint six absolute slots, groups identical full class (`:93`), then stable-sorts only those indices by max/total player counts (`:125`). No compaction/global/sliding sort, rank in class, generator mutation or dedupe. `:130` returns original object occurrences. Property test `:136` checks >12-card windows, holes, max displacement ≤5, stable ties, classes and multiset/idempotence before the later #419 removal. |
| R3 / T2, T3 player/pick/metadata classification | PASS | Helper `:25` validates both sides; generic and league-aware owned picks count zero, conflicting/unknown/malformed assets are unknown. `:112` locks unknown/pure-pick and all actual special markers, including `fatigue_retest`. `:67` demands attribution and required group only when expected; null group is legal when grouping is off, and credit is actual full arm. Tests `:167`, `:174`, `:188`, `:209`, `:218` exercise controls and mixed packages; picks do not break player-count ties. |
| R4 / T4, T5 captured mode/reuse | PASS | Exact finite numeric 1 only in helper `:18`; `server.py:3119` captures mode/version/base once; kickoff `:8234` stores at `:8284` and forwards at `:8310`/`:8322`. Completed/running cache checks (`:13539`, `:13555`), pregen (`:21162`) and replenishment (`:21977`) all compare capture. Tests `:296`, `:322`, `:354`, `:372`, `:395` execute hot flips and all reuse boundaries. Old-ID public reads filter dispositions only; they never invoke the helper. |
| R1, R4, R7 / T3 raw receive flag-off edge | PASS | Generate records raw request exemption before normalized receive targeting can disappear (`server.py:13528`). Mode-on exempt request bypasses otherwise organic cache (`:13529`) and kickoff avoids seeding shared organic index (`:8292`). `test_small_trade_presentment.py:480` exercises completed/running organic cache, both knob modes and raw receive shapes. Normalization/fairness/payload behavior remains unchanged; helper also sees the explicit exemption. |
| R5 / T4 one first publication | PASS | Sole helper call `server.py:7857` precedes first evaluated snapshot `:7868`. Final authoritative #419 cut `:7970` is removal only; `:7988` republishes final filtered list even when F1 is off. Subsequent serialization/impression paths consume that list. Held-worker test `:237` asserts helper count one, first-publication order and late pass removal across F1/telemetry combinations. No refill or final survivor re-sort. |
| R6 / T5, T6 frozen occurrence provenance | PASS | `small_trade_presentment.py:104` records each original occurrence; `:133` remaps survivors using order+identity, retaining repeated-object and distinct same-shape occurrences. `server.py:7972` applies it before writer enumeration; writer `:4891` uses final actual index and keeps source/group rank, true propensity, agreement and valuation variant, with separate serving version (`:4982`, `:5022`). Tests `:237`, `:296`, `:456` assert legacy/F1 position agreement, duplicate records, unknown first row, captured stamps and frozen rows after later poll removal. Existing telemetry gates remain at `:4724`; mode-on does not activate candidate/ghost telemetry or expose private values. |
| R7 / T7, T8 unchanged policy/supply/integration | PASS, integrated release still blocked by F-1 | Only neutral default registrations at `database.py:2942` and `trade_service.py:1293`, both 0.0. No arm reads the knob and no generator/price/quality threshold changed. Off/exempt serialized and frozen payload parity tests, arm A goldens, bakeoff composition/accounting, engine quality, policy/roster and standing-offer suites pass in the 869-test run. Larger packages remain present, not capped. Corpus shape diagnosis is conditional diagnostic evidence, not an acceptance or production-shape guarantee. |

## Findings

### F-1: Old pass is reused as proof of a new reason episode after fresh partner interest

- Severity: **major / release-blocking**.
- Contract: #419 R3 explicitly requires the durable pass for **this reason episode** and forbids unrelated historical pass evidence; R1 permits a deliberate later source like to become fresh interest.
- Exact cause: `backend/database.py:6776` selects active passes by actor, league and trade ID, and `:6785` returns `(True, False)` on matching oriented assets. It never compares the reason/impression episode, reason creation time or current source chronology. The inserted pass (`:6791`) also carries no link to that reason identity. `backend/server.py:15136` trusts this answer and `:15155` consumes the new reason's Elo claim as an already-supplied companion swipe.
- Repro: in the existing isolated reason-route harness, seed receiver B's pass on `trade_abc` at now−20 days; seed A's fresh mirrored like one minute before now; seed a new owned impression for the same B trade ID; POST layer-1 value reason using the new impression with no companion swipe. This is a valid distinct new episode, not a replay of the old pass.
- Expected: a new durable B pass after the renewed source, `passed:true` only after that commit; renewed A like then disappears from actionable-source readers. Subsequent retries of this new episode must not repeat decision/outcome/Elo/event work.
- Actual at tested SHA: HTTP 200 `{detail:null, elo_written:false, ok:true, passed:true, reason:"value", switched_from:null}`. Decisions remain exactly the original old pass and new source like. `load_recent_league_likes` returns `fresh_source` both before and after. The in-memory bind/local mask can temporarily hide the failure, but restored services/future generation have no current pass to suppress or resolve renewed interest.
- Independent run: session 9536 printed actual module path `/private/tmp/ftf-feedback-419-421-f1uMyt/qa-b/backend/database.py`; the old pass was `2026-08-17T16:10:57.700447+00:00`, fresh like `2026-09-06T16:09:57.700447+00:00`, response at approximately 16:10:57 UTC. No runtime or test mutation was needed.
- Existing test gap: successful old-pass/same-episode idempotency controls do not distinguish an old pass belonging to a prior episode from a fresh reason after renewed source consent. Add the above chronology with changed/new source evidence and prove one new pass plus idempotent retry. A green count alone does not satisfy R3.
- Shared references now promise verified exact pass semantics (`docs/api-reference.md`, `docs/architecture.md`); this runtime divergence is F-1, not a reason to weaken those contracts. No other concrete synchronized-reference divergence was confirmed.

Executable repro (same focused snapshot environment shown above; all identities are existing synthetic fixture labels):

```python
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import insert
from backend.tests import test_decline_reasons as t
from backend import database as db

mg = t.mem_engine.__wrapped__(); eng = next(mg)
hg = t.harness.__wrapped__(eng); client, service, svc, _ = next(hg)
try:
    now = datetime.now(timezone.utc)
    with eng.begin() as conn:
        conn.execute(insert(db.trade_decisions_table).values(
            user_id=t.ME, league_id=t.LEAGUE, trade_id=t.TRADE,
            give_player_ids=json.dumps(['g1']), receive_player_ids=json.dumps(['r1']),
            decision='pass', created_at=(now-timedelta(days=20)).isoformat()))
        conn.execute(insert(db.trade_decisions_table).values(
            user_id=t.OPP, league_id=t.LEAGUE, trade_id='fresh_source',
            give_player_ids=json.dumps(['r1']), receive_player_ids=json.dumps(['g1']),
            decision='like', created_at=(now-timedelta(minutes=1)).isoformat()))
    t._seed_impression('fresh_reason', t.TRADE, card_index=1)
    before = db.load_recent_league_likes(t.LEAGUE, t.ME)
    response = t._post(client, t._reason({'reason':'value', 'impression_id':'fresh_reason'}))
    after = db.load_recent_league_likes(t.LEAGUE, t.ME)
    rows = t._decision_rows(eng)
    print(db.__file__, response.status_code, response.get_json())
    print('before/after live sources:', before, after)
    assert response.get_json()['passed'] is True
    assert len(rows) == 2 and len(after) == 1  # observed defective behavior
finally:
    hg.close(); mg.close()
```

### E-1: Initial full regression lost in-memory startup schema (environment/isolation)

This is a separate failed-run record, not a second confirmed application finding. The run has 33 real pytest failures/errors in addition to expected non-fatal isolated receipt-worker diagnostics; the latter were not used to excuse the former.

First setup traceback: `backend/tests/test_mock_draft.py:1032` → `_abandon_all_mocks :971` → `backend/database.py:14377` executes SELECT from `mock_drafts` and raises `sqlite3.OperationalError: no such table: mock_drafts`. Both roster assertion failures trace `server.py:20074` → `database.py:8662` SELECT `leagues.platform`, raising `no such table: leagues`; the response becomes 500 instead of expected 404/503. The three direct mock failures likewise lack `mock_drafts`. No listed failure is a changed player-curve/value assertion or external-provider refusal.

The actual global engine uses `sqlalchemy.pool.impl.SingletonThreadPool` (`backend/database.py:62`), independently inspected in the installed runtime. Its `_cleanup` pops and closes a connection while the connection set has reached its configured size; in-memory SQLite schema is per connection. Startup `server.py:459` calls `database.init_db :3928` once, while the affected mock fixture (`test_mock_draft.py:996`, `:1032`) and roster fixture (`test_launch_qa_fixes.py:32`) rely on that startup database instead of creating their own schema. Existing test dispose sites inspected create/dispose fixture-local engines; no direct `db.engine.dispose()`/`drop_all` global reset was found. Connection eviction amid background threads is the supported isolation diagnosis; the exact eviction event was not instrumented, so it is not claimed as a captured trace.

Evidence distinguishing environment from app logic: the same six representative failures pass immediately in a fresh unmodified in-memory process; all 149 tests in the two affected files pass against a newly created file-backed DB. QA-B's separate full file-backed run then passed **5,622 tests, with 1 skipped, in 367.26 s**, retaining normal provider/default posture. The one skip was reported by pytest; the requested quiet command did not expand its reason, so no reason is inferred here. Parent/root and QA-A full-suite green results were reported contextually, never substituted for this agent's own failed/passing runs. No source, conftest, expected value or test was changed to silence the error. Non-fatal fixture-isolated receipt-worker diagnostics also appeared during the passing file-backed run, confirming those log messages alone do not determine pytest failure.

Initial failure inventory:

```text
FAILED test_launch_qa_fixes.py::test_rosters_sleeper_404_maps_to_404_no_leak
FAILED test_launch_qa_fixes.py::test_rosters_sleeper_5xx_maps_to_503
FAILED test_mock_draft.py::test_w2_11_only_one_active_mock_survives_per_user_and_league
FAILED test_mock_draft.py::test_292_01_abandoning_a_completed_mock_clears_the_whole_backlog
FAILED test_mock_draft.py::test_292_04_a_second_mock_creates_after_a_completed_one
ERROR test_mock_draft.py::test_295_02_the_route_fixture_is_production_shaped
ERROR test_mock_draft.py::test_w2_01_flag_off_404s_every_mock_route
ERROR test_mock_draft.py::test_w2_01_unknown_league_is_404
ERROR test_mock_draft.py::test_w2_01_bad_basis_is_400
ERROR test_mock_draft.py::test_w2_12_route_rejects_a_startup_shaped_round_count
ERROR test_mock_draft.py::test_w2_12_route_serves_the_typed_empty_when_the_class_is_not_loaded
ERROR test_mock_draft.py::test_the_abort_criterion_is_enforced_at_the_route
ERROR test_mock_draft.py::test_get_with_no_mock_is_a_typed_empty_not_a_404
ERROR test_mock_draft.py::test_pick_and_abandon_reject_a_mock_that_is_not_the_callers
ERROR test_mock_draft.py::test_w2_20_g1_the_real_order_and_traded_picks_come_off_the_lakeview_corpus
ERROR test_mock_draft.py::test_w2_20_g1_a_non_sleeper_league_stays_randomized_rather_than_guessing
ERROR test_mock_draft.py::test_w2_20_g1_personas_resolve_declared_then_inferred_then_default
ERROR test_mock_draft.py::test_w2_20_g2_the_capability_probe_answers_without_starting_a_mock
ERROR test_mock_draft.py::test_290_13_no_player_lookup_uses_an_uncrosswalked_id
ERROR test_mock_draft.py::test_295_01_the_user_is_in_their_own_mock_end_to_end
ERROR test_mock_draft.py::test_295_03_an_assigned_order_sizes_the_draft_not_owners
ERROR test_mock_draft.py::test_295_04_randomized_platform_branches_include_the_user
ERROR test_mock_draft.py::test_295_07_create_and_resume_build_identical_rostered_ids
ERROR test_mock_draft.py::test_295_08_the_probe_counts_the_caller
ERROR test_mock_draft.py::test_295_09_a_sessionless_user_id_is_refused_not_phantomed
ERROR test_mock_draft.py::test_295_13_the_engine_raise_maps_to_the_typed_empty_not_a_500
ERROR test_mock_draft.py::test_305_01_manual_create_stops_at_pick_one
ERROR test_mock_draft.py::test_305_02_a_full_manual_lap
ERROR test_mock_draft.py::test_305_03_bad_mode_400_and_absent_null_empty_default_to_cpu
ERROR test_mock_draft.py::test_305_04_the_guard_is_mode_blind
ERROR test_mock_draft.py::test_305_05_a_pre_mode_row_resumes_byte_identically
ERROR test_mock_draft.py::test_305_06_every_state_payload_carries_mode_and_user_owner_id
ERROR test_mock_draft.py::test_305_07_manual_mode_never_consults_the_rng
```

## Evidence honesty and held limits

The feedback skill normally requires meaningful sabotage RED evidence. Parent explicitly prohibited repeating or bypassing the earlier denied temporary source-disabling mutation and authorized unchanged original-runtime evidence instead. QA-B performed no disabling/deletion/in-memory sabotage. Four #419 and seven Win Now baseline failures were independently rerun after actual module checks. Win Now failures were 15.2 s timeout, stale verification callback (1 instead of 0), old wake-up copy, missing mounted 409 repair (one instead of two init requests), premature pending-init completion, B-before-A-ack dispatch, and automatic restart after ambiguous init. No absent export/import is counted as RED.

Reviewed build evidence additionally records original backend #419 failures and 26 package plus two raw-receive original-defect failures, and implementation-regression RED→GREEN cases. These are **builder-recorded**, not newly executed by QA-B. The proposed guard-removal, global/sliding-sort, timer-reset, wrong-class, shared-controller and other individual PRD sabotage variants were not all executed; no blanket mutation-coverage claim is made. The new installed backend guard test is a passing preservation test, not a claimed guard-removal RED. Native behavior is tested via actual transpiled helpers/transport/state, an effect harness and extracted handlers, not a device or full React Native renderer.

Intentional held boundaries are not new findings: remote-only invalidation of an already retained mobile deck without local pass evidence; standing-offer/post-match lifecycle; ordinary swipe best-effort persistence; no server cancellation/CAS/final-writer guarantee after an ambiguously accepted init; no unconditional ordering/cancel of native storage writes already dispatched; and the corpus's conditional-shape diagnostic status. No UI redesign or web runtime was introduced; no web server/browser flow was required beyond the passing structure checks.

## Consolidated TestFlight checklist — UNRUN, operator-run

Owner authorization permits unattended shipping **after QA**; it does not fabricate physical-device evidence. Record actual device/OS/build, backend SHA, controlled test configuration and sanitized outcomes for every item. Use only authorized synthetic/staging accounts and fixtures; do not propose a real platform trade, mutate real memberships or restart production merely to test.

1. **Acquire → In league builder → Find a Trade → Trade ideas:** seed #419's old-like/later-pass incident. Fresh results, cached reopen and old job polling must contain no interested card/boost from the resolved source. Any eligible fresh organic same package is unbadged; a different-package control remains possible.
2. **Trade ideas → card ✕ / reason overlay:** fresh partner like, then Value/Fit/Neither layer 1; separately each layer-2 select/bank/text/send and dismiss path. The current panel stays on its card until the one existing transition, then exactly the immediate next card appears. Repeat final card and earlier-masked siblings; no double advance.
3. **Trade ideas → edit package → pass:** verify actual edited ID/assets/counterparty/league in sanitized fixture evidence. Switch Value/Outlook/All, Find more, Back/reopen, scoring format and single-pin/restored source deck. Committed edited package never re-fronts; raw unedited package and different counterparty are not banned just by shared display ID.
4. **Trade ideas → pass, controlled reason/swipe response permutations:** reason `passed:true` plus failed/late-failing swipe remains committed with no rollback/toast; later false/missing refinement cannot clear it. Both writes fail, or `ok:true/ passed:false` plus failed swipe: normal retry controls work. Older failure cannot undo a newer action or rewind a later fronted card.
5. **Controlled canvas-results browse mode → calculator action-row ✕:** pass middle and final idea, finish/dismiss reason, verify count/tally and sibling order. Total failure restores the removed row exactly once and retry works. With reason capture disabled this cell is Clear, not a dead decline button.
6. **Trade ideas, reason capture off and existing Undo enabled:** pass then Undo within the held window. No pass POST/history row or committed local exclusion; original card actionable. Repeat without Undo after hold expiry. This does not claim an unswipe of a dispatched/durable pass.
7. **Trade ideas → switch account/league A→B→A while requests wait:** late success/failure must not change replacement cursor, reason panel, guard, toast or mask. Separately hold a worker after evaluated publication, pass, release and poll old ID after league switch: correct captured job league only, no frozen-index rewrite.
8. **Controlled backend reason-only renewal fixture → Trade ideas:** old same-ID pass → fresh partner like → new owned impression/reason with no companion swipe. After F-1 is repaired, verify one new current durable pass, renewed source resolved, then same-episode retry adds no decision/outcome/Elo/event. Also contextless bank → valid-context retry after service loss, both orientations and eight/thirteen-day restoration; ordinary cooldown/amnesty remains unchanged.
9. **Calculator ✓ / counterparty Trade ideas:** source requeues after exact pass inside ten seconds. Exactly one new source/like signal; immediate retry is idempotent. Receiver re-like alone cannot revive old source; deliberate new source like can. No automatic mutual match from rejected historical evidence.
10. **League → season projections / Acquire → Win Now:** enter immediately while initialization is deliberately slow. Loading and Back stay usable; acknowledged init produces available standings or the actual typed refusal without another tap. Repeat cold launch and foreground.
11. **Win Now → Refresh after controlled staging session-context loss:** retained signed-in session gets exact missing-context 409, one forced shared repair and one logical GET replay. A second refusal ends loading; Refresh starts a new bounded attempt. No sign-out requirement, recursion or write/scenario replay.
12. **Win Now repair → league picker / Back / sign-out and new test login:** delay A before dispatch, then separately after accepted successful dispatch. B is the only visible completion and its POST follows A acknowledgement. Old cache, navigation, busy cleanup, verification 403, token-clearing 401 or error cannot affect replacement identity; current 401 still shows sign-in error and releases loading.
13. **Win Now ambiguous init → Back/reopen/foreground:** no automatic init/projection chain resumes, even after throttle expiry. A new explicit Refresh/selection after uncertainty permits one bounded attempt; a gesture begun before uncertainty does not. Another ambiguous failure relatches; a genuinely replacement token may use its own lane. No claim that the app canceled or finally ordered the already accepted server request.
14. **Win Now controlled delay/errors:** approximately 16-second projection succeeds; 30-second logical GET and 90-second whole attempt terminate with “This request took too long. Please try again.” and enabled Refresh on active-runtime resume. Token/provider/body/repair waits consume the same original deadline. Blur produces no late alert or failure event. Typed unavailable/source/live-week, verification, 503 and offline remain truthful, never zero/stale standings or enabled search; restored network + Refresh recovers. Check VoiceOver/Dynamic Type for loading/error/Refresh/Back.
15. **League picker → actual imported ESPN/MFL/Fleaflicker league with account-only test identity; League Home → ESPN resync:** real league initializes with its platform builder, not Sleeper lookup; sentinel no-league does not request protected data. Resync does only its existing import and coordinated init, with current timeout/refusal releasing busy state. Check picker retry and no stale success navigation.
16. **Acquire → Find a Trade, controlled six-card organic package fixture:** mode 1 yields T1's checked early three shapes in both formats, while scrolling finds all larger packages unchanged. Pick-heavy mixed packages are not player-heavy; pure-pick/special/unknown and class positions stay fixed. F1 logging on/off must not change served order; no new panel/badge/value display.
17. **Builder explicit SEND, GET, named partner, calculator edit and More Offers:** no smaller-package preference is applied. Include raw GET selection with receive-targeting disabled and existing organic mode-on cache: exempt result does not reuse/seed that organic cache. No price, normalization, fairness or eligibility change.
18. **Retained Trade ideas deck while staging presentation knob flips 0→1→0:** old-ID/retained order stays captured, fresh organic job takes new mode. Pass after first publication removes only that package without re-sort/refill; final survivor indices and duplicates' occurrence records match actual logged final positions, and later poll removal never rewrites frozen rows. Operator activation/rollback is separately authorized and recorded, not performed by this QA report.
