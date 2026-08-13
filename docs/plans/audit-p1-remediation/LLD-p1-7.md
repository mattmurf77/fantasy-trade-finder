# LLD — P1-7 · Pick Anchors unlock + label derivation (audit A-16)

> **Purpose.** The buildable form of `plan-p1-7.md`: exact diff sites, the new
> branch's precise condition and its position in the ladder, the label
> derivation and its call sites, the structural test that prevents
> re-divergence, the `no_value` handling, and what must be re-verified after the
> P0 merge.
>
> **Status:** design-only. No source file is changed by this document.
> **Author:** LLD/PRD agent, 2026-08-11.
> **Worktree:** `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation`,
> branch `p1-remediation-2026-08-11` @ `ab9368f` (== `origin/main` at authoring time).
> **Companion:** [`PRD-p1-7.md`](PRD-p1-7.md) · **Plan:** [`plan-p1-7.md`](plan-p1-7.md) ·
> **Scope block:** [`scope-p1-7.md`](scope-p1-7.md) · **Reconciliation:** [`HLD-p1.md`](HLD-p1.md)
> (this item is **A1, Wave A** — the first P1 build wave, after commit T1).

**Every file:line in this document was re-read in this worktree at `ab9368f`.**
Where the plan's citation was wrong, the [Corrections](#0-corrections-to-the-plan)
section says so and gives the verified line.

## Contents

