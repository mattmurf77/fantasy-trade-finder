# PRD — Card evidence (“would this close?”)

**Date:** 2026-08-19
**Status:** active, not built
**Owner (product):** operator. **Owner (delivery):** EM, tasking the tickets in [README.md](README.md)
**Scope:** [scope.md](scope.md)
**Sister initiative:** [landability-challenger](../landability-challenger/PRD.md) owns *which cards exist*. This PRD owns *what the card says about them*.

This is the document an EM hands to engineering. The KTC / DD / Roster Audit / MyDynastyValues research is closed. If a line here disagrees with Slack, this file wins until the operator amends it.

---

## 1. One-page brief

FTF already **suggests** trades. Roster Audit and MyDynastyValues mostly **evaluate** them. KeepTradeCut and Dynasty Daddy do both, and they wrap every suggestion with “this is even on the market / this fits both rosters.”

We do not. A live card today is a ranked package plus a fairness meter and a template sentence. The user cannot answer:

1. Who wins, in words that match the engine’s own number?
2. What happens to *both* lineups if this closes?
3. Is this a you-vs-market angle, or just “fair on DP seeds”?
4. Has a deal like this actually closed, in this league?

Those four answers are **presentment**, not generation. They must not dualize R5 / outlook-rank / `fit_premium` inside `_generate_trades_v2`. They annotate the cards the generator already cut.

**Do not ingest Roster Audit Elo or MDV VORP as the ranking function.** FTF’s product is personal Elo. RA/MDV flow in as evidence around that.

Sibling: the [landability challenger](../landability-challenger/PRD.md) asks whether we should *generate* both-willing cards. This PRD is independent and can ship on live Arm B. Shipping evidence on a viewer-wins deck is still a win; shipping it on the challenger is a bigger one.

---

## 2. Problem

Measured / observed:

| Gap | Evidence | Competitor that already answers it |
|---|---|---|
| Copy says “balanced” when the engine’s own fairness would not | EM: 805 cards (11.1%) carry that sentence below the app’s bar. Serializer already emits `favors`/`gap`; copy does not respect a 0.75 floor | RA letter grade; MDV structural fairness; DD verdict banner |
| Card does not show both-roster consequences | `analyze_roster_strengths()` runs at generation and is mostly thrown away; `match_context` is a thin needs/surplus slice | RA trade intelligence; MDV 1y lineup sim; DD Team Position Ranks |
| Divergence is invisible | Engine trades on you-vs-partner / you-vs-seed; the card never says “you’re higher than market on X” | MDV market-divergence lens; GM DIFF column. **Nobody else has a personal board** — this is our actual moat, unused |
| No comps | `market.trade_capture` is **ON** and writing `sleeper_trades`. No UI, no score, no strip on the card | RA Tradabase; GM comps |

What is **already shipped** (do not rebuild):

- `give_value` / `receive_value` / `favors` / `gap` on every live engine card via `_value_verdict_payload` ([`server.py`](../../../backend/server.py) ~923 and `trade_card_to_dict` ~10664).
- `fairness_score`, `basis`, `narrative`, `match_context`, `need_fit`, `partner_fit`, `lane`.
- `POST /api/trade/evaluate` with the same verdict shape.
- `sleeper_trades` capture (`market.trade_capture` true). Capture only — no scoring, no UI ([market-data-readiness](../market-data-readiness.md)).
- Dark `GET /api/tiers/community-diff` behind `tiers.community_diff` (still false).

#6’s original “serialize two numbers” ticket is **done**. What remains is the copy matrix, the impact payload, the diff sentence, and the history/comps read path.

---

## 3. Goals and non-goals

### Goals

- **G1.** Every served card states who wins in language that cannot contradict `fairness_score` / `favors`. “Balanced” / “even” / “fair-value idea” only when the ratio clears **0.75** (or the live `fairness_threshold` if higher). Landability Track B2 is absorbed here as E1.
- **G2.** Every served card carries a both-teams positional impact block (value before/after, league rank before/after, needs filled/created). Computed **after** the top-K cut, not per candidate.
- **G3.** Divergence-basis cards name the 1–2 assets you and the market (or partner) disagree on. Consensus-basis cards do not fake a personal angle.
- **G4.** The same verdict + impact objects render on the **calculator** and on a **received-offer** analyzer, so a deal the user did not generate gets the same read.
- **G5.** Your league’s captured Sleeper trades become a scored history feed, then a comps strip (“3 similar SF deals in this league”). Cross-league Tradabase is **not** G5.

