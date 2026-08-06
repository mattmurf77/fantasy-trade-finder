# Trade Impact & Rank Integrity — measurement plan

**Role:** an-data-architect + an-user-data · **Date:** 2026-08-05 · **Status:** plan (queries prototyped, attribution not yet built)
**Operator question:** *"Is the app actually causing trades? Is letting users rank actually worth anything? And whose rankings can we trust when we build a crowd consensus?"*

This is deliberately an **analytics/data exercise, not a dashboard feature** (operator directive). Outputs are queries + a periodic report, not tabs.

---

> **Read prod, not dev.** `data/trade_finder.db` holds only test-suite artifacts
> (every event there is from pytest). Real usage is in Render Postgres. Use
> `python3 -m backend.tools.prod_analytics --diagnose` (read-only, forced at the
> session level) or `--report <name>`. The §0 table below was surveyed against
> **dev** and understates reality — prod has 3,346 events / 30+ types / 16 users.

## 0. What the database can answer TODAY (surveyed 2026-08-05)

| Source | Rows | Answers |
|---|---|---|
| `member_rankings` (user_id, league_id, player_id, elo, format) | 2,441 | user's own valuation of each player — **the personalization signal** |
| `player_value_history` (consensus_elo, per player/format/date) | 1,369 / 685 players | the market baseline to compare against |
| `league_members.roster_data` | 56 | who owns whom → **ownership-aware bias** |
| `trade_decisions` (like/pass + give/receive ids) | 22 | which suggested trades a user *accepted in-app* |
| `trade_matches` (+ per-side decisions) | 9 | mutual matches and their dispositions |
| `sleeper_trades` (**already built**, `market.trade_capture`) | 0 (no synced league has traded yet) | **executed** Sleeper trades: adds/drops/picks/roster_ids/traded_at + raw |
| `user_events` | 1,789 | only 3 event types have ever fired; envelope columns 100% NULL |

**The critical find:** you worried we'd need roster snapshots or "a transactions feed." `backend/sleeper_trades_service.py` **already sweeps Sleeper's public transactions API** (legs 1–18, idempotent on `transaction_id`) and stores adds/drops/draft_picks/raw. The attribution loop is buildable now — it needs zero new capture, only the join.

---

## 1. Did the app cause the trade? (suggested → sent → executed)

Three funnels, increasingly hard, each worth measuring separately:

**A. In-app acceptance** *(computable today)*
`trades_generated` → cards viewed → `trade_proposed` (like) → `trade_ratified` (both sides) — already in the funnel report. Like-rate and mutual-match rate per user/league.

**B. Sent to Sleeper** *(needs one event)*
The `trade.send_in_sleeper` path exists but fires **no analytics event**. Add server-fired `sleeper_send_attempted` / `sleeper_send_succeeded` / `sleeper_send_failed` (props: `trade_id`, `league_id`, `player_ids`, `error_code`). These are named in the tracking plan but absent from `analytics_taxonomy.py` — a taxonomy addendum + ~5 lines in `sleeper_write.py`. **This is the single highest-value instrumentation gap.**

**C. Executed in the league (the real proof)** *(buildable now)*
Join FTF's suggestion to Sleeper's executed transaction:

```
match(suggested_trade, sleeper_trade):
  same league_id
  AND traded_at within [suggested_at, suggested_at + 14d]
  AND the two sides' player-id sets overlap by ≥ threshold
```
Three confidence tiers, because real trades get amended:
- **exact** — asset sets identical both directions
- **strong** — every FTF-suggested player appears on the correct side (extra assets added by the users)
- **weak** — ≥1 headline player moved in the suggested direction

Store as `trade_attributions(suggested_trade_id, transaction_id, tier, matched_at)` so the number is auditable and re-derivable, never recomputed ad hoc. **Report:** *attributed trades ÷ suggested trades* and *÷ liked trades* — the app's causal claim, stated at the tier level.

**Guard:** attribution ≠ causation. A trade can match by coincidence, especially for obvious deals. Report tiers separately and pair with the counterfactual below.

---

## 2. Is trade volume actually rising?

`sleeper_trades` carries `traded_at` for **every** trade in a synced league, including trades FTF never suggested — that's the control group, free.

- **League-level:** trades/week per league, pre- vs post-FTF-adoption (adoption date = first `league_synced`). Difference-in-differences against leagues in the DB that synced but never generated decks — an honest internal control.
- **User-level:** trades/season per user before vs after activation.
- **Seasonality is a confound** (dynasty trade volume spikes at rookie drafts and the deadline; `docs/business/context.md` §Market). Always compare like-for-like calendar windows or use the control leagues to absorb it.

