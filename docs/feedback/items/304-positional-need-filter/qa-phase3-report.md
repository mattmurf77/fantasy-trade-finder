# Phase-3 QA verification — 2026-08-16 feedback wave (integration)

> Static post-merge verification of branch `feedback-2026-08-16-integration`
> (7 groups, 17 items; all group branches merged; full suite green before this
> pass: 3046/0 pytest, tsc clean, 47/47 structural). Scope per D-056/D-057: no
> Maestro, no simulator — requirement→evidence coverage on the MERGED tree plus
> the cross-group seams no per-group agent could see. Report only; nothing
> fixed. All line numbers are against merged HEAD `0feda15`.
>
> Bottom line: **no merge broke anything** — every cross-group seam is clean
> and all 90+ requirements across the seven groups have implementing code on
> the merged tree. Findings are coverage gaps, ship-time actions, and doc
> drift, not regressions. Nothing here blocks the integration branch.

## Verdicts

| Group | Items | Verdict |
|---|---|---|
| G1 (calc) | #303 #306 #320 | **CLEAR** — 13/13 requirements verified; merge byte-identical to branch tip on every G1-owned file |
| G2+G3 (mock draft) | #322–#327, #328 | **CLEAR** (one LOW note, F-11) — 30/30 requirements verified; suites re-run green on merged tree (138/138 pytest, 3 structural suites) |
| G4 (offer prefill) | #330 | **FINDINGS (LOW)** — 10/10 requirements verified; one clearing gap (F-4) |
| G5 (ESPN identity) | #321 | **FINDINGS (MEDIUM)** — 11/12 rows verified; R9 shipped with zero test coverage (F-1), release-cutoff literal still provisional (F-2) |
| G6 (presentment) | #304 #336 #339 #340 #341 | **FINDINGS (LOW–MEDIUM)** — 11 verified, 2 PARTIAL by disclosed design (R11 prod replay, R12 tuning owed); consensus `_emit` hook untested (F-5); stale code-walk row (F-6) |
| G9 (matches) | #334 #335 | **FINDINGS (LOW)** — 12/12 requirements verified; `hideKey` add-site unpinned by any test (F-7) |

Note on item mapping: **#336 (exclude actioned trades) is implemented and tested
in G6** (R4: windowless awaiting/matched exclusion, `backend/server.py:4942-4969`,
`backend/tests/test_presentment_rules.py:675-768`), not in G9 — the G9 PRD covers
#334/#335 only. No item is uncovered; the wave's own folder layout
(`docs/feedback/items/336-exclude-actioned-trades/status.md` → points at G6) agrees.

## Findings by severity

### MEDIUM

- **F-1 (G5): PRD R9 shipped with no automated coverage.** The wrong-account
  reconnect nudge (copy + `meta.reason`, `backend/server.py:17299-17319`) and the
  identity-aware roster-sync sweep (`backend/server.py:17379-17390`) have zero
  assertions — `backend/tests/test_roster_history.py:440-456` exercises only
  `reason="expired"`. Also untested: builder deviation #4 (membership read
  refused → conclusive mismatch, `backend/server.py:20660-20664`). Code is
  present and correct-by-read; a regression here would be silent.
- **F-2 (G5): release-cutoff literal is provisional.** `backend/database.py:2160`
  `_ESPN_VERIFIED_AT_RELEASE_CUTOFF = "2026-08-17T06:00:00+00:00"` — flagged in
  `docs/feedback/items/321-espn-token-bleed/status.md` as FINALIZE AT SHIP. If
  deploy lands after that instant, dishonest pre-release stamps survive the
  eviction migration and #321 re-opens for those rows. Operator ship-time action.
- **F-3 (G6): R11/R12 evidence is owed, not on the tree.** The D-055 bars were
  never measured on production state (build env blocked; local all-consensus DB
  has no divergence boards, so R1/R2 flag-ON kill bands are unmeasured there),
  and `pick_gap_frac`/`pick_gap_min_value` ship at unmeasured defaults. Both are
  disclosed (`status.md:10`, `living-memory/NEXT.md` 2026-08-16 items,
  TEST_LEDGER) — listed here because the flag ships ON.

