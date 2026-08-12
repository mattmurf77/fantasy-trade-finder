# #300 — mobile build status

> Build record for the mobile half of feedback #300 (League rankings →
> position trade candidates). Branch `build-300-mobile`, based on
> `origin/main` @ `62ff8d6`. Frozen design:
> [`operator-answers-2026-08-12.md`](operator-answers-2026-08-12.md).
> Mockups: [`mockups/candidates-300-v2/`](../../../../mockups/candidates-300-v2/).
>
> Everything ships behind two DARK flags. Nothing here is user-visible until
> an operator flips them.

---

## Table of Contents

- [1. What shipped, and where](#1-what-shipped-and-where)
- [2. Verification](#2-verification)
- [3. Frozen-spec items that were not buildable as written](#3-frozen-spec-items-that-were-not-buildable-as-written)
- [4. What the scope block needs from the mobile lane](#4-what-the-scope-block-needs-from-the-mobile-lane)
- [5. Proposed shared-doc text (orchestrator-owned files)](#5-proposed-shared-doc-text-orchestrator-owned-files)
- [6. QA checklist — including everything static analysis cannot reach](#6-qa-checklist--including-everything-static-analysis-cannot-reach)
- [7. 2026-08-12 — removing #294's rule A and rule B from `togglePos`](#7-2026-08-12--removing-294s-rule-a-and-rule-b-from-togglepos)

---

## 1. What shipped, and where

Two flags, both DARK, registered in `mobile/src/state/useFeatureFlags.ts`
`LAUNCHED_FLAG_DEFAULTS` as explicit `false`:

| Flag | Owns |
|---|---|
| `league.pos_candidates` | The median divider, the Buyer/Seller band labels, the pick-tier label under a single-position filter, and the auto-return when the filter changes while drilled in |
| `league.player_trade_handoff` | The drill-in's direction-aware roster and its Offer/Target row action |

`player_trade_handoff` is meaningless alone — it has no line to take a
direction from — so every drill-in consumer reads `candidateHandoffOn`, the
AND of the two. `pos_candidates` alone is coherent by itself: a divider and
two labels, no new behaviour.

| Item | Where |
|---|---|
| Flag defaults | `mobile/src/state/useFeatureFlags.ts:57-72` |
| `medians` response field (optional) | `mobile/src/api/league.ts:611-628` |
| `denseMicroTags` + `hitSlop` props | `mobile/src/components/PlayerCard.tsx:75-96`, `:145-146`, `:242`, `:260`, `:272` |
| Divider gate (`candidatePos`) | `mobile/src/screens/LeagueSummaryScreen.tsx:831-837` |
| Median + cut index | `:845-874` |
| Band arithmetic | `:877-883` |
| Direction rule (`candidateDir`) | `:897-909` |
| Stacked rosters (`drillRosters`) | `:913-930` |
| Pick-tier label (`activeValueLabel`) | `:947-957` |
| Filter-change auto-return | `:972-985` |
| Row action / pin handoff | `:1004-1020` |
| Drill-in section render | `:1669-1875` |
| Divider render | `:1966-1988` |
| `TeamRow` band chip | `:2316`, `:2352` |
| New styles | `:3134-3172` |

---

## 2. Verification

Static only — no simulator, no Maestro run. Parallel build agents contending
for one simulator reseed each other's databases.

```
npx tsc --noEmit                      clean
bash mobile/scripts/testid-lint.sh    testid-lint OK
check-league-drill-in.js              29/29
check-analytics-297-302.js            35/35
check-single-pin-actions.js           17/17
check-league-candidates-300.js        66/66   (new)
check-picks-subset-invariance.js      72/72   (see §7.5 — was 66/3-red)
```

The new suite was proven against **40 deliberate sabotages**: every one turns
it red, zero false passes, and each failed the assertion written for it. The
harness is not committed (it rewrites source in place); the sabotage list is
reproduced in the build report and each assertion in the suite names the
sabotage it detects. `testid-lint.sh` was itself sabotaged with a bad flow id
and went red, so the flow's selectors are genuinely cross-checked.

**Flag-off is byte-identical**, by construction rather than by inspection.
Every render-affecting hunk in the diff is gated on `sec.verb` (null unless
`candidateHandoffOn`), `cutAfter` (null unless `posCandidatesOn`), `band`
(null when `cutAfter` is), or `activeValueLabel` (whose flag-off branch
returns exactly the expression it replaced). Two deliberate exceptions, both
inert:

1. The ranked list's rows gained a `React.Fragment` wrapper so the divider can
   be interleaved — the `key` moved from `TeamRow` to the Fragment. A Fragment
   emits no host node; the rendered tree is unchanged. This is the same
   construction the shipped outlook list uses for the playoff cutline.
2. The roster tile gained an unconditional
   `testID="league-summary.roster-player.<player_id>"`. `testID` maps to
   `accessibilityIdentifier` — no pixels, no behaviour, and VoiceOver does
   not speak it. It is unconditional because a conditional test id is a
   selector that exists only in the configuration nobody debugs.

---

## 3. Frozen-spec items that were not buildable as written

Three, in order of how much they matter.

### 3.1 The divider's load-bearing premise is broken by `league.picks_always_counted`

`mockups/candidates-300-v2/directions.html` states as ground truth:

> `activeTotal()` with a single-position filter returns exactly
> `tc.posValues[P]` — nothing else, not even picks. **This is the
> load-bearing fact behind Direction 2.**

That is true of `activeTotal` in isolation and **false of the reachable UI**.
`league.picks_always_counted` shipped ON in v1.12.0, and its rule A auto-adds
`PICKS` on the first position tap out of the unfiltered state
(`LeagueSummaryScreen.tsx` `togglePos`). So in any league that carries draft
capital, tapping WR lands on `{WR, PICKS}` and `activeTotal` returns
`posValues.WR + picks.value` — the list is ranked by WR **plus capital**
while the median measures WR alone. A divider drawn there is in the wrong
place, and nothing on screen says so.

**Built:** the divider refuses to draw while `PICKS` is in the filter (and
outside the `all` subset, for the same class of reason — starters/bench
re-derive `posValues[P]` from part of the roster while the server's median is
over the whole one). Correct, and pinned by the new suite.

**RESOLVED 2026-08-12 — the operator took a stronger version of option 1.**
The cost described here (in a pick-carrying league the divider took **one
extra tap** to deselect the lit Picks pill, and the hermetic QA world's
zero-`draft_picks` seed meant it would have shipped unnoticed) is **closed**.
Rather than suppress rule A for one flag combination, the operator removed it
outright, in both flag states: *"All leagues have picks. They should not be
selected along with a position filter. Only by explicit user action."*
Tapping WR now means `{WR}` everywhere, so the divider appears on the natural
path and the design lab's ground truth above is restored as the ordinary case.
The gate itself is unchanged and still load-bearing for the now-deliberate
`{WR, PICKS}` state. Full record, including why rule B fell with rule A: §7.

The options not taken, for the record: a pick-inclusive `medians` variant was
rejected as a bigger API change for a thesis that is not positional ("richest
at WR once you count their picks"); leaving the extra tap in place was the
prior recommendation and is superseded.

### 3.2 Operator decision 6 cannot be fully satisfied from the client

Decision 6 asks that **2+ positions** also render pick-tier labels instead of
a raw numeric. `value_label` is per position and, as the lab itself
established, **is not additive as a label** — the pick-equivalent of a sum is
not the sum of two pick-equivalents. No field on the wire names a
combination.

**Built:** the single-position case, which is a complete fix for the view
#300's whole feature lives in — a one-position filter now shows that
position's `value_label` on the ranked row and in the drill-in subline, both
through one derivation (`activeValueLabel`) so a row and its own drill-in
cannot disagree.

**Not built:** 2+ positions still falls back to the numeric — the same
fallback every caller outside the `aggregate_tier_labels` experiment already
sees everywhere on this screen. Suppressing it instead would blank the value
column for most users, which is worse than the thing decision 6 objects to.
Closing it properly needs a server-side combined label
(`positions_value_label` for a requested set, or a per-request
`filtered_value_label`). **Not improvised — reported.**

### 3.3 `aggregate_tier_labels` is still an operator-only experiment

Recorded as unresolved in the frozen spec (§3, §4 item 3) and still is. The
client degrades correctly — no `value_label` ⇒ the line draws with the bare
caption `League median` — but for everyone outside the experiment the divider
carries no value at all, which is a thinner feature than the mockups show.
Either the experiment graduates or #300 ships with a label-less line.

### 3.4 Smaller ones, decided and recorded

- **Odd team counts (still-open item 1).** The at-median team sits **above**
  the line (`>=`), which matches mock D2-b. The **"At median" badge** in that
  mock is **not built** — item 1 asks the operator to confirm the reading
  first, and a badge is cheap to add afterwards.
- **The caller's own row** has no direction (offering your players to
  yourself). It keeps today's drill-in — its own roster, inert tiles. The
  spec's "every team is tappable and every team has a direction" holds for
  every team that is not the reader.
- **Flat-league copy (mock S-2)**, the **transient "Now showing TE" strip**
  and **scroll-to-the-line** on auto-return (mock F-3) are **not built** —
  none is in the build brief, and each adds state or copy. The auto-return
  itself, and its VoiceOver announcement, are built.
- **No analytics event fires for the row action.** An unregistered event name
  is accepted-and-dropped by ingest with no 4xx and no client log, and
  `backend/analytics_taxonomy.py` is not this change's to edit. Proposed
  registration in §5.

---

## 4. What the scope block needs from the mobile lane

For `scope.md`, owned by the backend agent:

- **Maestro delta:** delivered —
  `mobile/.maestro/flows/league/06-position-trade-candidates.yaml`, plus the
  new flag fixture `backend/tests/fixtures/flags/release-300.json` (a real
  fixture file, not a `release+key` prose header: flow-authoring law 16 says
  prose silently falls back to defaults). **The flow is authored but has
  never been executed** — it needs the `medians` field to exist in the
  hermetic world, and no agent held the simulator. Not a waiver; a sequencing
  note.
- **`testID`s added:** `league-summary.median-divider`,
  `league-summary.roster-section-caption`,
  `league-summary.roster-mirror-toggle`,
  `league-summary.roster-player.<player_id>`. All pass
  `mobile/scripts/testid-lint.sh`.
- **Analytics:** one existing event gains one new `via` **value**
  (`league_team_closed.via = 'filter_change'`). Prop **keys** are unchanged,
  so `check-analytics-297-302.js`'s client↔taxonomy cross-check still passes
  and nothing is stripped at ingest. One event is **proposed and not
  emitted** — see §5.
- **New dependencies:** none.
- **Sim-gate tier:** this is a user-visible mobile change with a new API
  consumer, so it is not a low tier — but both flags are dark, so the
  pre-ship run exercises the flag-OFF path (which must be indistinguishable
  from today) plus flow 06 under `release-300` once `medians` lands. The
  tier call is the operator's.

---

## 5. Proposed shared-doc text (orchestrator-owned files)

Proposed, not applied. Exact text follows.

### `mobile/src/screens/CLAUDE.md` — `LeagueSummaryScreen` row, append

> Also hosts the dark "position trade candidates" layer (#300, flags
> `league.pos_candidates` + `league.player_trade_handoff`): a median divider
> across the ranked list when exactly one core position is selected, Buyer /
> Seller band labels on the outer `round(n * 0.33)` at each end, and a
> drill-in whose roster is chosen by the tapped team's side of the line —
> yours below it, theirs above — with an Offer/Target row action that pins
> via `useFinderTargets` and routes to the finder.

### `mobile/src/screens/CLAUDE.md` — § Sharp edges, add three

> - `LeagueSummaryScreen`'s median divider (#300) draws **only** when the
>   ranked list is genuinely sorted by the quantity the median measures:
>   exactly one core position, `PICKS` **not** in the filter, subset `all`,
>   and `medians` present on the payload. Loosening any of the four draws a
>   line in the wrong place and nothing on screen says so. Reaching the
>   `PICKS`-in-filter case now takes a deliberate tap on the Picks pill —
>   `league.picks_always_counted`'s auto-add rule was removed on 2026-08-12
>   (§7) — so tapping WR from All draws the divider in a pick-carrying league
>   as much as a pickless one. Pinned by
>   `mobile/tests/check-league-candidates-300.js`.
> - The **median line is the direction rule** for every team, including the
>   unlabelled middle third; the Buyer/Seller band labels are **emphasis and
>   drive no behaviour**. `bandFor` has exactly one consumer, the `TeamRow`
>   caption prop, and a second one would silently make the middle third
>   inert.
> - The #300 handoff pins through **`useFinderTargets`**, never route params:
>   `trades.sheet_targeting` is ON, so `TradesScreen` reads sheet-local state
>   and a params-based preselection type-checks, demos with flags off, and
>   silently no-ops in production.

### `mobile/src/components/CLAUDE.md` — `PlayerCard` row, append

> `denseMicroTags` (#300 Variant D, default **true**) hides the RK + injury
> micro-tags on dense line 1 so a per-row action label fits — **visual only,
> the composed a11y label still speaks both facts**. Operator override
> against the design lab's recommendation, recorded in
> `docs/feedback/items/300-league-rankings-trade-candidates/operator-answers-2026-08-12.md`
> decision 2 and explicitly not to be relitigated. `hitSlop` is forwarded to
> the tile's **own outermost** `Pressable`, which is the only position from
> which slop extends into unclipped ancestors — a nested control cannot work
> here, because `styles.card` sets `overflow: 'hidden'` and the dense
> `Pressable`'s `accessible: true` hides children from VoiceOver and from
> Maestro id-selectors. Callers passing it must also space rows so adjacent
> slop regions do not overlap.

### `mobile/src/state/CLAUDE.md` — `useFinderTargets.ts` line, append

> Also written by `LeagueSummaryScreen`'s #300 handoff, which **replaces**
> both sides via `setSide` (never `addGive`/`addReceive`) so a stale pin
> cannot ride into the generated deck, and preserves `packageMode`.

### `docs/api-reference.md` — `GET /api/league/power-rankings`, add a response field

> `medians` *(object, optional)* — the league's median value at each core
> position, `{ QB|RB|WR|TE: { value, value_label? } }`. `value_label` is the
> pick-equivalent string produced by the same `_aggregate_pick_label` as
> `positions[P].value_label`, under the same `aggregate_tier_labels`
> experiment gating, and is absent for callers outside it. Consumed by the
> League-rankings median divider (#300, flag `league.pos_candidates`). The
> whole object is absent on servers predating #300; the client then draws no
> divider, because the median's **label** cannot be computed client-side
> (`elo_to_value` + `GENERIC_PICK_SEEDS` are server-only) and raw numeric
> values are not permitted on that screen.

### `backend/analytics_taxonomy.py` — two edits

1. In the `league_team_closed` `via` comment block, add:

> `filter_change` — #300. The AUTOMATIC exit: changing the position filter
> while drilled in invalidates the drill-in's premise ("Punt Gods are short
> at WR" says nothing about TE), so the screen returns the user to the list.
> Lands in the same place as `header_back` and must not be logged as the same
> thing: one is a choice, the other an ejection, and a funnel that conflates
> them reads every filter tap as a user giving up on the team.

2. **Proposed, not yet emitted** — the row action currently fires nothing,
   because an unregistered name is accepted-and-dropped silently. Once
   registered, `LeagueSummaryScreen.handleRowAction` should emit it:

```python
"league_candidate_pinned": frozenset({"verb", "position", "rank", "side"}),
```

> `verb` ∈ `offer|target` · `position` the filtered core position · `rank` the
> tapped team's 1-based on-screen rank · `side` ∈ `above|below` (the team's
> side of the median line). Belongs in `NON_INTENT_EVENTS`? **No** — it is a
> real value moment (the user has chosen an asset and entered the finder),
> so it should count like `league_team_opened`.

### `living-memory/DECISIONS.md` — two entries

> **The #300 median divider draws only when the ranked list is sorted by the
> quantity the median measures.** A median across a ranked list is only true
> if the list is ordered by the same quantity, so the client requires all
> four of: exactly one core position, `PICKS` not in the filter, subset
> `all`, and `medians` on the payload. Loosening any one draws a line that is
> confidently in the wrong place, and nothing on screen would say so. The
> `PICKS` clause was the contentious one: at authoring time
> `league.picks_always_counted` auto-added `PICKS` on the first position tap,
> which made a WR+capital ranking the routine state and cost the user an
> extra tap on the lit Picks pill to see the line. That auto-add was removed
> on 2026-08-12 (entry below), so the gate now fires only on a deliberate
> Picks tap and the natural path reaches the divider. The gate itself is
> unchanged and still correct: a user who adds Picks to a WR filter is asking
> for a WR+capital ranking, which the WR median does not describe.

> **`league.picks_always_counted` no longer touches the position-pill
> toggle — pick value is an explicit opt-in (2026-08-12, operator).**
> "All leagues have picks. They should not be selected along with a position
> filter. Only by explicit user action." This reverses two rules #293/#294
> shipped two days earlier, with their original reasoning on the record.
> Rule A auto-added `PICKS` on the first position tap so that "selecting a
> position must not remove draft capital" — a rebuilding team holding four
> 1sts had ranked like a team holding none the moment a filter was applied.
> The counter-reading that won: because *every* league carries picks, rule A
> fired for effectively every user on every first tap, which makes pick
> inclusion a default rather than a choice, and a position filter should mean
> that position. Rule B (removing the last core position clears the filter to
> All) fell with it, and had to: its stated job was to keep the user out of
> "a picks-only ranking they never asked for" — a state only rule A could
> produce unasked. With rule A gone every `PICKS` in the filter is a
> hand-tapped pill, so clearing to All would discard the explicit choice the
> ruling exists to protect. #294's objection that separating the two cases
> "would need a hidden 'the user chose picks by hand' state axis, which is
> deliberately NOT built" is obsolete for the same reason: removing rule A
> makes the axis unnecessary. `togglePos` is now a plain, flag-independent
> toggle — its own inverse, so reversibility no longer needs a rule, and
> `{PICKS}` + RB − RB returns to `{PICKS}` instead of costing the extra tap
> #294 accepted. Everything else the flag governs is untouched (picks counted
> in all three subsets, the bar segment / legend swatch / pill in every
> subset, the drill-in "Draft capital" group, three hint strings), and
> flag-OFF behaviour is byte-identical — the removed guard was
> `if (picksAlwaysCounted && …)`, inert when OFF. Twelve gated expressions
> remain of R-0.2's fourteen. Pinned by
> `mobile/tests/check-picks-subset-invariance.js` assertions 3e–3h, which
> assert the rules' **absence** where the old suite asserted their gating.

### `docs/config-reference.md:262` — `league.picks_always_counted` row, two corrections

Both sentences below are now false and would mislead anyone reading the flag's
contract. **Replace** *"the first position tap auto-adds `PICKS` (lit pill,
one tap to opt out);"* with:

> the Picks pill is a plain toggle and pick value enters the chart **only**
> when the user selects it (the first-position-tap auto-add and the
> clear-to-All-on-last-removal rules shipped with #294 were removed on
> 2026-08-12 by operator decision — `togglePos` is now flag-independent);

**Replace** *"Read ONCE and gating all fourteen expressions atomically"* with:

> Read ONCE and gating all **twelve** remaining expressions atomically (was
> fourteen; the two `togglePos` rules are gone)

### `living-memory/DECISIONS.md:201` — the #293/#294 entry, amend in place

The existing entry's decision sentence still asserts *"with the first position
tap auto-adding `PICKS` as a visibly lit pill that one tap removes"*, which is
no longer true. It should not be rewritten — the 2026-08-12 entry proposed
above supersedes that clause — but the clause needs a pointer so the two are
not read as contradicting each other. **Append** to that entry:

> **Amended 2026-08-12:** the auto-add clause of this decision (and the
> clear-to-All rule that supported it) was reversed by operator decision — see
> the 2026-08-12 entry. The rest of this decision stands: pick value remains
> subset- and filter-independent, counted in All, Starters and Bench and
> whenever `PICKS` is in the filter. What changed is only *how* `PICKS` gets
> into the filter — a user tap, never a side effect.

### `living-memory/TEST_LEDGER.md` — one entry

> #300 mobile, static gate only (no simulator — parallel agents contend for
> one sim): `tsc --noEmit` clean · `testid-lint.sh` OK ·
> `check-league-drill-in` 29/29 · `check-analytics-297-302` 35/35 ·
> `check-single-pin-actions` 17/17 · **`check-league-candidates-300` 66/66
> (new, proven against 40 sabotages, 0 false passes)** ·
> **`check-picks-subset-invariance` 72/72** (was 66/3-red on the branch —
> #300's `activeValueLabel` refactor had broken assertion 12; re-pinned, and
> 3e–3h added for the 2026-08-12 rule A/B removal, each proven against a
> targeted sabotage). Maestro flows `league/06-position-trade-candidates.yaml`
> (new) and `league/02-picks-in-position-filter.yaml` (rewritten for the plain
> toggle) authored but **not executed** — 06 needs the `medians` field live in
> the hermetic world; 02 is Tier B (zero seeded draft picks). Simulator items
> outstanding: §6 of `status-mobile.md`.

---

## 6. QA checklist — including everything static analysis cannot reach

Ordered by risk. **Items 1–4 are the ones no static tool can settle.**

### Must be verified on a simulator before the 44pt claim is asserted anywhere

1. **`hitSlop` actually delivers a 44pt target.** Drill in, then tap **5pt
   above** a roster row's visible top edge and confirm **that** row fires —
   not the one above it, and not nothing. Repeat 5pt below. The claim is that
   slop on the tile's own outermost `Pressable` extends into `rosterRow`
   (margin only) and `drillList` (gap only), neither of which clips. **This
   is reasoned, not measured.** If it fails, the fallback is R-2 from
   `mockups/candidates-300-v2/tile-affordance.html`: grow the actionable row
   to 44pt (`+72pt` over a six-player group) and drop the slop. The
   horizontal design is unaffected either way.
2. **Adjacent slop regions do not overlap.** With `rosterRowActionable`'s
   12pt margin, 32 + 12 = 44 exactly. Tap right on the boundary between two
   rows, repeatedly, and confirm the taps alternate sensibly rather than one
   row winning both. An 8pt overlap here fires the **wrong player** and is
   invisible in every screenshot and every Maestro id-tap.
3. **VoiceOver reads the row as one utterance with the right hint.** Expect:
   name, position, team, tier, posRank, **rookie**, **injury** — Variant D
   drops the printed tags but must not drop them from the utterance — then
   "Offers Puka Nacua to Punt Gods" as the hint. Confirm no separate focus
   stop for the "Offer ›" text (it is decoration inside an `accessible: true`
   container).
4. **The auto-return announces itself.** With VoiceOver on, drill in, change
   the position pill, and confirm "Filter changed. Back to all teams." is
   spoken and focus is somewhere sane on the list.

### Layout / visual review (needs eyes, per flow-authoring law 23)

5. **"Marvin Harrison Jr." renders unclipped on an actionable row** with the
   widest tier badge (`4+ 1sts`) and `WR61`. This is the whole geometric
   argument for Variant D: 146.4pt of name budget vs the 143.8pt baseline. If
   it clips, the override did not buy what it was measured to buy.
6. **The group head reads well in candidate mode** — "Your WR" / "Punt Gods'
   WR" as chalk owner + position-hex position, with the count · label · rank
   chip on the right. Confirm the owner name is **not** tinted with the
   position hex.
7. **The divider is legible between two hairline list rows.** It reuses
   `oddsCutRule`/`oddsCutText` verbatim; only the outer padding is this
   screen's own. Check it does not read as a third list row.
8. **Buyer/Seller chips do not crowd the "You" badge** on the caller's row
   when the caller is in a band.
9. **The mirror disclosure** reads as a control (44pt, chevron swaps
   down/right, never rotates) and its expanded rows carry the **opposite**
   verb.

### Data / arithmetic, on real leagues

10. **Small league (8 teams).** Bands are 3/2/3 — six of eight teams carry a
    call. The frozen spec calls this "the arithmetic working as specified,
    not a defect, but it is worth seeing once on a small league before it
    ships" (§4 item 4). This is the intended sighting.
11. **Odd team count.** The at-median team sits **above** the line. Confirm
    it does not read as mis-sorted. The mock's "At median" badge is **not
    built** pending still-open item 1.
12. **A pick-carrying league.** Tap WR → the Picks pill lights and **no
    divider appears**; tap Picks off → the divider appears. Confirm the lit
    pill is a sufficient explanation, or take one of §3.1's alternatives.
13. **A caller with no team in the league**, and **the caller's own row** —
    both must fall back to today's inert drill-in, no verb, no crash.
14. **A player with `tier: null`** (K/DEF, unpriceable) still renders,
    tappable, badge-less, `NR` — no dimming, per operator decision 7. Confirm
    the handoff still pins it.
15. **Outside `aggregate_tier_labels`**: the divider reads bare "League
    median" and the ranked rows fall back to the numeric under a
    multi-position filter. Both are the specified degradations, not bugs.

### End to end

16. **Flow `league/06-position-trade-candidates.yaml` runs green** once
    `medians` is live. Then **eyeball all four screenshots** — a green run is
    not a good capture (law 23).
17. **The Offer direction end to end.** Flow 06 only exercises Target
    (rank 1 is the one deterministically addressable row). Manually: tap a
    team **below** the line, confirm **your** roster appears with "Offer ›",
    tap a player, confirm you land in the finder with that player pinned on
    the **give** side.
18. **Pins are replaced, not accumulated.** Pin something in the finder
    first, then run the handoff, and confirm exactly **one** pin exists
    afterwards and it is the new one — `trades.asset-ideas` mounts only for a
    single pin, so its presence is the check.
19. **Flag-off regression.** With both flags off, the League screen and its
    drill-in are indistinguishable from `origin/main` — no divider, no chips,
    no captions, inert 32pt tiles at a 4pt margin, micro-tags present, and
    the numeric value column exactly as today.

---

## 7. 2026-08-12 — removing #294's rule A and rule B from `togglePos`

Operator decision, delivered mid-#300: *"All leagues have picks. They should
not be selected along with a position filter. Only by explicit user action."*

This is a deliberate reversal of behaviour shipped two days earlier, taken
with the original reasoning on the record. It is not relitigated here — the
reasoning on both sides is **preserved in the code comment** above
`togglePos` and in `config/features.json`'s flag block, rather than deleted.

### 7.1 What was removed

| Rule | What it did (flag ON) | Verdict |
|---|---|---|
| A — auto-add | first position tap out of `{}` also selected `PICKS` | **removed** — the operator's ruling |
| B — exit | removing a position leaving no core position cleared the filter to All | **removed** — see §7.2 |

Exactly one code hunk, `mobile/src/screens/LeagueSummaryScreen.tsx`
`togglePos`: four lines deleted, two collapsed into one. `picksAlwaysCounted`
references in that file go 24 → 23; the one lost is the `if (picksAlwaysCounted
&& pos !== 'PICKS')` guard the two rules lived under. Everything else is
comments.

### 7.2 The rule B decision, and why it follows

**Rule B goes.** Its stated justification — *"instead of stranding the user in
a picks-only ranking they never asked for"* — was true **only because rule A
could put `PICKS` in the filter without the user asking**. With rule A gone,
`PICKS` in the filter can only ever mean the user tapped the Picks pill
deliberately, so rule B's trigger and the operator's protected case are now
*the same set of states*: `{PICKS, RB}` minus `RB` clearing to All discards an
explicit choice, which is precisely what the ruling objects to.

It could not be narrowed instead, because there is nothing left to narrow it
*to*. Rule B's only observable effect was ever on states containing `PICKS` —
with no `PICKS`, removing the last core position already yields the empty set,
which *is* All. So the rule is now pure loss: every state it fires on is a
state it must not fire on.

Two of #294's other claims for rule B also dissolve:

- **Reversibility.** Rule B was described as "what keeps the position pill
  reversible — tap RB on, tap RB off, back where you started." A plain toggle
  is its own inverse, so reversibility is now structural rather than a rule.
  It is also strictly *better*: #294 accepted one broken case (`{PICKS}` → add
  RB → remove RB lands on All, one extra tap); a plain toggle returns to
  `{PICKS}`.
- **The "hidden state axis".** #294 recorded that distinguishing a hand-chosen
  `PICKS` from an auto-added one *"would need a hidden 'the user chose picks
  by hand' state axis, which is deliberately NOT built."* Removing rule A
  makes that axis **unnecessary**: every `PICKS` is hand-chosen, so the
  distinction is free. This is the load-bearing reason rule B can go without
  building anything.

A picks-only ranking is still reachable — tap Picks from All, as it always
was, since rule A never fired on the Picks pill itself. What changed is that
nothing but a user tap can put you there.

### 7.3 The three verifications requested

**(1) The pill invariant holds, unchanged.** *"Whenever the filter is
non-empty, the Picks pill's selected state is exactly equal to whether pick
value is in the chart."* Checked against the two halves:

- `activeTotal` (`:358–378`) is untouched. For a non-empty filter it sums per
  key and adds `picks.value` **iff** `'PICKS' ∈ filter`.
- The pill's `accessibilityState={{ selected }}` in `PosFilterPills`
  (`:2149`) **is** `filter.has('PICKS')`.

So the two sides are the same predicate, and always were — the invariant never
depended on rule A. Under flag OFF the `PICKS` arm returns 0 in a non-`all`
subset, but that state stays unreachable via `switchSubset`'s synchronous
strip, the reconciliation effect, and `showPicksKey` hiding the pill; that
machinery is untouched. The one **newly reachable** state is `{PICKS}` alone
arrived at from `{PICKS, RB}` — `activeTotal` returns `picks.value`, pill lit,
invariant satisfied — and it introduces no new rendering path, because
`{PICKS}` was already reachable by tapping Picks from All.

**(2) `league.picks_always_counted` is still meaningful.** All five surfaces
the task names are byte-untouched, verified by diffing the flag's occurrences:
`activeTotal`'s two arms (`:366–376`), `showPicksKey` (`:600`), `BarColumn`'s
key list / `segValue` / `shownBase` (`:2207–2222`), the drill-in "Draft
capital" group (`:1918`), and the three hint strings via `picksInView`
(`:606`) and the filtered-hint ternary (`:1498`). Twelve of R-0.2's fourteen
gated expressions remain; G4/G5 (`togglePos`) are the two that are gone.
**Flag-OFF behaviour is byte-identical** — the deleted guard began
`if (picksAlwaysCounted && …)`, so it was already inert with the flag off.

**(3) #300's divider gate stays, comment corrected.** `candidatePos`
(`:838–844`) still bails on `posFilter.has('PICKS')` — unchanged, and
`check-league-candidates-300.js` still catches its removal (sabotaged both by
deletion and by comment-out; both red). The comment block above it described
rule A as a live obstacle and now describes the current reality: the natural
path (tap WR from All) reaches the divider in a pick-carrying league, and the
gate fires only when a user explicitly adds Picks — which is the state where
the WR median genuinely does not describe the WR+capital ranking they asked
for.

### 7.4 What each pinning artifact needed

| Artifact | What it needed, and why |
|---|---|
| `mobile/.maestro/flows/league/02-picks-in-position-filter.yaml` | **Rewritten.** Its core premise (`{} --tap RB--> {RB, PICKS}`) is now wrong. The new four-step machine asserts the plain toggle, and its steps 1 and 3 are exactly the two that would fail on pre-change code. Step 1 asserts `selected: false` on the Picks pill rather than `assertNotVisible` — with the flag ON and real picks the pill *renders*; what must be dark is its selected state. T4 now needs two drill-in taps to reach `RB + Picks`, since rule A no longer supplies the second. |
| `mobile/.maestro/flows/league/04-picks-flag-off.yaml` | **Section (b) no longer distinguishes anything** — with rule A gone globally there is no rule to be dark, in either flag state. The claim is retired rather than reworded; the steps survive as screenshot baseline, which the header already declared the flow's honest job. Separately: this flow's header asserted `release.json` carries the flag `false`. It reads `true` (line 139) and has since 2026-08-10, so `# flags: release` runs it flag-**ON** despite the filename. Corrected in the header and filed below — fixing it properly needs a fixture, which is not this change's to add. |
| `mobile/.maestro/flows/league/06-position-trade-candidates.yaml` | Its seeding note said the zero-picks seed was what let one WR tap land on `{WR}`, and flagged the real-league divider-hidden case as a discoverability cost. That cost is **closed**; note rewritten. |
| `mobile/tests/check-picks-subset-invariance.js` | Pinned rule A/B via one row — `['G4/G5 togglePos', togglePosInit]` in `bodyGated`, asserting `togglePos` branches on the flag. That assertion encoded **rules A and B specifically**, not a broader invariant: the flag's other twelve gated expressions are asserted individually and none of them changed. Row removed, replaced by 3e–3h asserting the **absence** (§7.5). |
| `mobile/tests/check-league-candidates-300.js` | Gate assertion unchanged; its failure message called the `PICKS`-present state "the ROUTINE state under `league.picks_always_counted`'s auto-add rule". Reworded. |
| `config/features.json` | The `_comment_league_picks_always_counted` block documented both rules at length and would have become a lie. Rewritten to describe current behaviour, record the 2026-08-12 removal as an operator decision, and **preserve the original reasoning verbatim in substance**. |

### 7.5 New and changed assertions, each with its sabotage

`check-picks-subset-invariance.js`: **66 pass / 3 fail → 72 pass / 0 fail.**

The three pre-existing failures (12a/12b/12c) were **not caused by this
change** — they were red on `build-300-mobile` before it. Commit `1c3471a`
(#300) folded the screen's two inline `total_value_label` render sites into
one `activeValueLabel` helper and moved the gate from a JSX expression into an
`if` statement, breaking both shape assumptions the checks were written on.
Confirmed by running the suite against `62ff8d6`'s copy of the screen: green.
The invariant they defend is intact, so they were re-pinned to the new shape,
deliberately no weaker.

| Assertion | Change | Sabotage that proves it |
|---|---|---|
| `3 — G4/G5 togglePos branches on the flag` | **removed** | superseded — it asserted the rules exist |
| `3e — togglePos does not reference picksAlwaysCounted` | new | S1 re-add rule A · S2 re-add rule B · S3 re-add both — all red |
| `3f — togglePos contains no 'PICKS' literal` | new | S1, S3 red; **S4** re-adds rule A *without* the flag guard — 3e cannot see it, 3f still red |
| `3g — exactly ONE empty new Set()` | new | S2, S3 red; **S5** re-adds rule B with no flag reference and no `'PICKS'` literal — only 3g/3h see it |
| `3h — that empty Set is the pos === 'ALL' branch` | new | S2, S3, S5 red; **S6** moves the surviving clear onto `pos === 'QB'` — 3g stays green, 3h alone goes red |
| `12a — ONE render path` (was: two sites) | changed | **S8** adds a second `total_value_label` site — red |
| `12b — keeps the unfiltered-All gate` | changed (accepts an `if` gate as well as an expression) | **S9b** widens the gate to `subset === 'all'` — red, alone |
| `12c — site AND its whole host function are flag-free` (was: gate only) | changed, **strengthened** | **S10b** puts `picksAlwaysCounted` in the helper without adding a label site — red, alone. The old gate-only check would have missed it. |

**Comment immunity, checked rather than assumed.** All four new assertions are
AST-level (`ts.isIdentifier` / `ts.isStringLiteral` / `ts.isNewExpression`), and
12c was converted from `flat().includes()` to an identifier-node scan for the
same reason. **S7** is the control: a comment inside `togglePos` naming both
`picksAlwaysCounted` and `next.add('PICKS')` produces **zero** failures. The
shipped comment necessarily names both, so a raw-source scan would have been
red on the correct build. `check-league-candidates-300.js` was independently
checked: **S12** comments out the divider gate and the suite still goes red
(it strips comments before matching), where a naive text scan would pass.

**Twelve sabotages run, zero false passes.** The harness rewrites the screen
in place and `git checkout --`s it afterwards, so it is not committed; every
mutation was verified to have actually applied (`git diff --quiet` guard) —
a mutation that silently no-ops is itself a false pass.

### 7.6 Filed for the operator

1. **There is no flag-OFF fixture for `league.picks_always_counted`.**
   `release.json` has carried `true` since 2026-08-10, so
   `04-picks-flag-off.yaml` runs flag-**ON** despite its name, and the only
   route to the OFF arm is `sim-run.sh --flags` with inline JSON. The kill
   switch is therefore un-exercised end-to-end. A `release-picks-off.json`
   fixture would fix it; not added here because fixtures are shared and
   out of this change's lane.
2. **`02-picks-in-position-filter.yaml` remains Tier B.** The hermetic world
   seeds zero `draft_picks`, so `hasPicks` is false and the Picks pill never
   renders — the rewritten steps 1–4 cannot run until the seeding follow-up
   lands. Until then the rules' removal is evidenced by 3e–3h (source-level,
   seed-independent) and by manual control T-S6.
