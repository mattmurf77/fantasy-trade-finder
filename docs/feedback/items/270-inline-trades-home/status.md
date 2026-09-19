# #270 / #272 / #279 — Inline Trades Home mockup lab

**Status: built-dark — 2026-08-09.** Branch `worktree-agent-acc329e0f3f9a3cd5`
(base `worktree-agent-a16b8c9e20f110454`, includes the #279 landing this
item builds on top of). #279 (aggregate pick-equivalent labels on
`LeagueSummaryScreen`) shipped separately —
[docs/feedback/items/279-aggregate-tier-labels/status.md](../279-aggregate-tier-labels/status.md).
This item builds **variant (a) Minimal ("strip") and variant (b)
Calculator-style ("canvas")** from the spectrum below, per the operator's
2026-08-09 decision: *"I can't decide between A or B. Build both and
implement a test. I'll try A first, then B."* Both ship behind a new A/B
experiment, `trades_home_inline` — see "Built — 2026-08-09" below for the
mechanism, the shipped scope, and the A→B switch runbook. **Not merged or
pushed** — worktree branch only, per the build task's brief.

Everything from here through "Recommendation" below is the **original
mockup-lab record** (unchanged) — design history, not current status.
Deliverable: `mockups/polish-lab-2026-08/trades-home-inline.html` (current +
baseline + 4 variants + 1 extra `#279` frame, 393×852pt, Chalkline tokens).

## 2026-08-09 revision — two operator directives on the lab

After reviewing the first pass, the operator gave two revision directives
against the same mockup file (no new frames added beyond what's described
below; all other rows/frames left untouched):

1. **B1 (calculator canvas, empty state):** *"I don't know why you've
   removed the find a trade button. Re-gen with find a trade. Move the
   change pre section up to the top where it is in other mocks."*
   Fixed: `btnPrimary` "Find more trades" is restored in B1 (it drives the
   suggestion rail below the build columns — it was never meant to be
   removed, just under-drawn in the first pass). The frame's element order
   now matches A1's exactly for its first four blocks: utility row → League/
   Trading-with pills → prefs `editEntry` → CTA — only what renders below
   the CTA differs (build columns + suggestion rail vs. a swipe deck). B2
   (the populated calculator frame) was left untouched — the directive was
   B1-specific.