### LOW

- **F-4 (G4): `scopedEmpty` not cleared on fairness toggle.**
  `mobile/src/screens/TradesScreen.tsx:851-868` (`handleToggleFairness`) clears
  `deck`/`job`/`deckFailure` (:860-864) but never calls `setScopedEmpty(null)`,
  though PRD R-6 says it clears wherever `deckFailure` clears (the other four
  sites do: :837, :1610, :1675, :2231). Effect: after a scoped zero-result,
  toggling fairness leaves the stale "No trade found" card until the next
  search. Same function also nulls `job` without bumping `deckEpochRef` —
  spec-consistent per the PRD's scope note, but it is the one reset path
  outside the epoch guard.
- **F-5 (G6): consensus-path presentment hook untested.** The `_emit` hook
  (`backend/trade_service.py:4412-4414`) is live but every engine fixture in
  `test_presentment_rules.py` uses `has_rankings=True`; deleting the hook keeps
  all G6 tests green. Coverage rests on code-walk row CW-1/4 alone.
- **F-6 (G6): `code-walk-proof.md:25` is stale on the merged tree.** It claims
  gen-v2 inherits "R4 only", but merged `backend/trade_gen_v2.py:207` / `:239`
  carry independent ports of the #341/#340-adjacent rules (`g6_pos_net_ok`,
  `g6_pick_gap_ok`) behind separate knobs (`gen2_g6_net_position_cap`,
  `gen2_pick_band_frac`, `trade_service.py:555,560`) — a pre-existing parity
  port from main acknowledged at `trade_service.py:549-551`/D-062, not a merge
  drop, but now two sources of truth for two rules and a code-walk that no
  longer describes the tree.
