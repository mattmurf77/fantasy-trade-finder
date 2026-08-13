# P1-7 — Pick Anchors can never unlock, and its labels contradict the tier ladder

> Remediation plan for finding **A-16 / P1-7** of the 2026-08-09 mobile UX audit.
> Sources: `docs/business/product/2026-08-09-mobile-ux-audit/04-priority-backlog.md` (P1 table, row P1-7)
> and `06-resolutions.md` (row A-16).
>
> **Status:** PLAN ONLY — no code written. Worktree `ftf-p1-remediation`, branch
> `p1-remediation-2026-08-11`, off `origin/main @ ab9368f`.
>
> **Composes with P0-1** (`ftf-p0-remediation`, branch `p0-remediation-2026-08-10`),
> which merges to `main` **before** this builds. Every design choice below is made
> with `set_ranking_method_if_unset` and its `draft_room` exclusion in view.

## Contents

- [Verified current state](#verified-current-state)
- [Design](#design)
- [Exact change list](#exact-change-list)
- [Surface changes](#surface-changes)
- [Maestro delta](#maestro-delta)
- [Docs impact table](#docs-impact-table)
- [Test plan](#test-plan)
- [Risks and cross-item collisions](#risks-and-cross-item-collisions)
- [Operator checkpoints](#operator-checkpoints)

---

## Verified current state

Every citation below was re-read in **this** worktree at `ab9368f`. Nothing is
taken from a comment; each behavioural claim names the constant or branch that
decides it.

### 1. Defect (a) — the unlock is structurally unreachable for anchors

**The ladder.** `backend/server.py:6155-6175`, inside `get_rankings_progress`:

```
6163    if ranking_method == "manual":            → unlocked = True         (unconditional; that is A-17)
6165    elif ranking_method in ("tiers","quickset"):
6169        saved = get_tiers_saved(g_user_id, scoring_format=fmt)
6170        unlocked = all(p in saved for p in POSITIONS)
6173    else:   # 'trio' or null — and, silently, 'anchor'
6175        unlocked = all(counts[p] >= threshold for p in POSITIONS)   # 10 × 4 = 40
```

`'anchor'` is a first-class, server-accepted method string
(`backend/server.py:6289` docstring; `POST /api/ranking-method` accepts it) and is
**absent from every branch**, so it falls to the `else`.

**Why the else-branch is unsatisfiable on the anchor path.** `counts[p]` comes from
`service.get_progress(position=pos)["interaction_count"]`
(`backend/server.py:6147-6149` → `backend/ranking_service.py:715-722`), which reads
`self._interactions`. `_interactions` has exactly **two** writers:

| Writer | Where | Reached by |
|---|---|---|
| `record_ranking` | `backend/ranking_service.py:297-300` (`_interactions[pos] += 1`) | `POST /api/rank3` — the trio surface only |
| rehydration | `backend/ranking_service.py:770-783` — `_interactions = {pos: rank_swipe_count // 3}` | session build, derived **solely from persisted rank swipes** |

`apply_anchor` (`backend/ranking_service.py:1471-1487`) writes **only**
`self._elo_overrides[player_id]` and bumps `_version`. It does not touch
`_interactions`, and `/api/anchor/save` (`backend/server.py:7435-7550`) persists
only `save_tier_overrides`, `upsert_member_rankings`, a trends snapshot and the
`anchor_answered` event — **no rank swipe rows**.

Therefore: a user whose `ranking_method` is `'anchor'` needs 10 trio interactions in
each of QB/RB/WR/TE, and **no amount of anchoring ever produces one**. The only
escapes are the monotonic `unlocked_formats` floor (`server.py:6188-6189`), which
can only rescue someone who was *already* computed unlocked under some other
method, or abandoning the method entirely. Confirmed unreachable.

**Second-order damage, verified.** `mobile/src/screens/LeagueScreen.tsx:326-334`
computes `positionsRanked` from `progress[p] >= threshold || tiersSaved.includes(p)`.
Anchors write neither, so an anchor user's League ring reads **0/4** no matter how
many players they price — worse than P0-1's cohort, who at least see 4/4. And
`pushEnabled` in `mobile/src/navigation/RootNav.tsx:266-267` is `data?.unlocked ===
true`, so the push primer never fires for this cohort either — the same casualty
P0-1 documents, via a different route.

**How users land in this state today.** `mobile/src/screens/RankHomeScreen.tsx:57-71`
— `choose()` calls `setRankingMethod(m.pref)` for the tapped card, and
`mobile/src/navigation/rankChooserModel.ts:84-92` gives the "Pick Anchors" card
`pref: 'anchor'`. So **tapping the chooser card is today's live path into the
permanent lock.** The other door — the Rank tab action sheet — does *not*:
`TabNav.tsx:855-857` `pick()` calls `go(m.route)` only, never `setRankingMethod`, so
those users stay NULL (also locked, but by the trio rule).

**The audit's Option 1, taken literally, does not fix this.** "Add `anchor` to the
tiers/quickset unlock branch" would evaluate `all(p in get_tiers_saved(...))` — and
`/api/anchor/save` never calls `save_tiers_position` (verified: it is absent from
`server.py:7435-7550`, and `docs/cross-client-invariants.md:344` states the anchor
lane must never reach `save_tiers_position`). An anchor-only user has an empty
`tiers_saved`, so Option 1 as written leaves them locked forever. This plan
therefore builds a **third** option and says why (see Design §1).

### 2. Defect (b) — two vocabularies for one ladder, on the same screen

**The two constants.**

| Constant | File | Values |
|---|---|---|
| `TIER_LABEL` | `mobile/src/utils/tierBands.ts:39-48` | `4+ 1sts · 3 1sts · 2 1sts · 1 1st · 2nd · 3rd · 4th · FA` |
| `ANCHOR_ROWS` | `mobile/src/utils/anchorRows.ts:22-35` | `4 1sts · 3 1sts · 2 1sts · 1 1st · 1 2nd · 1 3rd · 1 4th · No value` |

**Five of eight rungs disagree, not two.** The audit named `4 1sts`/`4+ 1sts` and
`No value`/`FA`; re-verification adds `1 2nd`/`2nd`, `1 3rd`/`3rd`, `1 4th`/`4th`.
Only `3 1sts`, `2 1sts`, `1 1st` match.

**They are the same eight bands.** `docs/cross-client-invariants.md:358` states the
invariant outright — *every anchor answer lands in the tier that carries its name* —
and it is machine-pinned by
`backend/tests/test_tier_occupancy.py:179-198::test_anchor_rungs_land_in_matching_tiers`
for every position and format. The arithmetic checks out:
`_anchor_target_elo` (`server.py:1305-1324`) maps `1_second` → `GENERIC_PICK_SEEDS[(2,"Mid")]`
= 1460 (`backend/pick_values.py:24-38`), and `tier_config.json` puts `second` at
[1400, 1575]. Same for `1_third` → 1320 → `third`, `1_fourth` → 1240 → `fourth`, and
the three multi-first rungs → `firsts_2/3/4plus` at the default scale
(γ = log4/log4 = 1, `server.py:1323`).

**The contradiction is visible inside one tap.** `PickAnchorScreen.tsx:342-355`
renders the buttons from `ANCHOR_ROWS`; `:391-396` renders the confirmation line from
`TIER_LABEL[res.tier]`. Tap the button labelled **"1 2nd"**, read back **"2nd"**.
`AnchorSheet.tsx:124-140` / `:150-158` reproduce it exactly ("Set to 2nd").

**The `no_value` case is subtler than the audit states, and it matters.**
`ANCHOR_NO_VALUE_ELO = 1100.0` (`server.py:1263`) sits **below every band** —
`waivers` floors at 1150 (`backend/tier_config.json`), and
`RankingService.tier_for_elo` returns `None` below the lowest band
(`ranking_service.py:1259-1268`). So `/api/anchor/save` answers `tier: null`, and both
hosts fall back to their own literal `'No value'`
(`PickAnchorScreen.tsx:395`, `AnchorSheet.tsx:154`). **But mobile's own bucketing
disagrees with the backend:** `tierForElo` (`tierBands.ts:116-130`) has *no* lower
floor — anything under `fourth` (1220) returns `'waivers'`. So the same player reads
**"No value"** in the wizard and wears an **"FA"** badge on the Tiers board
(`TiersScreen.tsx:855`, `autoBucket` at `tierBands.ts:133-147`). That divergence is
the actual mechanism behind the audit's `No value` / `FA` complaint, and it is a
pre-existing mobile/backend gap, not something this change introduces.

**Which is canonical: `TIER_LABEL`, decisively.** It is replicated as the shared
ladder vocabulary across every client and the docs —
`mobile/src/utils/tierBands.ts:39`, `backend/og_image.py:61-70`,
`extension/content.js:33-42`, `web/profile.html:323-327`,
`web/positional-tiers.html:2960-2964`, `web/js/app.js:2076-2088` (`_eloToTierLabel`
floor mirror), `backend/trade_service.py:1892`, plus prose in
`docs/cross-client-invariants.md:15-22`, `docs/glossary.md:26`,
`docs/design/components.md:117`, `web/faq.html:197`, `web/style-guide.html:219`,
`web/index.html:187`, `web/ranking-method.html:225` — and it is even the vocabulary
the *chooser* uses to sell the Tiers board ("from 4+ 1sts down to FA",
`rankChooserModel.ts:75-76`). `ANCHOR_ROWS` exists in exactly **one** place
(`mobile/src/utils/anchorRows.ts`) plus one doc table
(`docs/cross-client-invariants.md:329-339`). Eleven-ish locations against one.

**The governing doc currently contradicts itself.** `cross-client-invariants.md:15`
gives `firsts_4plus` the label "4+ 1sts"; `:331` gives `4_firsts` the button label
"4 1sts"; `:358` asserts every anchor answer lands "in the tier that carries its
name". Those three statements cannot all be true. Reconciling the doc is part of this
fix, not a follow-up.

### 3. What is *not* broken (checked, so nobody re-checks)

- **No feature flag gates the wizard.** `PickAnchorScreen` is reachable unflagged
  from the chooser and the Rank action sheet. The second host, `AnchorSheet`, is
  gated by `draft.rank_inline`, which is **`true`** in both `config/features.json:158`
  and `backend/tests/fixtures/flags/release.json:158`. Both hosts are live.
- **No web or extension anchor surface exists.** `grep -rl "anchor/save|anchorRows|pick anchor" web/ extension/` → empty. The label change is mobile-only.
- **No Maestro flow asserts the anchor labels.** `grep -rn "1 2nd|1 3rd|1 4th|No value|4 1sts" mobile/.maestro/ screens/` → empty. `capture/anchors.yaml` anchors on `".*in draft capital.*"` and `".*Pull down to refresh.*"`; `AnchorSheet`'s rungs carry key-based testIDs (`anchor-sheet.rung.${key}`, `AnchorSheet.tsx:128`). **No flow asserts the bug** — a welcome exception to this audit's pattern. (`screens/manifest.json:55` *does* list `mobile/src/utils/anchorRows.ts` as a freshness source for the `anchors` screen, so editing it forces a re-capture — see Maestro delta.)
- **Anchor keys are unchanged by this plan.** `VALID_ANCHORS` (`server.py:1271-1273`) and `AnchorKey` (`mobile/src/api/rankings.ts:315-323`) are the wire contract; only display strings move.

### Drift from audit

The audit pinned `72a0770`; this worktree is `ab9368f`.

| Audit claim | Status at `ab9368f` | Note |
|---|---|---|
| "Pick Anchors can never unlock" | **Holds**, mechanism confirmed at `server.py:6163-6175` + `ranking_service.py:297-300, 770-783, 1471-1487` | — |
| Labels contradict: 2 mismatches (`4 1sts`, `No value`) | **Understated — 5 of 8 mismatch** | `1 2nd`/`2nd`, `1 3rd`/`3rd`, `1 4th`/`4th` also differ (`anchorRows.ts:30-33` vs `tierBands.ts:45-47`) |
| Resolution Option 1: "add `anchor` to the tiers/quickset unlock branch" | **Inert as written** | The tiers branch tests `tiers_saved`, which the anchor lane never writes (`server.py:7435-7550`) and is forbidden from writing (`cross-client-invariants.md:344`) |
| Resolution Option 2: "increment the interaction counter in `apply_anchor` (more consistent)" | **Non-durable and cross-contaminating** | `_interactions` is rebuilt from rank swipes at every session build (`ranking_service.py:770-783`), so an in-memory bump evaporates on the next cold start; see Design §1 |
| `No value` vs `FA` framed as "the same band, two names" | **Partly true** | Server pins `no_value` *below* `waivers` and returns `tier: null` (`server.py:1263`, `ranking_service.py:1259-1268`); mobile has no floor and buckets it as `waivers`/"FA" (`tierBands.ts:116-130`). The user-visible contradiction is real; the cause is a mobile/backend banding gap |
| A-16 graded **Effort S** | **Holds for the label half; the unlock half is S–M** | The unlock fix is ~15 lines of backend, but proving it on-device needs a new seed profile (see Test plan) |

---

## Design

### 1. The unlock: Option 3 — a durable, evidence-based `anchor` branch

**Rejecting Option 2 (increment `_interactions` in `apply_anchor`), with proof.**

1. **It does not survive a restart.** `_interactions` is *overwritten* at session
   build from persisted rank swipes only (`ranking_service.py:780-783`:
   `self._interactions = {pos: cnt // 3 …}`). Anchors persist as Elo overrides, never
   as swipe rows, so any in-memory increment is silently discarded on the next cold
   start. A user could unlock on Tuesday and be re-locked on Wednesday. To make it
   durable you would have to fabricate rank-swipe rows from an anchor — inventing a
   fake pairwise judgment that would then feed `_compute_elo` and distort the very
   board the anchor was pinning. Rejected on correctness, not taste.
2. **It fights P0-1's `draft_room` exclusion.** P0-1 deliberately does *not* write
   `ranking_method` for `via: 'draft_room'` (plan-p0-1 §2.2: "Answering an anchor
   inside the Draft Room is not choosing the Pick Anchor wizard as my ranking
   method"). But `apply_anchor` is the shared write lane for **both** surfaces
   (`server.py:7479`, reached by wizard and sheet alike), so a counter there would
   grant unlock credit to exactly the draft-room action P0-1 just excluded — and it
   would grant it on the **trio** branch, i.e. to NULL-method and `'trio'` users too.
   A Draft Room long-press would be silently worth one-fortieth of a Trade Finder
   unlock. That is precisely the double-count the prompt warns about.
3. **It conflates two different units.** A trio interaction is an ordering of three
   players; an anchor is a price on one. Adding them into one counter makes
   `total_completed` (`server.py:6153`, rendered as progress copy) a mixed-unit
   number.

**Rejecting Option 1 as literally written** — see Verified current state §1: the
tiers branch reads `tiers_saved`, which the anchor lane must never write.

**Option 3: give `'anchor'` its own branch, keyed on durable board evidence.**

```
elif ranking_method == "anchor":
    unlocked = (service.board_override_count() >= RankingService.ANCHOR_UNLOCK_MIN)
               or _tiers_rule(g_user_id, fmt)
```

- **The evidence is `tier_overrides`**, counted through a new
  `RankingService.board_override_count()` that returns the number of overrides whose
  pid is still in the current pool. It is:
  - **durable** — persisted by `save_tier_overrides` on every anchor save
    (`server.py:7486`) and rehydrated at session build
    (`server.py:14528-14531`), the exact opposite of `_interactions`;
  - **format-scoped for free** — overrides are stored per format
    (`database.py:3588-3621`) and `sess["service"]` is the *active format's* instance,
    re-pointed per request by `_require_session` (`server.py:2285-2291`,
    `_active_format` at `:2314-2316`). Unlock is per-format, so this matches;
  - **zero extra I/O** — the dict is already in memory on a hot, RootNav-polled GET.
    (This is why it beats counting `anchor_answered` rows in `user_events`, which
    would add a COUNT query to every poll *and* cannot be format-scoped: that event's
    props carry `player_id`/`pick_value`/`skipped`/`via` and no scoring format —
    `server.py:7519-7531`.)
- **It is not anchor-*pure*, and that is stated rather than hidden.** Tier saves and
  reorders also write overrides. But this predicate is evaluated **only inside the
  `'anchor'` branch**, which post-P0-1 is reached only by users whose *first* ranking
  action was a wizard anchor. Extra overrides from a later partial tier save mean
  *more* board work, never less, so the rule is strictly improving and can never
  re-lock anyone. An explicitly heuristic alternative — recognising the eight discrete
  anchor rung Elos in the override values — was considered and **rejected**: a
  fingerprint that clever is a comment waiting to lie.
- **The `or _tiers_rule(...)` clause** is belt-and-braces for legacy `'anchor'` users
  who already have a complete tier board from before P0-1's `allow_over` upgrade
  existed. One extracted helper, reused by both branches, so the two cannot drift.

**Threshold: `ANCHOR_UNLOCK_MIN = 40`** (class constant on `RankingService`, beside
`POSITION_THRESHOLDS` at `ranking_service.py:194`, so every unlock bar lives in one
place). Chosen to equal the trio bar (10 × 4 = 40, `server.py:6151-6152`) so the
product has *one* number to explain. Note it is deliberately **easier** than trios in
effort — 40 taps versus 40 three-player orderings — which is appropriate: the wizard's
default `ALL` scope serves a value-descending queue (`PickAnchorScreen.tsx:166-178`),
so the first 40 answers price the assets that actually move trade math. See
checkpoint **C2**.

**No per-position requirement, deliberately.** The trio and tiers rules are
per-position because those surfaces are per-position. The wizard's default scope is
one cross-position, value-descending queue (#133, `PickAnchorScreen.tsx:50-52, 175-178`).
Imposing 4-position completeness would import a shape the surface does not have and
would force users onto the position pills to escape a gate they cannot see.

### 2. How this composes with P0-1

P0-1 adds `set_ranking_method_if_unset(user_id, method, allow_over=())` and calls it
from `/api/anchor/save` **only when `via == "anchors"`** (plan-p0-1 §2.2, §3.2 item 9),
plus an `allow_over=("anchor",)` exception letting a completeness-marking
tiers/quickset save upgrade `'anchor'` → `'quickset'`.

Three consequences, all load-bearing here:

1. **P0-1 widens this bug before P1-7 fixes it.** Today only chooser-card tappers get
   `ranking_method = 'anchor'` (`RankHomeScreen.tsx:57-71`); the Rank action-sheet
   door leaves it NULL (`TabNav.tsx:855-857`). After P0-1, *every* wizard user is
   pinned to `'anchor'` on their first save. P0-1's own plan says so explicitly
   (§1.2: "`'anchor'` is not handled and also falls to the trio branch — that is audit
   finding **A-16**, out of scope here") and §2.1 calls the resulting state
   "permanently locked". **P0-1 must land first and P1-7 must follow closely**;
   shipping P0-1 alone strictly increases the size of the permanently-locked cohort.
2. **Option 3 composes; Option 2 would collide.** Option 3 reads a branch that only
   `ranking_method == 'anchor'` can enter, and `ranking_method` is written by exactly
   one mechanism — P0-1's. No double-counting is possible, because nothing outside the
   `'anchor'` branch consults the override count. Option 2 would have written unlock
   credit on the shared `apply_anchor` lane, *below* the method decision, reaching
   users P0-1 deliberately left NULL.
3. **P0-1's `allow_over` exception stays correct and becomes cheaper.** It exists
   because `'anchor'` was a guaranteed-locked state. After P1-7 it is no longer
   guaranteed-locked, so the exception is now a convenience (a user who anchors twice
   then completes Quick Set is scored on the rule that matches their real behaviour)
   rather than a rescue. **Recommendation: keep it unchanged.** Removing it is a
   P0-1 edit this plan has no business making, and keeping it can only unlock, never
   lock.

**What happens to a user who anchors via `draft_room` — explicitly.**

| Their situation | Before P0-1 | After P0-1 | After P0-1 + P1-7 |
|---|---|---|---|
| Only ever long-presses in the Draft Room (`via: 'draft_room'`) | `ranking_method` NULL → trio branch → locked | NULL (P0-1 skips `draft_room`) → trio branch → **still locked** | **Still locked. Unchanged and intended.** Their overrides accumulate but the `'anchor'` branch is never entered, because nothing wrote them into it |
| Draft Room first, then one wizard answer | NULL unless they used the chooser | `'anchor'` (written by the wizard save, `via: 'anchors'`) | Enters the anchor branch — and their **earlier draft-room overrides count** toward the 40, because the predicate reads the board, not the event stream |

The second row is a small asymmetry and it is deliberate: the board is the board, and
retroactively discounting work the user genuinely did would be the unfriendly reading.
It cannot leak credit to anyone P0-1 excluded, because entering the branch still
requires a wizard answer. Recorded as risk **R3**.

### 3. The labels: derive, don't copy

`TIER_LABEL` is canonical (Verified current state §2). The fix is **not** to
re-type its strings into `ANCHOR_ROWS` — that reproduces the divergence with a fresh
timestamp. Instead, `anchorRows.ts` gains an explicit key→tier map and *derives*
every button label from the ladder:

```ts
// mobile/src/utils/anchorRows.ts
export const ANCHOR_TIER: Record<AnchorKey, Tier | null> = {
  '4_firsts': 'firsts_4plus',
  '3_firsts': 'firsts_3',
  '2_firsts': 'firsts_2',
  '1_first' : 'first_1',
  '1_second': 'second',
  '1_third' : 'third',
  '1_fourth': 'fourth',
  'no_value': null,          // pins below every band (Elo 1100) — see below
};

/** The one string for "below the ladder" — button label AND the null-tier
 *  result fallback, so a rung and its confirmation can never disagree. */
export const BELOW_LADDER_LABEL = TIER_LABEL.waivers;   // 'FA'

export const anchorLabel = (k: AnchorKey): string => {
  const t = ANCHOR_TIER[k];
  return t ? TIER_LABEL[t] : BELOW_LADDER_LABEL;
};

export const ANCHOR_ROWS: readonly AnchorRung[][] = ANCHOR_KEY_ROWS.map(
  (row) => row.map((key) => ({ key, label: anchorLabel(key) })),
);
```

Resulting grid: **4+ 1sts · 3 1sts · 2 1sts · 1 1st** / **2nd · 3rd · 4th · FA**.

Both hosts then replace their hard-coded `'No value'` fallbacks
(`PickAnchorScreen.tsx:395`, `AnchorSheet.tsx:154`) with `BELOW_LADDER_LABEL`, so the
button a user taps and the confirmation they read are the same string by
construction. `ANCHOR_TIER` also encodes the name↔rung invariant in *code* for the
first time — until now it lived only in a doc sentence and a backend test.

**Three judgment calls inside this, each surfaced as a checkpoint:**

- **`4_firsts` → "4+ 1sts"** (C3). The rung pins to exactly 4 × a Mid 1st
  (Elo ≈ 1927.3), which is the *floor* of an open-ended top band, so "4+" slightly
  overstates the question while exactly stating the answer. Recommendation: adopt
  "4+ 1sts" — the badge the player will wear on every other surface says "4+ 1sts",
  and a button that disagrees with its own outcome is the defect being fixed.
- **`1_second/1_third/1_fourth` → "2nd"/"3rd"/"4th"** (C3). Losing the "1 " prefix
  costs a little readability in an eight-button grid, but the question above the grid
  ("Worth how much in draft capital?", `PickAnchorScreen.tsx:340`,
  `AnchorSheet.tsx:122`) supplies the unit, and the alternative — changing
  `TIER_LABEL` to "1 2nd" — would ripple through six clients, the OG image renderer,
  the extension, four docs and the style guide. Recommendation: adopt `TIER_LABEL`
  verbatim.
- **`no_value` → "FA"** (C4). The honest tension: the server pins `no_value` *below*
  the `waivers` band and answers `tier: null`, but mobile's own `tierForElo` has no
  floor and shows that player an **FA** badge on the Tiers board. Labelling the button
  "FA" makes the wizard agree with the board the user will actually look at, at the
  cost of the button no longer naming the sub-band pin. Recommendation: **"FA"**, with
  the doc updated to distinguish *display tier* from *pin Elo* in one sentence — and
  the underlying mobile/backend banding gap (mobile ignores the 1150 floor) recorded
  as a separate backlog item rather than fixed here. It is a `TiersScreen` bucketing
  change (`autoBucket` returns `Record<Tier, T[]>`; a null tier would need the
  existing `unassigned` zone) and does not belong in an S-sized label fix.

### 4. Making the gate visible (severable)

An unlock bar the user cannot see is exactly the failure shape of P0-1. The wizard
already renders `{answered} / {scopedQueue.length} anchored`
(`PickAnchorScreen.tsx:314-319`). Two additive response keys — `anchor_count`,
`anchor_required` — let it read `12 / 40 priced · unlocks at 40` for anchor-method
users. This is **severable from the correctness fix** and is checkpoint **C5**.

---

## Exact change list

Ordered; backend before mobile before tests before docs.

### Backend

1. **`backend/ranking_service.py`** — beside `POSITION_THRESHOLDS` (`:194`), add
   `ANCHOR_UNLOCK_MIN = 40` with a docstring stating it is the anchor-method
   equivalent of the trio bar and why it is not per-position.
2. **`backend/ranking_service.py`** — add
   `def board_override_count(self) -> int:` near `apply_anchor` (`:1471`). Returns
   `len({pid for pid in self._elo_overrides if pid in pool_ids})` over `self._pool(None)`.
   Docstring must state *why* pool-restriction matters: `_elo_overrides` deliberately
   retains stale pids (`server.py:14515-14526`), so a raw `len()` would over-count a
   long-lived board.
3. **`backend/server.py:6163-6175`** — extract the tiers predicate into a local
   helper (`_tiers_rule(user_id, fmt) -> bool`, wrapping the existing
   `get_tiers_saved` + `all(...)` + `except → False`), use it in the existing
   `("tiers","quickset")` branch, and add:
   ```python
   elif ranking_method == "anchor":
       # A-16 / P1-7: anchors write Elo overrides, never trio interactions
       # (ranking_service.apply_anchor) and never tiers_saved (the anchor lane
       # must not — cross-client-invariants.md). Without this branch the
       # method falls to the trio rule and can NEVER unlock.
       unlocked = (service.board_override_count()
                   >= RankingService.ANCHOR_UNLOCK_MIN) or _tiers_rule(g_user_id, fmt)
   ```
   Keep it **above** the `else`, below the tiers branch. Do not touch the `manual`
   branch (that is A-17 / P1-8).
4. **`backend/server.py:6274-6283`** — add two additive response keys to the
   `get_rankings_progress` payload: `"anchor_count": <int>` and
   `"anchor_required": RankingService.ANCHOR_UNLOCK_MIN`. Computed unconditionally
   (cheap, in-memory) so clients need no branch. *Only if C5 is approved; otherwise
   skip 4 and mobile item 9.*
5. **`backend/server.py:6289-6298`** — extend the `POST /api/ranking-method`
   docstring: `'anchor'` now has its own unlock rule. One sentence; the comment there
   currently implies the chooser is the only writer, which P0-1 already falsifies.

### Mobile

6. **`mobile/src/utils/anchorRows.ts`** — rewrite per Design §3: keep `AnchorRung`
   and the two-row ordering as `ANCHOR_KEY_ROWS`; add `ANCHOR_TIER`,
   `BELOW_LADDER_LABEL`, `anchorLabel`; derive `ANCHOR_ROWS`. Import `TIER_LABEL`
   from `./tierBands` and `Tier` from `../shared/types`. Rewrite the header comment:
   it currently says the keys are the contract and the order is presentational —
   still true — and must now add that **labels are derived from the ladder, not
   authored here**, with a pointer to `docs/cross-client-invariants.md`.
   *(Check for an import cycle: `tierBands.ts` imports only from `shared/types` and
   `api/rankings` types — no cycle. Verify with `tsc` regardless.)*
7. **`mobile/src/screens/PickAnchorScreen.tsx:391-396`** — replace the literal
   `'No value'` fallback with `BELOW_LADDER_LABEL`; import it. No other logic change.
8. **`mobile/src/screens/PickAnchorScreen.tsx:344-353`** — add
   `testID={`anchors.rung.${key}`}` to each rung `Button`. The wizard's rungs have
   **no testIDs today**, which is why the label change cannot currently be asserted
   on the primary host. (`AnchorSheet` already has `anchor-sheet.rung.${key}`.)
9. **`mobile/src/screens/PickAnchorScreen.tsx:314-319`** — *(C5 only)* append
   `· unlocks at {anchor_required}` / progress toward it, sourced from the progress
   query. Requires adding a `useQuery(['progress'])` read or lifting the existing one;
   keep it non-blocking (absent data ⇒ render today's string unchanged).
10. **`mobile/src/components/AnchorSheet.tsx:150-158`** — same `BELOW_LADDER_LABEL`
    substitution as item 7.
11. **`mobile/scripts/testid-lint-allow.txt`** — add `anchors.rung*` beside the
    existing `anchors.scope*` entry (`:44-45`), with the same
    `PickAnchorScreen.tsx:<line>` provenance comment. The id is a template literal, so
    the lint's `testID=` grep cannot see it.
12. **`mobile/src/screens/CLAUDE.md`** — register the new `anchors.rung.*` ids in the
    screen's testID list (mirroring how `anchors.scope-*` is documented).

### Tests

13. **`backend/tests/test_anchor_unlock.py`** (new) — the unlock matrix (Test plan §1).
14. **`backend/tests/test_pick_anchor.py`** — extend, don't replace: add one case
    pinning that `/api/anchor/save` still writes **no** `tiers_saved` entry and no
    rank swipe (the two things the fix deliberately does not do).
15. **`mobile/tests/check-anchor-labels.js`** (new) — AST structural check in the
    style of `check-member-entered-marker.js` / `check-mock-lifecycle.js`: fail if
    `anchorRows.ts` contains any string literal in a `label` position, or if
    `ANCHOR_TIER` does not cover every `AnchorKey`. This is what stops the two
    vocabularies from re-diverging; without it the fix is a one-time patch.
16. **`backend/tests/fixtures/profiles/anchors-done.json`** (new) + seeder support for
    the already-reserved-but-unimplemented `app_user.anchors` key (it appears as
    `null` in every profile — `quickset-done.json`, `near-unlock.json`, etc. — and
    `seed_ui_test_db.py` has no handler for it; verified by grep). Minimal shape:
    `{"count": 40, "formats": ["sf_tep"]}` → write `count` overrides at anchor-rung
    Elos for the top-valued pool players and set `ranking_method: "anchor"`. Gated on
    checkpoint **C6**.

### Docs and living memory

17. Per the [Docs impact table](#docs-impact-table).
18. `living-memory/CHANGELOG.md`, `TEST_LEDGER.md`, `DECISIONS.md` (**D-012**, or the
    next free id after P0-1 takes D-011 — check at write time).

---

## Surface changes

| Surface | Changed? | Detail |
|---|---|---|
| **Routes** | **None added, renamed or removed.** | `GET /api/rankings/progress` and `POST /api/anchor/save` keep their paths, methods and gates (`@_gate_unverified_read` / `@_gate_unverified_write`). |
| **API contract — request** | **No.** | No new or changed request field on any route. `VALID_ANCHORS` (`server.py:1271`) and `AnchorKey` (`api/rankings.ts:315`) are byte-identical. |
| **API contract — response (shape)** | **Additive, and only if C5 is approved.** | `/api/rankings/progress` gains `anchor_count` and `anchor_required`. Purely additive; no key removed, renamed or retyped. Existing consumers (`RootNav.tsx:259-283`, `LeagueScreen.tsx:326-334`, `RankScreen.tsx:356`) ignore unknown keys. Without C5: **no shape change at all.** |
| **API contract — values** | **Yes — that is the fix.** | `/api/rankings/progress` → `unlocked` flips `false → true` for anchor-method users with ≥ 40 board overrides. `unlocked_formats` gains the active format for that cohort via the existing monotonic write (`server.py:6199-6213`). No other value domain moves. |
| **Schema** | **None.** | No column, table, index or type. The evidence store (`users.tier_overrides`) and the method column (`users.ranking_method`) both already exist (`database.py:181-183`). No migration, no backfill — a legacy `'anchor'` user with zero anchors correctly stays locked until they anchor. |
| **Feature flags** | **None added; none re-defaulted.** | The wizard is unflagged; `AnchorSheet` rides the already-`true` `draft.rank_inline`. No bright line demands a new flag: the unlock change removes a wrong answer rather than adding a surface, so a flag's OFF position would be a known bug. |
| **Analytics events** | **No new event name; no event removed.** | `anchor_answered` (`server.py:7519-7531`) is untouched, including its `via` prop. Nothing new is registered against the default-deny taxonomy (`backend/analytics_taxonomy.py`). |
| **Analytics — derived series** | **Yes, flagged.** | `ranking_complete_first_time` (`server.py:6228-6238`) will now fire for anchor users who cross 40, and the `league_member_unlocked_trades` push fans out to their leaguemates on that same transition (`:6241-6265`). Both are *correct* — those users genuinely became unlocked — but they are a step change in a shipped series. See **R2**. |
| **Experiment targeting** | **No new attribute.** | `ranking_method` is already a registered targeting attribute (`backend/experiments.py:59`); P0-1 owns that risk and flags it as its **Q4**. P1-7 does not change which users hold which method — only what `'anchor'` *means* at the unlock gate. |
| **Cross-client enums** | **Display strings only.** | The eight tier keys, the eight anchor keys and every Elo band are unchanged. Five anchor **button labels** change on two mobile surfaces. Web, extension and OG images render `TIER_LABEL` already and are untouched. |
| **Push behaviour** | **Yes — intended.** | `pushEnabled` (`RootNav.tsx:266-267`) starts becoming true for the anchor cohort. Same acceptance shape as P0-1. |

**Bright-line verdict.** Routes: no. Schema: no. Feature-flag surfaces: no. Analytics
events: no new names. But the change alters an **API value domain** consumed by the
client and shifts a **shipped funnel series**, and it changes a **cross-client
display vocabulary** governed by `docs/cross-client-invariants.md`. Per root
`CLAUDE.md` § Feature gates this is **not** a quick fix; **full gates apply** unless
the operator declares express, and an agent never self-selects express. This plan
assumes full gates.

---

## Maestro delta

Conventions: `mobile/.maestro/README.md`, flow-authoring laws 1-23.

### Nothing currently asserts the bug — verified

`grep -rn "1 2nd|1 3rd|1 4th|No value|4 1sts|2 1sts|3 1sts|1 1st" mobile/.maestro/ screens/`
returns **nothing**. `capture/anchors.yaml` anchors on `".*in draft capital.*"`
(`:175-178`) and `".*Pull down to refresh.*"` (`:93-96`), neither of which moves.
No flow needs *repairing*; flows need *adding*, because the labels have never been
covered.

### 1. New flow — `mobile/.maestro/flows/p1-7-anchor-labels.yaml`

Header per convention: `appId`, `# tc:`, `# profile: standard`, `# flags: release`
(law 16 — a resolved fixture filename under `backend/tests/fixtures/flags/`),
`# source:`, `tags: [p1-7, anchors]`.

Steps:

1. `launchApp: {clearState: true, clearKeychain: true, stopApp: true}` (law 6 — the
   query cache is persisted, `App.tsx:241`).
2. Retry-hardened sign-in as `qa_standard`, asserting the typed username before
   Continue (law 10), then `leagues.row.990000000000000001` → tap. Reuse the preamble
   from `capture/anchors.yaml:35-63` verbatim.
3. `extendedWaitUntil: id: rank.more-ways` before any tab tap (law 8 — #244 launch
   routing steals early tab taps).
4. `tapOn: rank.more-ways` → `rankmenu.more-toggle` → `rankmenu.anchors`.
5. `extendedWaitUntil: visible: {text: ".*in draft capital.*"}` — the loaded branch
   (`PickAnchorScreen.tsx:340`), the same arrival anchor the capture flow proved.
6. **The assertion.** For each of the five changed rungs, one
   `assertVisible: {id: "anchors.rung.<key>", text: "<label>"}` pair using the new
   testIDs from change 8 — `4_firsts`→`4+ 1sts`, `1_second`→`2nd`, `1_third`→`3rd`,
   `1_fourth`→`4th`, `no_value`→`FA`. Id-scoped, so it cannot pass on a stray label
   elsewhere on screen (law 1: assert on ids, and full-match regex is avoided by
   scoping to the element).
7. `tapOn: {id: "anchors.rung.no_value"}` then
   `assertVisible: {text: ".*FA.*"}` on the consequence line
   (`PickAnchorScreen.tsx:391-396`) — **this is the round-trip that proves the fix**:
   the rung tapped and the confirmation read are now the same word. Pre-fix this step
   reads "No value" and fails.
8. `takeScreenshot: p1-7__anchor-rungs` and eyeball it (law 23).

**Why one flow, not two.** The defect is the *disagreement* between the button and its
confirmation; two flows could each pass in separate sessions and never prove they
agree.

### 2. Extended flow — `mobile/.maestro/capture/anchors.yaml`

`screens/manifest.json:55` lists `mobile/src/utils/anchorRows.ts` among the `anchors`
screen's freshness sources, so `screen-freshness.sh` **will** flag this screen and the
three captures (`error`, `loading`, `question`) must be re-taken. The `question`
capture is the one whose pixels change (the eight rung buttons). No step edits are
required — the flow's anchors are label-independent — but add one line to the header
noting that the rungs now render `TIER_LABEL`-derived text, so a future reader does not
"fix" it back.

### 3. New flow — `mobile/.maestro/flows/p1-7-anchor-unlock.yaml` *(gated on C6)*

Requires the `anchors-done` seed profile (change 16). Shape mirrors P0-1's
`p0-1-quickset-unlock.yaml`: cold start → sign in as the anchor user → League tab →
progress module → then Rank tab → assert `rank.unlocked-banner` (**the testID P0-1
introduces at `RankScreen.tsx:686`** — a hard dependency on P0-1 having merged).
If C6 is declined, this flow is **waived in writing**, with the unlock proved by
pytest (Test plan §1) plus the manual pass (§4); the waiver and its reason go in the
scope block §3.

### 4. Smoke-suite impact

Crossing surfaces: `flows/smoke/04-tiers.yaml` (tier labels — unchanged, but the same
constant), `09-league.yaml` (the progress ring), `06-trades-deck.yaml` (unlock-gated
deck), and the Draft Room flows that can open `AnchorSheet`. Expectation: all green and
unchanged, since no smoke profile has `ranking_method = 'anchor'`. **Verify, don't
assume.**

### 5. testID lint

Two new ids, both template literals: `anchors.rung.${key}`. Covered by the
`anchors.rung*` glob added to `testid-lint-allow.txt` (change 11). Run
`mobile/scripts/testid-lint.sh` — exit 0 required.

---

## Docs impact table

Row per `docs/CLAUDE.md` trigger, plus the scope template §4 rows.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/cross-client-invariants.md` | **Updated — YES, twice, and it is the load-bearing doc row** | (a) **§Pick anchor keys, the button-label table (`:329-339`)**: five labels change (`4 1sts`→`4+ 1sts`, `1 2nd`→`2nd`, `1 3rd`→`3rd`, `1 4th`→`4th`, `No value`→`FA`), plus one sentence stating labels are now **derived** from `TIER_LABEL` via `ANCHOR_TIER` in `mobile/src/utils/anchorRows.ts` and must never be authored independently. (b) **§"Tier labels ARE pick terms" (`:358`)**: it currently asserts every anchor answer lands in the tier carrying its name while `:331` gives different names — resolve the self-contradiction and add the *display-tier vs pin-Elo* sentence for `no_value` (pins at 1100, below the `waivers` floor of 1150; server returns `tier: null`; mobile's floor-less `tierForElo` shows FA). (c) Note the mobile/backend floor divergence as a known gap with a pointer to the backlog item from **C4**. |
| `docs/api-reference.md` | **Updated** | `GET /api/rankings/progress` — document the new `'anchor'` unlock rule (≥ `ANCHOR_UNLOCK_MIN` board overrides in the active format, OR the tiers rule), and the additive `anchor_count` / `anchor_required` keys **if C5 is approved**. No route added/renamed/removed. |
| `docs/glossary.md` | **Updated** | The **Tier band** entry (`:26`) already lists the eight labels; add one clause to the **Pick anchor** vocabulary noting the wizard's buttons are the same eight labels, derived. (Check whether a "Pick Anchors" entry exists at write time; if not, add one — it is a domain term used in four screens and two docs.) |
| `living-memory/LLD.md` | **Updated** | A convention shifts twice: (1) unlock rules are per-method and now include an evidence-count rule keyed on `tier_overrides`; (2) display labels for a shared vocabulary are **derived from a single constant**, with a structural test enforcing it. Two short entries. |
| `living-memory/DECISIONS.md` | **Updated** | **D-012** (verify the next free id — P0-1 claims D-011): why Option 3 over the audit's Options 1 and 2 (durability + the P0-1 `draft_room` collision), why `TIER_LABEL` is canonical over `ANCHOR_ROWS` (11 locations vs 1), why `no_value` displays as FA, and why `ANCHOR_UNLOCK_MIN = 40` is not per-position. |
| `docs/data-dictionary.md` | **n/a** | No schema change. `users.tier_overrides` and `users.ranking_method` are unchanged in shape and semantics. *(P0-1 already corrects the stale `ranking_method` enum comment at `database.py:181` — do not duplicate that edit; re-diff before touching the line.)* |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change: same routes, same services, same store. |
| `living-memory/HLD.md` | **n/a** | No new module, client or major flow. |
| `docs/config-reference.md` | **n/a** | No env var, no `config/features.json` key, no `model_config` key. `ANCHOR_UNLOCK_MIN` is a Python class constant, not runtime config (see **C2** if the operator wants it tunable — that *would* make this row a YES). |
| `docs/runbook.md` | **n/a** | No new operational procedure, no migration, no backfill. |
| ADR | **n/a** | No decision of ADR weight; `DECISIONS.md` D-012 carries it. |
| `docs/design/design-system.md` / `components.md` | **n/a** | No new component, no token change. The rung buttons stay the specced compact `Button`. *(`components.md:117` mentions the ladder's top/bottom labels in prose — re-read at build time and correct only if it names an anchor label.)* |
| `living-memory/CHANGELOG.md` | **Updated** | Dated H2 at ship. |
| `living-memory/TEST_LEDGER.md` | **Updated** | pytest + `tsc` + `testid-lint.sh` + `check-anchor-labels.js` + the sim-gate run. |
| `living-memory/GOTCHAS.md` | **Conditional** | Only if the build loses >30 min to something new. The `_interactions`-is-rebuilt-from-swipes trap is a strong candidate (**G-0xx**) — it is exactly the kind of thing the next agent will re-derive the hard way. |
| `living-memory/DEPENDENCIES.md` | **n/a** | No dependency added, bumped or removed. |
| `screens/manifest.json` + `screens/CLAUDE.md` | **Updated** | The `anchors` screen's three captures are re-taken (its freshness source `anchorRows.ts` changed); manifest hashes update as a side effect of `screen-capture.sh`. |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a** | The audit is a dated artifact. Record the outcome in `CHANGELOG.md`; do not rewrite the audit. *(The label-count drift — 5 mismatches, not 2 — and the "Option 1 is inert" finding are recorded **here**, in Verified current state.)* |

---

## Test plan

### 1. Backend — `backend/tests/test_anchor_unlock.py` (new)

In-repo pattern (`backend/tests/test_rookie_scope.py`, `test_pick_anchor.py`):
in-memory SQLite via `monkeypatch.setattr(db_module, "engine", engine)`, an injected
`RankingService`, a real Flask test client with a seeded session token.

**The unlock rule**

| # | Case | Assert |
|---|---|---|
| T-1 | `ranking_method='anchor'`, 0 overrides | `unlocked is False` |
| T-2 | `'anchor'`, `ANCHOR_UNLOCK_MIN - 1` overrides | `unlocked is False` |
| T-3 | `'anchor'`, exactly `ANCHOR_UNLOCK_MIN` overrides | **`unlocked is True`** — the headline |
| T-4 | `'anchor'`, 0 overrides but all four positions in `tiers_saved` | `unlocked is True` (the `or _tiers_rule` clause) |
| T-5 | `'anchor'`, 40 overrides in `1qb_ppr`, request under `sf_tep` | `unlocked is False` — per-format scoping is real |
| T-6 | `'anchor'`, 40 overrides of which 10 are pids absent from the pool | `unlocked is False` — `board_override_count` restricts to the pool |
| T-7 | Live path: `'anchor'` user POSTs `/api/anchor/save` × 40, then GETs `/api/rankings/progress` | `unlocked is True` **and** all four `counts[p] == 0` — proving the unlock came from the board, not from a fabricated interaction |

**No regressions to the other branches**

| # | Case | Assert |
|---|---|---|
| T-8 | `'trio'` with 40 overrides and 0 interactions | `unlocked is False` — the anchor rule must not leak into the trio branch |
| T-9 | `NULL` method with 40 overrides | `unlocked is False` — same, and this is the `draft_room`-only cohort |
| T-10 | `'quickset'` with 4/4 `tiers_saved` | `unlocked is True` — untouched by the refactor into `_tiers_rule` |
| T-11 | `'manual'` | `unlocked is True` — A-17's bug is deliberately preserved here; P1-8 owns it |
| T-12 | `'anchor'` user already in `unlocked_formats` with 0 overrides | `unlocked is True` — the monotonic floor (`server.py:6188-6189`) still wins |
| T-13 | `'anchor'`, cross 40, GET progress twice | `ranking_complete_first_time` recorded exactly once (`was_first` gating, `server.py:6228`) |

**Composition with P0-1** *(these run against merged `main`, post-P0-1)*

| # | Case | Assert |
|---|---|---|
| T-14 | Fresh NULL user → `POST /api/anchor/save {via:'anchors'}` × 40 → progress | method is `'anchor'` (P0-1's write) **and** `unlocked is True` (P1-7's rule). The two fixes compose end to end |
| T-15 | Fresh NULL user → `POST /api/anchor/save {via:'draft_room'}` × 40 → progress | method still `NULL` **and** `unlocked is False`. **The draft-room exclusion is preserved** — this is the anti-double-count assertion |
| T-16 | `'anchor'` user with 40 overrides then a completeness `tiers/save {via:'quickset'}` | method upgrades to `'quickset'` (P0-1 `allow_over`) and `unlocked` **stays True** (tiers rule now satisfied). No re-lock on the method transition |

**Durability — the reason Option 2 was rejected**

| # | Case | Assert |
|---|---|---|
| T-17 | 40 anchor saves, then rebuild the session service from the DB (simulating a cold start) | `board_override_count() == 40` — and, as the control, `_interactions` is `{}`. This test is the executable form of the Option-2 rejection; name it so |

**Non-goals, pinned** (extend `backend/tests/test_pick_anchor.py`)

| # | Case | Assert |
|---|---|---|
| T-18 | `POST /api/anchor/save` | `tiers_saved` unchanged and **no** rank-swipe row written — the anchor lane still touches neither (`cross-client-invariants.md:344`) |

Command: `python3 -m pytest backend/tests/ -q`. Suites that must stay green because
they touch the ladder or the unlock: `test_pick_anchor.py`, `test_tier_occupancy.py`,
`test_draft_extensions_w1.py`, `test_test_users.py`, `test_seed_ui_test_db.py`,
`test_trio_cross_position.py`, `test_rookie_scope.py`, and P0-1's new
`test_ranking_method_point_of_use.py`.

### 2. Mobile — static

- `cd mobile && npx tsc --noEmit` — must be clean. The derived `ANCHOR_ROWS` keeps its
  `readonly AnchorRung[][]` type, so both hosts compile unchanged apart from the
  fallback constant.
- `mobile/scripts/testid-lint.sh` — exit 0.
- **`mobile/tests/check-anchor-labels.js` (new)** — the anti-regression: fails if any
  rung label is a string literal, or if `ANCHOR_TIER` misses an `AnchorKey`. Without
  this the next agent re-types the strings and the bug returns.

### 3. Simulator gate

Change class: **mobile screen visual change on two surfaces** ⇒ **Tier 1** per the
matrix in `docs/runbook.md` § Pre-ship simulator gate: full smoke suite (11 flows) +
`p1-7-anchor-labels.yaml` (+ `p1-7-anchor-unlock.yaml` if C6 is approved) +
`mobile/scripts/screen-capture.sh --screen anchors`. Evidence: `TEST_LEDGER.md` entry
and `qa/sim-runs/last-sim-run.json`.

### 4. Manual verification (by eye, with a pre-fix control)

1. Seed `standard`, boot the UI-test backend on :5001 (kill orphans first — law 19),
   install the build.
2. Rank → More ways → Pick Anchors. The grid reads **4+ 1sts / 3 1sts / 2 1sts /
   1 1st / 2nd / 3rd / 4th / FA**.
3. Tap **FA**. The confirmation reads "… → FA". Tap **2nd**; it reads "… → 2nd".
4. Open the Tiers board and confirm the FA-anchored player carries the **FA** badge —
   the wizard and the board now say the same word.
5. **Pre-fix control:** repeat 2-4 on the pre-fix build and observe "4 1sts" → "4+ 1sts"
   and "No value" → FA badge. *A test that never observed the bug proves nothing.*
6. Unlock, on device: with the `anchors-done` profile (C6) confirm `unlocked:true` and
   the payoff banner. Without it, drive 40 anchors by hand once, or verify at the
   network layer (`/api/rankings/progress` → `unlocked:true`) and record which was used.

---

## Risks and cross-item collisions

**R1 — P0-1 must land first, and this must follow closely.** P0-1 pins every wizard
user to `ranking_method = 'anchor'` at their first save, which today means
*permanently locked*. Between P0-1's merge and P1-7's, the locked cohort grows. P0-1
mitigates partly (`allow_over=("anchor",)` rescues anyone who later completes a Quick
Set board) but not for anchor-only users. **Mitigation:** sequence them in the same
release window; if P1-7 slips, say so to the operator explicitly rather than letting
the gap widen quietly.

**R2 — First-unlock fan-out for the anchor cohort.** Crossing 40 takes the `was_first`
branch: `ranking_complete_first_time` fires and `league_member_unlocked_trades` pushes
to every joined leaguemate (`server.py:6228-6265`). At 16 production users this is a
handful of notifications and arguably correct. P0-1 raises the identical risk as its
**R2/Q5** for the Quick Set cohort. **The two deploys must not stack unnoticed** —
whatever the operator decides for P0-1's fan-out should apply here (see **C1**).

**R3 — The draft-room asymmetry.** A user who long-presses 40 anchors in the Draft
Room and *then* answers one wizard question unlocks immediately, because the predicate
reads the board rather than the event stream. Deliberate (Design §2), strictly
improving, and unreachable without a wizard answer — but state it in D-012 so nobody
later reads it as a leak in P0-1's exclusion.

**R4 — `board_override_count` is not anchor-pure.** Partial tier saves and manual
reorders also write overrides, so an `'anchor'`-method user with a half-finished tier
board could cross 40 without 40 anchors. They did do the board work; the rule cannot
re-lock anyone and cannot be entered without a wizard answer. Accepted, documented,
asserted by T-8/T-9 (the leak directions that would matter).

**R5 — Collision with P1-8 (A-17, the manual branch).** P1-8 adds an evidence
requirement to `ranking_method == "manual"` in the **same ladder**
(`server.py:6163-6175`) that this plan edits. Same function, adjacent lines, near-
certain merge conflict. **Mitigation:** whoever lands second rebases; the `_tiers_rule`
helper extracted here (change 3) is the natural shared seam, and P1-8 should be told it
exists. If both build concurrently, agree the branch order up front:
`manual` → `tiers/quickset` → `anchor` → `else`.

**R6 — Collision with P0-1 in `server.py`.** P0-1 edits `save_anchor_route`
(`:7479`), comments the unlock ladder (`:6155-6175`), and imports into `:148`. P1-7
edits the ladder body and the response dict. **Re-diff `server.py` immediately before
editing**; do not trust the line numbers in this plan after P0-1 merges.

**R7 — The `no_value` label decision is a semantic claim, not just a string.**
Labelling the button "FA" asserts an equivalence the backend does not make (it pins
below the band and returns `tier: null`). If a future change makes mobile honour the
1150 floor, that player becomes tier-less and the button's promise breaks. Mitigation:
`ANCHOR_TIER['no_value'] = null` keeps the distinction in the type system even while
the *display* borrows the `waivers` label, and the doc sentence records it. See **C4**.

**R8 — Sibling sessions mutate this worktree's premises.** Root `CLAUDE.md` warns that
several sessions run concurrently. `mobile/src/utils/tierBands.ts` is the source this
plan derives from; if another item re-labels a tier, the anchor grid follows silently —
which is the *point*, but it means a label review must look at one file, not two.

---

## Operator checkpoints

**C1 — Suppress the first-unlock push fan-out for the anchor cohort?** (R2)
P0-1 asks the same question as its Q5 for Quick Set users. Whatever is decided there
should apply here, so the two deploys don't produce two separate bursts of
"@user just unlocked Trade Finder." **Recommendation: match P0-1's answer, whatever it
is.** Not blocking on build; blocking on merge only if P0-1's answer is "suppress".

**C2 — `ANCHOR_UNLOCK_MIN = 40`: confirm the number, and should it be tunable?**
40 equals the trio bar, so the product explains one number. It is *easier* than trios
in real effort (40 taps vs 40 three-player orderings), which I read as correct given
the wizard's value-descending queue. Alternatives: **20** (faster time-to-unlock, board
thinner), **40** (recommended), **60** (parity in perceived effort, more friction).
Secondary: making it a `model_config` key instead of a Python constant would add a
deploy-free lever — at the cost of a `docs/config-reference.md` row and one more knob.
**Recommendation: 40, as a constant.** If the operator wants the lever, say so now; it
flips one row of the docs table to YES.

**C3 — Confirm the label direction: `ANCHOR_ROWS` conforms to `TIER_LABEL`.**
Evidence for `TIER_LABEL` as canonical: ~11 code/doc locations across four clients
versus one, and it is already the vocabulary the chooser uses to describe the tiers
board. The cost is that three buttons lose their "1 " prefix (`1 2nd` → `2nd`) and the
top button gains a "+" (`4 1sts` → `4+ 1sts`). The alternative — moving `TIER_LABEL`
toward the anchor strings — touches mobile, web ×3, the extension, OG image rendering,
the style guide, the FAQ and the glossary. **Recommendation: conform `ANCHOR_ROWS`.**

**C4 — `no_value`: display "FA", or keep "No value" as a ninth vocabulary item?**
- **Option A (recommended): "FA".** The wizard then agrees with the badge the player
  actually wears on the mobile Tiers board. Cost: the label no longer signals that the
  pin sits *below* the FA band server-side; the doc gains one clarifying sentence.
- **Option B: keep "No value"**, and instead fix the *other* direction by making the
  confirmation line and the board agree with it — which requires teaching mobile the
  1150 floor (`tierForElo` → nullable), rippling into `autoBucket`/`autoBucketMixed`
  and `TiersScreen`'s zone model. Correct, but not an S.
**Recommendation: A now, B logged as a separate backlog item** ("mobile `tierForElo`
ignores the `waivers` 1150 floor that `tier_config.json` and the backend enforce").

**C5 — Ship the visible progress hint (`anchor_count` / `anchor_required` + wizard
copy)?** An unlock bar the user cannot see is the exact shape of P0-1's failure. Cost:
two additive response keys and one line of wizard copy (changes 4 and 9). **Recommendation:
yes** — but it is cleanly severable, so decline it and the correctness fix ships
unchanged with **no API shape change at all**.

**C6 — Build the `anchors-done` seed profile so the unlock is provable on-device?**
`app_user.anchors` is already reserved in every profile JSON and implemented by
nothing. Implementing it costs a seeder handler plus one fixture, and buys a Maestro
flow that proves the unlock end to end (and a reusable fixture for any future anchor
work). Declining it means the unlock is proved by pytest + a manual pass only, and the
Maestro waiver must be written into the scope block. **Recommendation: yes** — the
audit found this class of bug precisely because no fixture reproduced it.

**C7 — Sequencing with P1-8 (A-17).** Both edit the same unlock ladder (R5). Confirm
which lands first and tell the second agent that `_tiers_rule` exists, or hand both
items to one session. **Recommendation: one session, or P1-7 first** — P1-7 extracts
the helper P1-8 will want.