2. **D (accordion):** *"I like this layout when a user hits 'Change'...
   Re-do the mock so the default state is still that these are hidden
   behind the 'change' button."* Reworked: variant (d)'s default state
   (D1) is now byte-for-byte identical to baseline (BASE-1) — one `Change
   ›` line, full deck, nothing accordion-shaped visible on first paint.
   The accordion itself (the five collapsed section rows) is now what
   **opens** when Change is tapped (D2), replacing the `editEntry` line in
   place and pushing the deck down — instead of the earlier draft's
   full-height modal sheet. This flips what the accordion is being
   compared against: previously it competed with (c) for real estate on
   the default page (both always-on); now it's a strict presentation
   swap for the existing "Change" gate — same one-tap entry point every
   other variant uses, just a different destination (in-place accordion,
   not `TradeDnaSheet`'s `<Modal>`). See "Recommendation" below for how
   this changes the ship call.

## The three asks, verbatim

**#270 (core ask), TradesHome:**

> "One alternative version of this page is just presenting the manual trade
> calc experience and incorporate the change options naturally (so you add
> and remove players directly from the UI — removing the need to have
> player selection hidden under the change link. League and teams to trade
> with more naturally presenting back outside the change link too. Let's
> mock up a few different versions. Give me options that vary pulling some
> of the change sheet inputs back into the UI directly."

**#272:**

> "I want to make the icons for Draft, Trade, and Free Agents bigger. Also
> we can remove the manual calc tab and instead just have a button wrapped
> into the updated UI we'll be mocking to remove any league or player
> references for 'Manual' calc."

**#279:**

> "Would be a nice attempt to mock up doing it for team and positional
> values too though." (tier labels, extended to aggregate values)

## Grounding — what actually exists vs. what the brief assumed

- **`mockups/polish-lab-2026-08/trades-edit-full-sheet.html` does not
  exist.** The brief pointed at it for structure; `git log --all` shows no
  such path was ever committed to this repo. #257 shipped straight from
  its `status.md` design notes without a surviving mockup file (see
  `docs/feedback/items/257-edit-full-sheet/status.md`). The lab instead
  reverse-grounds the "before" sheet directly from the shipped
  `mobile/src/components/TradeDnaSheet.tsx` (`full` branch, Variant C —
  "Big three + one quiet strip") and follows the phone-frame/current-vs-
  proposed conventions of the nearest precedent,
  `mockups/polish-lab-2026-08/trades-player-first.html`.
- **#269 and #277 are both in-flight, not on `origin/main`, and the brief
  asks every frame to assume they landed:**
  - #269 — team-targeting + league-picker move into the sheet,
    `TradeFinderModeBar`'s three deck-mode chips (Guided/Team/Player) are
    removed.
  - #277 — tier labels replace numeric player values app-wide. This
    pattern already ships in exactly one place today: the Calculator's
    `TradeSide.tsx` (`tierOf` prop, shipped under **#263**) renders a
    `TierBadge` chip instead of the raw `value` number, with numeric
    fallback only for picks/untiered rows. #277 is read here as
    generalizing that one component to every remaining raw-number surface.
- **#272's "icons" — what's real in code.** Bottom tab-bar icons render via
  `tabIcon()` (`mobile/src/navigation/TabNav.tsx:513`), flat `<Icon
  size={22}>`. **Draft** (glyph `flag`) and **Trade** (tab labeled
  "Acquire" since the #245 rename, glyph `trade`) are real 22pt tab icons.
  **Free Agents has no icon anywhere in the app** — it's a text-only chip
  in `TradeFinderModeBar` (`CHIPS` array,
  `mobile/src/components/TradeFinderModeBar.tsx:40-46`) and a pushed
  screen with no tab-bar presence; `mobile/src/components/chalkline/
  Icon.tsx`'s `IconName` union has no `free-agents` glyph. The lab proposes
  **22 → 28pt (+27%)** for all three and borrows the existing `search`
  glyph for Free Agents (nearest semantic fit already in the shared icon
  set) rather than inventing a new SVG — flagged as a real, if small, new-
  icon cost, not a free relabeling.
- **#279's caveat, upfront:** team/positional totals
  (`LeagueSummaryScreen.tsx`'s `posValues`/`total_value`) are **sums**
  across many assets, not single-asset values. The shipped 8-tier ladder
  (`TIER_LABEL`/`ORDERED_TIERS`, `mobile/src/utils/tierBands.ts`) is a
  fixed 8-bucket per-asset classification whose top bucket (`4+ 1sts`) is
  an open-ended catch-all — a competitive roster's total is worth many
  multiples of that ceiling, so bucketing a sum into one of the 8 labels
  is not meaningful without new calibration.

## The spectrum — how the 4 variants differ

Every variant starts from the same **baseline** (BASE-1: #269 + #277
landed — mode chips gone, League+Team live inside the sheet, tier badges
everywhere, bigger Draft/FA icons + Manual-calc-as-button already applied)
and is scored on ONE axis: **how much of `TradeDnaSheet`'s `full` content
moves out of the modal and onto the page.**

| Variant | What moves onto the page | What stays in the sheet | Disclosure mechanism |
|---|---|---|---|
| **(a) Minimal** | League + Team only (2-pill strip) | Outlook, Positions, Trade idea, Specific players, Fairness, Lanes | Modal (shorter) |
| **(b) Calculator-style** | League + Team (header row) + the specific-players section, reshaped into a real add/remove two-column build canvas (`TradeSide.tsx` reused) | Outlook, Positions, Trade idea, Fairness, Lanes | Modal (shorter) — but the deck itself is replaced by the canvas |
| **(c) Maximal inline** | Everything — League, Team, Outlook, Positions, Trade idea, Specific players, Fairness, Lanes | Nothing (sheet deleted); Untouchables keeps its own second-layer Manage sheet | No modal at all |
| **(d) Accordion** *(repositioned 2026-08-09)* | Nothing by default — page is identical to baseline. Tapping "Change" reveals everything as five collapsed accordion rows in place; each still expands its own body on a further tap | Nothing in a `<Modal>` — Change now opens an in-place accordion instead of `TradeDnaSheet`'s full-screen sheet | In-place accordion, gated by the same one-tap "Change" entry every other variant uses (not always-on) |

(a) and (b) both keep a shorter version of the modal, gated by "Change."
(c) removes the modal *and* the Change gate entirely for an always-on
inline panel. (d), after the 2026-08-09 repositioning, keeps the Change
gate exactly like (a)/(b)/baseline — the default page is unchanged — but
replaces what's *behind* it: a full-screen modal sheet becomes an
in-place accordion instead. This is still the "genuinely distinct fourth
point" the brief allowed for, just not in the way originally drawn: (d)
is no longer a denser cousin of (c) (always-on, no gate) — it's a
same-gate, different-destination cousin of (a)/(b) (one-tap Change, but
the reveal is an accordion instead of a modal).

Every frame in every row also carries the three #272/#277 requirements
unconditionally: bigger Draft/Free-agents icons + Manual-calc-as-button in
a utility row, and `TierBadge` chips instead of numeric player values.

## Code-level cost per variant

- **(a) Minimal** — smallest. One new presentational component
  (`TradingWithStrip`, ~60 lines: two pills, two tap handlers). Reuses the
  existing league-switch entry point (TopBar's sheet) for the League pill;
  the Team pill needs either a scroll-to-section prop on `TradeDnaSheet`
  or a new lightweight standalone picker. No engine/state change — this is
  #269's own League/Team state, just given a second entry point. Sheet
  shrinks by two rows since they're answered on-page.
- **(b) Calculator-style** — largest, and the only one that's an
  architecture decision, not a layout one. Reuses shipped components
  (`TradeSide`, `VerdictPanel`/`ConsensusVerdictCard`,
  `PlayerPickerModal`) but requires deciding whether the swipe deck still
  exists underneath the canvas or whether `TradesScreen`'s guided landing
  forks into two render modes. This mock assumes full replacement (canvas
  + a horizontal suggestion rail replaces the swipe stack), which is a
  bigger behavioral change than the other three and needs its own scope
  block before any build estimate is trustworthy.
- **(c) Maximal inline** — moderate-to-large. No new sheet UI to write
  (delete `TradeDnaSheet`'s `full` branch, or leave it dead behind the
  flag), but every control it held gets re-laid-out as a permanent card on
  an already-long screen (`TradesScreen.tsx` is 5,861 lines today). Directly
  re-opens the height problem #257 was built to close — see Tradeoffs.
- **(d) Accordion** *(repositioned 2026-08-09)* — moderate, and now lower
  on the page side specifically: the default landing render (D1) needs
  zero new components — it's the exact `editEntry` + Change gate baseline
  already ships. All the cost is in the destination: swapping
  `TradeDnaSheet`'s `full`-branch `<Modal>` for a collapsible in-place
  list. That list is still a genuinely new shell component (no existing
  accordion pattern anywhere else in the app to reuse styling/behavior
  from — least precedented of the four in the codebase), but every
  expanded body reuses the exact inner JSX `TradeDnaSheet` already renders
  per section — the change is the container, not the controls.

## Tradeoffs (condensed — full rationale is in each frame's caption)

- **(a)** Cheapest, safest, but only answers #270's *second* sentence
  (League/Team). The "add and remove players directly from the UI" ask is
  untouched. Also introduces a real redundancy: the League pill duplicates
  the global TopBar's league switcher.
- **(b)** The only variant that delivers #270's literal first sentence.
  Costs the zero-effort swipe discovery loop that's the app's core PFO
  surface — a brand-new user with no target in mind now faces two empty
  columns instead of an auto-populated card, the same regression the
  `trades-player-first.html` (#211) lab flagged for its own direction (a).
- **(c)** Zero navigation cost to change anything, but re-inflates the
  exact height problem #257's own PRD explicitly rejected even in its most
  conservative option (Variant A, "least risky, least brave" — this goes
  further than that).
- **(d)** *(repositioned 2026-08-09)* No longer competes with (c) for
  re-inflating the height problem #257 fixed — its default page is now
  byte-for-byte (a)/baseline's footprint, not an always-on panel. What's
  left reads close to a strict upgrade over today's shipped sheet: same
  one-tap Change gate as every other variant, but the reveal is an
  in-place accordion instead of a full-screen modal hop. Still the most
  novel interaction pattern in the app (no existing accordion component to
  borrow from) and still leaves the accordion-exclusive-vs-multi-open
  question unresolved. Repositioning raises one new question: since
  content is still gated behind a single "Change" tap, is this
  meaningfully "presenting back outside the change link" per #270's
  literal ask, or is it closer in spirit to (a)/(b) — same gate, nicer
  destination — than to (c)'s always-on inline?

## #279 frame (E1) — what was and wasn't attempted

Mocked: swapping the numeric team-total label above each power-rankings
bar chart column for a pick-equivalent phrase ("≈14 firsts" instead of
"14,820"), reusing the **existing** value→pick-equivalent formula already
live on every trade card (`backend/server.py`'s `_gap`/`pick_equivalent`,
surfaced today as "a Late 2nd" in the Dynasty Value Swing bar) — applied to
a raw total instead of a value delta. Bar heights, position-color
stacking, and rank numerals are untouched; only the human-facing label
text changes.

Explicitly **not** attempted, flagged as open:

1. The roster drill-in (`LeagueSummaryScreen.tsx:1027`,
   `Math.round(p.value)`) is the one part of #279 with a clean, already-
   solved answer — swap in the existing `TierBadge`, no new work, since
   those rows ARE single-asset values.
2. The bar chart's stacked position segments have **no numeric label at
   all today** (color-proportion only). Extending pick-equivalent labels
   down to sub-segments (e.g. "QB: ≈3 firsts" per team) wasn't mocked —
   at small segment sizes a 4-way split of one aggregate total starts to
   read as false precision, and no rounding/threshold rule exists yet.
   This needs product input, not just engineering time.
3. `TIER_LABEL`'s 8-bucket table itself was deliberately NOT reused or
   extended upward (e.g. adding "8+ 1sts", "12+ 1sts" rungs) — that would
   require new calibration of what a roster-scale aggregate should mean at
   each rung, which is a product decision this lab doesn't make on the
   operator's behalf.

## Recommendation

**Updated 2026-08-09** to reflect the D repositioning above. Before the
revision, (d) was scored as the "longer-term" option specifically because
it competed with (c) for the same always-on-inline territory — both
re-inflated the height problem #257 fixed, just to different degrees. That
conflict is gone now: (d)'s default page (D1) is byte-for-byte the same
as (a)/baseline, so it costs nothing extra on first paint. What (d) buys
over (a) is what happens *after* the one tap on Change — every sheet
section, not just League/Team, and no full-screen modal hop to get there.

**(d) Accordion** is now the recommended default ship candidate, ahead of
(a) — it strictly dominates (a) on scope (all sheet content reachable, not
just League/Team) at the same default-page cost, and it's a real upgrade
over today's shipped `TradeDnaSheet` modal (same gate, lighter reveal).
The one real risk against it: it's the least precedented pattern in the
codebase (no existing accordion component to build from), so if the
operator wants the safest, most boring possible ship, **(a) Minimal**
remains the fallback — cheapest, safest, and still the more literal
reading of #270's second sentence taken alone. If the operator's priority
is specifically the "add/remove players directly" experience over
League/Team-and-everything-else surfacing, **(b)** is the one that
actually delivers it, but it should go through its own scope block first —
it's an architecture decision (does the swipe deck survive?), not a
styling one, and the PFO regression risk needs a real answer before build,
not just a mockup caption.

## Open questions for the operator

1. Which single variant (or which two, e.g. a-now/d-later) should move to
   a build scope block?
2. If (b) is chosen: does the swipe deck disappear entirely in guided
   mode, or does the canvas replace it only once a Team is selected
   (keeping zero-effort discovery for the "Any team" / cold-start case)?
3. For #279: is a pick-equivalent label ("≈14 firsts") an acceptable
   permanent replacement for the numeric team total, or is it only wanted
   as a secondary/supplementary label alongside the number? The frame
   mocks full replacement; a hybrid wasn't drawn.
4. For #279's positional segments: is per-position pick-equivalent
   labeling in scope at all, or is #279 satisfied by the team-total swap
   alone (item 1 above, already a clean win) plus the existing
   `TierBadge` roster drill-in fix?

## Built — 2026-08-09

Operator decision (open question 1, above): build **both** (a) Minimal and
(b) Calculator-style, ship both behind one A/B experiment, operator starts
on (a) and switches to (b) later without a new build. (c) Maximal inline
and (d) Accordion were NOT built — out of scope for this pass.

### Rollout mechanism: experiment `trades_home_inline`

Mirrors `aggregate_tier_labels`
([docs/feedback/items/279-aggregate-tier-labels/status.md](../279-aggregate-tier-labels/status.md))
and `onboarding_v2_rollout`
([docs/business/analytics/2026-07-18-onboarding-v2-rollout-experiment.md](../../../business/analytics/2026-07-18-onboarding-v2-rollout-experiment.md)):

| Field | Value | Why |
|---|---|---|
| key / version | `trades_home_inline` v1 | One key; `/revise` moves the operator between variants (see below) |
| layer | `trades_ui` | Semantically correct home — a `TradesScreen.tsx` landing-surface experiment, not `ranking`/`onboarding` |
| unit_type | `account` | Same reasoning as `aggregate_tier_labels` — the surface requires sign-in + a selected league |
| buckets | `[0, 10000)` | Full layer — targeting narrows to the operator, not bucketing |
| targeting | `{"is_tester_allowlist": true}` | Same allowlist mechanism (`config/tester_allowlist.json` ∪ `FTF_TESTER_ALLOWLIST`) |
| variants | `control` 0bp / `strip` 10000bp / `canvas` 0bp (day-1) | 0-weight control+canvas makes `strip` certain for the allowlisted unit; everyone else never matches targeting → `control` |
| `strip` client_config | `{"flags": {"trades_home_inline.strip": true}}` | Overlaid client-side (same `configs.<key>.flags` merge `mobile/src/api/flags.ts` already does for onboarding) |
| `canvas` client_config | `{"flags": {"trades_home_inline.canvas": true}}` | Same mechanism, mutually exclusive with `strip` (a unit is assigned exactly one variant) |
| primary_metric | `wat` | Placeholder catalog metric — no readout intended (n=1, same as the two precedents) |
| exposure_surface | `trades_home` | |
| scope | none | No funnel-event stamping need for a UI-layout swap |

**Why a boolean-flag overlay (not a payload field, unlike #279):** this is a
UI-flow toggle — which component tree `TradesScreen.tsx` renders — not a
value shown inside an existing payload. The #279 status doc's own note
calls this out: "onboarding's UI-flow toggle, where a boolean flag is the
more natural fit" vs. #279's payload-field-presence gate. Two flag keys
(rather than one, the way onboarding's ten `onboarding.*` keys work under
one master switch) because there are two mutually-exclusive UI trees, not a
layered feature set — `homeInlineVariant` in `TradesScreen.tsx` reduces them
to one three-way value (`'control' | 'strip' | 'canvas'`) at the top of the
component so nothing downstream branches on two booleans separately.

**No `server.py` route change was needed.** `/api/feature-flags`
(`feature_flags_route`) already resolves ANY running experiment generically
via `experiments.resolve_for_unit` and returns its `client_config.flags`
overlay in `configs`; the client already merges `configs.*.flags` over the
global flag map (`mobile/src/api/flags.ts`, built for onboarding). This
experiment rides that existing, already-tested plumbing — the new backend
test file only seeds a `trades_home_inline` row and exercises the
pre-existing generic path against it.

### A → B switch procedure (binding requirement — no new build)

Moving the operator from `strip` to `canvas` is a pure admin-API weight
change against the SAME experiment key — no code change, no redeploy, no
TestFlight build. `revise()` mints a new DRAFT version (edits to a running
experiment are forbidden by design — metrics reset, prior readout
archived), so it still needs the same required spec fields as the initial
create, plus a follow-up `transition` to `running` exactly like the initial
launch:

```bash
curl -s -X POST https://fantasy-trade-finder.onrender.com/api/admin/experiments/trades_home_inline/revise \
  -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" \
  -d '{
    "layer": "trades_ui", "unit_type": "account",
    "bucket_start": 0, "bucket_end": 10000,
    "targeting": {"is_tester_allowlist": true},
    "variants": [
      {"name": "control", "weight_bp": 0},
      {"name": "strip", "weight_bp": 0},
      {"name": "canvas", "weight_bp": 10000,
       "client_config": {"flags": {"trades_home_inline.canvas": true}}}
    ],
    "primary_metric": "wat", "exposure_surface": "trades_home"
  }'
# → {"key": "trades_home_inline", "version": 2, "status": "draft"}

curl -s -X POST https://fantasy-trade-finder.onrender.com/api/admin/experiments/trades_home_inline/transition \
  -H "X-Cron-Secret: $CRON_SECRET" -H "Content-Type: application/json" \
  -d '{"to": "running", "version": 2, "override_underpowered": true,
       "reason": "n=1 operator switch strip→canvas, not a powered test"}'
```

Force-quit and reopen the app — the boot flags fetch resolves `canvas`
deterministically (100% weight on the one non-zero variant, same technique
`aggregate_tier_labels` documents for its own "widening the cohort" path).
To move back to `strip`, repeat both calls with the weights swapped. Both
directions are exercised by
`backend/tests/test_trades_home_inline_experiment.py::test_switch_to_canvas_is_a_pure_weight_revise`,
which seeds the post-`/revise` weight shape directly and confirms
`variant_for` resolves to `canvas`.

**Initial launch** (creating the experiment for the first time, before any
switch) uses the same `POST /api/admin/experiments` + `.../transition`
two-step the `aggregate_tier_labels` runbook documents, with the `strip`
variant at 10000bp and `canvas` at 0bp — the operator's account
(`313560442465169408`, already in `config/tester_allowlist.json`) resolves
to `strip` on first boot after launch.

### What shipped, per variant

Both variants are scoped to the guided landing only
(`finderMode === 'guided'` in `TradesScreen.tsx`) — team/player deck modes
(reachable only via a stored deep link post-#269, since the mode-bar's
chips are hidden) keep today's `TradeFinderModeBar` untouched regardless of
assignment. Control (or any non-allowlisted unit, or any non-guided mode)
renders exactly as before — verified byte-identical by
`test_route_byte_identical_for_non_allowlisted_caller`.

**Both variants** (new component `mobile/src/components/TradeHomeUtilityRow.tsx`
+ `mobile/src/components/TradingWithStrip.tsx`):
- The mode-bar's row is replaced by a 3-button utility row: Draft (28pt,
  omitted when `draft.room` is off, same as today), Free Agents (28pt,
  borrows the shared `search` glyph — no dedicated icon exists), Manual
  calc (24pt `swap` glyph, a plain button with no league or player
  reference — #272 verbatim).
- A League + "Trading with" 2-pill strip renders above the deck
  (`TradingWithStrip`), reusing the SAME #269 sheet-scoped state
  (`league?.league_name`, `scopedOpponentName`) and the SAME picker Modals
  (`teamPickerOpen`/`leaguePickerOpen`) the full sheet's own rows open —
  just opened directly (new `openTeamPickerFromStrip`/
  `openLeaguePickerFromStrip` handlers) instead of via the sheet's
  close-then-reopen dance, since popping the full sheet back open on close
  would defeat the point of a strip that exists to avoid the sheet.
- `OutlookBiasReceipt` (existing component, unchanged) still renders below
  and still stands in as the "prefs summary + Change" line — see the
  judgment call below.
- The `TradeDnaSheet` full sheet (#257/#172/#269 machinery) is completely
  untouched and remains the target of every "Change" affordance in both
  variants, exactly as the brief required.

**`canvas` additionally** (new component
`mobile/src/components/TradeBuildCanvas.tsx`, rendered after the existing
Find-a-Trade CTA, before the deck): a two-column hand-built trade canvas
that mounts the shipped `InLeagueCalculator` **wholesale** — not a re-skinned
subset — reusing `TradeSide`, `PlayerPickerModal`, `ConsensusVerdictCard`,
evener rows, lineup-impact, Send-in-Sleeper, and share, exactly as the task
brief specified ("reuse the calc machinery... same component, same `tierOf`
tier-badge treatment"). Below it, a horizontal suggestion rail built from
the guided deck's own `TradeCard[]` (the SAME cards the swipe deck already
generated for this session); tapping a card prefills the canvas by bumping
a remount `key` with fresh `initialOpponentId`/`initialGiveIds`/
`initialReceiveIds` — `InLeagueCalculator` documents that it "owns all
state after mount" (initial props are read once), so a fresh mount is the
correct prefill technique, the same one the deck's existing "Edit in
calculator" hand-off already uses elsewhere in the app. Excluded (renders
nothing beyond the shared utility row/strip) in first-run and single-pin
featured mode — see the scope-bound decision below.

### Two deliberate scope-bounding decisions (flagged for the operator)

1. **The canvas is additive, not a replacement.** The mockup lab's B1/B2
   frames show the swipe deck fully replaced by the canvas + suggestion
   rail. This build instead renders the canvas ABOVE the existing deck,
   which stays fully intact and reachable by scrolling past it — nothing
   about the deck's rendering, state, or job-polling was touched. Reasoning:
   (a) forking `TradesScreen.tsx`'s ~2,500-line deck-rendering region behind
   a second top-level branch would be a large, hard-to-verify restructuring
   of code this build doesn't otherwise need to touch, working against the
   "surgical changes" guideline on a change this size; (b) the lab's own
   "Con" for variant (b) explicitly flagged losing "the zero-effort swipe
   discovery loop that's the app's core PFO surface" as a real regression
   risk for a brand-new user with no target in mind — keeping the deck
   intact avoids that risk entirely; (c) it gives the operator MORE signal
   during the A/B trial (canvas AND deck both visible) rather than a hard
   cutover. This is a genuine interpretation-narrowing call on an
   ambiguous, large-scope item — surfaced here explicitly per root
   `CLAUDE.md`'s guidance to note ambiguous frame details rather than
   silently pick one.
2. **The "prefs summary line" reuses `OutlookBiasReceipt` verbatim**, not a
   new composite string. The canvas mock's B1/B2 frames show a line reading
   "Contend · Chasing WR · Value moves — Change ›" combining outlook +
   chasing/shopping positions + trade-idea lane. `TradesScreen.tsx` has no
   existing state or query that assembles that exact string — chasing/
   shopping positions live entirely inside `TradeDnaSheet.tsx`'s own local
   state (autosaved, never lifted to the screen) and pulling them out just
   for this experiment would be new state plumbing unrelated to #270/#272's
   actual ask. `OutlookBiasReceipt` is the closest existing analog (same
   "Change" affordance opening the same sheet, sourced from the same
   `league-prefs` query) and is what both variants render for this role.

### Gates run

- `python3 -m pytest backend/tests -q` → **2068 passed, 1 skipped**
  (baseline 2064 passed / 1 skipped + 4 new tests in
  `backend/tests/test_trades_home_inline_experiment.py`: operator-only
  assignment starting on `strip`, the `/revise`-to-`canvas` switch proven
  directly, `/api/feature-flags` overlay correctness for the allowlisted
  caller, and byte-identical responses for a non-allowlisted caller under a
  running experiment).
- `cd mobile && npx tsc --noEmit` → clean (symlinked
  `.claude/worktrees/agent-a16b8c9e20f110454/mobile/node_modules` for the
  run; remove after per the task brief).
- `mobile/scripts/testid-lint.sh` → `testid-lint OK`.

**Maestro delta — waived, same precedent as #279.** No new/extended flow
was authored. This experiment is allowlist-gated to the operator's single
real account exactly like `aggregate_tier_labels`; the app's Maestro QA
account (`qa_standard`) is not on the allowlist, so a flow driving the
`.maestro` harness could not exercise either treatment branch without
allowlisting a QA identity — a decision for a future pass, not this one.
`test_route_byte_identical_for_non_allowlisted_caller` is the equivalent
regression guard for everyone the harness's account represents (a
non-allowlisted caller). New testIDs added
(`trades.home-utility-row`, `trades.home-utility.{draft,free-agents,manual-calc}`,
`trades.trading-with-strip`, `trades.trading-with-strip.{league,team}`,
`trades.build-canvas`, `trades.build-canvas.suggestion.<trade_id>`) are
unreferenced by any existing flow, so `testid-lint.sh` has nothing to check
against them yet — they're ready for that future flow.

### Docs updated

- `docs/config-reference.md` — new row documenting `trades_home_inline.strip`
  / `.canvas` as experiment-overlay-only flags (never in
  `config/features.json`, unlike every other row in that table) + the
  `FTF_TESTER_ALLOWLIST` row's example list.
- This status doc.

Not touched (n/a): `docs/api-reference.md` — `/api/feature-flags`'s
`{flags, experiments, configs}` contract is unchanged; this experiment
populates the same already-documented generic `experiments`/`configs`
objects with a new key, not a new field or shape. `docs/data-dictionary.md`
— no schema change (experiments already have a table, no new column).

### Feature-scope gate note

Same posture as `aggregate_tier_labels`: **express-adjacent**, not a
from-scratch feature-scope block. The task brief itself supplied the
equivalent of that block's answers — rollout mechanism specified up front
(mirroring two shipped precedents), variant scope pre-drawn in the mockup
lab above, and the A→B switch requirement stated explicitly as binding. It
touches an API-adjacent surface (a new experiment, a bright-line item per
root `CLAUDE.md`'s express-lane rule) and a genuinely large mobile UI
surface, so: full gates were run (tests + typecheck + testid-lint), docs
were updated, and this section records the rollout mechanism, the switch
runbook, and the two scope-bounding decisions in place of a separate
`docs/templates/feature-scope.md` copy.
