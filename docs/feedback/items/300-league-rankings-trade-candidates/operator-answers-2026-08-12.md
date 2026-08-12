# #300 — Round 2 operator decisions, 2026-08-12

> **This is the frozen design.** It supersedes
> [`operator-answers-2026-08-11.md`](operator-answers-2026-08-11.md) §6 and
> [`plan.md`](plan.md) wherever they disagree. Drawn against
> [`mockups/candidates-300-v2/`](../../../../mockups/candidates-300-v2/), which
> was measured against the **shipped** #299 tile (`PlayerCard.tsx`
> `styles.cardDenseSingle`, `height: 32`) rather than a mockup box model.
>
> **Recorded, not executed** — no production code exists for #300.
>
> **Status: build-ready.** Every design question raised across three rounds is
> answered. What remains before a build starts is process, not design: the
> scope block, the new API field's contract, and the full feature gates that an
> API-contract change requires.

---

## Table of Contents

- [1. The decided design](#1-the-decided-design)
- [2. Decisions, and what each one overrode](#2-decisions-and-what-each-one-overrode)
- [3. Build consequences](#3-build-consequences)
- [4. Still open](#4-still-open)

---

## 1. The decided design

**Direction 2 — one list, one median divider.** No separate candidates
section, no Buyers/Sellers pills, no collapse/expand.

1. The user filters League rankings to **exactly one** core position, P.
2. The already-ranked list (filtering to P re-ranks the league by P — the
   `activeTotal` sum over `posValues[P]`) gains **one labelled divider**:
   the league median at P, styled on the shipped playoff-cutline pattern
   (`oddsCutline` / `oddsCutRule` / `oddsCutText`, `LeagueSummaryScreen.tsx:2253`).
3. Teams **above** the line are sellers; **below** are buyers. The user's own
   team stays in the list as the anchor — there is no separate section for it
   to be wrongly included in.
4. **The bottom 33% carry a "Buyer" label and the top 33% a "Seller" label**
   (band = `round(team_count * 0.33)`); the middle is unlabelled. The labels are
   **emphasis only** — they do not drive behaviour.
5. **The median line is the direction rule, for every team including the
   unlabelled middle.** Tapping a team opens a drill-in showing **stacked**
   rosters — never side-by-side columns — and which roster appears is decided
   by the team's side of the median line: **your** players if they sit below it,
   **their** players if above. Every team in the list is tappable and every team
   has a direction, because the line covers all of them while the labels cover
   only the extremes.
6. Row action: **"Offer"** on the user's own players (pins `give`),
   **"Target"** on the other team's (pins `receive`). Then route to the trade
   finder, replacing existing pins.

---

## 2. Decisions, and what each one overrode

| # | Decision | Note |
|---|---|---|
| 1 | **Direction 2**, with its labels | Aligned with the lab's recommendation. Direction 1's pills would have sliced a list that already exists 180pt below them. |
| 2 | **Variant D — drop the injury and rookie tags to fit a visible "Offer" label** | **Operator override, taken with the objection on the record.** Geometry supports it: dropping RK + injury frees 53.6pt, "Offer ›" costs 51.0pt, net **+2.6pt** vs the shipped baseline of 143.8pt, so "Marvin Harrison Jr." renders unclipped. The lab recommended *against* it on content grounds — the injury tag was deliberately raised to the 11px floor by S2 PRD-04 **because it is a decision input**, and a trade surface is where that matters most. The operator has chosen the visible label anyway; that call stands and is not to be relitigated at build time. |
| 3 | **No delta-from-median in pick tiers** | Agreed with the lab. `_pick_gap_equivalent` is the right converter but its rungs are too sparse: 4 of 12 deltas collapsed onto "an Early 1st", the largest gap had no name, and just above the floor naming was 66% off. Per-team **level** labels instead, with the median's level on the divider. |
| 4 | **Stack the rosters**, never side-by-side | Agreed. 171pt columns against a 113.1pt right cluster truncates even when stripped of tier badge and posRank. |
| 5 | **The divider renders only when exactly one position is selected** | Multi-position has no single median to draw. |
| 6 | **The combined-positions view must still use pick-tier labels** | **New scope, operator-added.** Today `TeamRow`'s `totalLabel` is passed only when `subset === 'all' && posFilter.size === 0` (`LeagueSummaryScreen.tsx:1533-1536`); every other combination — including 2+ positions — falls back to a **raw numeric**, which contradicts the no-numeric-values ruling. Fix it in this work rather than leaving it as a separate item. |
| 7 | **Unpriceable players: no special treatment — the existing FA tier covers it** | Operator call, and it is correct. **A caveat first recorded here was wrong and is withdrawn:** it claimed FA was only `player.team \|\| 'FA'`, the NFL-team slot. There are two unrelated "FA"s in this app and that grep found the wrong one. The load-bearing one is the **bottom tier band** — key `waivers`, display label **`FA`**, defined as *"below 4th-round value"* (`mobile/src/utils/tierBands.ts:32,38-47`; same mapping in `TierBadge.tsx:22`, `chalkline/Badge.tsx:38`, `backend/trade_service.py:1894`). That is a value statement in the Pick Anchor wizard's own vocabulary, which is exactly what was wanted. A player with no meaningful value carries the FA tier badge and needs no bespoke dimming. **This closes the round-1 "dim with caption" answer** — round 1 is superseded here. |
| 8 | **Bottom 33% of teams are labelled "Buyer"; top 33% are labelled "Seller".** Band size = `round(team_count * 0.33)`, **rounded to the nearest whole number** | **Operator-added, and it narrows the candidate set.** Round 2 §4 left open whether "below the median" was really the wanted set. It is not — only the extremes are called out. Initially specified as 25%, revised to 33%. Resolved sizes: **8 teams → 3/2/3 · 10 → 3/4/3 · 12 → 4/4/4 · 14 → 5/4/5** (buyers / unlabelled / sellers). The unlabelled middle stays at 4 teams across every common league size, and 12-team leagues land on exact thirds. |

---

## 3. Build consequences

- **A new API field is required.** The divider needs the median's *label*, and
  the client can compute the median value but cannot label it — labelling is
  server-side (`value_label`, gated by the `aggregate_tier_labels` experiment).
  Shape proposed by the lab: `medians: {QB|RB|WR|TE: {value, value_label}}`.
  **This is an API-contract change and therefore on the `CLAUDE.md` bright
  line — not a quick fix, full gates.** Decision 6 may widen it further.
- **The 44pt problem is resolved by making the whole row the button** — one
  focusable element, one `testID`, one label+hint, with `hitSlop` 6/6 on the
  tile's own outermost `Pressable` and `rosterRow` margin 4 → 12 so slop
  regions do not overlap. 44pt pitch, 32pt visual, 264pt for six rows. A
  nested control was **rejected**: `styles.card` has `overflow: 'hidden'`
  (`PlayerCard.tsx:388`) so a child's hit area clips, and `accessible: true`
  on the dense `Pressable` hides it from VoiceOver and from Maestro
  id-selectors. **This is a sim-verify-before-asserting item, not a proven
  fact.**
- **Variant D changes the drill-in player rows only** — the divider list rows
  are teams and are unaffected.
- The experiment gating `value_label` (`aggregate_tier_labels`, operator-only
  treatment) has to graduate, or #300 has to read the same computation
  directly. Unresolved.

---

## 4. Still open

1. **Odd team counts leave exactly one team at the median.** Direction 2 marks
   it "At median". Confirm that reads correctly, or decide which side it
   belongs to.
2. ~~Whether "below the median" is genuinely the wanted candidate set.~~
   **ANSWERED by decision 8** — it is not. Only the bottom and top quartiles
   are called out.
3. **The `aggregate_tier_labels` experiment's status** — see §3.
4. ~~Quartile rounding.~~ **ANSWERED** — the band is **33%, rounded to the
   nearest whole number**, superseding the original 25%. See decision 8 for the
   resolved sizes. Note the consequence: on an 8-team league this labels 6 of 8
   teams, so three-quarters of the league carries a call. That is the arithmetic
   working as specified, not a defect, but it is worth seeing once on a small
   league before it ships.
5. ~~What the unlabelled middle does.~~ **ANSWERED — option (a).** The median
   line stays the direction rule for every team, including the unlabelled
   middle; the Buyer/Seller band labels are emphasis layered on top of it. This
   was the option that added no new behaviour and left the §1 divider decision
   intact. Nothing in the list becomes inert and no team lacks a direction.

