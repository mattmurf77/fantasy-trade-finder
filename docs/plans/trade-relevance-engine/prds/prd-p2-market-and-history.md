# PRD: P2 — Market & History Data

> Phase P2 of the trade-relevance initiative ("Source the data we're leaving on
> the table"). Parents SIGNED OFF and binding:
> [enhancement-plan.md](../enhancement-plan.md) §Phase 2, [hld.md](../hld.md)
> (§2.4, §3.3, D7, §5.1, §5.2), [lld.md](../lld.md) (B12–B13, §4.9/4.10). This
> PRD states the product contract; the HLD/LLD own the how. Dual-agent
> authored; log in [../reconciliation-log.md](../reconciliation-log.md).

## 1. Summary

FTF stores executed trades with zero readers, discards waiver/FA rows from the
same fetch, never walks `previous_league_id` for pre-join history, and leaves
standings code dead behind a dark flag. P2 builds the readers, widens capture,
backfills history, syncs standings, and derives activity features — via the
cursor-based ingest machine under one global daily call budget. **Risk posture
up front:** the phase's headline promise ("day-zero personalization") is
arithmetically false at the budget and is replaced here by an honest SLO; its
flashiest signal (`price_level`) will be NULL for most leagues at real trade
volume, so the committed value is pacing/liquidity/behavioral features; and its
biggest item (fleet-wide backfill) is gated on a legal question (OQ-1) that
this PRD assigns an owner, a deadline, and a defined "no" branch.

## 2. Problem & Context

What users feel today:

- Suggestions push 3-for-2 packages in leagues that only ever do 1-for-1s;
  swipes burn on trades this league would never execute.
- Opponent ordering can't distinguish the manager who answers every offer from
  one who hasn't traded since 2023 — proposals go to people who never respond.
- A brand-new user's first deck is generic, while their league carries years of
  executed trades and waiver moves that reveal exactly how they and their
  leaguemates behave — stored unread, discarded at parse, or never fetched.
- A 10-1 deadline contender and a 2-9 September rebuilder get the same deck,
  because outlook inference sees only roster ages and pick counts.

The data to fix all four is already stored, already fetched-and-dropped, or one
budgeted API call away. Consumption beyond two bounded ordering multipliers is
P1/P3/P4 scope — P2 is the sourcing phase.

## 3. Goals & Non-Goals

**Goals**

| # | Goal | User-visible outcome |
|---|---|---|
| G1 | League market model (P2-1) | Deck pacing and shapes match how this league actually trades; market profile rows for ≥95% of leagues with ≥1 stored trade |
| G2 | Opponent behavioral profiles (P2-1) | Proposals ordered toward managers who demonstrably trade; consensus-basis cards grounded in revealed behavior |
| G3 | Waiver/FA capture (P2-2) | Need reads reflect real churn habits — waiver volume is 10–50× trade volume, the densest signal in the phase |
| G4 | Pre-join history prior (P2-3) | A newly linked user's early decks carry a real prior from their own league history, under the R2 SLO |
| G5 | Standings sync (P2-4) | Win-now pressure + points-for need urgency, with explicit partial-data semantics |
| G6 | Activity features (P2-5) | Ordering/timing reflects who is actually active in-app |

**Non-Goals (binding)**

- No MFL/ESPN transaction scraping (Sleeper proves value first).
- No cross-league joins of `manager_trade_profiles`; never keyed to a global
  person; server-internal (HLD §5.2).
- No UI naming of an individual's inferred tendencies — "this league pays up
  for RBs" may render; "Alex overpays for RBs" never; push copy never carries
  counterparty profiling.
- No intraday market refresh (trailing-window recency weight only); no
  FAAB-advice or waiver-recommendation product (`faab_aggression` is a model
  feature, full stop).
- No fleet-wide retroactive backfill until OQ-1 clears (new-links-only).
- No new serving-path model changes — P2 delivers data + profiles + two
  clamped composite multipliers behind `relevance.profiles`; ranker
  consumption is P1-2/P3.

## 4. Success Metrics

Instrumented on `/api/admin/analytics/relevance`; the primary is judged
**only** inside a flag-scoped experiment:

- **Primary:** served-but-never-viewed card rate **down** in a
  `relevance.profiles` 50% A/B (exposure-logged, 4-week window, other
  relevance flags frozen or stratified), with north star not down. **Pre/post
  comparisons are inadmissible** — P0-4/P0-5/P1 flags move in the same
  season. This is also the plan's stop signal: no reduction ⇒ P2-1 pacing
  rolls back.
- **Prior latency vs SLO (R2):** median ≤48h, p95 ≤7d from league link to
  backfilled prior, at sustained link volume ≤15 leagues/day; histogram
  published.
- **Coverage:** % leagues with market profiles; % managers above
  `confidence_n ≥ 5`; `price_level` NULL fraction **published** (expected
  high — so nobody oversells R1).
- **Consensus-card quality:** like rate on `basis="consensus"` cards up
  without flag-rate up (G2).

**Guardrails (hard):** Sleeper 429 rate ≈ 0 (sustained 429s ⇒ alert + budget
cut); daily `calls_used ≤ ingest.daily_budget`, observable; stuck-cursor count
visible and trending down; north star unchanged (minutes are a cost); quality
gates never relax.

## 5. Requirements

- **R1 (P2-1 readers).** Nightly `market_model` + `opponent_profiles` passes
  per LLD §4.10 formulas verbatim (nothing else defines them). Consumers:
  frozen `features_json` families + the two bounded multipliers behind
  `relevance.profiles`; fail-soft everywhere. **Small-n honesty is a
  requirement:** `price_level` NULL at `n_trades < 5` (floor may rise to 10
  after first real data — LLD §8.5); the committed year-one value is
  `trades_per_month`, `shape_histogram`, `positional_flow`, `trade_pace`,
  `waiver_churn`. Any P4 copy of the form "your league pays up for X" is
  outside P2's committed scope and ships only for leagues clearing the floor.
- **R2 (P2-3 SLO — replaces "day-zero").** Backfill arithmetic at the 2,000
  budget with ~50% reserved for live sweeps/standings: ~20 calls/season ×
  ≤3 seasons ≈ **60 calls per league** (3 `/league` + 3 `/rosters` + 54
  week-pages) ⇒ **~16 league backfills/day** on the ~1,000 reserved calls; the prior exists only after the
  next nightly profiles pass. The requirement is therefore an SLO: *prior
  available median ≤48h, p95 ≤7d post-link at ≤15 links/day.* Above that
  volume the queue stretches; nothing downstream may assume completeness
  (`confidence_n`/`seasons_observed` carry the truth). First decks before the
  prior serve composite + F9 unchanged — the deck must be correct on an empty
  profile DB, day one and forever.
- **R3 (P2-2 capture).** `parse_all_transactions` keeps completed waiver/FA
  rows (`kind` stamped) behind `market.transactions_all`; idempotent on
  `transaction_id`; flag off ⇒ byte-identical capture. **The 3-season raw
  prune (LLD §4.9.6) is a launch requirement** — P2-2+P2-3 roughly triple raw
  volume and nothing else deletes raws (T-33).
- **R4 (P2-3 backfill).** Chain walk ≤3 seasons via cursors; 404 =
  `done_empty` (an answer, not a failure); 5 failures = `stuck` + operator
  report; every `/league` fetch persists `waiver_budget` (the
  `faab_aggression` denominator dies silently without it). New-links-only
  until OQ-1; behind `market.history_backfill`.
- **R5 (P2-4 standings).** Weekly sync behind `market.standings_sync`,
  independent of `outlook.odds`. **Mid-season join semantics (an LLD §4.9
  amendment, logged — the signed-off text said only "one week per league per
  run," under which a week-15 link waits ~15 weekly runs for usable win-now
  features):** first sync of a league linked in week W backfills weeks 1..W
  (≤18 budgeted calls, W ≤ 18); thereafter one week/league/run. Features carry `weeks_observed`; win-now
  and need-urgency emit **neutral below 4 observed weeks** and whenever
  `pf_by_position` is NULL (not all payloads decompose — consumers must not
  require it). Retention season+1.
- **R6 (P2-5 activity).** Per LLD §4.10 (28d window, 14d half-life). Hard
  dependency on P0-1: if registration slips, the row ships with fields
  derivable from already-registered events only — stated in metadata, never
  zeros that look like measurements.
- **R7 (budget/safety).** All background ingestion shares D7's single budget
  (`ingest.daily_budget`, default 2,000; kill switch = 0 with nothing
  downstream breaking); backoff-and-park on 429/5xx; queue observability
  (backlog, budget consumed, projected days-to-drain) on the admin page.
- **R8 (integrity).** `batch_write` on the product engine; no transaction
  across a network call; applied multipliers frozen per HLD §2.3; Postgres
  tripwire telemetry live **before** `market.history_backfill` flips.
- **R9 (privacy/deletion, verified not asserted).** Disclosure line ships
  before capture widening (see §7); account deletion covers
  `manager_trade_profiles` + `user_activity_profiles` in `delete_user_data`
  and `_EXPORT_TABLES` (T-32); **T-35 (new id, correctly next after the LLD's
  T-34; propagated into lld.md §7 in the B12 diff so a future edit can't mint
  a colliding id): unlink league ⇒ zero `manager_trade_profiles` +
  `league_market_profiles` rows for that league, and its cursor rows deleted
  (the "parked" mechanism — the cursor enum has no such status; deletion
  stops capture, re-link recreates). Deletion/stop is conditioned on
  **last-unlink**: if two FTF users link the same Sleeper league, one user's
  unlink must not delete profiles the other still uses.** Ships in the B12
  diff.

## 6. Scope & Phasing

MVP = LLD B12 (ingest substrate: cursors, budget, capture widening, backfill
new-links, standings) → B13 (profile derivations + the two multipliers). The
OQ-1 "no" branch (see §8) re-scopes to already-held data — R1 readers over
existing `sleeper_trades`, R6 activity features — which still carries most of
the feature value at current league counts. **New-links-only-forever is still
worth building:** it covers 100% of future growth, where cold-start pain
concentrates; existing users already have swipe history.

## 7. Privacy, Trust & Disclosure

Product commitments (P2 profiles **non-users**):

- League-scoped only; never cross-league; platform ids only — no display
  names/avatars/message content; influence is ordering/features only.
- Deleted on league unlink (T-35); raws age out on the 3-season window;
  account deletion cascades (T-32).
- **Disclosure before capture:** the privacy policy gains a plain-language
  line ("FTF reads public league transaction history to model league
  markets") **before** `market.transactions_all` or `market.history_backfill`
  flips — a rollout-order constraint, same class as "surface filters before
  push rows." Operator signs wording + the 3-season retention number first.
- UA posture: the P2 scope block carries the operator's decision on the
  Chrome-spoofed sweep path (HLD OQ-3) before flags flip — silence is not a
  waiver.

## 8. Rollout, Dependencies & Open Questions

**Flag order (aligned with LLD §6.1 as amended — one authoritative order):**
`market.transactions_all` → `market.standings_sync` → **profile passes
(dark-derive)** → `market.history_backfill` (new links — profiles must already
be deriving, or early-linked leagues' priors would wait on a later flag and
break the R2 SLO) → `relevance.profiles` (consume last, A/B-scoped).
**LLD §6.1 amendment (logged):** `relevance.profiles` is decoupled from
`data.archetypes` and flips at the end of P2 gating the two P2 multipliers;
P3's wiring later extends the same flag with its own holdback — without this
amendment, P2's primary success metric would be unmeasurable until P3 ships.
Rollback: flag off + truncate derived tables; schema additive, never rolled
back. Bright line throughout — never express.

**Dependencies:** P2-5 ← P0-1; P2-3 ← P2-1/P2-2 parsing + ingest machine;
P2-4 independent; P3-2 consumes P2 outputs downstream.

**OQ-1 (the phase's hard external dependency), operationalized:**

- **Owner:** the operator, via the §11.3 agreement contact. **Ask within 14
  days of P2 build start**; log in OPEN_QUESTIONS.
- **No answer in 60 days ⇒ default:** new-links-only becomes permanent scope
  and the fleet ETA is removed from the roadmap rather than left "pending."
- **If "no":** mechanism, named (no per-class budget knob exists):
  `market.history_backfill` off + backfill cursor rows deleted within 24h;
  if the operator's read of "no" covers *all* automated public reads, the
  global `ingest.daily_budget` → 0 — stated explicitly because that also
  stops standings sync and the session-init sweep (same read class); the
  phase then re-scopes per §6.
- **If "yes":** fleet backfill of ~500 leagues ≈ 30k calls ≈ **a month of the
  entire budget** at 50% reservation — scheduled work with an operator-visible
  ETA from the cursor backlog, not a flag flip that "just happens." Postgres
  cutover decision (HLD ⛔ OQ-2) precedes it.

**Other open questions:** D7's 2,000/day default — start there or lower (HLD
OQ-6); price-level floor n=5 vs 10 after first real data; whether standings
public reads fall inside OQ-1's answer.