- [0. Corrections to the plan](#0-corrections-to-the-plan)
- [1. Binding decisions this LLD implements](#1-binding-decisions-this-lld-implements)
- [2. The defect, stated as a proof](#2-the-defect-stated-as-a-proof)
- [3. Design, restated compactly (do not re-open)](#3-design-restated-compactly-do-not-re-open)
- [4. Diff sites — exact, current → intended](#4-diff-sites--exact-current--intended)
- [5. The `anchor` branch — condition and placement](#5-the-anchor-branch--condition-and-placement)
- [6. Label derivation — map, function, call sites](#6-label-derivation--map-function-call-sites)
- [7. The structural anti-divergence test](#7-the-structural-anti-divergence-test)
- [8. `no_value` handling](#8-no_value-handling)
- [9. Test fixtures — and the monotonic-floor trap](#9-test-fixtures--and-the-monotonic-floor-trap)
- [10. Re-verify after P0 merge](#10-re-verify-after-p0-merge)
- [11. Docs and living-memory write-back](#11-docs-and-living-memory-write-back)
- [12. Operator gates (unresolved — do not resolve at the keyboard)](#12-operator-gates-unresolved--do-not-resolve-at-the-keyboard)

---

## 0. Corrections to the plan

Nine places where `plan-p1-7.md` (or the audit it derives from) is wrong or
imprecise against the code at `ab9368f`. **None changes the design; all change
what the implementer types.**

| # | Plan says | Verified state | Consequence |
|---|---|---|---|
| **X-1** | Change 12: "register the new `anchors.rung.*` ids in `mobile/src/screens/CLAUDE.md` (mirroring how `anchors.scope-*` is documented)" (`plan-p1-7.md:452-453`) | **`mobile/src/screens/CLAUDE.md` contains no testID registry at all.** Its only headings are the screen table and `## Sharp edges` (`:33`); the `PickAnchorScreen` row is `:15` and names no ids. `anchors.scope-*` is documented in exactly two places: `mobile/scripts/testid-lint-allow.txt:44-45` and the dated artifact `docs/plans/mobile-testing/app-inventory-2026-08-09.md:173` | **Change 12 is unbuildable as written.** Replace it with: (a) the `testid-lint-allow.txt` entry (change 11, which already covers it), and (b) one clause appended to the `PickAnchorScreen` row at `screens/CLAUDE.md:15` naming `anchors.rung.<key>`. Do **not** invent a registry section — that is a convention change nobody asked for. `app-inventory-2026-08-09.md:173` currently asserts "The 8 rung buttons … have no testIDs"; it is a dated artifact and is **not** edited (same rule the docs table applies to the audit itself) |
| **X-2** | Change 16 + Maestro flow 3: the `anchors-done` profile proves the unlock on-device | **A profile with `app_user.unlocked: true` cannot prove it.** `seed_ui_test_db.py:1009-1010` calls `db.mark_format_unlocked(...)` for every format in `world.unlocked_formats()` (`:688-690`, which returns `[]` unless `app_user.unlocked`). A seeded row makes `server.py:6188-6189`'s monotonic floor answer `unlocked = True` **before the `'anchor'` branch is ever consulted** | The fixture must set **`"unlocked": false`** and let the new branch compute it. This is also literally accurate: a user who has just crossed 40 anchors has no prior `unlocked_formats` row — that row is written by `mark_format_unlocked` at `server.py:6211` on the first `/api/rankings/progress` after the fix. See [§9](#9-test-fixtures--and-the-monotonic-floor-trap) |
| **X-3** | (silent) | `_validate_quickset` (`seed_ui_test_db.py:314-368`) refuses `unlocked: false` together with `ranking_method` ∈ `("tiers","quickset","manual")` (`:361-367`). `'anchor'` is deliberately absent from that tuple **because it was the permanently-locked method** | The `anchors-done` fixture depends on that absence. After this fix, `'anchor'` + ≥ 40 overrides also computes `unlocked: true`, so the guard's stated rationale changes. **Add a comment at `:358-367` recording why `'anchor'` stays out** (its unlock is override-count-conditional, not method-conditional), or the next agent "completes" the tuple and breaks the fixture |
| **X-4** | Design §3: labels derived from the ladder mean "the button a user taps and the confirmation they read are the same string by construction" (`plan-p1-7.md:345-348`) | **True only at the default anchor scale, and only unconditionally for the four scale-invariant rungs.** `_anchor_target_elo` (`server.py:1305-1324`) re-spaces the three multi-first rungs by `γ = log 4 / log N` where `N = users.anchor_scale` (`ANCHOR_TOP_TIER_FIRSTS_DEFAULT = 4.0`, `server.py:1293`). At `N = 2`, tapping **2 1sts** pins to `2² × base` ≈ Elo 1927 → `firsts_4plus` → the confirmation reads **"4+ 1sts"** | The guarantee must be **scoped in writing**, in the code comment and in the doc sentence: *by construction at the default scale; deliberately divergent for a user who has set a non-default `anchor_scale`.* `1_first`/`1_second`/`1_third`/`1_fourth` and `no_value` are scale-invariant (`_ANCHOR_SINGLE_PICK`, `server.py:1264-1269`; `no_value` short-circuits at `:1314-1316`), so the Maestro round-trip **must** use one of those. The plan's flow taps `no_value` — correct, but for a reason it did not state. `cross-client-invariants.md:358` already carries the "at the default scale" qualifier |
| **X-5** | "`docs/cross-client-invariants.md:344` states the anchor lane must never reach `save_tiers_position`" (`plan-p1-7.md:92-93`, and `scope-p1-7.md:54`) | **Mis-citation.** `:344` is inside the pick `pool_value` paragraph. The `via`-whitelist rule is at **`:340`**, and it forbids *W1 Draft Room surfaces* reaching the merged-band path — not the anchor lane writing `tiers_saved` per se. The **binding** prohibition is in code: `backend/server.py:1280-1282` ("no W1 surface may reach `save_tiers_position` / the merged-band path"), and the fact itself is structural — `save_tiers_position` occurs at `server.py:6626` and `:7370` only, i.e. **nowhere inside `save_anchor_route` (`:7437-7550`)** | Cite `server.py:1280-1282` + the absence at `:7437-7550` as the evidence that Option 1 is inert. Keep `cross-client-invariants.md:340` as the doc form. The conclusion is unchanged |
| **X-6** | "The governing doc currently contradicts itself" across `:15`, `:331`, `:358` (`plan-p1-7.md:154-158`) | **Overstated.** `:358` already says "lands in the tier that carries its name **at the default scale**". The genuine contradiction is narrower: `:331` labels `4_firsts` "4 1sts" while `:15` labels its landing tier `firsts_4plus` "4+ 1sts". The other four mismatches (`1 2nd`/`2nd`, …, `No value`/`FA`) are **vocabulary style**, not landing errors | The doc edit is smaller and more precise than the plan implies: fix the five button labels in the `:329-338` table, add the derivation sentence, add the display-tier-vs-pin-Elo sentence for `no_value`. **Do not rewrite `:358`'s scale qualifier** — it is correct |
| **X-7** | `TIER_LABEL` is canonical, `ANCHOR_ROWS` is the one divergent copy (`plan-p1-7.md:140-152`) | Holds, and the count is right — but **mobile already carries two further label maps** that duplicate `TIER_LABEL` verbatim: `mobile/src/components/TierBadge.tsx:15` and `mobile/src/components/chalkline/Badge.tsx:31`. Both currently agree with `TIER_LABEL`; neither is derived | **Out of scope for this item** (they are not divergent, and touching them is a drive-by). Recorded here so the next reader does not think `TIER_LABEL` has exactly one consumer per client. File alongside the `tierForElo` floor gap ([§8](#8-no_value-handling)) as one "derive mobile's three label maps from one constant" backlog item |
| **X-8** | Line numbers for the mobile edits: rungs `344-353`, consequence `391-396`, `AnchorSheet` `124-140` / `150-158` | Verified exact: rung grid **`PickAnchorScreen.tsx:342-355`** (the `<Button>` is `:345-352`); consequence block **`:388-397`** with `TIER_LABEL` at `:394` and `'No value'` at `:395`; `AnchorSheet.tsx` rung grid **`:124-140`** (testID `:129`, `label={label}` `:130`), result block **`:148-161`** with `TIER_LABEL` at `:154` and `'No value'` at `:155` | Cosmetic drift only. **All of these move again after the P0 merge** — [§10](#10-re-verify-after-p0-merge) |
| **X-9** | "`_elo_overrides` deliberately retains stale pids (`server.py:14515-14526`)" | The comment block is **`server.py:14505-14527`**; the load is `:14528` and the assignment `:14529`. Content is exactly as the plan describes | Cite `server.py:14505-14531` |
| **X-10** | Docs table: "`GET /api/rankings/progress` — document the new `'anchor'` unlock rule" in `docs/api-reference.md` | **There is no per-route section for it.** The route appears exactly twice: in the gated-reads list at `:101` and as one table row at `:170` (`\| GET \| /api/rankings/progress \| Same, alternate shape \|`) | The doc edit is an extension of the `:170` row (and, if RL-8 ships, the two additive keys) — not an edit to a section that does not exist. Decide the shape against the file's own convention at write time; do not invent a new route-detail format for one row |

**One more thing the plan got right and is worth pinning**, because it is the
load-bearing claim: `self._interactions` has **exactly two writers and one
clearer** — `record_ranking` (`ranking_service.py:299-300`), the session-build
rehydration (`:780-783`), and `reset()` (`:792`, `:803`). `apply_anchor`
(`:1471-1487`) touches `self._elo_overrides` and `self._version` only. Verified
by grep over the whole file; there is no third writer.

---

## 1. Binding decisions this LLD implements

| Source | Decision | Effect here |
|---|---|---|
| **`DECISIONS-p1.md` D-P1-02** | **The manual lane is out of scope by explicit operator decision.** P1-7 fixes the anchor lane only | The `manual` branch at `server.py:6163-6164` is **not touched**. No implementer may "also fix" it while in the file. A `GOTCHAS.md` entry recording the accepted lock is a **deliverable of this build** — text in [`PRD-p1-7.md` §8](PRD-p1-7.md#8-required-gotchasmd-entry--the-accepted-manual-lane-lock) |
| **`HLD-p1.md` §C, §D** | P1-7 is **A1, Wave A** — the first P1 build wave after T1, because P0-1 grows the locked cohort daily | Build order, and the escalation duty in [§10](#10-re-verify-after-p0-merge) if it slips |
| **`HLD-p1.md` §B** | A1 holds `backend/server.py`, `backend/ranking_service.py`, `backend/tests/fixtures/seed_ui_test_db.py`, `mobile/src/utils/anchorRows.ts`, `PickAnchorScreen.tsx`, `AnchorSheet.tsx`, `testid-lint-allow.txt` **exclusively for Wave A** | No other agent edits these in Wave A. Release them before Wave B (P1-9 takes `server.py` and `seed_ui_test_db.py`) |
| **`HLD-p1.md` RL-6 / plan C3** | `ANCHOR_ROWS` conforms to `TIER_LABEL` | [§6](#6-label-derivation--map-function-call-sites) — **gated, see §12** |
| **`HLD-p1.md` RL-7 / plan C4** | `no_value` displays "FA"; the floor divergence is logged, not fixed | [§8](#8-no_value-handling) — **gated** |
| **`HLD-p1.md` RL-2 / plan C2** | `ANCHOR_UNLOCK_MIN = 40`, as a Python constant | [§5](#5-the-anchor-branch--condition-and-placement) — **gated** |
| **`HLD-p1.md` RL-8 / plan C5** | The visible progress hint is severable | D4 + D10 are the only diff sites it adds. Declined ⇒ **zero API shape change** |
| **`HLD-p1.md` RL-9 / plan C6** | The `anchors-done` seed profile | [§9](#9-test-fixtures--and-the-monotonic-floor-trap) — **gated** |
| **`HLD-p1.md` SQ-1 / plan C7** | P1-8 (A-17) sequencing | Not decidable here. `_tiers_rule` is extracted as the shared seam either way |
| **`HLD-p1.md` §A.6 / R-12** | No agent uses the `living-memory` ID printed in its plan | [§11](#11-docs-and-living-memory-write-back) |

---

## 2. The defect, stated as a proof

Four verified facts. Together they make the unlock **structurally unreachable**,
not merely hard.

1. **`'anchor'` is a first-class method string.** `POST /api/ranking-method`
   accepts it (`server.py:6303`), its docstring names it (`:6289-6294`), the
   seeder's `RANKING_METHODS` includes it (`seed_ui_test_db.py:138`), and the
   rank-home chooser writes it — `rankChooserModel.ts:83` gives the "Pick
   Anchors" card `pref: 'anchor'`, and `RankHomeScreen.tsx:57-72`'s `choose()`
   calls `setRankingMethod(m.pref)`.
2. **`'anchor'` is absent from every branch of the unlock ladder**
   (`server.py:6163-6175`), so it falls to the `else` at `:6173-6175`:
   `all(counts[p] >= threshold for p in POSITIONS)` — 10 per position
   (`ranking_service.py:194-200`), 40 total.
3. **`counts[p]` can only be produced by trio swipes.** It is
   `service.get_progress(position=pos)["interaction_count"]`
   (`server.py:6147-6149` → `ranking_service.py:715-722`), reading
   `self._interactions`, whose only writers are `record_ranking`
   (`:299-300`, reached solely by `POST /api/rank3`) and the session-build
   rehydration `{pos: rank_swipe_count // 3}` (`:780-783`).
4. **The anchor lane writes none of it.** `apply_anchor`
   (`ranking_service.py:1471-1487`) sets `self._elo_overrides[player_id]` and
   bumps `_version`. `save_anchor_route` (`server.py:7437-7550`) persists
   `save_tier_overrides` (`:7486`), publishes member rankings (`:7499-7504`),
   snapshots trends (`:7513`) and records `anchor_answered` (`:7519-7531`). It
   writes **no rank-swipe row and no `tiers_saved` entry** — `save_tiers_position`
   appears at `server.py:6626` and `:7370` only.

**Therefore:** an `'anchor'`-method user needs 10 trio interactions in each of
QB/RB/WR/TE, and no quantity of anchoring produces one. The only escape is the
monotonic floor at `server.py:6188-6189`, which can rescue only a user already
computed unlocked under a *different* method.

**Second-order damage, verified.** `LeagueScreen.tsx:328-334` derives
`positionsRanked` from `progress[p] >= threshold || tiersSaved.includes(p)` —
anchors write neither, so the League ring reads **0/4** forever. And
`RootNav.tsx:266-267` sets `pushEnabled` from `progressQuery.data?.unlocked ===
true`, so `usePushNotifications` (`:279-283`) never arms for this cohort.

**P0-1 widens it on merge.** Today only chooser-card tappers reach
`ranking_method = 'anchor'`; the Rank action sheet does not
(`TabNav.tsx` `pick()` calls `go(m.route)` only). After P0-1, every wizard save
with `via == 'anchors'` pins the method. The locked cohort grows from the P0
merge until this lands — the reason `HLD-p1.md` §C places P1-7 in Wave A.

---

## 3. Design, restated compactly (do not re-open)

The chosen design is **settled**. Both audit options were rejected **with proof**;
this section exists so no implementer re-litigates them.

**Audit Option 1 — "add `anchor` to the tiers/quickset unlock branch" — is inert.**
That branch evaluates `all(p in get_tiers_saved(...))` (`server.py:6169-6170`).
The anchor lane never writes `tiers_saved` (`save_tiers_position` absent from
`:7437-7550`) and is forbidden from doing so (`server.py:1280-1282`;
`cross-client-invariants.md:340`). An anchor-only user's `tiers_saved` is empty,
so Option 1 leaves them locked forever.

**Audit Option 2 — "increment the interaction counter in `apply_anchor`" — is
non-durable and cross-contaminating.** Three independent reasons:

1. **It does not survive a restart.** `_interactions` is *overwritten* at session
   build from persisted rank swipes only (`ranking_service.py:780-783`). Anchors
   persist as Elo overrides, never swipe rows, so an in-memory bump is discarded
   on the next cold start — unlock on Tuesday, re-locked on Wednesday. Making it
   durable would require fabricating rank-swipe rows from an anchor, i.e.
   inventing a pairwise judgment that then feeds `_compute_elo` and distorts the
   board the anchor was pinning.
2. **It hands unlock credit to the action P0-1 deliberately excludes.**
   `apply_anchor` is the shared write lane for **both** hosts (`server.py:7479`,
   reached by the wizard and by `AnchorSheet` alike). A counter there would grant
   credit for `via: 'draft_room'` saves — which P0-1 excludes from writing
   `ranking_method` — and would grant it on the **trio** branch, i.e. to
   NULL-method users too. A Draft Room long-press would silently be worth
   1/40th of a Trade Finder unlock.
3. **It mixes units.** A trio interaction orders three players; an anchor prices
   one. Summing them makes `total_completed` (`server.py:6153`, rendered as
   progress copy) a mixed-unit number.

**Option 3 — a dedicated `anchor` branch keyed on durable board evidence — is
what ships.** The evidence is `users.tier_overrides`, counted through a new
`RankingService.board_override_count()`. It is **durable** (persisted at
`server.py:7486`, rehydrated at `:14528-14529`), **format-scoped for free**
(`sess["service"]` is the active format's instance), and **free of extra I/O**
(the dict is already in memory on a hot, RootNav-polled GET).

**A draft-room-only anchorer stays locked. That is designed behaviour, not a
bug.** Their `ranking_method` remains NULL (P0-1 skips `via: 'draft_room'`), so
the `'anchor'` branch is never entered and the trio rule still applies. Their
overrides accumulate and count later *if* they ever answer one wizard question —
because the predicate reads the board, not the event stream. That asymmetry is
deliberate: the board is the board, and retroactively discounting work the user
genuinely did would be the unfriendly reading. It cannot leak credit to anyone
P0-1 excluded, because entering the branch still requires a wizard answer.

---

## 4. Diff sites — exact, current → intended

Ordered backend → mobile → tests → fixtures. Line numbers are `ab9368f`;
**every one is re-located by content after the P0 rebase** ([§10](#10-re-verify-after-p0-merge)).

### Backend

**D1 — `backend/ranking_service.py:194-200`, immediately after `POSITION_THRESHOLDS`**

*Current:* the `POSITION_THRESHOLDS` dict, then `ELO_INITIAL = 1500.0` at `:203`.

*Intended:* insert between them —

```python
    # A-16 / P1-7 — the anchor method's unlock bar, in BOARD OVERRIDES.
    # Equal to the trio bar (10 × 4 positions, POSITION_THRESHOLDS above) so
    # the product has one number to explain. Deliberately NOT per-position:
    # the Pick Anchor wizard's default scope is a single cross-position,
    # value-descending queue (#133, PickAnchorScreen.tsx), so a 4-position
    # completeness rule would import a shape that surface does not have.
    ANCHOR_UNLOCK_MIN = 40
```

Gated on **RL-2** (the number, and constant-vs-`model_config`).

**D2 — `backend/ranking_service.py`, new method after `apply_anchor` (ends `:1487`)**

```python
    def board_override_count(self) -> int:
        """How many of this service's Elo overrides are for players still in
        the pool. The durable evidence behind the 'anchor' unlock rule
        (server.get_rankings_progress).

        Pool-restricted ON PURPOSE. `_elo_overrides` deliberately retains
        stale pids — session_init keeps the full stored dict rather than
        filtering it, precisely so a pid missing from one day's pool is not
        destroyed (server.py:14505-14531). A raw len() would therefore
        over-count a long-lived board and could unlock a user on players
        who are no longer rankable.
        """
        pool_ids = {p.id for p in self._pool(None)}
        return sum(1 for pid in self._elo_overrides if pid in pool_ids)
```

`_pool(None)` is `ranking_service.py:811-816` and returns every player, so this
is O(pool) per call on an already-hot in-memory structure.

**D3 — `backend/server.py:6163-6175` — the unlock ladder.** This is the change.
See [§5](#5-the-anchor-branch--condition-and-placement) for the exact block.

**D4 — `backend/server.py:6274-6283` — the response payload (RL-8 only)**

*Current:* the `jsonify({...})` with `threshold`, `unlocked`, `ranking_method`,
`scoring_format`, `total_required`, `total_completed`, `unlocked_formats`.

*Intended (only if RL-8 = ship):* two **additive** keys, computed
unconditionally so clients need no branch —

```python
        "anchor_count":    _anchor_count,
        "anchor_required": RankingService.ANCHOR_UNLOCK_MIN,
```

where `_anchor_count = service.board_override_count()` is hoisted above the
ladder so both the branch and the payload read one value. **Declined ⇒ D4 and
D10 are both dropped and the API shape is byte-identical.**

**D5 — `backend/server.py:6289-6298` — the `POST /api/ranking-method` docstring**

*Current:* `'anchor' (2026-07-10) = the Pick Anchor wizard — added alongside the
mobile rank-home chooser, which records the user's preferred ranking flow here
(the routing itself is client-side; …)`.

*Intended:* append one sentence — that `'anchor'` now has its own unlock rule in
`get_rankings_progress` (≥ `ANCHOR_UNLOCK_MIN` pool-resident board overrides in
the active format, or the tiers rule). Also correct the implication that the
chooser is the only writer, which P0-1 already falsifies.

### Mobile

**D6 — `mobile/src/utils/anchorRows.ts` — full rewrite (36 lines today)**

Header comment `:1-13`, `AnchorRung` `:17-20`, `ANCHOR_ROWS` `:22-35` with
authored labels at `:24-27` and `:30-33`. Intended shape in
[§6](#6-label-derivation--map-function-call-sites).

**D7 — `mobile/src/screens/PickAnchorScreen.tsx:345-352` — rung testIDs**

*Current:*

```tsx
                <Button
                  key={key}
                  label={label}
```

*Intended:* insert `testID={`anchors.rung.${key}`}` after `key={key}`. Nothing
else in the element changes. These buttons have **no testIDs today**, which is
why the label change cannot currently be asserted on the primary host.
(`AnchorSheet.tsx:129` already carries `anchor-sheet.rung.${key}`.)

**D8 — `mobile/src/screens/PickAnchorScreen.tsx:391-396` — the confirmation fallback**

*Current:*

```tsx
          {lastPlaced.res.tier
            ? TIER_LABEL[lastPlaced.res.tier as Tier] ?? lastPlaced.res.tier
            : 'No value'}
```

*Intended:* `: BELOW_LADDER_LABEL}` — imported from `../utils/anchorRows`
alongside the existing `ANCHOR_ROWS` import at `:27`. No other logic change.

**D9 — `mobile/src/components/AnchorSheet.tsx:151-158` — the same substitution**

*Current:* `: 'No value'}` at `:155`, inside the
`<Text testID="anchor-sheet.result">` block. *Intended:* `: BELOW_LADDER_LABEL}`,
imported alongside `ANCHOR_ROWS` at `:11`.

**D10 — `mobile/src/screens/PickAnchorScreen.tsx:314-319` — the progress hint (RL-8 only)**

*Current:* `{answered} / {scopedQueue.length} anchored` plus scope/format tails.
*Intended:* append the unlock tail from the progress query
(`… · unlocks at {anchor_required}` / progress toward it). **Non-blocking:**
absent data renders today's string unchanged. Declined with RL-8.

**D11 — `mobile/scripts/testid-lint-allow.txt:44-45`**

*Current:*

```
# PickAnchorScreen.tsx:293      testID={`anchors.scope-${s.toLowerCase()}`}
anchors.scope*
```

*Intended:* append the same two-line shape for `anchors.rung*`, with the
`PickAnchorScreen.tsx:<line>` provenance comment. Template-literal ids are
lint-invisible (`mobile/.maestro/README.md` law 4).

**D12 — `mobile/src/screens/CLAUDE.md:15`** — append one clause to the
`PickAnchorScreen` row naming `anchors.rung.<key>`. **Not** a new registry
section — see correction X-1.

### Tests and fixtures

**D13 — `mobile/tests/check-anchor-labels.js` (new)** + a
`"test:anchor-labels": "node tests/check-anchor-labels.js"` entry in
`mobile/package.json:5-20` (beside the eight existing `test:*` scripts).
Spec in [§7](#7-the-structural-anti-divergence-test).

**D14 — `backend/tests/test_anchor_unlock.py` (new)** — the 17-case matrix from
`plan-p1-7.md` § Test plan §1, unchanged, plus the fixture caveat in
[§9](#9-test-fixtures--and-the-monotonic-floor-trap).

**D15 — `backend/tests/test_pick_anchor.py` (extend, do not replace)** — T-18:
`POST /api/anchor/save` still writes **no** `tiers_saved` entry and **no** rank
swipe.

**D16 — `backend/tests/fixtures/seed_ui_test_db.py`** — an `app_user.anchors`
handler (the key is reserved as `null` in all nine profiles, e.g.
`standard.json:33`; no handler exists) plus the X-3 comment at `:358-367`.
Gated on **RL-9**.

**D17 — `backend/tests/fixtures/profiles/anchors-done.json` (new)** — gated on
**RL-9**. Shape in [§9](#9-test-fixtures--and-the-monotonic-floor-trap).

---

## 5. The `anchor` branch — condition and placement

### 5.1 The intended block

Replacing `server.py:6163-6175` in full:

```python
    def _tiers_rule() -> bool:
        """Board-completeness unlock: all four positions committed through
        /api/tiers/save for the ACTIVE format. Extracted so the tiers/quickset
        branch and the anchor branch's fallback clause cannot drift apart."""
        try:
            saved = get_tiers_saved(g_user_id, scoring_format=fmt)
            return all(p in saved for p in POSITIONS)
        except Exception:
            return False

    if ranking_method == "manual":
        unlocked = True
    elif ranking_method in ("tiers", "quickset"):
        # 'quickset' (#119) commits through the same /api/tiers/save
        # contract as the Tiers board, so it unlocks the same way.
        unlocked = _tiers_rule()
    elif ranking_method == "anchor":
        # A-16 / P1-7. Anchors write Elo overrides (ranking_service.apply_anchor)
        # and NOTHING ELSE: never a trio interaction, never tiers_saved (the
        # anchor lane must not — server.py _ANCHOR_VIA comment,
        # docs/cross-client-invariants.md § Pick anchor keys). Without this
        # branch 'anchor' fell to the trio rule below and could NEVER unlock.
        # The evidence is the persisted board, not the event stream: overrides
        # survive session rebuilds (session_init restores them), which an
        # in-memory interaction bump would not.
        unlocked = (
            service.board_override_count() >= RankingService.ANCHOR_UNLOCK_MIN
            or _tiers_rule()
        )
    else:
        # 'trio' or null — original threshold logic
        unlocked = all(counts[p] >= threshold for p in POSITIONS)
```

### 5.2 Placement invariants — all four are load-bearing

| # | Invariant | Why |
|---|---|---|
| **P-a** | The new arm sits **below** `("tiers","quickset")` and **above** the `else` | It must be an `elif` on an exact string, so no other method can enter it. Placing it above the tiers branch would be harmless but obscures the "one method, one rule" reading |
| **P-b** | The `manual` arm at `:6163-6164` is **byte-unchanged** | D-P1-02. A-17 is P1-8's. Changing it here is an unrequested scope expansion against an explicit operator decision |
| **P-c** | `_tiers_rule` is a **local closure over `g_user_id` and `fmt`**, defined after both are bound (`g_user_id` at `:6156`, `fmt` at `:6143`) | It is the shared seam P1-8 will want (`HLD-p1.md` SQ-1). Keeping it local avoids adding a module-level name to a 20k-line file for two call sites |
| **P-d** | Nothing outside the `'anchor'` arm consults `board_override_count()` | This is what makes double-counting impossible. `ranking_method` is written by exactly one mechanism (P0-1's), so the branch is the sole gate. Asserted by tests T-8 (`'trio'` + 40 overrides ⇒ locked) and T-9 (NULL + 40 overrides ⇒ locked) |

### 5.3 What the condition does and does not claim

- **Format-scoped by construction.** `service` is `sess["service"]`
  (`server.py:6142`), re-pointed to the active format's instance per request;
  overrides are stored per format (`save_tier_overrides(..., scoring_format=fmt)`
  at `:7486`; restored per format at `:14528`). Asserted by T-5.
- **Pool-restricted.** See D2's docstring. Asserted by T-6.
- **Not anchor-pure, stated rather than hidden.** Tier saves and manual reorders
  also write overrides (`server.py:7325`, `:7861`). But the predicate is
  evaluated *only* inside the `'anchor'` arm, which post-P0-1 is reached only by
  users whose method-write came from a wizard anchor. Extra overrides mean *more*
  board work, never less: the rule is strictly improving and can never re-lock
  anyone. An Elo-fingerprint alternative (recognising the eight discrete rung
  Elos in the override values) was considered and **rejected** — a fingerprint
  that clever is a comment waiting to lie.
- **The `or _tiers_rule()` clause** rescues legacy `'anchor'` users who already
  hold a complete tier board. It can only unlock, never lock. Asserted by T-4
  and T-16.
- **The monotonic floor is unchanged** (`server.py:6188-6189`) and still wins
  (T-12).

### 5.4 Downstream consequences of `unlocked` flipping — all intended

| Consumer | Effect |
|---|---|
| `server.py:6199-6213` `mark_format_unlocked` | First write for this cohort; monotonic by contract |
| `server.py:6228-6238` `ranking_complete_first_time` | Fires once per format per user (`was_first`). **Step change in a shipped funnel series** |
| `server.py:6241-6265` `league_member_unlocked_trades` | Push fan-out to every joined leaguemate. **Gated on RL-5** — must match P0-1's Q5 answer so the two deploys don't each produce a burst |
| `server.py:6215-6226` `_invalidate_league_members_cache` | Leaguemates see the new badge on next fetch |
| `LeagueScreen.tsx:328-334` | Ring jumps 0/4 → 4/4 via the `progress.unlocked ? 4` short-circuit |
| `RootNav.tsx:266-267` → `usePushNotifications` | Push primer becomes reachable for this cohort |
| `RankScreen.tsx:356` `isUnlockedEverywhere` | Unlock banner renders (`:685-696`; P0-1 adds `testID="rank.unlocked-banner"` at `:686`) |

---

## 6. Label derivation — map, function, call sites

### 6.1 Why `TIER_LABEL` is canonical (evidence, verified)

`TIER_LABEL` (`mobile/src/utils/tierBands.ts:39-48`) is replicated verbatim
across four clients and the docs. Verified occurrences of the top rung's string
`4+ 1sts` at `ab9368f`:

`mobile/src/utils/tierBands.ts:40` · `mobile/src/components/TierBadge.tsx:15` ·
`mobile/src/components/chalkline/Badge.tsx:31` ·
`mobile/src/navigation/rankChooserModel.ts:75` · `backend/og_image.py:62` ·
`backend/trade_service.py:1892` · `extension/content.js:34` ·
`web/profile.html:324` · `web/positional-tiers.html:1364`, `:1410`, `:2961` ·
`web/js/app.js:2076`, `:2080` · `web/style-guide.html:219` ·
`web/index.html:187` · `web/ranking-method.html:225` · `web/faq.html:197` ·
`docs/cross-client-invariants.md:15` · `docs/glossary.md:26` ·
`docs/design/components.md:117`, `:118`, `:119`.

`ANCHOR_ROWS` exists in **one** code location (`mobile/src/utils/anchorRows.ts`)
plus one doc table (`cross-client-invariants.md:329-338`). The direction of
conformance is not a close call. **Gated on RL-6.**

### 6.2 The intended `anchorRows.ts`

```ts
// The pick-anchor rung grid — the ONE vocabulary for "worth how much in
// draft capital?".
//
// [existing W1 provenance paragraph retained verbatim]
//
// LABELS ARE DERIVED, NOT AUTHORED HERE (A-16 / P1-7, 2026-08-11). Every
// rung's button text comes from TIER_LABEL — the ladder vocabulary shared by
// mobile, web, the extension and the OG renderer (docs/cross-client-
// invariants.md § Tier bands). Before this, the grid carried its own strings
// and FIVE of the eight disagreed with the tier the answer actually lands in,
// so a user tapped "1 2nd" and read back "2nd" inside one interaction.
// Re-typing a label here re-creates that bug; mobile/tests/check-anchor-labels.js
// fails the build if anyone does.
//
// SCOPE OF THE GUARANTEE: exact at the DEFAULT anchor scale. A user who has
// set users.anchor_scale to N < 4 re-spaces the three multi-first rungs
// upward (server._anchor_target_elo, γ = log 4 / log N), so their "2 1sts"
// answer can land in firsts_4plus and read back "4+ 1sts". That is by design
// and predates this change (cross-client-invariants.md § Tier labels ARE pick
// terms). The four single-pick rungs and no_value are scale-invariant.
//
// Two rows of four, top-of-board first. Order is presentational; the keys
// are the contract.

import type { AnchorKey } from '../api/rankings';
import type { Tier } from '../shared/types';
import { TIER_LABEL } from './tierBands';

export interface AnchorRung {
  key: AnchorKey;
  label: string;
}

/** Which tier each rung's answer lands in at the default anchor scale.
 *  Encodes in CODE the name↔rung invariant that until now lived only in a
 *  doc sentence (cross-client-invariants.md) and a backend test
 *  (test_tier_occupancy.py::test_anchor_rungs_land_in_matching_tiers).
 *  `no_value` is null on purpose — the server pins it BELOW every band and
 *  answers tier: null. See BELOW_LADDER_LABEL. */
export const ANCHOR_TIER: Record<AnchorKey, Tier | null> = {
  '4_firsts': 'firsts_4plus',
  '3_firsts': 'firsts_3',
  '2_firsts': 'firsts_2',
  '1_first':  'first_1',
  '1_second': 'second',
  '1_third':  'third',
  '1_fourth': 'fourth',
  'no_value': null,
};

/** The ONE string for "below the ladder": the no_value button label AND the
 *  null-tier fallback both hosts render, so a rung and its confirmation can
 *  never disagree. Borrows the waivers label deliberately — see §8. */
export const BELOW_LADDER_LABEL = TIER_LABEL.waivers;   // 'FA'

export const anchorLabel = (k: AnchorKey): string => {
  const t = ANCHOR_TIER[k];
  return t ? TIER_LABEL[t] : BELOW_LADDER_LABEL;
};

/** Presentational grid: two rows of four, top-of-board first. */
const ANCHOR_KEY_ROWS: readonly (readonly AnchorKey[])[] = [
  ['4_firsts', '3_firsts', '2_firsts', '1_first'],
  ['1_second', '1_third', '1_fourth', 'no_value'],
];

export const ANCHOR_ROWS: readonly AnchorRung[][] = ANCHOR_KEY_ROWS.map(
  (row) => row.map((key) => ({ key, label: anchorLabel(key) })),
);
```

**Resulting grid:** `4+ 1sts · 3 1sts · 2 1sts · 1 1st` / `2nd · 3rd · 4th · FA`.
Five of eight strings change (`4 1sts`→`4+ 1sts`, `1 2nd`→`2nd`, `1 3rd`→`3rd`,
`1 4th`→`4th`, `No value`→`FA`).

**Import-cycle check.** `tierBands.ts` imports only from `../shared/types` and
`../api/rankings` (type-only, `:21-22`); `anchorRows.ts` currently imports only
`AnchorKey` from `../api/rankings`. No cycle is created. **Verify with
`npx tsc --noEmit` regardless** — do not run `npm install`.

**Type note.** `ANCHOR_ROWS` keeps its `readonly AnchorRung[][]` type, so both
hosts' `.map(({ key, label }) => …)` destructuring compiles unchanged.

### 6.3 Call sites

| Client | Site | Change |
|---|---|---|
| Mobile — wizard | `PickAnchorScreen.tsx:342-355` | None (reads `ANCHOR_ROWS`; labels arrive derived) + D7's testID |
| Mobile — wizard | `PickAnchorScreen.tsx:391-396` | `'No value'` → `BELOW_LADDER_LABEL` (D8) |
| Mobile — draft sheet | `AnchorSheet.tsx:124-140` | None (reads `ANCHOR_ROWS`) |
| Mobile — draft sheet | `AnchorSheet.tsx:151-158` | `'No value'` → `BELOW_LADDER_LABEL` (D9) |
| Web (×4 files), extension, OG renderer, `trade_service.py` | render `TIER_LABEL`'s own copies | **Untouched.** No anchor surface exists outside mobile — `grep -rl "anchor/save\|anchorRows\|pick anchor" web/ extension/` returns empty |
| Backend | `_anchor_target_elo` (`server.py:1305-1324`), `VALID_ANCHORS` (`:1271-1273`), `AnchorKey` (`api/rankings.ts:315-323`) | **Untouched.** Keys are the wire contract; only display strings move |

---

## 7. The structural anti-divergence test

`mobile/tests/check-anchor-labels.js` — **this is what makes the fix permanent
rather than a one-time patch.** Without it the next agent re-types the strings
and the bug returns with a fresh timestamp.

**Form.** Node script, no test framework, modelled on
`mobile/tests/check-member-entered-marker.js`: `require('typescript')`, parse the
real `.ts` with `ts.createSourceFile`, walk the AST, `PASS`/`FAIL` lines,
`process.exit(failures ? 1 : 0)`, `process.exit(2)` if `typescript` is not
resolvable. Registered as `npm run test:anchor-labels` in
`mobile/package.json:5-20`. **A grep would not do** — it passes on a label
reconstructed inside a ternary or a template literal, which is exactly the
regression worth catching.

**Assertions — five, each independently failing:**

| # | Assertion | The regression it catches |
|---|---|---|
| **A-1** | In `mobile/src/utils/anchorRows.ts`, **no object literal property named `label` has a `StringLiteral`, `NoSubstitutionTemplateLiteral` or `TemplateExpression` initializer.** Every `label` must be a call to `anchorLabel` or an identifier resolving to it | Someone re-types `label: '1 2nd'` — the original defect, re-created |
| **A-2** | `ANCHOR_TIER`'s object literal has **exactly the eight `AnchorKey` members**, read from `mobile/src/api/rankings.ts:315-323`'s union — no missing key, no extra key | A ninth rung, or a renamed key, silently falls through `anchorLabel` to `BELOW_LADDER_LABEL` and prices as FA |
| **A-3** | Every non-null `ANCHOR_TIER` value is a **member of `TIERS`** in `mobile/src/utils/tierBands.ts:24-33`, and `ANCHOR_TIER['no_value']` is **`null`** | A typo'd tier key (`'first1'`) compiles under a loose read and yields `undefined` at runtime |
| **A-4** | `anchorRows.ts` **imports `TIER_LABEL` from `./tierBands`**, and `BELOW_LADDER_LABEL` is initialized from a `TIER_LABEL.<member>` property access — not a literal | Someone "simplifies" `BELOW_LADDER_LABEL = TIER_LABEL.waivers` to `= 'FA'`, re-forking the vocabulary |
| **A-5** | Neither `PickAnchorScreen.tsx` nor `AnchorSheet.tsx` contains the string literal `'No value'`, and each references `BELOW_LADDER_LABEL` | A host re-introduces its own null-tier fallback — the exact shape of the pre-fix bug on the confirmation line |

**Explicitly not asserted (and why).** The test does **not** compare
`TierBadge.tsx:15` or `chalkline/Badge.tsx:31` against `TIER_LABEL`. Those two
maps duplicate it today and currently agree (correction X-7); deriving them is a
separate, larger change and out of this item's scope. Recorded as a backlog item
in [§8](#8-no_value-handling).

**Gate.** Exit 0 required before merge; logged in `TEST_LEDGER.md` alongside
pytest, `tsc --noEmit` and `testid-lint.sh`.

---

## 8. `no_value` handling

**The mechanism, precisely — it is subtler than the audit states.**

| Layer | Behaviour | Evidence |
|---|---|---|
| Server pin | `no_value` → **Elo 1100** | `ANCHOR_NO_VALUE_ELO = 1100.0`, `server.py:1263`; short-circuit `:1314-1316` |
| Band floor | `waivers` floors at **1150** | `docs/cross-client-invariants.md:21` (`[1150, 1215]`); `backend/tier_config.json` |
| Server tier | `RankingService.tier_for_elo` returns **`None`** below the lowest band | `ranking_service.py:1250-1268` (`return None` at `:1268`) |
| API | `POST /api/anchor/save` answers **`tier: null`** | `server.py:7515`, `:7544`; typed nullable at `mobile/src/api/rankings.ts:331-332` |
| Mobile bucketing | `tierForElo` has **no lower floor** — anything under `fourth` (1220) returns `'waivers'` | `mobile/src/utils/tierBands.ts:116-130` (`return 'waivers'` at `:129`) |
| Mobile display | So the same player reads **"No value"** in the wizard and wears an **"FA"** badge on the Tiers board | `PickAnchorScreen.tsx:395` vs `autoBucket` (`tierBands.ts:133-147`) |

So the audit's "same band, two names" is only half right: the user-visible
contradiction is real, but the cause is a **mobile/backend banding gap** that
predates this change and is not introduced by it.

**Decision implemented here (gated on RL-7): display "FA".**

- `ANCHOR_TIER['no_value'] = null` keeps the distinction **in the type system**
  even while the *display* borrows the `waivers` label. The code never asserts
  that `no_value` *is* `waivers`.
- `BELOW_LADDER_LABEL = TIER_LABEL.waivers` is the single string used by the
  button **and** by both hosts' null-tier fallback, so the rung tapped and the
  confirmation read are the same word by construction.
- The wizard then agrees with the badge the player actually wears on the Tiers
  board the user will look at next.

**The hazard, recorded rather than papered over (plan R7).** "FA" asserts an
equivalence the backend does not make. If a future change makes mobile honour the
1150 floor, that player becomes tier-less and the button's promise breaks. The
mitigations are the `null` in `ANCHOR_TIER` and one doc sentence at
`cross-client-invariants.md` § Pick anchor keys distinguishing **display tier**
from **pin Elo**.

**Logged separately, not fixed here — one backlog item, two facts:**

> `mobile/src/utils/tierBands.ts:116-130` (`tierForElo`) ignores the `waivers`
> 1150 floor that `backend/tier_config.json` and
> `RankingService.tier_for_elo` (`ranking_service.py:1250-1268`) enforce, so a
> `no_value`-anchored player (Elo 1100) badges as FA on mobile while the API
> answers `tier: null`. Fixing it makes `tierForElo` nullable and ripples into
> `autoBucket` / `autoBucketMixed` (`tierBands.ts:133-169`) and `TiersScreen`'s
> zone model (its existing `unassigned` zone is the natural home). **Same item:**
> mobile carries three copies of the ladder vocabulary — `TIER_LABEL`
> (`tierBands.ts:39-48`), `TierBadge.tsx:15`, `chalkline/Badge.tsx:31` — which
> agree today but are not derived from one another (correction X-7).

Filed to `NEXT.md` at ship; **not** built in this item. It is a `TiersScreen`
bucketing change and does not belong in an S-sized label fix.

---

## 9. Test fixtures — and the monotonic-floor trap

**The trap, stated first because it invalidates the obvious fixture.**
`seed_ui_test_db.py:1009-1010` seeds `mark_format_unlocked` for every format in
`world.unlocked_formats()`, which is `[]` unless `app_user.unlocked` is truthy
(`:688-690`). A seeded row makes `server.py:6188-6189` answer `unlocked = True`
**before the `'anchor'` arm is consulted** — so a fixture with
`"unlocked": true` would produce a green Maestro flow that proves nothing.

**Therefore `anchors-done.json` sets `"unlocked": false`.** That is not a lie:
the user has no *prior* unlock record; the row is written by
`mark_format_unlocked` (`server.py:6211`) on the first `/api/rankings/progress`
after the fix. The flow's assertion is that the **first** progress call returns
`unlocked: true` — which is only possible through the new branch.

**D17 — `backend/tests/fixtures/profiles/anchors-done.json` (new), gated on RL-9:**

```jsonc
"app_user": {
  "username": "qa_anchors",
  "user_id": "<new id in the 9000000000000000NN space>",
  "unlocked": false,                     // ← see the trap above
  "ranking_method": "anchor",
  "rankings": null,                      // no trio history: counts stay 0/4
  "tiers": null,                         // no tiers_saved: the OR clause stays false
  "anchors": { "count": 40, "formats": ["sf_tep"] }
}
```

**D16 — the `app_user.anchors` handler in `seed_ui_test_db.py`.** The key is
reserved as `null` in all nine profiles (`standard.json:33`, `fresh.json:28`,
`quickset-done.json:34`, `near-unlock.json:33`, `espn.json:50`,
`single-format.json:33`, `two-leagues.json:33`, `draft.json:47`,
`draft-pre.json:47`) and no handler exists. Minimal behaviour:

1. Validate in `_validate_profile` (`:252-288`): object with `count` ≥ 1 and
   `formats` ⊆ the known scoring formats; refuse `anchors` together with
   `ranking_method` ∉ `(None, "anchor")` — an anchored board under another
   method is not a state the app produces.
2. Seed: for each listed format, take the top-`count` pool players by value
   (`_pool_by_position` / `_value_key`, the shape the Quick Set block uses at
   `:1017-1029`), assign each an **anchor-rung Elo** — one of the eight
   `_anchor_target_elo` outputs at the default scale, cycled deterministically so
   the board is legible — and write them with **one** `db.save_tier_overrides`
   call per format.
3. **Do not** call `save_tiers_position` — the anchor lane never does, and a
   `tiers_saved` row would satisfy the `or _tiers_rule()` clause and mask the
   branch under test (the same masking failure as the monotonic floor).
4. Add the X-3 comment at `:358-367` recording why `'anchor'` stays out of
   `_validate_quickset`'s refusal tuple.

**If RL-9 is declined:** D16, D17 and `flows/p1-7-anchor-unlock.yaml` are all
dropped, the on-device unlock proof is **waived in writing** in `scope-p1-7.md`
§3 (waiver 1 of 3), and the unlock is proved by pytest T-3/T-7/T-14/T-15/T-17
plus the manual pass. The **label** flow is unaffected — it runs on the existing
`standard` profile.

**Backend matrix.** `backend/tests/test_anchor_unlock.py` implements
`plan-p1-7.md` § Test plan §1 T-1…T-18 unchanged. Two clarifications:

- **T-3 and T-7 must assert no `unlocked_formats` row exists beforehand**,
  for the same reason the fixture does — otherwise they pass through the
  monotonic floor.
- **T-17** (40 anchor saves → rebuild the service from the DB →
  `board_override_count() == 40` **and** `_interactions == {}`) is the executable
  form of the Option-2 rejection. **Name it so** —
  `test_override_count_survives_rebuild_but_interactions_do_not`.

---

## 10. Re-verify after P0 merge

**P0-1 is the reason this item goes first, and its interaction with the new
branch is the single highest-value thing to re-check.** Run every row before the
first edit; answer each in writing in `scope-p1-7.md`. `HLD-p1.md` §0.5: **a row
that comes back "the premise no longer holds" stops the build and returns the
item to planning** — it is not patched around at the keyboard.

### 10.1 Global (HLD §G.0)

1. `git fetch origin && git rev-parse origin/main` — record the sha in the scope block.
2. Confirm the P0 commits (P0-1, -2, -3, -5, -6, -7, -8/9) are on `origin/main`.
3. Rebase; resolve nothing blind.
4. Re-read `DECISIONS.md`, `GOTCHAS.md`, `MISTAKES.md`, `OPEN_QUESTIONS.md` for
   the next free IDs — **not** the ones printed in the plan (`HLD-p1.md` R-12).
5. Re-grep every file:line cited here. `backend/server.py` is 20k+ lines and P0
   inserts into six of its functions.
6. Confirm `mobile/node_modules` is still symlinked. **Never run `npm install`.**

### 10.2 P1-7 specific

| # | Check | Why it could invalidate this design |
|---|---|---|
| **RV-1** | **Re-locate the unlock ladder.** P0-1 comments `:6155-6175`. Confirm the `("tiers","quickset")` branch still has the exact `try / get_tiers_saved / all(...) / except → False` shape `_tiers_rule` is extracted from | If P0-1 restructured it, the extraction changes shape and D3's block must be re-derived rather than pasted |
| **RV-2** | **The `'anchor'` write path.** `grep -n "set_ranking_method_if_unset" backend/server.py` and read its call in `save_anchor_route` (was `:7479`). Confirm it fires **only** when `via == "anchors"` and skips `via == "draft_room"` | This is the sole gate on entering the new branch. If P0-1 shipped without the `draft_room` exclusion, the branch would grant unlock credit for Draft Room long-presses — **stop and report**, do not compensate in the predicate |
| **RV-3** | **`allow_over=("anchor",)`.** Confirm P0-1's exception still lets a completeness tiers/quickset save upgrade `'anchor'` → `'quickset'` | Recommendation stands: **keep it unchanged**. After P1-7 it is a convenience rather than a rescue, and removing it is a P0-1 edit this item has no business making. It can only unlock, never lock (T-16) |
| **RV-4** | **Re-check the `manual` branch's post-P0 state.** P0-1 adds `_note_ranking_method(sess, "manual")` to `reorder_rankings`, pinning manual-first users to `'manual'` | This is the evidence for `HLD-p1.md` **SQ-1** and for the required `GOTCHAS.md` entry. **Report what you find; change nothing** (D-P1-02) |
| **RV-5** | **`RankScreen.tsx:686` carries `testID="rank.unlocked-banner"`** (P0-1 edit #14) | `flows/p1-7-anchor-unlock.yaml` has a **hard dependency** on it. Absent ⇒ that flow cannot be written; say so rather than adding the testID (it is P1-11's file in Wave C and P0-1's edit) |
| **RV-6** | **`seed_ui_test_db.py`** — P0-1 rewrote `_validate_quickset` (`:314-368`). Re-locate the guard at `:358-367` and confirm `app_user.anchors` is **still unhandled** | If P0-1 implemented `anchors`, D16 collapses to a fixture-only change; if it extended the refusal tuple to include `'anchor'`, X-3 becomes a blocking conflict |
| **RV-7** | **`backend/experiments.py:59`** — `ranking_method` is a live targeting attribute, and P0-1 changed which users hold which value. Confirm no experiment is mid-flight on it | P1-7 does not change who holds `'anchor'`, only what it means at the gate — but an in-flight experiment segmenting on it would see a behaviour change mid-run |
| **RV-8** | **`server.py:6199-6265`** — confirm the first-unlock fan-out is unchanged and still `was_first`-gated | RL-5 depends on it. If P0-1 suppressed the fan-out for its own cohort, this item inherits that decision automatically — record which |
| **RV-9** | **Mobile line numbers.** Re-grep `ANCHOR_ROWS` in both hosts and `'No value'` in both. P0 does not own these files, but sibling P1 sessions run concurrently (`HLD-p1.md` R-15) | D7/D8/D9 are edit-by-content, never edit-by-line |
| **RV-10** | **`mobile/src/utils/tierBands.ts:39-48` still holds the eight labels unchanged** | The whole derivation hangs off it. If another item re-labelled a tier, the anchor grid follows silently — which is the *point*, but a label review must then look at one file, not two |
| **RV-11** | **Confirm P1-7 is actually in Wave A.** If it slips past `HLD-p1.md` §C step 2, **say so to the operator explicitly** | It is the only P1 item whose delay actively grows a defect cohort (`HLD-p1.md` §C, R-1, R-8) |

---

## 11. Docs and living-memory write-back

Per `scope-p1-7.md` §4, with the corrections above folded in.

| Doc | Verdict | Precise edit |
|---|---|---|
| `docs/cross-client-invariants.md` | **YES — the load-bearing row** | (a) `:329-338` button-label table: five labels change; add the sentence that labels are **derived** from `TIER_LABEL` via `ANCHOR_TIER` in `mobile/src/utils/anchorRows.ts` and must never be authored independently. (b) `:338` `no_value` row: add the **display-tier vs pin-Elo** clause (pins at 1100, below the `waivers` floor of 1150; API returns `tier: null`; mobile's floor-less `tierForElo` shows FA) and note the mobile/backend banding gap as a known issue. (c) **Do not rewrite `:358`** — its "at the default scale" qualifier is already correct (X-6). Keys, Elo bands and colors are unchanged |
| `docs/api-reference.md` | **YES** | Per correction **X-10**: the route has only the gated-reads mention at `:101` and the table row at `:170`; there is no per-route section. Extend the `:170` row with the `'anchor'` unlock rule, plus `anchor_count` / `anchor_required` **only if RL-8 = ship**. No route added, renamed or removed |
| `docs/glossary.md` | **YES** | `:26` **Tier band** already lists the eight labels — add one clause that the Pick Anchor wizard's buttons are the same eight, derived. Check at write time whether a "Pick Anchors" entry exists; if not, add one |
| `living-memory/LLD.md` | **YES** | Two convention shifts: (1) unlock rules are per-method and now include an **evidence-count** rule keyed on `users.tier_overrides` rather than the trio counter; (2) display labels for a shared vocabulary are **derived from one constant**, enforced by a structural test |
| `living-memory/DECISIONS.md` | **YES** | Next free ID at write time (`D-025` at `ab9368f`; **not** the plan's `D-012` — `HLD-p1.md` §A.6). Records: Option 3 over Options 1 and 2 with both proofs; `TIER_LABEL` canonical; `no_value` displays FA; `ANCHOR_UNLOCK_MIN = 40` and not per-position; the draft-room asymmetry (plan R3) |
| `living-memory/GOTCHAS.md` | **YES — mandatory, not conditional** | **D-P1-02 requires it.** Next free ID at write time (`G-027` at `ab9368f`). Text in [`PRD-p1-7.md` §8](PRD-p1-7.md#8-required-gotchasmd-entry--the-accepted-manual-lane-lock). A second entry for the `_interactions`-rebuilt-from-swipes trap is **recommended** — it is exactly what the next agent will re-derive the hard way |
| `living-memory/CHANGELOG.md` | **YES** | Dated H2 at ship; name the analytics seam (`ranking_complete_first_time` begins firing for the anchor cohort) so a later analyst sees the discontinuity rather than discovering it in a chart |
| `living-memory/TEST_LEDGER.md` | **YES** | pytest · `tsc --noEmit` · `testid-lint.sh` · `check-anchor-labels.js` · the Tier-1 sim run · `qa/sim-runs/last-sim-run.json` |
| `living-memory/NEXT.md` | **YES** | File the [§8](#8-no_value-handling) backlog item |
| `screens/manifest.json` + `screens/CLAUDE.md` | **YES** | `anchorRows.ts` is declared a freshness source for the `anchors` screen (`screens/manifest.json:55`, inside the `"source"` list `:52-56`, hashed at `:57`), so all three captures re-take and `source_sha256` updates as a side effect of `screen-capture.sh`. **Coordinate with `HLD-p1.md` §A.5 R1** — the single consolidated re-capture pass after Wave C, not a per-item run |
| `mobile/src/screens/CLAUDE.md` | **YES (one clause)** | `:15`, per correction X-1 |
| `docs/data-dictionary.md` · `docs/architecture.md` · `living-memory/HLD.md` · `docs/config-reference.md` · `docs/runbook.md` · ADR · `docs/design/*` · `living-memory/DEPENDENCIES.md` | **n/a** | No schema, no wiring change, no new module, no env/flag/`model_config` key (unless RL-2 elects the `model_config` lever, which flips `config-reference.md` to YES), no operational procedure, no ADR-weight decision, no new component or token, no dependency |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a** | Dated artifact. The drift (5 mismatches not 2; Option 1 inert) is recorded in `plan-p1-7.md`; further corrections are in [§0](#0-corrections-to-the-plan) here |

---

## 12. Operator gates (unresolved — do not resolve at the keyboard)

Seven, unchanged from `plan-p1-7.md` § Operator checkpoints, mapped to their
`HLD-p1.md` §E ids. **This LLD resolves none of them.** Recommendations are
carried forward from the plan and the HLD; they are recommendations, not
decisions.

| Plan | HLD | Question | Blocks | Recommendation carried forward |
|---|---|---|---|---|
| **C1** | **RL-5** | Suppress the first-unlock push fan-out for the anchor cohort? | **Merge** (only if the answer is "suppress") | Match P0-1's Q5 answer, whatever it is — the two deploys must not each produce a burst |
| **C2** | **RL-2** | Confirm `ANCHOR_UNLOCK_MIN = 40`; constant or `model_config` key? | **Build** (D1; flips `config-reference.md` to YES if a key) | 40, as a constant |
| **C3** | **RL-6** | `ANCHOR_ROWS` conforms to `TIER_LABEL`? | **Build** (all of [§6](#6-label-derivation--map-function-call-sites)) | Conform — ~21 verified locations across four clients versus one |
| **C4** | **RL-7** | `no_value` displays "FA", or stays a ninth vocabulary item? | **Build** ([§8](#8-no_value-handling)) | "FA" now; log the `tierForElo` floor gap separately |
| **C5** | **RL-8** | Ship the visible progress hint (`anchor_count` / `anchor_required`)? | **Build**, severable (D4 + D10) | Yes — but declining it means **zero** API shape change |
| **C6** | **RL-9** | Build the `anchors-done` seed profile? | **Build** ([§9](#9-test-fixtures--and-the-monotonic-floor-trap)) | Yes — the audit found this class of bug precisely because no fixture reproduced it |
| **C7** | **SQ-1** | Sequencing with P1-8 (A-17), which edits the same ladder | **Build order** | Not agent-decidable. `_tiers_rule` is extracted here either way and is the seam P1-8 wants. **D-P1-02 forbids absorbing A-17 into this item** |
