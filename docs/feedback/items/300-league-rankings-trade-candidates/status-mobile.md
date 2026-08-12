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

**Cost, and the operator decision it needs:** in a pick-carrying league the
divider now costs **one extra tap** — the user must deselect the lit Picks
pill. In the hermetic QA world this never bites (the seed writes zero
`draft_picks`), which is exactly why it would have shipped unnoticed. Options
if the operator wants it to appear on the first tap:

- have rule A skip the auto-add while `league.pos_candidates` is on and the
  tap is the first position — i.e. tapping WR means `{WR}`. Reverses #294's
  ruling for one flag combination;
- add a `medians` variant that includes pick value so the two agree — a
  bigger API change, and "richest at WR once you count their picks" is not a
  positional thesis;
- leave it: one visible, reversible tap, with the lit pill explaining itself.

Recommend the third; flagging it because the design lab's recommendation
assumed the first was already true.

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
>   line in the wrong place and nothing on screen says so. Under
>   `league.picks_always_counted` (shipped ON) rule A auto-adds `PICKS` on the
>   first position tap, so in a pick-carrying league the divider costs one
>   extra tap on the lit Picks pill — by design. Pinned by
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

### `living-memory/DECISIONS.md` — one entry

> **The #300 median divider draws only when the ranked list is sorted by the
> quantity the median measures.** The design lab's ground truth ("a
> single-position filter returns exactly `posValues[P]`") predates
> `league.picks_always_counted`'s auto-add rule, which puts `PICKS` in the
> filter on the first position tap and makes the list a WR+capital ranking.
> Rather than draw a line that is confidently in the wrong place, the client
> requires: one core position, no `PICKS`, subset `all`, and `medians` on the
> payload. Cost: one extra tap on the lit Picks pill in pick-carrying
> leagues. Alternatives (suppress rule A under the flag; add a
> picks-inclusive median) are recorded in
> `docs/feedback/items/300-league-rankings-trade-candidates/status-mobile.md`
> §3.1 for the operator.

### `living-memory/TEST_LEDGER.md` — one entry

> #300 mobile, static gate only (no simulator — parallel agents contend for
> one sim): `tsc --noEmit` clean · `testid-lint.sh` OK ·
> `check-league-drill-in` 29/29 · `check-analytics-297-302` 35/35 ·
> `check-single-pin-actions` 17/17 · **`check-league-candidates-300` 66/66
> (new, proven against 40 sabotages, 0 false passes)**. Maestro flow
> `league/06-position-trade-candidates.yaml` authored but **not executed** —
> it needs the `medians` field live in the hermetic world. Simulator items
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
