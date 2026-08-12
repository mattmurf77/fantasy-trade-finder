# #300 — Operator answers and scope expansion, 2026-08-11

> Answers to the open questions in [`plan.md`](plan.md) §9, plus a **material
> scope expansion** the answers introduce. **This file supersedes `plan.md`
> where they conflict**, and two of the plan's load-bearing conclusions are
> invalidated below (§3). The Author writing the PRD must read this first.

---

## Table of Contents

- [1. Answers](#1-answers)
- [2. The expansion, in the operator's words](#2-the-expansion-in-the-operators-words)
- [3. What the expansion invalidates](#3-what-the-expansion-invalidates)
- [4. New open questions the expansion creates](#4-new-open-questions-the-expansion-creates)

---

## 1. Answers

| Q | Question | Answer |
|---|---|---|
| Q1 | Definition of "worse at that position" | **Median/average-relative.** The operator asked for one of the three alternatives rather than the plan's recommendation. Of the three, median-relative is the only one without a structural blocker (starter-quality is unavailable on non-Sleeper platforms via `starters_available`; need-based requires a new endpoint and a second value system that can visibly contradict the chart). **Recorded with the tradeoff stated:** it answers "who is weak league-wide", not "who can I sell to" — a team below the median but above the caller will now surface as a candidate. Operator was told this explicitly and did not reverse. |
| Q2 | Replace vs append pins on handoff | **Replace.** |
| Q3 | Entry trigger | **A — the existing position filter pills.** No new sell-intent control. |
| Q4 | Value-0 players | **Dim the affordance with a caption**, do not hide it. |
| Q5 | Button label | **Match the existing "Find a Trade" vocabulary** rather than inventing "Find trade suggestions". Exact strings still to be written (§2). |
| Q6 | Team-level handoff | **YES — reversed from the plan's recommendation.** See §2 and §3. |

---

## 2. The expansion, in the operator's words

> "Be sure to plan it forward to actually getting to trades. The screen that
> shows the teams who are weak at the position should have a redirect to the
> trade calc with the team pre-selected. The screen showing the teams who are
> weak should have the same tiles as the league summary page. So each team is
> clickable, clicking the team shows the player at the position of weakness,
> and there should be a button to 'Find my Trades with this team' — work on the
> copy — and a 'Find players for X' which behaves the same way."
>
> "We should have a 'trade with this team' button."

Restated as requirements:

- **R-A1** The candidates view reuses the **same tiles as the League summary
  page** — not a bespoke row. (Note: those tiles are being redesigned by #299
  to 32pt. See §3.3.)
- **R-A2** Each candidate team is **tappable**.
- **R-A3** Tapping a team **surfaces that team's player(s) at the position of
  weakness** — the drill-in already does roster display; this scopes it to P.
- **R-A4** A **"Find my Trades with this team"** button (copy to be written)
  that lands in the trade finder **scoped to that team**.
- **R-A5** A **"Find players for X"** button that "behaves the same way".
  **X is ambiguous — see §4 Q-N2.**
- **R-A6** A **"trade with this team"** button — read as the same affordance as
  R-A4, not a second one. Confirm.

---

## 3. What the expansion invalidates

### 3.1 "300-B needs zero edits to `TradesScreen.tsx`" — NO LONGER TRUE

This was the plan's headline reason 300-B was low-risk and free of collision
with #297/#298. It held **only because player preselection rides the
`useFinderTargets` pin store**, which is read at generate time and needs no
route params.

**Team scoping has no such contract.** With `trades.sheet_targeting` ON
(`config/features.json:180`), `scopedOpponent` reads sheet-local `sheetOpponent`
state and **route params are ignored** (`TradesScreen.tsx:515-524`). There is
currently **no way to preset the opponent from outside the screen.** R-A4/R-A6
therefore require one of:

- **(a)** extend the pin store (or add a sibling store) with an opponent that
  the sheet reads on mount — symmetrical with how player pins already work, and
  the only option that keeps the contract outside `TradesScreen.tsx`; or
- **(b)** re-enable route-param reads under `sheet_targeting`, i.e. seed
  `sheetOpponent` from params on mount — smaller diff, but it re-opens the path
  #269 deliberately closed.

Either way this is **a real edit to `TradesScreen.tsx` and/or `TradeDnaSheet.tsx`.**

### 3.2 File-ownership collision is now REAL, not hypothetical

`TradesScreen.tsx` is simultaneously owned by **#298 (V1 — rebuilding the
single-pin surface into a deck card)** and now **#300**. Per the lab's decision
record these already needed one owner or serialization with #297. #300 joins
that set. **Recommendation: #300's team-handoff work lands after #297/#298
merge, not beside it.**

### 3.3 The candidates view now depends on #299

R-A1 says "the same tiles as the league summary page". #299 is changing exactly
those tiles (60pt → 32pt, tier badge relocated). Building the candidates view
against today's tiles would ship a view that looks wrong the day #299 lands.
**#299 is a prerequisite of R-A1**, or R-A1 must explicitly target the post-#299
tile.

### 3.4 The definition change interacts with the anchor

The plan's empty states were written for `theirValue < yourValue` — e.g. "No
team has less RB value than you", and the caller is the anchor and never a
candidate. **Under median-relative the caller can themselves be below the
median**, so the caller's own team can qualify as a "candidate" unless
explicitly excluded, and the empty state's copy no longer parses. All of §3.2's
states in `plan.md` need rewriting against the new definition.

---

## 4. New open questions the expansion creates

**Q-N1 — "trade calc" or the trade finder?** The operator wrote "a redirect to
the **trade calc** with the team pre-selected". `TradeCalculator` and the trade
finder (`TradesScreen`) are different screens with different mechanisms, and
team preselection is a finder concept — the calculator is a manual two-sided
tool. **Assumption carried forward: the trade finder.** Confirm.

**Q-N2 — what is X in "Find players for X"?** Two readings: (a) the *position*
— "Find players for RB", i.e. find RBs to acquire; or (b) the *team* — a
mirrored "what can I get from them" direction. The plan cannot proceed on
R-A5 without this.

**Q-N3 — is R-A6 the same button as R-A4?** "Find my Trades with this team" and
"trade with this team" read as one affordance described twice. Assumed one.

**Q-N4 — exact copy.** The operator asked to "work on the copy" and separately
ruled that the existing **"Find a Trade"** vocabulary wins. Proposed:
**"Find a Trade with this team"** — reuses the shipped noun phrase, states the
scope, no new vocabulary. Needs sign-off.

---

## 5. Second pass — 2026-08-11

> Verbatim: *"Route to trade finder. 'Find players for X', should have been
> written 'Find trades for X'. Where X is the player selected."*

**Q-N1 — RESOLVED: the trade finder** (`TradesScreen`), not `TradeCalculator`.

**Q-N2 — RESOLVED: R-A5 is a player button, and it is 300-B.** "Find players
for X" was a mis-write for **"Find trades for X"**, where **X is the selected
player**. This is not a new mechanism — it is exactly the player→finder handoff
already designed as 300-B, riding the `useFinderTargets` pin store. Restated:

- **Team button** (R-A4/R-A6) — "Find a Trade with this team" → finder scoped
  to that opponent. **Needs the new opponent-scoping mechanism** (§3.1); this is
  the part that collides with #297/#298.
- **Player button** (R-A5) — "Find trades for <Player>" → finder with that
  player pinned. **Uses the existing pin store; no `TradesScreen.tsx` edit.**

**Q-N3 — resolved by implication.** With R-A5 established as the *player*
button, "trade with this team" and "Find my Trades with this team" are one
affordance (the team button), not two.

### 5.1 UNRESOLVED — the give/receive side is backwards for the stated use case

The original feedback set the rule: a tapped player is pinned **give** if it is
the caller's own, **receive** if it is an opponent's ("depending on whether the
user is clicking the button on one of their players or one of their opponents
players").

Follow that rule through the candidates flow and it inverts the feature's
purpose:

1. The caller is shopping a WR, so they filter to WR.
2. The candidates view lists teams **weak at WR**.
3. They tap one and see **that team's WR** — the weak team's weak player.
4. "Find trades for <their bad WR>" pins it as **receive** — i.e. *acquire
   their worst WR*.

The caller's intent was to **sell their surplus WR to that team**, not to
acquire that team's deficient one. The literal rule produces the opposite
trade.

Three candidate resolutions, none yet chosen:

| Option | Behaviour | Cost |
|---|---|---|
| **(a) Literal** | Keep the own/opponent rule as written; the drill-in's player button pins their player as `receive`. | Free, but ships the inversion above. |
| **(b) Context-aware** | Inside the candidates flow, the team button scopes the opponent AND pins the **caller's own** best surplus at P as `give`. The player button stays literal elsewhere. | Two behaviours for one control depending on entry path — needs a clear rule so it is not surprising. |
| **(c) Show the caller's players instead** | In the drill-in reached from a candidate, list **the caller's own** players at P (the sellable surplus), not the opponent's. Tapping one pins `give` and scopes the opponent. | Contradicts the operator's literal instruction ("clicking the team shows the player at the position of weakness"), which reads as *their* player. |

**This must be settled before the PRD.** It is the difference between a feature
that finds the trade the operator described and one that finds its mirror.

### 5.2 RESOLVED — option (c), with the caller's full inventory at P

> Verbatim: *"I'm aligned on C. But we should present all of our players at
> that position somewhere on the page where the 'Offer this player' or
> something similar is presented next to the player."*

**Decision: (c).** The drill-in reached from a candidate team presents **the
caller's own players at position P — all of them, not a filtered "surplus"
subset — each with an inline offer action.** Tapping it pins that player as
`give`, scopes the opponent, and routes to the finder.

The flow now reads end-to-end without inversion: *filter to WR → these teams
are weak at WR → tap one → here are my WRs → offer this one to them.*

**Requirements added:**

- **R-A7** The candidate drill-in lists the caller's players at P. **No
  surplus/quality filtering** — the operator asked for all of them; ranking
  them by value is presentation, excluding them is not.
- **R-A8** Each row carries an inline action next to the player. Working label
  **"Offer"** (see Q-N5) which pins `give` + scopes the opponent + routes.
- **R-A9** The value-0 rule (Q4) applies per row: a 0-value player keeps a
  **dimmed** action with a caption, not a hidden one.

### 5.3 New questions from 5.2

**Q-N5 — the label.** "Offer this player" is too long to sit next to a player
row. **"Offer"** alone is proposed: it is a verb the app already uses
(`Send offer`, `Send in Sleeper`), it is unambiguous next to a named player,
and it does not collide with the "Find a Trade" noun phrase reserved for the
screen-level buttons. Needs sign-off.

**Q-N6 — do the opponent's players at P still appear?** The operator's earlier
instruction was that tapping a team "shows the player at the position of
weakness", which reads as *their* player; 5.2 establishes that the actionable
list is *ours*. Two readings: (i) **both** — their players as read-only
evidence of the weakness, ours as the actionable inventory below; or (ii)
**ours only** — the candidates row already asserts the weakness with a number,
so their roster is redundant. (i) is more persuasive, (ii) is denser. Unresolved.

**Q-N7 — the inline action competes with #299 for tile space.** R-A1 reuses the
League summary tiles, and **#299 is simultaneously compressing those tiles to
32pt by emptying line 2 and moving the tier badge into the right cluster** —
the same right cluster an inline "Offer" button would occupy. A 32pt row
carrying name, position, tier, value AND a tappable action is a genuine layout
problem, not a styling detail. Options: a wider tile variant for this surface
only, the action as a trailing chevron-style affordance, or accepting a taller
row here than on the League summary. **This needs a mockup before build**, and
it is a second hard dependency on #299 landing first.

---

## 6. Third pass — 2026-08-11. #300 is fully specced.

| # | Question | Answer |
|---|---|---|
| Q-N5 | Label for the inline action | **"Offer"** — aligned. Short enough to sit beside a player row; reuses the app's existing offer verb; does not collide with the screen-level "Find a Trade" phrasing. |
| Q-N6 | Do the opponent's players at P render? | **No — ours only.** The candidates row already asserts the weakness with a number, so the opponent's roster is redundant here. The drill-in reached from a candidate shows **only the caller's players at P**, each with the Offer action. |
| Q-N7 | Inline action vs #299's 32pt tile | **Trailing chevron-style affordance** — not a button competing for the right cluster. **Mockups required before build**, operator-confirmed. #299 remains a hard prerequisite. |

**No open questions remain on #300.** The decided design, end to end:

1. Filter the League rankings to exactly one core position, P.
2. A **Trade candidates** section lists teams below the league
   **median/average** at P — weakest first, reusing the League summary tiles
   (post-#299).
3. Tapping a candidate team opens a drill-in showing **the caller's own players
   at P** — all of them, unfiltered, ranked by value — each with a **trailing
   chevron "Offer"** affordance. 0-value players keep a **dimmed** affordance
   with a caption rather than a hidden one.
4. **"Offer"** pins that player as `give`, scopes the opponent, and routes to
   the **trade finder** (`TradesScreen`), **replacing** any existing pins.
5. A screen-level **"Find a Trade with this team"** button routes to the finder
   scoped to that opponent without a player pin.

**Build order is forced, not preferred:** #299 → candidate-view mockups →
#297/#298 merge → #300's team-scoping work. Steps 1–4's player path rides the
existing pin store and needs no `TradesScreen.tsx` edit; step 5 needs the new
opponent-scoping mechanism (§3.1) and is the only part that collides.