### Non-goals (rejection rules)

- **N1.** Do not change `_generate_trades_v2` gates, surplus, shrink, `_tier_mult`, or R5. That is [landability-challenger](../landability-challenger/PRD.md).
- **N2.** Do not dualize user-only ranking overlays because RA shows a cliff warning. Fit annotates; it does not decide existence.
- **N3.** Do not call Roster Audit’s API at runtime (mandatory attribution; keys revoked if stripped).
- **N4.** Do not rank on MDV-style VORP or RA Elo. A later calculator *basis toggle* is a different PRD.
- **N5.** No 1-year / 3-year NPV. #5 already deferred this (needs projections we don’t own). Age as a **label** on a player row is fine; age as a score is not.
- **N6.** No Sleeper-wide trade crawler (#41). Your leagues only, off data we already capture.
- **N7.** No pending-offer auto-inbox (V2 of #11) until the #83 Sleeper-auth memo. V1 is manual reconstruct from the two rosters.
- **N8.** FTF never accept/decline/counter *in* Sleeper from this initiative. Deep link only.
- **N9.** Do not light `bakeoff_serve_interleaved`. Irrelevant here.

---

## 4. Product shape

One card, four stacked evidence layers. Each layer is flag-gated and omit-when-absent so flag-off payloads stay byte-identical (existing serializer convention).

```text
┌─────────────────────────────────────────┐
│ E1  Verdict  “Leans your way by ~420”   │  numbers already on the wire
│ E3  Angle    “You > market on BTJ”      │  divergence cards only
│ E2  Impact   You RB 4→2 · Them WR 6→3   │  both sides, after top-K
│ E6  Comps    “2 similar deals in FFV3”  │  after E5 scores history
└─────────────────────────────────────────┘
```

Calculator and offer-analyzer **reuse** E1+E2. They do not get a second math path.

Parents (do not fork; this PRD sequences them):

| Layer | Parent spec | Delta vs parent |
|---|---|---|
| E1 verdict copy | [top20 #6](../competitor-top20/06-verdict-gap-banner.md) | Serializer is done. Copy floor is 0.75, not #6’s 8% “fair” band. Absorb landability B2. |
| E2 impact | [top20 #5](../competitor-top20/05-post-trade-impact-preview.md) | Binding. Both teams. No 1y/3y. |
| E3 you-vs-market | [top20 #9](../competitor-top20/09-community-diff-angles.md) **FR4 only** | Card narrative hooks. Full angles list / badges app-wide are out of this PRD (keep on #9). |
| E4 offer analyzer | [top20 #11](../competitor-top20/11-received-offer-analyzer.md) **V1 only** | Manual entry. Needs E1+E2 on the payload. |
| E5 history | Backlog **#26**; data: [market-data-readiness](../market-data-readiness.md) | Score `sleeper_trades` with current engine; render a league feed. |
| E6 comps strip | Backlog **#41** scoped down to *this league* | No crawler. Join E5 rows to the open card by shape + value band. |

---

## 5. Tickets

Independently mergeable except where noted. Estimates = one engineer who knows this repo.

### Wave 1 — on the live card (can start now, Arm B)

#### E1 — Honest verdict copy
**Who:** backend (small) + mobile + web. **Est:** 1.5d. **Depends:** none.

- Keep `_value_verdict_payload`. Do not re-derive `favors` on the client.
- `even` today is `min/max >= 0.95`. That is the 5% band, **not** the 0.75 fairness floor, and it is why “balanced” ships on unfair cards.
- Server: add `verdict.band` = `even` \| `slight` \| `lopsided` using knobs `verdict_even_min_ratio` (default **0.75**) and `verdict_lopsided_max_ratio` (default **0.55**). `favors` stays. Additive field, omit-when-you-want-old-clients-fine — actually always send; old clients ignore unknown keys.
- Copy matrix (clients render, never recompute band):

  | band × favors | Copy |
  |---|---|
  | even | “Even by league values.” |
  | slight / receive | “Leans your way by ~{N}.” |
  | slight / give | “Leans their way by ~{N}.” |
  | lopsided / receive | “Lopsided — you get ~{N} more. Expect a no.” |
  | lopsided / give | “Lopsided — you’re paying ~{N} extra.” |

- Forbidden below `verdict_even_min_ratio`: “balanced”, “fair”, “dead even”, “Fair-value idea” as a fairness claim. Consensus-basis may still say “Fair-value *idea*” **only** when band is `even`; otherwise “Consensus idea — leans {you/them}.”
- Flag: `trade.card_verdict` default **true** (this is a copy bug under both product choices). Kill = flag off restores today’s strings. Landability B2 is this ticket; do not also file it there.

**Done when:** a card with fairness 0.58 never renders “balanced” / “even” / “fair” on mobile or web. A card at 0.80 with receive > give says “even” or “leans your way,” never “lopsided.” Calculator uses the same matrix.

#### E2 — Both-team impact on the card
**Who:** backend, then mobile + web. **Est:** 2d + 1.5d. **Depends:** none (payload can land dark).

Binding parent: [05-post-trade-impact-preview.md](../competitor-top20/05-post-trade-impact-preview.md) FR1–FR6.

- After top-K (not per candidate): for user and partner, per position QB/RB/WR/TE: `{value_before, value_after, rank_before, rank_after}`, plus `needs_filled` / `needs_created`.
- Value basis = **consensus** `dynasty_value()` so both sides are comparable. Personal-Elo impact is a non-goal v1 (#5 open question, same ruling).
- Flag `trade.impact_preview` default **false**. Payload omit-when-flag-off.
- UI: two-row strip, you / them, rise/fall on the positions that actually move. No 1y/3y. No contender-mode toggle.
- Cliff: if a received starter is age ≥ position cliff (RB 28, WR 30, TE 31, QB 35) stamp `cliff: true` on that player row — **label only**, not a score. This is the RA intelligence crumb we can do without projections.

**Done when:** a fixture 1-for-1 that fills the user’s RB need and punches the partner’s WR room shows RB rank up for you and WR rank down for them; flag off = byte-identical payload.

#### E3 — You-vs-market sentence (divergence cards only)
**Who:** backend + copy in `trade_narrative.py`; clients render a chip. **Est:** 1d. **Depends:** none.

- #9 FR4 only. Do **not** ship the league-wide angles list or app-wide badges in this PRD.
- On `basis == "divergence"`: `diff_highlights` = top 1–2 assets by |user_value − seed_value| (user shrunk, same helper as #9 FR1), threshold |diff| ≥ 15% and comparison_count ≥ 3.
- Narrative one-liner: “Works because you two disagree on {player}.”
- Consensus cards: no chip. Cold boards: no chip (shrink makes diff ~0; that’s the point).
- Flag `trade.diff_angles` default **false**. `tiers.community_diff` stays false; this ticket does not flip it.

**Done when:** a boarded-pair card with a 20%+ you-vs-seed gap on one named player shows that player in `diff_highlights`; an unranked-partner consensus card has no such field.

---

### Wave 2 — a deal that already exists

#### E4 — Received-offer analyzer V1
**Who:** backend + mobile (primary) + web. **Est:** 3d. **Depends:** E1 (copy), E2 (impact payload). Sweetener counters are nice-to-have; ship without #3 swap-builder if that isn’t ready.

Binding parent: [11-received-offer-analyzer.md](../competitor-top20/11-received-offer-analyzer.md) V1.

- Manual: league → offering team → tap assets from the two real rosters.
- Output = the same card object as the deck (verdict + impact + optional counters).
- Persist the analysis. Action row: Open in Sleeper / mark accepted·declined·countered. **No write to Sleeper.**
- Flag `offers.analyzer` default **false**. `offers.inbox_auto` stays false.

**Done when:** reconstructing a 2-for-1 from two rosters produces a card that uses E1 copy and E2 impact; no Sleeper token is collected.

---

### Wave 3 — comps from data we already have

#### E5 — Score league trade history
**Who:** backend, then a league-tab feed (mobile + web). **Est:** 2d. **Depends:** none (`sleeper_trades` already filling).

- Batch-score captured complete trades with current consensus packages + E1 band. Stamp `give_value`/`receive_value`/`fairness`/`band` at **score time** (values move; history should not silently rewrite — store the scored snapshot).
- League tab: reverse-chrono list, A-side / B-side names, verdict, date. Empty state: “We’ll grade deals as this league trades.”
- Flag `league.trade_history` default **false**.
- Do not block session_init; score in the same daemon class as capture, or a cron.

**Done when:** a league with ≥1 `sleeper_trades` row shows a scored row; leagues with zero capture stay empty; flag off = no new route needed by clients.

#### E6 — Comps strip on the open card
**Who:** backend + clients. **Est:** 1.5d. **Depends:** E5.

- Given an open card, query **this league’s** scored history for same shape (1-for-1 / 2-for-1 / …) and overlapping value band (±15%). Return up to 3, newest first.
- UI: “2 similar deals in this league” → tap expands the E5 row.
- Zero matches: omit the strip. Do not fetch other leagues. Do not call RA.
- Flag: same `league.trade_history` (or a child `trade.comps_strip` default false if the EM wants to light the feed before the strip).

**Done when:** a 1-for-1 card in a league that has a scored 1-for-1 in-band shows the strip; a league with no history omits it.

---

## 6. Sequencing

```text
E1 copy          ─┐
E2 impact dark   ─┤ parallel, Wave 1
E3 diff sentence ─┘
        │
        ▼
E2 clients + E1 clients  (user-visible Wave 1)
        │
        ▼
E4 offer analyzer V1     (Wave 2; needs E1+E2)
        │
        ▼
E5 score history         (can start in parallel with Wave 1 — data is already there)
        │
        ▼
E6 comps strip
```

Do not block Wave 1 on E5. Do not block the landability challenger on any of this.

---

## 7. Flags and knobs

| Key | Default | Ticket | Kill |
|---|---|---|---|
| `trade.card_verdict` | **true** | E1 | false → today’s copy |
| `verdict_even_min_ratio` | 0.75 | E1 | set 0.95 to restore “even ≈ 5% band” |
| `verdict_lopsided_max_ratio` | 0.55 | E1 | — |
| `trade.impact_preview` | false | E2 | false → no `impact` key |
| `trade.diff_angles` | false | E3 | false → no `diff_highlights` |
| `offers.analyzer` | false | E4 | false → no analyzer routes/screens |
| `league.trade_history` | false | E5/E6 | false → no feed, no strip |
| `offers.inbox_auto` | false | — | stays false (N7) |
| `tiers.community_diff` | false | — | not flipped by this PRD |

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Impact job cost | Compute only on the served top-K, once per card, in the existing generation thread. Flag off is free. |
| “Lopsided — you get more” tanks like-rate on viewer-wins Arm B | That’s information. If it hurts, the product call is the challenger (stop generating those), not quieter copy. |
| Comps are sparse in quiet leagues | Omit the strip. Leave-empty is the finding. |
| Scoring history with today’s values rewrites the past | Snapshot at score time (E5). |
| Clients fork verdict math | Forbidden. Band comes from the server. Structural guard on copy strings (E1). |
| Scope creeps into generate | N1–N2. Reviewer rejects any diff in `_generate_trades_v2` gates. |

---

## 9. Acceptance (initiative)

Wave 1 accepted when E1 is on for TestFlight, E2+E3 can be lit per-flag, and a deck card in a boarded league shows verdict + impact + (if divergence) a named disagreement, without a generation-math change.

Wave 2 accepted when a user can reconstruct an inbound offer and see the same verdict+impact.

Wave 3 accepted when a league with captured trades shows a scored history and in-band cards show a comps strip.

Initiative is **not** accepted when we have a Tradabase clone or a VORP ranker.

---

## 10. References

- Research: RA Tradabase / intelligence; MDV 3-lens eval; KTC/DD even-band both-ways (finder, not this PRD).
- Live serializer: `trade_card_to_dict`, `_value_verdict_payload`.
- Capture already on: `market.trade_capture` → `sleeper_trades`.
- Generate identity: [landability-challenger/PRD.md](../landability-challenger/PRD.md).