**Sample-size reality:** with 7 leagues and 0 captured trades, this is a *2026-season* measurement. Build the pipeline now so the data accrues; don't expect a readout this month.

---

## 3. What is ranking actually worth? *(built — `rankquality` report)*

Per user: `mean_abs_delta` (avg |user Elo − consensus Elo|), `spearman_vs_consensus` (ordering agreement), `players_ranked`, and the ranking-surface mix.

**First real reading (2026-08-05):** the one non-test user has **958 players ranked, mean |Δ| = 160.7 Elo, ρ = 0.566**. That is a *large* personalization signal — their board is meaningfully, not cosmetically, different from consensus. Test users sit at ρ ≈ 0.93 (they barely diverge).

**The impact question this sets up:** do trades surfaced against a *personalized* board convert better than trades surfaced against consensus? That's an **experiment**, not an observation — the P3 engine can run it (engine layer, variant = personalized vs consensus pricing, primary metric = like-rate, PFO guardrails auto-attached). Correlational analysis alone will always be confounded by "users who rank more are more engaged."

---

## 4. Whose rankings can we trust? (consensus eligibility)

You couldn't name the signal; here it is. **Divergence is not the signal — asymmetric, ownership-correlated divergence is.**

A user with genuinely different opinions diverges from consensus *symmetrically*: some players up, some down, regardless of who owns them. A user gaming the system marks **their own roster up and everyone else's down**, because that's what manufactures favorable trades.

```
own_roster_bias = mean(Δ on players the user OWNS)
                − mean(Δ on players they DON'T own)          [Elo units]
```
Requires ≥5 owned and ≥5 non-owned ranked players; renders "—" otherwise. Ownership comes from `league_members.roster_data`.

**Triage (`integrity_flag`), deliberately conservative — "divergent" is never an accusation:**

| Flag | Rule | Meaning |
|---|---|---|
| `insufficient` | <25 players ranked | not enough board to judge |
| `review` | bias ≥100 Elo **and** ρ <0.5 — or bias ≥150 regardless | marks own roster up *and* orders unlike the market |
| `divergent` | ρ <0.2, bias normal | very different opinions, honestly held — **keep** |
| `ok` | otherwise | |

**First reading:** nobody is gaming. Real user bias = **−2.2 Elo** (essentially zero — honest divergence despite a large |Δ|); test users **−34 / −60** (they actually value their own players *below* consensus). The metric discriminates and doesn't false-positive on the biggest diverger.

**Corroborating signals to add before this gates anything real** (behavior is harder to fake than a board):
1. **Do they trade?** A user whose board manufactures great offers but who never sends one is optimizing the feed, not their team.
2. **Acceptance asymmetry** — their offers accepted by leaguemates vs their acceptance of others'. Gamers get declined a lot.
3. **Board volatility** — Elo churn on players *right before* a trade proposal (`elo_history` has per-player snapshots) is the sharpest tell: re-rating an asset immediately before pricing a deal.
4. **Rank-set entropy** — degenerate boards (everything at one Elo, or a step function) suggest gaming the unlock, not opinion.

**Design rule for the future crowd consensus:** never hard-exclude on one flag. **Weight** contributions — down-weight `review` users, cap any single user's influence per player, and require a minimum board depth to contribute at all. That's robust to both gaming and honest eccentricity, and it degrades gracefully as the population grows.

---

## Decisions needed

1. **Add the `sleeper_send_*` events** (taxonomy addendum + `sleeper_write.py`)? *Rec: yes* — without them, funnel B is permanently dark and "did they actually send it" is unanswerable.
2. **Build `trade_attributions` + the matcher** now, so the 2026 season accrues attributable data? *Rec: yes*, tiered as above.
3. **Confirm the integrity thresholds** (bias ≥100 Elo / ρ <0.5). Proposed from one real board + two synthetic ones — recalibrate once ≥30 real boards exist.
4. **Run the personalized-vs-consensus experiment** to convert §3 from correlation to causation? *Rec: yes*, once client capture is on.

## Handoffs

- `sleeper_send_*` instrumentation → an-data-architect (taxonomy) → eng-backend (`sleeper_write.py`).
- Attribution matcher + `trade_attributions` → eng-backend; readout → an-user-data.
- Personalized-vs-consensus experiment design → `/an-experiment`.
- Consensus weighting policy → eng-backend (ranking) with pm-technical; **do not** ship exclusion before the corroborating signals exist.
