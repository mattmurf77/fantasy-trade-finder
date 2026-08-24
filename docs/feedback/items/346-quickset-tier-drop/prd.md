# PRD — Quick Set holds unselected players (#346 + #381, supersedes #161)

- **Date:** 2026-08-24 · **Author:** Group F author agent · **Path:** fast-track bug, full gates
- **Plan:** [plan-group-f.md](plan-group-f.md) · **Batch:** [plan.md](plan.md) · **Status:** [status.md](status.md)
- **Decision:** the operator's #381 ruling — "By default, they should stay in the same tier" — **supersedes the #161 demote rule**. Records as **D-160** (§4).

Plain-words summary: today, saving a Quick Set rung silently drops every visible
player you *didn't* tap (whose current tier is that rung or higher) to FA. After
this fix, a save touches only the players you tapped; everyone else keeps their
tier. Demoting a player stays possible — but only by an explicit act (the FA
rung, deselecting on a revisit, or the Tiers board).

## 1. Repro and root cause

**Repro (the exact #381 Nabers scenario, v1.15.0):** Rank tab → Quick set → WR.
Malik Nabers sits in "4+ 1sts". On the 4+ 1sts rung, select 3 *other* WRs — not
Nabers — and Save. On the next rung ("3 1sts") Nabers is gone from the top of
the grid: he now sits at the very bottom of the ~200-player list with chip label
**FA**. Both reports are this one mechanism: #381 (tier drop) and #346
(preseeded "1 1st" values dropping to zero when not re-selected).

**Root cause chain (all file:line verified on `ff153a0`):**

1. `mobile/src/screens/QuickSetTiersScreen.tsx:153` — `selected` starts empty
   on every rung; already-tiered players are **not** pre-selected. Not tapping
   a player is the default state, not an explicit act.
2. `QuickSetTiersScreen.tsx:475–485` (`onSave`) — the #161 rule: on any
   explicit save (`ids.length > 0`), every grid-visible unselected player whose
   `tierForElo(elo)` is the saved tier **or higher** goes into `demoted`.
3. `mobile/src/api/rankings.ts:343–350` — `saveTiers` posts it as
   `demoted_pids` on `POST /api/tiers/save`.
4. `backend/server.py:8724–8727` — `save_tiers_route` parses `demoted_pids`
   and passes it to `apply_tiers` (8771–8777) / `apply_tiers_subset`
   (8756–8763, rookie scope).
5. `backend/ranking_service.py:1782` — `DEMOTED_ELO = 1100.0`; the pin loop at
   1832–1835 (subset mirror 1918–1920) pins each demoted pid to 1100 — below
   the waivers floor (1150, `backend/tier_config.json`). Persisted durably via
   `save_tier_overrides` (`server.py:8782`) into `users.tier_overrides`.
6. Back on the client, `onSuccess` invalidates `['rankings', …]`
   (`QuickSetTiersScreen.tsx:437`) → refetch → Nabers' elo is 1100 → he sorts
   to the bottom of the elo-desc grid (line 232) and
   `mobile/src/utils/tierBands.ts:119–133`'s `tierForElo` falls through to
   `'waivers'`, labeled **FA**.

Introduced by commit `a8898a7` (#161, 2026-07-25, shipped v1.10.0) — a
deliberate, tester-driven rule, not a malfunction. #381 overrules it.

## 2. Contract — HOLD

> During the Quick Set walk, a save assigns the **selected** players to the
> rung and touches **no one else**. A visible-but-unselected player keeps his
> current tier and remains selectable on any later rung. No auto-demotion
> exists anywhere in the walk.

### Requirements

**R-1 — Save payload (mobile).** A Quick Set save sends exactly
`{position, tiers, cleared_pids}` (+ `scope`/`via` when rookie-scoped). The
`demoted` computation (`QuickSetTiersScreen.tsx:475–485`), the `demoted` member
of the mutation payload (419–429, 486), and `saveTiers`'s `demotedPids`
param + `demoted_pids` body key (`rankings.ts:321–351`) are deleted. The #161
comment blocks (`QuickSetTiersScreen.tsx:64–79`, `453–459` "Skip ≠ demote",
`461–474`, and the trailing "#161 demotion only ever fires…" clause of the
#233 save-button label comment at `766–775`; `rankings.ts:338–342`) are
rewritten to state HOLD.
*Mechanical criteria:* `check-quickset-hold.js` A1/A2 (§6b); `tsc --noEmit`.

**R-2 — Backend stops honoring `demoted_pids`.** `apply_tiers` and
`apply_tiers_subset` lose the `demoted_pids` parameter, their pin loops
(`ranking_service.py:1832–1835`, `1918–1920`), and the docstring sections
(1805–1813, 1888–1890). The D-085 tier-bounded-voting docstring bullet at
~549–557 is **reworded, not removed**: its frozen-populations rule (below-band
pins stay frozen, never dragged back onto the board) remains true and
load-bearing — anchor no-value still writes 1100-pins and historical #161
pins persist un-repaired (§3) — so only its #161 clause moves to past tense
("historical Quick Set demotions" + anchor no-value).
`save_tiers_route` stops parsing the key (`server.py:8724–8727`), drops the
kwarg at 8762/8776, and fixes its docstring (8698–8711). A save mutates only
assigned + cleared pids. This half ships the fix to **every installed binary**
(v1.10.0–v1.16.x all send the key) the moment Render deploys.
*Mechanical criteria:* T-1, T-2, T-5, T-7 (§6a).

**R-3 — Old-binary requests: accepted, ignored, silently.** A body still
carrying `demoted_pids` is treated as an unknown key: no pin, no error, no
response change — the response stays byte-identical to one without the key.
**Decision: ignored-silently**, for three reasons: (a) no installed binary has
any code that could read an echo/warning key, so echoing changes the response
shape for zero consumers — and response-shape stability on unrelated changes
is a standing repo norm; (b) a 4xx would break a year of installed binaries on
their happy path; (c) the discoverable record of the back-compat behavior is
`docs/api-reference.md` (R-9), not a wire annotation. The emptiness guard
reverts to `total_assigned == 0 and not cleared_pids` (`server.py:8736`) —
safe because a client only ever computes `demoted` when `ids.length > 0`
(`QuickSetTiersScreen.tsx:476–477`) and only mutates when
`ids.length > 0 || cleared.length > 0` (453), so no old binary sends a
demote-only request; a hand-rolled one now honestly 400s instead of "saving"
nothing while pinning players.
*Mechanical criteria:* T-2 (200 + override unchanged + response keys
unchanged), T-6 (guard).

**R-4 — `cleared_pids` unchanged: consensus restore.** Revisit-deselect keeps
sending `cleared_pids`; the override is deleted (`_unpin`,
`ranking_service.py:1826–1828`) and the player returns to his
consensus-suggested tier. The #161 "demote wins over clear" precedence dies
with the demote: an old binary's revisit-deselect (which sends the pid in
*both* keys) now restores consensus — the pre-#161 semantics, which is the
desired behavior under D-160.
*Mechanical criteria:* T-3.

**R-5 — `DEMOTED_ELO` is kept.** The constant stays (renamed nothing, value
1100.0), re-commented as the anchor-"no value"/unranked pin value rather than
a quickset writer. It is load-bearing outside this flow: the D-085
tier-bounded-voting goldens read it (`backend/tests/test_pin_tier_bounded.py:
113, 214, 407`), and it mirrors `server.ANCHOR_NO_VALUE_ELO = 1100.0`
(`server.py:1313`) — the anchor wizard's explicit "no value" answer still
creates 1100-pins on purpose. After the fix, no caller of
`_pin(…, DEMOTED_ELO)` remains in `ranking_service.py`.
*Mechanical criteria:* `test_pin_tier_bounded.py` stays green untouched;
code-walk item CW-4 (§6c).

**R-6 — Grid behavior (emergent, no new UI).** With R-1/R-2, an unselected
player's elo never changes, so on later rungs he renders at his held position
(elo-desc sort, `QuickSetTiersScreen.tsx:231–234`) with his held tier chip
(`tierForElo`, lines 532/581) and one tap places him. Nabers stays near the
top of the "3 1sts" grid labeled "4+ 1STS". No redesign: pre-selecting
current-tier chips was considered and **rejected** for this fix (it rewires
the #233 empty-save CTA, the F3 `seeded_accepted` telemetry at 314–337, and
the walk's whole selection model) — noted as an optional operator follow-up.
*Mechanical criteria:* TestFlight checklist steps 2 and 6 (§6d); CW-3.

**R-7 — TiersScreen mechanical touch.** Drop the 4th positional `[]`
(demoted) at the 4 `saveTiers` call sites (`TiersScreen.tsx:339, 380, 1096,
1103`). No behavior change — those sites never demoted.
*Mechanical criteria:* `tsc --noEmit` (extra positional args fail strict
typecheck once the param is gone).

**R-8 — Explicit demotion survives via three existing affordances.**
(1) the **FA rung** — `waivers` is the walk's 8th step; selecting a player
there pins him into the FA band (1150–1215) like any rung save; (2)
**revisit-deselect** → `cleared_pids` → consensus restore (R-4); (3)
**TiersScreen** drag-to-pool / clear paths, untouched.
*Mechanical criteria:* T-4; TestFlight steps 4–5.

**R-9 — Docs + decision record.** `docs/api-reference.md` `/api/tiers/save`
row rewritten (exact wording in scope.md §4); DECISIONS.md gains D-160 (§4
below); `../161-quickset-demote/status.md` gains a superseded note (§4). At
ship: CHANGELOG + TEST_LEDGER entries.
*Mechanical criteria:* the three docs diffs exist in the ship commit.

### File ownership (Group F exclusive — verified disjoint from Groups A/B/C/D)

`mobile/src/screens/QuickSetTiersScreen.tsx` ·
`mobile/src/api/rankings.ts` · `mobile/src/screens/TiersScreen.tsx` ·
`backend/server.py` (`save_tiers_route` only) · `backend/ranking_service.py`
(`apply_tiers` / `apply_tiers_subset` only) ·
`backend/tests/test_quickset_demote.py` ·
`backend/tests/test_override_pin_unpin.py` (one parametrize entry) ·
`backend/tests/test_rookie_scope.py` (`test_m2_08` only) ·
`mobile/tests/check-quickset-hold.js` (new) + `mobile/package.json` (one
script line) · `docs/api-reference.md` (the `/api/tiers/save` row only).
Checked 2026-08-24: none of these files appear in the plans under
`376-finder-filters-regression/`, `397-swipe-tour-placement/`,
`395-lineup-impact-superflex/`, or `386-analyst-playoff-odds/`.

## 3. Out of scope

- **No data repair for historical 1100-pins.** A stored 1100 override is
  byte-indistinguishable from an anchor "no value" answer
  (`ANCHOR_NO_VALUE_ELO`, same 1100.0), so a backfill cannot tell operator
  intent from #161 damage. Rescue is manual re-placement (any rung, anchors,
  Tiers board); the TestFlight checklist has the operator re-place Nabers
  (step 7).
- **The `quickset_completed` via-tag analytics gap** (mobile's unscoped saves
  send no `via`, so the FR-20 server event never fires for mobile walks) —
  pre-existing, flagged separately in plan-group-f.md §7. Not touched here.
- **No UI redesign.** Pre-selected current-tier chips: rejected for this fix
  (R-6 rationale); recorded as an optional follow-up for the operator.
- **No cross-format backfill.** `rankings.cross_format_derive` copies
  overrides; pre-existing derived 1100-pins stay (same no-repair stance).
  Fewer ever get created from now on.

## 4. Decision record

**D-160 (new; next id verified — DECISIONS.md max is D-159):**

> ## D-160 — Quick Set saves HOLD unselected players (supersedes #161's demote rule)
> **Date:** 2026-08-24 · **Trigger:** feedback #381 (+#346), operator ruling
> A Quick Set rung save touches only the selected players. The #161
> auto-demote (visible-but-unselected at/above the rung → pinned to
> `DEMOTED_ELO` 1100) is removed on both sides: the client no longer computes
> or sends `demoted_pids`, and `POST /api/tiers/save` accepts-and-silently-
> ignores the key from old binaries (v1.10.0–v1.16.x), so the backend deploy
> alone fixes every installed build. Explicit demotion survives via the FA
> rung, revisit-deselect (`cleared_pids` → consensus restore; the #161
> demote-beats-clear precedence dies too), and TiersScreen. `DEMOTED_ELO`
> stays for the anchor no-value path and the D-085 goldens. No flag: the old
> behavior is the bug per the operator's ruling, and rollback is a revert —
> a backend revert alone restores demote for binaries ≤ v1.16.x (they still
> send the key), but not for binaries carrying the client half of this fix,
> which would also need a client revert + EAS build.
> No historical 1100-pin repair — indistinguishable from anchor no-value.

**One-line note for `../161-quickset-demote/status.md`** (append under the
title, don't rewrite history):

> **SUPERSEDED 2026-08-24 by #381/#346 (D-160):** the demote rule below is
> removed — Quick Set saves now HOLD unselected players. See
> [`../346-quickset-tier-drop/`](../346-quickset-tier-drop/prd.md).

## 5. Why no feature flag

The change alters API behavior (a POST route stops honoring a field), which is
bright-line territory — hence full gates and this written justification rather
than express. **No flag, deliberately:** (a) the removed behavior *is* the bug
per the operator's explicit #381 ruling — there is no audience for toggling it
back; (b) a flag would keep a live code path that silently pins users' players
to 1100, i.e. the defect itself, dormant in prod; (c) the rollback lever is a
git revert on a Render-autodeployed backend (minutes, no client rebuild) —
fully true for every installed binary ≤ v1.16.x, which keeps sending
`demoted_pids` forever, so a backend revert restores demote fleet-wide today;
once binaries carrying the client half ship, they no longer send the key and
restoring demote for *them* would additionally need a client revert + EAS
build — an acceptable narrowing, since the rollback audience is nil by the
operator's own ruling; (d) flag
surface costs four synchronized touchpoints (`feature_flags.py`,
`config/features.json`, `docs/config-reference.md`, `fixtures/flags/
release.json`) for a behavior nobody may re-enable. If the operator disagrees,
the flaggable seam is a single `if` around the two pin loops — say so before
build, not after.

## 6. Evidence plan (D-056 — no Maestro, no simulator)

### (a) Backend pytest — `backend/tests/test_quickset_demote.py`, rewritten

Filename kept for history; module docstring rewritten to state D-160. Every
test asserts the held tier **value** (via `tier_for_elo` / the override dict),
never merely "no demotion happened". Prove-to-fail: each is RED under the
named sabotage (for T-1/T-3/T-5, "old code" = re-adding the parse + pin loops
is the sabotage, i.e. they are red on today's `ff153a0`).

| # | Test | Asserts | RED under (sabotage) |
|---|---|---|---|
| T-1 | `test_passed_over_player_holds_tier` | Route-level Nabers repro: seed a player in `firsts_4plus`; POST `/api/tiers/save` with 3 *other* ids **and** `demoted_pids=[him]` (the exact old-binary payload); his elo is byte-unchanged and `tier_for_elo` still says `firsts_4plus`; the 3 selected land in the band | Old code / re-added pin loop (he reads 1100 → `None`) |
| T-2 | `test_demoted_pids_key_is_ignored` | Old-binary request naming a pid with an existing override: 200 `ok`, that override value byte-unchanged, response JSON key set identical to the same request without the key (pins "silently") | Re-added parse (override → 1100) or any echo/warning key |
| T-3 | `test_clear_restores_consensus_even_with_legacy_demote_key` | Save a player into `second`, then revisit-deselect as an old binary sends it (pid in **both** `cleared_pids` and `demoted_pids`): override deleted, tier back to his consensus `first_1` | Old code (demote-beats-clear → `None`); or `_unpin` regression |
| T-4 | `test_fa_rung_save_pins_waivers_band` | `{waivers: [pid]}` save pins elo inside the FA band read from `tier_config.json` (1150–1215) and `tier_for_elo` says `waivers` — the explicit-demote affordance survives | Removing/breaking the waivers rung write path |
| T-5 | `test_scoped_save_holds_passed_over_rookie` | Rookie-scoped route save (`scope:"rookie"`, `via:"rookie_quickset"`) with legacy `demoted_pids` covering a visible unselected rookie + an unshown vet: rookie keeps his prior value/tier, vet's override byte-unchanged | Old code (rookie → 1100); subset pin loop re-added |
| T-6 | `test_empty_save_still_400s` | `total_assigned == 0`, no clears — with **and** without a legacy `demoted_pids` list — both 400 (guard reverted; a demote-only body no longer counts as "something to do") | Old guard (`… and not demoted_pids` → demote-only body got 200) |
| T-7 | `test_apply_tiers_signature_has_no_demote_param` | `pytest.raises(TypeError)` on `apply_tiers(…, demoted_pids=[…])` and `apply_tiers_subset(…, demoted_pids=[…])` — the param cannot silently return | Re-adding the parameter (even with an inert body) |

T-7 is one test beyond the plan's six: it is the only case red under
"parameter restored but pin loop left out", which T-1/T-5 would miss.

**Touches to neighboring suites:**

- `backend/tests/test_override_pin_unpin.py:456` — the
  `test_every_override_mutator_stamps` parametrize entry
  `lambda s: s.apply_tiers("WR", {"firsts_2": ["p0"]}, demoted_pids=["p1"])`
  becomes `lambda s: s.apply_tiers("WR", {"firsts_2": ["p0"]})` (still pins
  the tier-write stamp; the demote kwarg would now TypeError).
- `backend/tests/test_rookie_scope.py:305–316` —
  `test_m2_08_demotion_is_scoped_to_the_visible_subset` is rewritten in place
  (T-M2-08 numbering kept) to the hold contract at the service level:
  `apply_tiers_subset` with a visible unselected rookie → his value/override
  state byte-unchanged; the unshown-vet assertion (`v1` untouched) survives
  verbatim. `test_m2_08b_clears_are_scoped_too` (319) and
  `test_m2_09*` (329, no `demoted_pids` usage) are untouched.

### (b) Mobile structural guard — `mobile/tests/check-quickset-hold.js` (new)

Dependency-free plain-node guard + `"test:quickset-hold"` script in
`mobile/package.json`. Note (drift from plan-group-f.md §5): CI's
`mobile-typecheck` job **does** glob-run every `mobile/tests/check-*.js`
(`.github/workflows/ci.yml:47`), so this guard is CI-gating, not
`npm run`-only. Ship-time housekeeping recorded for the orchestrator (not
this group's files): root `CLAUDE.md`'s "`check-*.js` … gate nothing yet"
line and the matching NEXT.md open item (if still listed) are stale against
ci.yml and should be corrected in the ship commit.

| # | Assertion | RED sabotage |
|---|---|---|
| A1 | `QuickSetTiersScreen.tsx` contains no `demoted` token: no demote computation (`TIERS.indexOf(cur) <= tierRank` filter absent), no `demoted` key in the mutation payload/`mutationFn` — **and** (positive anchor, so a renamed/gutted file can't green it vacuously) the file still contains the two-member mutate shape (`mutate({ ids, cleared })` or equivalent) with `cleared` flowing into `saveTiers` | `sabotage-A1`: re-add the `demoted` computation or payload member; also red if the mutate call disappears |
| A2 | `api/rankings.ts` `saveTiers` has no `demotedPids` param and its POST body has no `demoted_pids` key — while `cleared_pids` is still present (anti-trivial check: proves the guard reads the real body, and R-4 didn't ride along) | `sabotage-A2`: re-add `demoted_pids: []` to the body |
| A3 | `TiersScreen.tsx` contains no `demoted` token and still calls `saveTiers(` at its 4 sites | `sabotage-A3`: re-add a positional demote arg by name |

(TiersScreen's positional-arg arity itself is enforced by `tsc --noEmit` —
a 5th positional arg to the 4-param `saveTiers` is a type error.)

### (c) Code-walk proof outline (written at build time, into this folder)

The §1 chain re-cited against the post-fix tree:

- CW-1: `onSave` builds `{ids, cleared}` only; the mutation payload has two
  members; file:line of the new `saveTiers` call.
- CW-2: `saveTiers`'s POST body has exactly `position`, `tiers`,
  `cleared_pids` (+ conditional `scope`/`via`).
- CW-3: grid render path (`players` sort → `gridPlayers` → chip
  `tierForElo`) provably reads only elo, which no longer changes on a save
  that excludes the player — the R-6 hold-in-grid behavior.
- CW-4: `save_tiers_route` never reads `demoted_pids`; `git grep demoted_pids
  backend/` hits only tests/history; no `_pin(…, DEMOTED_ELO)` caller remains
  in `ranking_service.py` (the anchor path pins via `server.py`'s
  `ANCHOR_NO_VALUE_ELO`).
- CW-5: `_record_trends_snapshot` was already called with
  `assigned_pids + cleared_pids` only (`server.py:8812–8817`) — demotions
  never fed elo_history, so removing them changes no Trends behavior.

### (d) Operator TestFlight checklist (runtime proof — the Nabers walk)

1. Rank tab → Quick set → WR, format as in your league. On **4+ 1sts**:
   confirm Nabers' chip shows "4+ 1STS". Select 3 other WRs — **not**
   Nabers. Save.
2. On **3 1sts**: Nabers is still near the **top** of the grid, chip still
   "4+ 1STS" — not FA, not missing. *(Old behavior: bottom of the list as
   FA — this step alone catches the regression.)*
3. Tap Nabers + Save → back on the Tiers board: the 3 WRs sit in 4+ 1sts,
   Nabers in 3 1sts, nobody new in FA.
4. Explicit demote still works: walk to the **FA** rung, select a
   currently-tiered depth player, Save → Tiers board shows him in FA.
5. Revisit path: Back to a rung where you placed **two or more** players this
   run, deselect one and keep the rest selected, then Save → the deselected
   player returns to his consensus-suggested tier (chip label), not FA.
   *(Must be ≥2: deselecting a rung's only player takes the clear-only branch,
   which never demoted even on old code — the ≥2 path is the demote-beats-
   clear case this fix reverses, matching test T-3.)*
6. #346 angle: on the **1 1st** rung, select only some of the preseeded
   1-1st players and Save → the unselected ones still read "1 1ST" on the
   next rung.
7. Cleanup: re-place any player the old behavior FA'd (Nabers included —
   the fix does not retro-repair old pins).

### Requirement → criterion map

| R | Mechanical criteria |
|---|---|
| R-1 | A1, A2; `tsc --noEmit` |
| R-2 | T-1, T-2, T-5, T-7 |
| R-3 | T-2, T-6 |
| R-4 | T-3 |
| R-5 | `test_pin_tier_bounded.py` green untouched; CW-4 |
| R-6 | CW-3; TestFlight 2, 6 |
| R-7 | `tsc --noEmit`; A3 |
| R-8 | T-4; TestFlight 4, 5 |
| R-9 | docs diffs present in ship commit; D-160 in DECISIONS.md |

## 7. Risks (from plan-group-f.md §6, verified)

- `threshold_met` / completeness: unaffected — `save_tiers_position` /
  `all_done` / `_note_ranking_method` key off `tiers`/`via`
  (`server.py:8820–8858`), never `demoted_pids`.
- Trends/elo_history: no interaction — snapshots never included demoted pids
  (CW-5).
- Tier-bounded voting (D-085): keeps consuming `DEMOTED_ELO` as the unranked
  pin value; only the quickset writer is removed (R-5).
- Old binaries: get HOLD immediately on backend deploy; the demote was
  invisible at save time anyway, so nothing in the old UI reads differently.
- `member_rankings` publish / cross-format derive: payload shapes unchanged;
  fewer 1100-pins ever exist to propagate.