- **F-7 (G9): the `hideKey` *add* is unpinned.** Tests pin unhide ordering and
  the filter (`check-awaiting-dismiss.js` #26-#29) but no test asserts the
  tap-time `hideKey(...)` calls (`MatchesScreen.tsx:462`, `:510`) exist —
  deleting both leaves all 51 checks green, silently reverting #334's fix.
- **F-8 (G5, docs): stale "Known residual (2026-08-12)" text survives at
  `docs/integrations/espn.md:259`** — R4 closed it; the api-reference copy was
  correctly deleted, this one wasn't swept. Also `espn_connect_store_rejected`
  is missing from `docs/business/analytics/2026-07-17-tracking-plan-v2.md`
  (open ship-time remainder per the group's own status.md:141).
- **F-9 (G1, docs): stale post-graduation comments** describe the retired
  `aggregate_tier_labels` gate as live in
  `mobile/src/screens/LeagueSummaryScreen.tsx:859,1081,2177,2530` — comment
  drift only (that screen keys on field presence; fields now always present).
- **F-10 (G6, wording): two PRD clauses read stricter than the code** — kill
  counters log only when `trade.presentment_rules` is ON (`server.py:5538`),
  not "always"; the R10 no-contract-change test asserts card key-sets, not enum
  values. Neither is a behavior defect.
- **F-11 (G2): taxonomy side of R-15 untested.** `check-mock-g2-ui.js:332`
  pins the screen's three `track` names, but no backend test asserts
  `mock_team_sheet_opened`/`mock_pool_filtered`/`mock_pool_searched` in
  `ALLOWED_CLIENT_EVENTS` + props maps — a merge-dropped registration would
  have gone green (the G-031 silent-drop-behind-a-200 class). G3 pins its own
  taxonomy side twice (`test_mock_pick_ownership.py:640`,
  `test_mock_draft.py:3086`); mirroring that for G2's three names is the
  cheap fix. Registration itself is verified present
  (`analytics_taxonomy.py:283, 955-958`). Related minor: G2-R10's sheet
  *content* (two sections, power-rankings source) is TestFlight-only — the
  structural suite pins the shell.

## Cross-group seam checks (all CLEAR unless noted)

| Seam | Method | Result |
|---|---|---|
| (a) `backend/server.py`, 4 groups | Scripted: every added line from each branch (vs common base `96f6945`) located in merged HEAD and its enclosing `def` compared to the branch's; then every branch-deleted line checked for resurrection (filtered to lines absent from the branch tip) | **CLEAR** — all additions survive in the same function; zero resurrected deletions (G1's `variant_for` guard is gone; remaining `aggregate_tier_labels` refs are comments/tests only) |
| (b) `mobile/src/screens/LeagueSummaryScreen.tsx` | `git diff feat/fb330-offer..HEAD` on the file = empty; G1 branch diffstat confirms it never touched the file | **CLEAR** — merged file byte-identical to G4's branch; G4's edit is confined to `handleRowAction` (:1173-1193, setHandoff + dep-array `selected`); single commit `154c211` is the only writer since merge-base |
| (c) `backend/analytics_taxonomy.py` | Union check: every `+` line from both contributing branches (`feat/fb321-espn`, `feat/fb322-draftui` — the only two that touched the file) grep-verified in merged file | **CLEAR** — G2's `mock_team_sheet_opened`/`mock_pool_filtered`/`mock_pool_searched` (names :283, props :955-959), G3's `ownership_source` prop (:931-936), G5's `espn_connect_store_rejected` (name :104, props :688 `{reason, source, saw_otp}`) all intact, names AND props |
| (d) `mobile/package.json` scripts | Parsed merged scripts block; diffed vs base; existence-checked every referenced file | **CLEAR** — 8 new scripts this wave (G1×4, G4×2, G2's `test:mock-g2-ui`, G5's `test:espn-wrong-account`), every referenced file exists; G9 deliberately added none (its two suites run via the CI glob `.github/workflows/ci.yml:42`). The wave brief said "six" — the tree has eight, all valid |
| (e) `_DEFAULT_CFG` keep-both | Parsed the full literal `backend/trade_service.py:40-599` (184 keys) plus `mock_draft_service.py:152` and `ranking_service.py:55` for repeated key strings | **CLEAR** — zero duplicate keys in any literal; G6's 7 new knobs each appear exactly once (and once each in the DB seed `database.py:2125-2131` and `docs/config-reference.md`) |
| (f) `mock_draft_service.py` G3+G2 chain | Direct read of merged `state_payload` | **CLEAR** — `picks[].tier` emitted at `backend/mock_draft_service.py:1440-1443` AND `settings_echo.ownership_source` at `:1464` coexist in the same payload dict (:1445-1480) |

## Copy consistency

- **"≈N firsts" labels:** single producer — `_aggregate_pick_label`
  (`backend/server.py:845`, format `≈{N:g} firsts`). Both consumers render the
  server string verbatim (`InLeagueCalculator.tsx:191-198,666-682`;
  `LeagueSummaryScreen.tsx:1085-1087,1957`) — divergence impossible by
  construction. Per-asset `TierBadge` labels ("4+ 1sts" ladder) are a distinct,
  documented vocabulary (per-asset vs aggregate), not a contradiction. The
  aggregate-label invariant was added to `docs/cross-client-invariants.md` by
  integration commit `0feda15`, closing G1's proposed-doc item.
- **Honest-empty copy (G4 vs G9):** no contradiction. G4's scoped card
  (`TradesScreen.tsx:5913-5921`: "No trade found" / "…Your player and team
  stayed locked." / "Back to league rankings") and G9's Matches zero states
  ("No mutual matches yet", "No pending trades.") share tone (honest, no
  fabricated counts). Pre-existing nit, not wave-introduced: the two Matches
  empty titles are internally inconsistent on end-punctuation.

## Doc sync (scope.md "updated" claims vs merged tree)

| Group | Claimed rows | Verified on merged tree |
|---|---|---|
| G6 | api-reference behavior note; architecture lifecycle; glossary ×3 terms; config-reference 7 knob rows + flag row; runbook tripwire; LLD | All present (`docs/config-reference.md:186-190,659`; presentment hits in all six files; knob-row cross-check above) |
| G5 | api-reference `/api/espn/link` + `/import` contract (incl. residual-sentence deletion), data-dictionary `verified_at` addendum, runbook cohort re-sign-in | All present (`api-reference.md:574,578`; `data-dictionary.md:894`; `runbook.md:844`); residual text gone from api-reference — but see F-8 for the unswept copy in `docs/integrations/espn.md` |
| G2 | api-reference `picks[].tier`; architecture `tier_for_elo` amendment; invariants tier-enum consumer | All present (`api-reference.md:552`; `architecture.md:135`; `cross-client-invariants.md:9`) |
| G3 | api-reference `settings_echo.ownership_source` + resolution + probe-absence; architecture/HLD wiring; invariants closed-vocabulary section; glossary "Ownership source"; DECISIONS D-063; LLD | All present (`api-reference.md:552,556,558`; `architecture.md:135`; `cross-client-invariants.md:663`; `glossary.md:66`; `living-memory/HLD.md:134`; `DECISIONS.md:653`; `LLD.md:235`) |
| G4 | LLD handoff-contract line (others n/a) | Present (`living-memory/LLD.md:247-253`) |
| G9 | All n/a | Consistent — G9 merge diffstat touches no backend/doc-reference files |

No merge dropped a doc hunk.

## Per-group requirement coverage

### G1 — #303/#306/#320 (spec: `wave-calc:docs/feedback/items/303-calc-send-placement/plan-2026-08-13.md`) — CLEAR

| R | Requirement | Code evidence | Test evidence |
|---|---|---|---|
| G1-R1 | Send button after eveners, before verdict; single mount | `InLeagueCalculator.tsx:766→794-796→816` | `check-calc-send-placement.js:40-57` |
| G1-R2 | Only send moves; Share/Clear stay end-of-flow | `InLeagueCalculator.tsx:856,884`; guard :794 | `check-calc-send-placement.js:60-81` |
| G1-R3 | `aggregate_tier_labels` guard removed; labels emit ungated | `backend/server.py:21652-21692` (no `variant_for` anywhere in server.py) | `test_power_rankings.py:814-880` |
| G1-R4 | Additive `picks.value_label` = literal #285 count | `backend/server.py:21687-21693` | `test_power_rankings.py:905-946` |
| G1-R5 | Chips label-first, numeric only as fallback | `InLeagueCalculator.tsx:100-103,191-198,666-682` | `check-calc-partner-labels.js:44-100` |
| G1-R6 | a11y speaks the same labels | `InLeagueCalculator.tsx:634-639,651` | `check-calc-partner-labels.js:58-77` |
| G1-R7 | `/api/league/picks` rows gain `tier` (discounted band; null-safe) | `backend/server.py:9566-9587` | `test_league_picks_tier.py:125-170+` |
| G1-R8 | `OwnedPick.tier` wire type | `mobile/src/api/league.ts:123,147` | `check-calc-pick-tiers.js:44-52` |
| G1-R9 | `tierById` merge; 4 `tierOf` sites drop PICK carve-out | `InLeagueCalculator.tsx:268-276,723,745,895,910` | `check-calc-pick-tiers.js:54-79` |
| G1-R10 | Share image stays numeric (single surviving carve-out) | `InLeagueCalculator.tsx:540-548` | `check-calc-pick-tiers.js:81-100` |
| G1-R11 | 44pt `chipCol` in both row layouts; `PositionChip` untouched | `TradeSide.tsx:59,133`; `PlayerPickerModal.tsx:164,351` | `check-picker-chip-alignment.js:44-72` |
| G1-R12 | Suites wired into CI | `mobile/package.json:40-43`; `.github/workflows/ci.yml:42` | executed: 4/4 suites pass, 65 backend tests pass |
| G1-R13 | api-reference + config-reference rows | `docs/api-reference.md:466`; `docs/config-reference.md:66` | n/a (doc) |

Merge integrity: every G1-owned file byte-identical between `feat/fb303-calc`
tip `a58fb9a` and merged HEAD. Maestro flows named in the plan correctly not
built (D-056/D-057); operator retirement of the prod experiment record remains
a checklist step (status.md step 8) and cannot affect code behavior.

### G2+G3 — #322–#327 / #328 — 30/30 VERIFIED (finding: F-11)

Suites re-executed on the merged tree in this pass: `test_mock_draft.py` +
`test_mock_pick_ownership.py` → **138 passed**; `check-mock-g2-ui.js`,
`check-mock-ownership-caption.js`, `check-mock-draft-modes.js` all green.

| R | Requirement | Code evidence | Test evidence |
|---|---|---|---|
| G2-R1..R-4 | Ascending 8-deep ticker via pure `tickerWindow` (defensive sort, growth phase, fixed steady-state, `firstNewIndex` tint; `sinceUserPick` deliberately untouched) | `mobile/src/utils/tickerWindow.ts:38-40`; `MockDraftScreen.tsx:990-991,1007` | `check-mock-g2-ui.js:64-92` (T-U1 incl. shuffled input), `:176-199` (T-S1/T-S2) |
| G2-R5 | Server-computed `picks[].tier`, consensus-denominated | `backend/mock_draft_service.py:1440-1443` (import :64; INV-10 header :44-48) | `test_mock_draft.py:3344,3361` (T-P1/T-P2) |
| G2-R6 | `MockPick` gains `tier`/`consensus_rank`/`consensus_delta`/`valued` | `mobile/src/api/mockDraft.ts:93,97,100,102` | `check-mock-g2-ui.js:239-242`; tsc |
| G2-R7 | Chips render via `TierBadge`; no client-side derivation | `MockDraftScreen.tsx:636` | `check-mock-g2-ui.js:210-232` (no `tierForElo`/`tierBands` import) |
| G2-R8 | 3-across `flexBasis` grid, `minHeight 44`, no nested scroll | `MockDraftScreen.tsx:1294-1295` | `check-mock-g2-ui.js:252-258` (exactly one ScrollView) |
| G2-R9/R-10 | `MockTeamSheet` modal (Roster + Drafted sections), entry on clock card | `MockTeamSheet.tsx:87,154-161,178,207`; mounts `MockDraftScreen.tsx:840,956` | `check-mock-g2-ui.js:263-276`; content = TestFlight T-F4 (F-11 note) |
| G2-R11..R-13 | Position filter + search through pure `filterPool` (filter-then-search); reset on turn advance | `mobile/src/utils/mockPool.ts:30-33`; `MockDraftScreen.tsx:194-198,540,696-701,731,742` | `check-mock-g2-ui.js:113-123` (T-U2), `:285-304` (T-S6), `:327` (T-S7) |
| G2-R14 | `keyboardShouldPersistTaps="handled"` | `MockDraftScreen.tsx:560` | TestFlight T-F7 only (per PRD) |
| G2-R15 | 3 analytics events, backend-first | `analytics_taxonomy.py:283,955-958`; emitters `MockDraftScreen.tsx:215,233,254` | `check-mock-g2-ui.js:332-335` — taxonomy side untested (F-11) |
| G2-R16 | "Mine" keys on `user_owner_id`, never `by` | `MockDraftScreen.tsx:1162` | `check-mock-g2-ui.js:354-386` (T-S9 both directions) |
| G2 T-P3/T-P4 | `my_picks` same-dict identity; schema stays 1 | `mock_draft_service.py:1456,57` | `test_mock_draft.py:3371,3384` |
| G3-R1/R-2/R-13 | ESPN grid order (`assigned`), traded picks → `"user"`, `type` from grid | `backend/server.py:12517-12562,12828` | `test_mock_pick_ownership.py:308` (T-1) |
| G3-R3 | Manual mode reads the same snapshot | `server.py:12811` (single resolution path) | `:339` (T-2) |
| G3-R4/R-5 | MFL overlay anchored to original owner's shuffled slot; deterministic order | `server.py:12579-12637,12813-12825` | `:377` (T-3, two-seed de-vacuous + SAB-D precondition pin) |
| G3-R6 | Identity guard: drop-all→`none`, partial→`partial`, full→positive | `server.py:12605,12625-12637` | `:423` (T-4) |
| G3-R7 | Labeled fallback, zero egress | `server.py:12504,12527-12532` | `:471` (T-5 fetch-spy), `:500` (T-6) |
| G3-R8/R-9 | Full-coverage zero-trades labels positively; Sleeper byte-identical + `"platform"` | `server.py:12508-12516,12561,12574-12575` | `:534,612,624` (T-7/T-9) |
| G3-R10 | Pre-change rows: key present, value `null` | `mock_draft_service.py:1464` | `:573` (T-8, `in` AND `is None`) |
| G3-R11 | One disclosure caption, both mounts, render-nothing default | `MockDraftScreen.tsx:125-129,936-938,1089-1091` | `check-mock-ownership-caption.js:70-141` (S-1) |
| G3-R12 | `mock_started` carries `ownership_source` | `DraftRoomScreen.tsx:324`; `analytics_taxonomy.py:936` | `:640` (T-10); `test_mock_draft.py:3086`; `check-mock-draft-modes.js:626` (S-2) |
| G3-R14 | Partial labeled; round-1 hole → `none` (asymmetry pinned) | `server.py:12551-12575` | `:661,681,694,710` (T-12a-d) |

Seam integrity re-confirmed: G2's `tier` key lives in the pick-build loop and
G3's `ownership_source` in the `settings_echo` dict of the same
`state_payload()` — the serialized region ownership held through the merge.
`check-mock-ownership-caption.js` has no `test:*` script in package.json (no
branch ever added one — not a merge casualty; CI's glob runs it). Pre-existing,
out of scope: duplicate `## D-039` heading in `living-memory/DECISIONS.md`
(:356/:374), present on origin/main before this wave.

### G4 — #330 — 10/10 VERIFIED (findings: F-4)

| R | Requirement | Code evidence | Test evidence |
|---|---|---|---|
| G4-R1 | `handoff` + monotonic `seq` on `useFinderTargets` | `useFinderTargets.ts:33-37,63,81-84,91-101` | `check-offer-prefill-330-unit.js:106-204` |
| G4-R2 | `handleRowAction` sets handoff both verbs; deps gain `selected` | `LeagueSummaryScreen.tsx:1179-1193` | `check-offer-prefill-330.js:73-101` |
| G4-R3 | Focus-gated one-shot consume; one generation per handoff | `TradesScreen.tsx:2274-2314` | `check-offer-prefill-330.js:107-160` |
| G4-R4 | `find_trades_tapped {source:'league_offer', mode}` | `TradesScreen.tsx:2300-2304` | `check-offer-prefill-330.js:166-183`; `check-analytics-297-302.js:260-271` |
| G4-R5 | Hard lock: backend assert + narrative proof | engine-enforced; `status.md:96-135` | `test_offer_hard_lock_330.py:177-233` (re-run green post-G6 merge) |
| G4-R6 | Honest zero-result card; toast suppressed | `TradesScreen.tsx:1370-1374,1607-1622,1440-1445,5903-5929` | `check-offer-prefill-330.js:189-250` — but see F-4 |
| G4-R7 | Never relax: no zero-card path drops pin/scope | same regions; P-3 walk `status.md:151-169` | `check-offer-prefill-330.js:254-264` |
| G4-R8 | Kill switch `league.player_trade_handoff`; degradation | `config/features.json:158`; `LeagueSummaryScreen.tsx:600-601,1034`; `TradesScreen.tsx:2282-2285` | `check-offer-prefill-330.js:112-131` |
| G4-R9 | Target verb mirrors Offer | `LeagueSummaryScreen.tsx:1171-1190`; `TradesScreen.tsx:5917` | `test_offer_hard_lock_330.py:215,233`; unit U-3c |
| G4-R10 | Generation-epoch guard, pure helper | `applyJobResult.ts:19-25`; `TradesScreen.tsx:1382,2224,1428-1472,1521-1528` | `check-offer-prefill-330.js:270-302`; unit U-4 |

Executed on merged tree: structural 45/45, unit 14/14, backend 4/4.

### G5 — #321 — 11 VERIFIED, R9 test-MISSING (findings: F-1, F-2, F-8)

| R | Requirement | Code evidence | Test evidence |
|---|---|---|---|
| G5-R1 | Membership assertion, set semantics, precedence | `server.py:20629-20697` | `test_espn_identity_binding.py:198-304` |
| G5-R2 | 403 + additive `reason:"wrong_account"`, nothing stored | `server.py:20825-20835,20483` | `:517-542` |
| G5-R3 | Team-binding assertion (pasted/captured/stored); stamp nulled | `server.py:20946-20977`; `database.py:10774-10790` | `:373-425` |
| G5-R3b | Re-sync assertion on `/api/espn/import` | `server.py:21258-21275` | `:428-448` |
| G5-R4 | Public-league import stops self-stamping; `credential_stored/_reason` | `server.py:20982-21113` | `:342-370`; `test_espn_link_route.py:231` |
| G5-R5 | Zero false rejects (ownerless/co-owned/purged/vacuous) | `server.py:20649-20684,20956-20959` | `:285,304` |
| G5-R6 | Outage → 502 `espn_unavailable`, subordinate to mismatch | `server.py:20665-20696,20859-20870` | `:320-335` |
| G5-R7 | Wrong-account state on `EspnConnectScreen`; sheet preserved | `EspnConnectScreen.tsx:153,269-277,436-441` | `check-espn-wrong-account.js:84-160,184-229` |
| G5-R8 | Typed `reason` narrowing client-side | `mobile/src/api/espn.ts:133-137` | `check-espn-wrong-account.js:162-181` |
| G5-R9 | Wrong-account reconnect nudge (`espn_reconnect` reuse + `meta.reason`) | `server.py:17299-17319,17379-17390` | **MISSING** — no assertion anywhere (F-1) |
| G5-R10 | One-time eviction migration, idempotent, boundary-exact | `database.py:2139-2181,2358-2368` | `:455-510` — cutoff literal provisional (F-2) |
| G5-R11 | `espn_connect_store_rejected` event, 3 props | `analytics_taxonomy.py:104,688`; emitter `EspnConnectScreen.tsx:239-253` | `check-espn-wrong-account.js:231-252`; no backend ingest-side test (consistency gap, sibling groups have one) |

Merge integrity: G5 branch tip `1e0f0fc` vs HEAD — no G5 hunk lost.

### G6 — #304/#336/#339/#340/#341 — 11 VERIFIED, R6/R11 PARTIAL (findings: F-3, F-5, F-6, F-10)

| R | Requirement | Code evidence | Test evidence |
|---|---|---|---|
| G6-R1 | #340 overpay ceiling, both directions, fairness-independent | `trade_service.py:1175-1194,3546-3548` | `test_presentment_rules.py:118-166` |
| G6-R2 | #341 per-position net cap, picks uncounted | `trade_service.py:1197-1219,3549-3551` | `:194-223` |
| G6-R3 | #339 pick-is-the-gap two-sided band | `trade_service.py:1222-1253,3552-3554` | `:307-379,345` |
| G6-R4 | #336 windowless awaiting/matched exclusion, all paths | `server.py:4942-4969,5087-5089,5228,5271`; `trade_service.py:2700,2884-2906`; `database.py:7341` | `:675-768` |
| G6-R5 | #304 need gate, window-scaled, post-give incumbent | `trade_service.py:1256-1319,3529-3541` | `:408-541` |
| G6-R5b | Server-derived targeted-job bypass, never client-passable | `server.py:4922-4939,5085,5227`; `trade_service.py:2661,3401,3529` | `:570-602` |
| G6-R6 | Rules inside every generator; sweetener re-validation | `trade_optimizer.py:540-546,637,699-703`; `trade_service.py:4079-4081,4412-4414` | PARTIAL — consensus `_emit` hook untested (F-5) |
| G6-R7 | #189 relaxed pass never relaxes R1/R2/R3/R5 | `trade_service.py:2934-2942,2757-2793` | `:803` |
| G6-R8 | Flag OFF byte-identical; per-knob disables | `trade_service.py:3527-3528,1186,1208,1236,1281` | `:834-851` |
| G6-R9 | Kill counters + tripwire WARNING | `trade_service.py:2597,2701,2908-2915`; `server.py:4972-4993,5538-5540`; `runbook.md:232` | `:874` (wording caveat F-10) |
| G6-R10 | No API/payload contract change | server-derived only; behavior note in api-reference | `:901` (key-set only, F-10) |
| G6-R11 | D-055 bars flag-ON on prod leagues | instrumentation `scripts/deck_eval.py:243,410,700-722` | PARTIAL/OWED (F-3) |
| G6-R12 | Pick-gap knobs: measure or ship-with-lever | `trade_service.py:590-591`; `database.py:2128-2129`; NEXT.md follow-up | VERIFIED via PRD fallback clause |
| G6-R13 | Likes-you exempt from R1/R2/R3/R5; R4 dedup applies; D-055 floor untouched | `server.py:2892,2969-2980` | `:768` |

Merge integrity: G6-owned files byte-identical to branch tip except
`trade_service.py` (+18 lines of gen-v2 parity comments from main, zero G6
deletions). Flag-parity fixtures updated in merge commit `b280b24`.

### G9 — #334/#335 — 12/12 VERIFIED (finding: F-7)

| R | Requirement | Code evidence | Test evidence |
|---|---|---|---|
| G9-R1 | Render-layer suppression via `hiddenKeys`/`filterVisible` | `MatchesScreen.tsx:109-125,462,510,673-681`; `matchesDerive.ts:38-49` | `check-matches-counts.js:93-98`; `check-awaiting-dismiss.js:257-262` |
| G9-R2 | Lifecycle: add both branches; ordered unhide; no `onSettled` | `:462,510,431,435,323,371,346-347,383-384` | `check-awaiting-dismiss.js:264-295` — add-site unpinned (F-7) |
| G9-R3 | `cancelQueries` before all four optimistic writes | `:309,359,472,517` | `check-awaiting-dismiss.js:239-254` |
| G9-R4 | Undo + #318 wire contract untouched; 5000ms hold | `:64,486,530,444-449` | `check-awaiting-dismiss.js:182-195` (asserts identifier, not literal) |
| G9-R5 | Honest failure: restore, refetch, toast, immediate unhide | `:323-331,371-379` | `check-awaiting-dismiss.js:162-173` |
| G9-R6 | Mutual segment symmetric | `:309,462,472,323,346-347,673-676` | suites #22/#24/#26/#27 |
| G9-R7 | Mount-time awaiting fetch, staleTime 15s, placeholderData | `:272-277` | `check-matches-counts.js:166-176` |
| G9-R8 | Pills = league scope, chips = segment, post-R1 arrays | `:688-720,949-954` | `check-matches-counts.js:121-162` |
| G9-R9 | Pure derivations in `matchesDerive.ts`, zero runtime imports | `matchesDerive.ts:1-66` | transpile-shim + U-1..U-5 |
| G9-R10 | Never fabricate: unresolved → no count; resolved-empty → honest 0 | `matchesDerive.ts:59-66`; `MatchesScreen.tsx:984-988,1389-1393` | `check-matches-counts.js:116-119,178-185` |
| G9-R11 | Chalkline construction, a11y labels | styles `:1516-1569`; `chalkline.ts:93`; `components.md:60` | `check-matches-counts.js:187-216` |
| G9-R12 | No testID changes | `:918,930,960` | `check-matches-counts.js:218-224`; testid-lint OK |

Executed on merged tree: 21/21 + 30/30, tsc clean, testid-lint OK. No G9
backend change (by design). Repopulation-path hunt re-run post-merge: no
seventh writer of the two query keys introduced by the wave; three line-number
cites in `qa-code-walk.md` drifted (:38→:777, :95→:444-449, TradesScreen
:3323→:3447) — doc drift only.
