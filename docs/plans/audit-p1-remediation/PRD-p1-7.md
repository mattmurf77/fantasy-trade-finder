# PRD — P1-7 · Pick Anchors can never unlock, and its labels contradict the ladder (audit A-16)

> **Purpose.** What is broken, what "fixed" means, and how each claim is
> individually proved. Acceptance criteria are numbered and testable one at a
> time — including the negative case that must *stay* broken by design.
>
> **Status:** requirements only. No source file is changed by this document.
> **Author:** LLD/PRD agent, 2026-08-11.
> **Worktree:** `/Users/teresadickens/Documents/Claude/Projects/ftf-p1-remediation`,
> branch `p1-remediation-2026-08-11` @ `ab9368f`.
> **Companion:** [`LLD-p1-7.md`](LLD-p1-7.md) · **Plan:** [`plan-p1-7.md`](plan-p1-7.md) ·
> **Scope block:** [`scope-p1-7.md`](scope-p1-7.md) · **Reconciliation:** [`HLD-p1.md`](HLD-p1.md)
>
> **Binding:** [`DECISIONS-p1.md` D-P1-02](DECISIONS-p1.md#d-p1-02--p1-7-fixes-the-anchor-lane-only)
> — **the manual lane is out of scope by explicit operator decision.** This item
> fixes the anchor lane only. §8 is the required write-down of the accepted
> manual-lane lock.

## Contents

- [1. Problem statement](#1-problem-statement)
- [2. Who is affected, and how they get there](#2-who-is-affected-and-how-they-get-there)
- [3. Before / after, per ranking method](#3-before--after-per-ranking-method)
- [4. Goals and non-goals](#4-goals-and-non-goals)
- [5. Acceptance criteria](#5-acceptance-criteria)
- [6. Maestro flow specs](#6-maestro-flow-specs)
- [7. Docs impact](#7-docs-impact)
- [8. Required GOTCHAS.md entry — the accepted manual-lane lock](#8-required-gotchasmd-entry--the-accepted-manual-lane-lock)
- [9. Operator gates](#9-operator-gates)
- [10. Release risk and rollback](#10-release-risk-and-rollback)

---

## 1. Problem statement

### 1.1 Defect (a) — the unlock is not hard, it is **impossible**

A user who picks "Pick Anchors" as their ranking method can never unlock the
Trade Finder. Not "rarely", not "slowly" — **never**, by construction. The proof
is four verified facts at `ab9368f`:

1. `'anchor'` is a first-class ranking method: `POST /api/ranking-method` accepts
   it (`backend/server.py:6303`), and the rank-home chooser writes it —
   `mobile/src/navigation/rankChooserModel.ts:83` gives the "Pick Anchors" card
   `pref: 'anchor'`, and `RankHomeScreen.tsx:57-72` persists it.
2. The unlock ladder (`backend/server.py:6163-6175`) has three arms — `manual`,
   `("tiers","quickset")`, and an `else`. **`'anchor'` is in none of them**, so it
   falls to the `else`: 10 trio interactions in each of QB/RB/WR/TE.
3. That counter can only be moved by trio swipes. It is
   `RankingService._interactions`, written by `record_ranking`
   (`backend/ranking_service.py:299-300`, reached only by `POST /api/rank3`) and
   rebuilt at every session build from persisted rank swipes
   (`:780-783`).
4. The anchor lane writes none of it. `apply_anchor`
   (`ranking_service.py:1471-1487`) sets an Elo override and nothing else;
   `POST /api/anchor/save` (`server.py:7437-7550`) persists overrides, member
   rankings, a trends snapshot and an `anchor_answered` event — **no rank-swipe
   row, no `tiers_saved` entry** (`save_tiers_position` occurs only at
   `server.py:6626` and `:7370`).

**Second-order damage.** The same cohort reads **0/4** on the League progress
ring (`mobile/src/screens/LeagueScreen.tsx:328-334` counts
`progress[p] >= threshold || tiersSaved.includes(p)` — anchors write neither),
and never receives the push primer, because `pushEnabled` is
`progressQuery.data?.unlocked === true` (`RootNav.tsx:266-267`).

**The audit's two proposed fixes do not work, and the reasons are load-bearing.**
Option 1 ("add `anchor` to the tiers/quickset branch") is **inert** — that branch
tests `tiers_saved`, which the anchor lane never writes and is forbidden from
writing (`server.py:1280-1282`). Option 2 ("increment the interaction counter in
`apply_anchor`") is **non-durable** — `_interactions` is rebuilt from swipes at
every session build, so the credit evaporates on the next cold start — **and
cross-contaminating**: `apply_anchor` is the shared lane for both hosts, so it
would hand unlock credit to the `via: 'draft_room'` action P0-1 deliberately
excludes, on the *trio* branch, reaching NULL-method users too. Full rationale in
[`LLD-p1-7.md` §3](LLD-p1-7.md#3-design-restated-compactly-do-not-re-open).

### 1.2 Defect (b) — two vocabularies for one ladder, contradicting inside one tap

| Constant | File | Values |
|---|---|---|
| `TIER_LABEL` | `mobile/src/utils/tierBands.ts:39-48` | `4+ 1sts · 3 1sts · 2 1sts · 1 1st · 2nd · 3rd · 4th · FA` |
| `ANCHOR_ROWS` | `mobile/src/utils/anchorRows.ts:22-35` | `4 1sts · 3 1sts · 2 1sts · 1 1st · 1 2nd · 1 3rd · 1 4th · No value` |

**Five of eight rungs disagree, not the two the audit named.** Beyond
`4 1sts`/`4+ 1sts` and `No value`/`FA`, re-verification adds `1 2nd`/`2nd`,
`1 3rd`/`3rd`, `1 4th`/`4th`. Only `3 1sts`, `2 1sts` and `1 1st` match.

They are the same eight bands — pinned by
`backend/tests/test_tier_occupancy.py::test_anchor_rungs_land_in_matching_tiers`
and stated at `docs/cross-client-invariants.md:358`. So the contradiction is
visible **inside a single interaction**: `PickAnchorScreen.tsx:342-355` renders
the buttons from `ANCHOR_ROWS`; `:391-396` renders the confirmation from
`TIER_LABEL`. Tap **"1 2nd"**, read back **"2nd"**. `AnchorSheet.tsx:124-140` /
`:151-158` reproduce it exactly ("Set to 2nd").

`TIER_LABEL` is canonical by an enormous margin: **~21 verified locations across
mobile, three web pages, the extension, the OG renderer, the trade service and
four docs** (enumerated in [`LLD-p1-7.md` §6.1](LLD-p1-7.md#61-why-tier_label-is-canonical-evidence-verified)),
against `ANCHOR_ROWS`'s one code location and one doc table.

---

## 2. Who is affected, and how they get there

| Door | Writes `ranking_method`? | Today | After P0-1 merges |
|---|---|---|---|
| Rank Home chooser → "Pick Anchors" card | **Yes** (`RankHomeScreen.tsx:57-72` → `rankChooserModel.ts:83`) | `'anchor'` → permanently locked | unchanged |
| Rank tab action sheet → Anchors | No (`TabNav.tsx` `pick()` navigates only) | NULL → locked by the trio rule | unchanged |
| Draft Room long-press → `AnchorSheet` (`via: 'draft_room'`) | No | NULL → locked by the trio rule | **still NULL — P0-1 excludes `draft_room`** |
| Any wizard save (`via: 'anchors'`) | No | — | **`'anchor'` → permanently locked.** P0-1 pins every wizard user |

**P0-1 widens this defect on merge.** Its own plan says so (§1.2: "`'anchor'` is
not handled and also falls to the trio branch — that is audit finding **A-16**,
out of scope here"). The locked cohort grows every day between the P0 merge and
this one — which is why `HLD-p1.md` §C places P1-7 in **Wave A**, the first P1
build wave. **If P1-7 slips past that wave, say so to the operator explicitly**
rather than letting the gap widen quietly.

---

## 3. Before / after, per ranking method

`unlocked` as computed by `GET /api/rankings/progress`, before the monotonic
floor (`server.py:6188-6189`), which is unchanged and still wins in both columns.

| `users.ranking_method` | Rule before | Rule after | Behaviour change |
|---|---|---|---|
| `'manual'` | `True`, unconditionally (`:6163-6164`) | **identical — byte-unchanged** | **None. Deliberate.** A-17 / P1-8 owns this arm; **D-P1-02 forbids touching it** |
| `'tiers'` | all four positions in `tiers_saved` for the active format | identical, now expressed through the extracted `_tiers_rule()` helper | **None.** Pure refactor; pinned by T-10 |
| `'quickset'` | same as `'tiers'` | same as `'tiers'` | **None** |
| **`'anchor'`** | **fell to the trio rule → structurally impossible** | **≥ `ANCHOR_UNLOCK_MIN` (40) pool-resident board overrides in the active format, OR the tiers rule** | **The fix.** `unlocked` flips `false → true` for anchorers with a real board |
| `'trio'` | 10 interactions × 4 positions | identical | **None.** The anchor rule must not leak here — pinned by T-8 |
| `NULL` | same as `'trio'` | identical | **None.** This is the draft-room-only cohort — pinned by T-9 |

**Why the anchor rule is not per-position.** The trio and tiers rules are
per-position because those surfaces are per-position. The wizard's default scope
is one cross-position, value-descending queue (#133,
`PickAnchorScreen.tsx`), so imposing 4-position completeness would import a shape
the surface does not have and force users onto the position pills to escape a
gate they cannot see.

**Why 40.** It equals the trio bar (10 × 4, `server.py:6151-6152`) so the product
has one number to explain. It is deliberately *easier* in effort — 40 taps versus
40 three-player orderings — which is appropriate: the wizard serves a
value-descending queue, so the first 40 answers price the assets that actually
move trade math. **Gated on RL-2.**

### Label change, before / after

| Key | Before | After | Scale-invariant? |
|---|---|---|---|
| `4_firsts` | `4 1sts` | **`4+ 1sts`** | No — re-spaced by `users.anchor_scale` |
| `3_firsts` | `3 1sts` | `3 1sts` | No |
| `2_firsts` | `2 1sts` | `2 1sts` | No |
| `1_first` | `1 1st` | `1 1st` | **Yes** |
| `1_second` | `1 2nd` | **`2nd`** | **Yes** |
| `1_third` | `1 3rd` | **`3rd`** | **Yes** |
| `1_fourth` | `1 4th` | **`4th`** | **Yes** |
| `no_value` | `No value` | **`FA`** | **Yes** |

**Scope of the round-trip guarantee.** "The button you tap and the confirmation
you read are the same word" is exact at the **default** anchor scale, and
unconditionally exact for the five scale-invariant rungs. A user who has set
`users.anchor_scale` to N < 4 re-spaces the three multi-first rungs upward
(`server.py:1305-1324`, γ = log 4 / log N), so their "2 1sts" answer can land in
`firsts_4plus` and read back "4+ 1sts". That is **by design and pre-existing** —
`docs/cross-client-invariants.md:358` already carries the "at the default scale"
qualifier — and it is why every automated round-trip assertion uses a
scale-invariant rung.

---

## 4. Goals and non-goals

**Goals**

- G1. An anchor-method user with a real board unlocks the Trade Finder, durably,
  across cold starts and format switches.
- G2. The wizard's eight buttons speak the app's one ladder vocabulary, derived
  from it rather than copied.
- G3. Neither can silently regress: the unlock is pinned by a pytest matrix, the
  labels by a structural AST test.

**Non-goals — each stated so nobody "helpfully" adds it**

- **N1. The manual lane.** `ranking_method == 'manual'` still unlocks
  unconditionally, and after P0-1 a manual-first user is pinned to `'manual'` and
  falls through to the trio rule for everything else. **Known, accepted, unfixed,
  by explicit operator decision (D-P1-02).** §8 is the required write-down.
- **N2. Mobile's missing `waivers` floor.** `tierForElo`
  (`mobile/src/utils/tierBands.ts:116-130`) ignores the 1150 floor the backend
  enforces. Logged as a backlog item, not fixed —
  [`LLD-p1-7.md` §8](LLD-p1-7.md#8-no_value-handling).
- **N3. Mobile's three duplicated label maps.** `TIER_LABEL`,
  `TierBadge.tsx:15` and `chalkline/Badge.tsx:31` agree today but are not derived
  from one another. Same backlog item.
- **N4. Anchor keys, Elo bands, tier colors, the `via` whitelist.** Wire
  contracts. Untouched.
- **N5. New analytics events, new flags, schema.** None. `anchor_answered` is
  byte-unchanged including its `via` prop.

---

## 5. Acceptance criteria

Twenty-two, each independently testable. **Test key:** `PY` = pytest ·
`AST` = `mobile/tests/check-anchor-labels.js` · `TSC` = `npx tsc --noEmit` ·
`LINT` = `mobile/scripts/testid-lint.sh` · `MAE` = Maestro (§6) ·
`EYE` = manual, by eye · `GREP` = static check.

### The unlock — positive

| # | Criterion | Proof |
|---|---|---|
| **AC-1** | An `'anchor'`-method user with **0** board overrides gets `unlocked: false` | PY T-1 |
| **AC-2** | With **39** overrides: `unlocked: false` | PY T-2 |
| **AC-3** | With exactly **40**: `unlocked: true` — **the headline** | PY T-3 |
| **AC-4** | Reached via the live path — 40 × `POST /api/anchor/save`, then `GET /api/rankings/progress` — `unlocked: true` **and all four per-position counts are still 0** | PY T-7. Proves the unlock came from the board, not from a fabricated interaction |
| **AC-5** | An `'anchor'` user with 0 overrides but all four positions in `tiers_saved`: `unlocked: true` (the `or _tiers_rule()` clause) | PY T-4 |
| **AC-6** | **Durability:** 40 anchor saves, then rebuild the service from the DB (cold-start simulation) → `board_override_count() == 40` **and** `_interactions == {}` | PY T-17, named `test_override_count_survives_rebuild_but_interactions_do_not`. The executable form of the Option-2 rejection |
| **AC-7** | **Format scoping:** 40 overrides in `1qb_ppr`, request under `sf_tep` → `unlocked: false` | PY T-5 |
| **AC-8** | **Pool restriction:** 40 overrides of which 10 are pids absent from the pool → `unlocked: false` | PY T-6 |
| **AC-9** | Crossing 40 twice records `ranking_complete_first_time` **exactly once** (`was_first` gating, `server.py:6228`) | PY T-13 |

### The unlock — negatives (the rule must not leak)

| # | Criterion | Proof |
|---|---|---|
| **AC-10** | **A draft-room-only anchorer stays locked.** A fresh NULL-method user who POSTs `/api/anchor/save {via:'draft_room'}` × 40 keeps `ranking_method` NULL **and** `unlocked: false`. **This is designed behaviour, not a bug** — P0-1 deliberately excludes `draft_room` from writing the method, so the `'anchor'` arm is never entered and the trio rule still applies | PY T-15. **The anti-double-count assertion of this item** |
| **AC-11** | A `'trio'`-method user with 40 overrides and 0 interactions: `unlocked: false` | PY T-8 |
| **AC-12** | A NULL-method user with 40 overrides: `unlocked: false` | PY T-9 |
| **AC-13** | `'quickset'` with 4/4 `tiers_saved`: `unlocked: true` — untouched by the `_tiers_rule` extraction | PY T-10 |
| **AC-14** | `'manual'`: `unlocked: true`, unconditionally. **A-17's behaviour is deliberately preserved** (D-P1-02) | PY T-11 |
| **AC-15** | An `'anchor'` user already in `unlocked_formats` with 0 overrides: `unlocked: true` — the monotonic floor still wins | PY T-12 |
| **AC-16** | An `'anchor'` user with 40 overrides who then completes a `tiers/save {via:'quickset'}` upgrades to `'quickset'` (P0-1 `allow_over`) and **stays** `unlocked: true` — no re-lock on the method transition | PY T-16 |
| **AC-17** | `POST /api/anchor/save` still writes **no** `tiers_saved` entry and **no** rank-swipe row | PY T-18 (extends `test_pick_anchor.py`) |
| **AC-18** | **Composition with P0-1:** a fresh NULL user who POSTs `{via:'anchors'}` × 40 ends with method `'anchor'` **and** `unlocked: true` | PY T-14. The two fixes compose end to end |

### The labels

| # | Criterion | Proof |
|---|---|---|
| **AC-19** | The wizard grid reads **`4+ 1sts · 3 1sts · 2 1sts · 1 1st` / `2nd · 3rd · 4th · FA`**, each assertion scoped to its own `anchors.rung.<key>` testID | MAE flow 1 step 6 · EYE |
| **AC-20** | **Round trip:** tapping `anchors.rung.no_value` produces a confirmation containing the **same word** as the button (`FA`). Pre-fix this reads "No value" and fails | MAE flow 1 step 7 · EYE. Uses a scale-invariant rung on purpose (§3) |
| **AC-21** | `mobile/src/utils/anchorRows.ts` contains **no string literal in a `label` position**; `ANCHOR_TIER` covers every `AnchorKey` exactly; every non-null value is a member of `TIERS`; `ANCHOR_TIER['no_value']` is `null`; `BELOW_LADDER_LABEL` derives from `TIER_LABEL`; neither host contains `'No value'` | AST (5 assertions, [`LLD-p1-7.md` §7](LLD-p1-7.md#7-the-structural-anti-divergence-test)) |
| **AC-22** | `npx tsc --noEmit` clean; `testid-lint.sh` exit 0; `grep -rn "anchor/save\|anchorRows\|pick anchor" web/ extension/` still empty (no non-mobile anchor surface appeared) | TSC · LINT · GREP |

**If RL-8 (the visible progress hint) is approved, add:**

| # | Criterion | Proof |
|---|---|---|
| **AC-23** | `GET /api/rankings/progress` returns additive `anchor_count` and `anchor_required` on every call, for every method; no existing key is removed, renamed or retyped | PY · GREP |
| **AC-24** | The wizard's progress line renders the unlock target when the data is present and **today's string unchanged** when it is absent | EYE · MAE |

**If RL-9 (the `anchors-done` fixture) is approved, add:**

| # | Criterion | Proof |
|---|---|---|
| **AC-25** | Signing in as the seeded anchor user and opening the app produces `unlocked: true` on the **first** progress call, with **no pre-seeded `unlocked_formats` row** — the League ring reads 4/4 and the Rank unlock banner renders | MAE flow 3 · EYE. See the monotonic-floor trap, [`LLD-p1-7.md` §9](LLD-p1-7.md#9-test-fixtures--and-the-monotonic-floor-trap) |

**If RL-9 is declined:** AC-25 is **waived in writing** in `scope-p1-7.md` §3
(waiver 1 of 3) and AC-3/AC-4/AC-6/AC-18 plus the manual pass stand as the proof.

---

## 6. Maestro flow specs

Conventions: `mobile/.maestro/README.md`, flow-authoring laws 1–23. **id-selectors
only** (law 1: text matchers are full-match regex).

**Nothing currently asserts the bug — verified.**
`grep -rn "1 2nd\|1 3rd\|1 4th\|No value\|4 1sts" mobile/.maestro/ screens/`
returns nothing. `capture/anchors.yaml` anchors on `".*in draft capital.*"` and
`".*Pull down to refresh.*"`, neither of which moves; `AnchorSheet`'s rungs carry
key-based testIDs (`anchor-sheet.rung.${key}`, `AnchorSheet.tsx:129`) and are
immune. **No flow needs repairing; flows need adding.**

### Flow 1 — `mobile/.maestro/flows/p1-7-anchor-labels.yaml` (new, mandatory)

Header: `appId` · `# tc: TC-P1-7-LABELS` · `# profile: standard` ·
`# flags: release` (law 16 — a resolved fixture filename under
`backend/tests/fixtures/flags/`) · `# source:` · `tags: [p1-7, anchors]`.

1. `launchApp: {clearState: true, clearKeychain: true, stopApp: true}` (law 6 —
   the query cache is persisted).
2. Retry-hardened sign-in as `qa_standard`, asserting the typed username before
   Continue (law 10), then `leagues.row.990000000000000001` → tap. **Reuse the
   preamble from `capture/anchors.yaml:36-58` verbatim.**
3. Reach the wizard exactly as `capture/anchors.yaml:53-63` does — and settle on
   the surface's own header control, not on the tab bar, before proceeding
   (law 8: #244 launch routing steals early tab taps):
   `extendedWaitUntil {id: "tab.rank"}` → `tapOn tab.rank` →
   `extendedWaitUntil {id: "rank.more-ways"}`.
4. `tapOn: {id: "rank.more-ways"}` → wait `rankmenu.more-toggle` → tap → wait
   `rankmenu.anchors` → tap.
5. `extendedWaitUntil: {visible: {text: ".*in draft capital.*"}}` — the loaded
   branch (`PickAnchorScreen.tsx:340`), the same arrival anchor the capture flow
   already proved.
6. **The label guard (AC-19).** Five id-scoped pairs, one per changed rung, using
   the testIDs added by this item:

   ```yaml
   - assertVisible: {id: "anchors.rung.4_firsts", text: ".*4\\+ 1sts.*"}
   - assertVisible: {id: "anchors.rung.1_second", text: "2nd"}
   - assertVisible: {id: "anchors.rung.1_third",  text: "3rd"}
   - assertVisible: {id: "anchors.rung.1_fourth", text: "4th"}
   - assertVisible: {id: "anchors.rung.no_value", text: "FA"}
   ```

   Scoping to the id means the assertion cannot pass on a stray label elsewhere
   on screen. The three unchanged rungs (`3_firsts`, `2_firsts`, `1_first`) are
   asserted too, as controls.
7. **The round trip (AC-20).** `tapOn: {id: "anchors.rung.no_value"}`, then
   `assertVisible: {text: ".*FA.*"}` on the consequence line
   (`PickAnchorScreen.tsx:391-396`). **This is the step that proves the fix** —
   pre-fix it reads "No value" and fails. `no_value` is chosen because it is
   scale-invariant (§3): a multi-first rung could legitimately disagree for a
   user with a non-default `anchor_scale`.
8. `takeScreenshot: p1-7__anchor-rungs`, and **eyeball it** (law 23).

**Why one flow, not two.** The defect *is* the disagreement between the button
and its confirmation. Two flows could each pass in separate sessions and never
prove they agree.

### Flow 2 — `mobile/.maestro/capture/anchors.yaml` (extend, mandatory)

`screens/manifest.json:55` lists `mobile/src/utils/anchorRows.ts` in the `anchors`
screen's `"source"` array (`:52-56`, hashed at `:57`), so `screen-freshness.sh`
**will** flag this screen and all three captures (`error`, `loading`, `question`)
must be re-taken. The `question` capture is the one whose pixels move.

**No step edits are required** — the flow's anchors are label-independent. Add
**one header line** recording that the rungs now render `TIER_LABEL`-derived
text, so a future reader does not "fix" it back.

### Flow 3 — `mobile/.maestro/flows/p1-7-anchor-unlock.yaml` (new, **gated on RL-9**)

Requires the `anchors-done` seed profile. Shape mirrors P0-1's
`p0-1-quickset-unlock.yaml`: cold start → sign in as the seeded anchor user →
League tab → assert the progress module reads 4/4 → Rank tab → assert
`rank.unlocked-banner`.

**Two hard dependencies, both re-verified before writing a line:**

- `testID="rank.unlocked-banner"` at `RankScreen.tsx:686` is **introduced by
  P0-1**. Absent ⇒ this flow cannot be written; report it rather than adding the
  testID (that file is P1-11's in Wave C).
- The fixture must seed **`"unlocked": false`**, or the monotonic floor
  (`server.py:6188-6189`) answers before the new branch and the flow proves
  nothing. See [`LLD-p1-7.md` §9](LLD-p1-7.md#9-test-fixtures--and-the-monotonic-floor-trap).

**If RL-9 is declined**, this flow is waived in writing in `scope-p1-7.md` §3.

### testID delta

Eight new ids, all template literals: `anchors.rung.${key}`
(`PickAnchorScreen.tsx`, whose rung buttons have **no** testIDs today). Covered by
an `anchors.rung*` glob in `mobile/scripts/testid-lint-allow.txt` beside the
existing `anchors.scope*` entry (`:44-45`), plus one clause on the
`PickAnchorScreen` row of `mobile/src/screens/CLAUDE.md:15` — **not** a new
registry section; that file has none. `mobile/scripts/testid-lint.sh` exit 0
required.

### Re-capture requirement

**Screen: `anchors`, all three states.** Run
`mobile/scripts/screen-capture.sh --screen anchors` and
`mobile/scripts/screen-freshness.sh` to confirm nothing else is flagged
(re-check whether any Draft Room capture photographs an open `AnchorSheet` —
`draft.rank_inline` is `true` in both `config/features.json:158` and
`backend/tests/fixtures/flags/release.json:158`, so verify rather than assume).

**Coordinate with `HLD-p1.md` §A.5 R1.** Six items invalidate captures this
round; the HLD consolidates them into **one pass after Wave C, before the P1
branch merges**. This item does **not** run its own capture pass in Wave A — it
contributes `anchors` to R1's list and preserves the pre-fix PNGs per
`screens/CLAUDE.md`'s artifact-of-record rule.

### Simulator gate

**Tier 1** per `docs/runbook.md` § Pre-ship simulator gate (mobile screen visual
change on two live surfaces; the backend half alone would be Tier 3 and the
stricter tier governs). Required before merge: full smoke suite (11 flows,
`mobile/.maestro/flows/smoke/01-…11-…`) + flow 1 (+ flow 3 if RL-9) + the
`anchors` captures. Evidence: `TEST_LEDGER.md` entry and
`qa/sim-runs/last-sim-run.json`; `githooks/pre-push` enforces locally.

**Smoke-suite expectation:** all green and unchanged — **no smoke profile has
`ranking_method = 'anchor'`**, so no smoke path enters the new branch. Crossing
surfaces to watch: `04-tiers.yaml` (same label constant), `09-league.yaml` (the
progress ring), `06-trades-deck.yaml` (unlock-gated deck). **Verify, do not
assume.**

### Manual verification (with a pre-fix control)

1. Seed `standard`, boot the UI-test backend on :5001 (kill orphans first —
   law 19), install the build.
2. Rank → More ways → Pick Anchors. Grid reads
   **4+ 1sts / 3 1sts / 2 1sts / 1 1st / 2nd / 3rd / 4th / FA**.
3. Tap **FA** → confirmation reads "… → FA". Tap **2nd** → "… → 2nd".
4. Open the Tiers board: the FA-anchored player carries the **FA** badge — wizard
   and board now say the same word.
5. **Pre-fix control:** repeat 2–4 on the pre-fix build and observe "4 1sts" and
   "No value". *A test that never observed the bug proves nothing.*

---

## 7. Docs impact

Full table with the exact edits in
[`LLD-p1-7.md` §11](LLD-p1-7.md#11-docs-and-living-memory-write-back). Summary:

| Doc | Updated? | Why |
|---|---|---|
| **`docs/cross-client-invariants.md`** | **YES — load-bearing** | Five button labels in the `:329-338` table; the sentence that labels are **derived** and must never be authored independently; the display-tier-vs-pin-Elo clause for `no_value`. `:358`'s "at the default scale" qualifier is already correct and is **not** rewritten |
| `docs/api-reference.md` | **YES** | `GET /api/rankings/progress` — the `'anchor'` unlock rule (+ two additive keys if RL-8). No route added, renamed or removed |
| `docs/glossary.md` | **YES** | One clause on the Tier band entry (`:26`); add a "Pick Anchors" entry if absent |
| `living-memory/LLD.md` | **YES** | Two convention shifts: evidence-count unlock rules; derived shared-vocabulary labels enforced by a structural test |
| `living-memory/DECISIONS.md` | **YES** | Next free ID **at write time** (`D-025` at `ab9368f`; **not** the plan's `D-012` — `HLD-p1.md` §A.6/R-12) |
| **`living-memory/GOTCHAS.md`** | **YES — mandatory** | §8 below. Required by D-P1-02 |
| `living-memory/CHANGELOG.md` · `TEST_LEDGER.md` · `NEXT.md` | **YES** | Ship entry (naming the analytics seam) · the five gates · the N2/N3 backlog item |
| `screens/manifest.json` · `screens/CLAUDE.md` · `mobile/src/screens/CLAUDE.md` | **YES** | Capture hashes via R1; the `anchors.rung.*` clause |
| `docs/data-dictionary.md` · `architecture.md` · `HLD.md` · `config-reference.md` · `runbook.md` · ADR · `design/*` · `DEPENDENCIES.md` | **n/a** | No schema, wiring, module, env/flag/`model_config` key (unless RL-2 elects the lever), procedure, ADR-weight decision, component/token or dependency |
| `docs/business/product/2026-08-09-mobile-ux-audit/*` | **n/a** | Dated artifact; the drift is recorded in the plan and in [`LLD-p1-7.md` §0](LLD-p1-7.md#0-corrections-to-the-plan) |

---

## 8. Required GOTCHAS.md entry — the accepted manual-lane lock

**Mandated by [`DECISIONS-p1.md` D-P1-02](DECISIONS-p1.md#d-p1-02--p1-7-fixes-the-anchor-lane-only).**
Written even though the gap is not fixed, so that (1) it is not rediscovered and
filed as a new bug, (2) the P1-7 implementer does not "helpfully" fix it while in
the file, and (3) there is an answer when a tester reports it.

**ID:** next free at write time (`G-027` at `ab9368f`; re-read the file — do not
reuse a plan's printed ID, `HLD-p1.md` R-12). Filed under a dated H2 per
`living-memory/FORMAT.md`. Draft text:

> ### G-0NN — the `manual` ranking method has the same structural lock A-16 fixed for anchors, and it is knowingly left in place
>
> - **Symptom:** a user whose first ranking action was a manual reorder sees the
>   Trade Finder behave inconsistently around the unlock gate, and the League
>   progress ring can disagree with what the Rank tab shows. Reported as "I
>   ranked everyone and it still won't let me in", or the mirror image.
> - **Cause, two halves.** (1) `GET /api/rankings/progress`'s unlock ladder
>   (`backend/server.py:6163-6175`) answers `unlocked = True` for
>   `ranking_method == 'manual'` **unconditionally, with no evidence check** —
>   that is audit finding **A-17 / P1-8**, which the operator excluded from the
>   2026-08-11 P1 round. (2) After P0-1, `reorder_rankings` calls
>   `_note_ranking_method(sess, "manual")`, so a manual-first user is *pinned* to
>   `'manual'` and every other per-method rule falls through to the trio rule —
>   the same structural lock **P1-7 removed for `'anchor'`, in the same function,
>   seven lines away**.
> - **Status: known, accepted, unfixed.** Operator decision, 2026-08-11
>   (`docs/plans/audit-p1-remediation/DECISIONS-p1.md` **D-P1-02**): "the manual
>   lane is not a priority. Anchors only." **This is not a bug to fix while
>   passing through the file** — doing so is an unrequested scope expansion
>   against an explicit decision.
> - **When it is fixed:** the seam already exists. P1-7 extracted `_tiers_rule()`
>   as a local helper in that ladder precisely so the `manual` arm can adopt an
>   evidence rule without a second refactor. Branch order settles as
>   `manual → tiers/quickset → anchor → else`. See
>   `docs/plans/audit-p1-remediation/LLD-p1-7.md` §5 and `HLD-p1.md` **SQ-1**
>   (which records the consequence of shipping half the ladder), and raise A-17
>   in `NEXT.md`.

**Recommended second entry** (not mandated): the `_interactions` trap —
`RankingService._interactions` is **rebuilt from persisted rank swipes on every
session build** (`backend/ranking_service.py:780-783`), so anything that
increments it in memory silently evaporates on the next cold start. It is exactly
what the next agent will re-derive the hard way, and it is the reason the audit's
Option 2 was rejected.

---

## 9. Operator gates

Seven, unresolved. **This PRD resolves none of them.** Full text in
`plan-p1-7.md` § Operator checkpoints; consolidated ids in `HLD-p1.md` §E.

| Plan | HLD | Question | Blocks | Recommendation carried forward |
|---|---|---|---|---|
| **C1** | **RL-5** | Suppress the first-unlock push fan-out for the anchor cohort? Crossing 40 fires `ranking_complete_first_time` and pushes `league_member_unlocked_trades` to every joined leaguemate (`server.py:6228-6265`) | **Merge**, if the answer is "suppress" | Match P0-1's Q5 answer. **The two deploys must not stack unnoticed** (`HLD-p1.md` R-8) |
| **C2** | **RL-2** | `ANCHOR_UNLOCK_MIN = 40` — confirm the number; constant or `model_config` key? | **Build** | 40, as a constant. A key flips `config-reference.md` to YES |
| **C3** | **RL-6** | `ANCHOR_ROWS` conforms to `TIER_LABEL`? | **Build** — the whole label design | Conform. ~21 locations across four clients versus one |
| **C4** | **RL-7** | `no_value` → "FA", or a ninth vocabulary item? | **Build** | "FA" now; log the mobile floor gap separately (N2) |
| **C5** | **RL-8** | Ship the visible progress hint? | **Build**, severable | Yes — declining it means **zero** API shape change |
| **C6** | **RL-9** | Build the `anchors-done` seed profile (`app_user.anchors` is reserved everywhere and implemented by nothing)? | **Build** | Yes — the audit found this class of bug precisely because no fixture reproduced it |
| **C7** | **SQ-1** | Sequencing with P1-8 (A-17), which edits the same ladder | **Build order** | Not agent-decidable. `_tiers_rule` is the seam either way; **D-P1-02 forbids absorbing A-17 here** |

---

## 10. Release risk and rollback

### This item ships LIVE ON MERGE — one of four in the round

`HLD-p1.md` **R-1** corrects the briefing's "flag-gated" framing: **four P1 items
ship user-visible change live on merge**, not one — P1-1/2, P1-5, **P1-7** and
P1-11. **P1-9 is the only item in the round with a real kill switch.**

For P1-7 specifically, "no flag" was a deliberate call, not an oversight: the fix
removes a *wrong answer* rather than adding a surface, so a flag's OFF position
would ship a knob whose off state is a known bug. But that means:

| Fact | Consequence |
|---|---|
| No flag gates the Pick Anchor wizard; `AnchorSheet` rides `draft.rank_inline`, already `true` in `config/features.json:158` and `release.json:158` | Both hosts render the new labels the moment the build lands |
| `unlocked` flips `false → true` server-side for the anchor cohort | Live on the Render deploy, before any app update — this half needs no TestFlight build |
| `ranking_complete_first_time` begins firing for a cohort that has never emitted it | **A step change in a shipped funnel series.** Record the seam date in `CHANGELOG.md` so a later analyst sees a discontinuity rather than discovering it in a chart |
| `league_member_unlocked_trades` fans out to every joined leaguemate on the transition | A burst of "@user just unlocked Trade Finder" pushes. **RL-5**, and it stacks with P0-1's Quick Set cohort (`HLD-p1.md` R-8) |
| `ranking_method` is a live experiment-targeting attribute (`backend/experiments.py:59`) | P1-7 does not change who holds `'anchor'`, only what it means at the gate — but confirm no experiment is mid-flight on it (RV-7) |

**Bright-line verdict.** Routes: no. Schema: no. Feature-flag surfaces: no.
Analytics event names: no. **But** an **API value domain** changes (`unlocked`)
and a **cross-client display vocabulary** governed by
`docs/cross-client-invariants.md` changes. Per root `CLAUDE.md` § Feature gates
this is **not** a quick fix: **full gates apply, Tier 1 sim**, unless the operator
declares express — and an agent never self-selects express.

### Rollback

**The lever is `git revert`, not a flag flip.** The change is ~15 lines in one
backend function plus one new method, one derived mobile constant and two
fallback substitutions. Nothing persisted is stranded by a revert:
`unlocked_formats` rows written during the window are **monotonic by contract**
(`server.py:6191-6213`), so users who unlocked stay unlocked — which is the
desired end state anyway. The only truly irreversible effects are the ones a
revert cannot recall: `ranking_complete_first_time` rows already recorded, and
push notifications already delivered. **That is what RL-5 is deciding.**

Partial rollback is available and clean: reverting only the mobile commit
restores the old labels while leaving the unlock fixed; reverting only the
backend commit does the reverse. Keep them as separate commits within the wave
so this option exists.
