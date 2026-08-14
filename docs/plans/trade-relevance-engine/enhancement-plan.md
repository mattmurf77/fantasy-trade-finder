# Enhancement Plan — interaction-driven trade relevance ("do what X does")

> **Purpose:** the buildable roadmap out of [audit-x-vs-ftf.md](audit-x-vs-ftf.md).
> Goal, in the operator's words: *use user interaction and information to produce and
> present the most relevant and enticing trade offers to the end user* — the way X's
> For You feed uses interaction history to rank posts. Covers data we already hold and
> data we have not yet sourced (pre-join trade/FA history, player archetypes, what each
> user values by position/age/archetype).
>
> Written 2026-08-14. Each item is gate-eligible work: anything user-visible or
> schema/API-touching goes through the four feature gates (scope block → Maestro delta
> → docs → sim run) at build time. Nothing here is built yet.

---

## Table of Contents
- [Objective and guardrails](#objective-and-guardrails)
- [The one-sentence strategy](#the-one-sentence-strategy)
- [Phase 0 — Close the loops we already paid for](#phase-0--close-the-loops-we-already-paid-for)
- [Phase 1 — Turn on and widen the learned ranker](#phase-1--turn-on-and-widen-the-learned-ranker)
- [Phase 2 — Source the data we're leaving on the table](#phase-2--source-the-data-were-leaving-on-the-table)
- [Phase 3 — Player archetypes and "what this user values"](#phase-3--player-archetypes-and-what-this-user-values)
- [Phase 4 — Presentation: relevant AND enticing](#phase-4--presentation-relevant-and-enticing)
- [Data-to-source summary](#data-to-source-summary)
- [Sequencing and dependencies](#sequencing-and-dependencies)
- [Measurement](#measurement)

---

## Objective and guardrails

**Objective:** every deck, notification, and match surface orders trades by a learned
estimate of *this user's* probability of acting on *this trade*, fed by everything we
know — their swipes and dwell, their board, their roster, their league's real market,
their pre-platform history, and what they demonstrably value in players.

**Guardrails (standing, from `docs/plans/tiktok-discovery/backlog.md`, reaffirmed by
the audit):** north star = proposals-sent + matches-accepted per weekly active; session
minutes are a cost; quality gates (user-gain, junk-filler, fairness, feasibility) never
relax for engagement; no fake-infinite inventory; no label hand-boosts. Dwell is a
feature, never a reward.

## The one-sentence strategy

FTF already built X's architecture in miniature (F1–F10); the plan is: **finish the
loop (P0), widen the objective (P1), feed it the data we already have access to but
throw away or never read (P2), then add the archetype/value-decomposition layer that
makes suggestions feel hand-picked (P3–P4).**

---

## Phase 0 — Close the loops we already paid for

*No new data, no new models. Highest ROI per line of code. Target: ~1–2 sessions each.*

| # | Item | X analogue | What to do | Where |
|---|---|---|---|---|
| P0-1 | **Register the 28 dropped client events** | every action is a sequence token | Add the mobile-emitted-but-unregistered names (`untouchable_toggled`, `trade_keep_side_tapped`, `deck_summary_viewed`, `trade_edit_in_calculator_tapped`, `suppression_undo_tapped`, `player_menu_opened`, `stud_tax_mode_changed`, …) to `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS`, per the tracking-plan taxonomy process. They're currently 200-OK'd and discarded. | `backend/analytics_taxonomy.py` |
| P0-2 | **Read the F8 gate and decide F6** | X retrains continuously; nothing promotes without eval | The nightly replay already runs inside `/api/cron/daily-tick` (`server.py:16600`) and has been accumulating results in `data/eval_runs/runs.jsonl`. What's missing is the *decision*: define the promotion criterion, read the accumulated results, and graduate or kill `deck.value_model` (NEXT.md has carried this since 2026-08-08). Note F6's nightly refit is itself flag-gated (`:16618`) — dark means frozen, so evaluate accordingly. | `data/eval_runs/runs.jsonl`, `backend/eval/`, flag flip |
| P0-3 | **Join proposal outcomes back to impressions** | X joins later actions to served features (3h cache → labels) | `trade_accepted` / `trade_declined` / `trade_responded` server events know the trade; thread `impression_id` (or `trade_hash` + recency match) through propose → match → disposition so `deck_outcomes` gains `accepted` / `declined_by_partner` rows. The single most business-real label we have is currently orphaned. | `server.py` propose/match/disposition paths, `deck_outcomes` |
| P0-4 | **Exposure-normalized flag aggregation** | agatha: blocks/reports *per favorite* → labels | Nightly job over `bad_trade_flags` ⋈ `deck_impressions`: flag-rate per exposure by archetype × shape × value-band (and by config lineage via snapshotted telemetry). High flag-rate classes get a global demotion multiplier and an operator report; today a flag only suppresses one card for one user. | new batch job; consume in `_order_deck` |
| P0-5 | **Near-duplicate package dedup** | vm-ranker DPP drops near-identical posts | At ordering, collapse cards sharing centerpiece + ≥N% package-value overlap, keep the highest-scored. Cheap set-overlap version of the DPP. | `server.py:_order_deck` |
| P0-6 | **`decided_by` gate observability** | first-drop-wins with recorded rule | Count gate kills per gate per job (already partially derivable); expose in the admin analytics so "why is this deck thin" is queryable. | `trade_service._consider`, `analytics_queries` |

Also in P0, hygiene the audit surfaced: fix the stale `analytics_queries.py:23` comment,
`architecture.md` request-lifecycle section, `feature_flags.py:422` F4 comment, and
`api-reference.md` "ships dark" header; update `docs/plans/tiktok-discovery/current-state.md`
banner to point at [ftf-current-state.md](ftf-current-state.md).

## Phase 1 — Turn on and widen the learned ranker

*The audit's central finding: F6 is X's architecture, built, dark. Make it live, then make it multi-head.*

**P1-1 — Promote F6 v1.** Run the P0-2 replay cadence until the specced win condition
holds; flip `deck.value_model` behind an experiment (`experiments.py` A/B, exposure
logged); watch north star + guardrail metrics. If replay says no-win, retrain on the
larger outcome set from P0-3 first.

**P1-2 — F6 v2: multi-head action prediction (the Phoenix pattern at FTF scale).**
Extend from 2 heads to the full action ladder we already log:

```
P(viewed→like), P(detail_expand), P(calc_open), P(propose | like),
P(accepted | proposed), P(declined | proposed),
P(flag), P(fast_pass) (<2s), P(undo)
score = Σ V_a · P(a)   — X-style explicit value blend, in config, inspectable
```

Value-vector principles from X: deep actions dwarf shallow ones (accepted ≫ propose ≫
calc_open ≫ like ≫ viewed — the "share-with-a-friend +20 vs favorite +0.5" ladder);
negatives get outsized magnitude (flag should cost ~50–100× a like's gain — X prices a
report at 468 favorites). Logistic/GBDT per head, Platt-calibrated like v1, trained on
`deck_impressions.features_json` ⋈ `deck_outcomes` with propensity correction. **Not a
transformer** — event volume doesn't support it (audit: "scale honesty").

**P1-3 — Push/pull eligibility split.** X holds unsolicited recommendations to ~26
extra drop-only rules. FTF equivalent: suggestions that reach the user via
push/notification inbox must clear a stricter bar than in-deck cards — e.g. score
percentile ≥ P75 for that user, zero fatigue debt, not a relaxed/consensus-basis card,
counterparty activity fresh. One config block, enforced where notification payloads are
assembled.

**P1-4 — Feature-flag the value blend as config**, mirroring
`home-mixer/params/param.rs`: the V-vector and head list live in `model_config` so
tuning is an ops change with an experiment, not a deploy (X tuned a headline feed
change in days as one param).

## Phase 2 — Source the data we're leaving on the table

*New readers for data we hold; new fetches for data one API call away.*

**P2-1 — Read `sleeper_trades` (stored since capture began, zero readers).** Build the
league market model the table was created for:

- **League liquidity:** trades/month, shape distribution, position flow — feeds pacing
  (don't push 3-for-2s in a league that only does 1-for-1s) and the bandit prior per league.
- **Per-opponent behavioral profile:** who actually trades, at what pace, which
  positions they've bought/sold, consolidation vs spread tendencies — a *revealed*
  counterpart to their (often missing) Elo board. Feeds opponent ordering
  (`partner_fit_score` gains a "actually trades" term) and `basis="consensus"` quality.
- **Market pricing signal:** realized package values vs consensus at execution time →
  per-position league price level (this league pays up for RBs), a divergence-style
  input that works even when opponents never rank.

**P2-2 — Stop discarding waiver/FA transactions.** `parse_trade_transactions` filters
to `type == "trade"`; the same fetch returns waiver/free-agent adds/drops. Store them
(new table or widen `sleeper_trades` with a `kind` column) → per-user FA habit profile:
positions churned, FAAB aggression, streaming vs hold patterns. A user who churns RBs
weekly values RB depth differently than their board admits.

**P2-3 — Pre-join history backfill (the cold-start prize).** Sleeper leagues chain via
`previous_league_id`; the transactions endpoints work on past seasons. Walk the chain
at league link time and backfill 1–3 seasons of executed trades + FA moves *predating
the user's FTF signup*. Products:

- **Day-zero personalization:** a trade-style prior (shapes, positions, aggression,
  age-lean of acquired players) for a user with zero swipes — X's cold-start answer is
  "history is the identity"; this is the only history a new user has.
- Same backfill enriches every P2-1 opponent profile for free.

**P2-4 — Standings/matchup ingestion, decoupled from `outlook.odds`.** A weekly sync of
standings + points-for (endpoint code exists in `backend/outlook/league_state.py`,
currently dead behind the flag) feeding two features: *win-now pressure* (contender at
the deadline ≠ September rebuilder — sharpens `infer_team_outlook`, which today sees
only roster ages and pick counts) and *need urgency* (points-for by position vs league
median beats roster-value gaps for "where am I actually bleeding").

**P2-5 — `user_events` as ranker features.** Once P0-1 registers the dropped events,
derive per-user recency-weighted aggregates (calculator sessions per week, board-edit
recency, screens dwelled, notification taps) as F6 v2 features — Phoenix-lite: the
*spirit* of the 1024-event sequence, expressed as features a logistic model can eat.

## Phase 3 — Player archetypes and "what this user values"

*The operator's examples live here: position-specific, age-specific, player-archetype
preferences (rushing QBs, pass-catching RBs, deep-threat vs possession WRs).*

**P3-1 — Player archetype layer (new external data).** Source per-player usage stats —
nflverse/nflfastR public data is free, licensed for this, and covers: rush share &
designed-run rate (QBs), target share, routes, aDOT, YAC, slot rate, red-zone share,
snap share, age/experience. Derive a small per-player archetype vector, e.g.:

```
QB:  rushing ↔ pocket        RB: pass-catching ↔ early-down grinder ↔ bellcow
WR:  deep threat ↔ possession ↔ slot           TE: move/receiving ↔ inline
plus: age-curve bucket (ascending / prime / cliff-adjacent), draft-capital pedigree
```

Ship as a nightly-refreshed `player_archetypes` table keyed to Sleeper IDs. This is a
data feature with no UI, but it changes schema — full gates apply.

**P3-2 — User value decomposition ("what you value").** Regress each user's board
deltas (their Elo vs consensus seed, which `member_rankings` already snapshots) onto
position + age + archetype features → an interpretable preference profile per user:
*+8% on rushing QBs, −5% on cliff-adjacent RBs, +250 Elo on pass-catching backs*.
Enriched by revealed behavior: archetypes of players they liked/targeted/acquired
(P2 history) vs passed/flagged/traded away. This is the X user-embedding, made
inspectable.

**P3-3 — Wire archetypes through the stack.** Taste vectors gain archetype dimensions
(today: positions, shapes, value bands); F6 v2 gains user-profile × card-archetype
interaction features; the F7 wildcard pool can audition archetypes, not just shapes;
`need_fit_score` can distinguish "needs a RB" from "needs a pass-catching RB for PPR."

**P3-4 — Roster-construction taste.** From current roster + acquisition history, infer
build philosophy (stars-and-scrubs vs depth; age-barbell; QB-premium hoarding) as
features for both sides of a trade — a consolidation card entices a stars-and-scrubs
builder and repels a depth builder at identical value.

## Phase 4 — Presentation: relevant AND enticing

*Same trades, presented so the user sees why they should care. All UI work: full gates,
Chalkline system, Maestro deltas.*

- **P4-1 — Personal hooks on cards.** Lead with the inferred value connection: "Adds
  the rushing QB profile you rate above market" / "Sells a cliff-adjacent RB while
  your league still pays up for RBs" (P3 profiles + P2 market model). The deck's
  `reasons[]` become personal, not just structural.
- **P4-2 — "Why am I seeing this" affordance.** One tap → ranking explanation from
  `features_json` + score components (X's Under-the-Hood pattern, card-scale). Builds
  the trust that makes users feed the loop more signal — and it's nearly free, the
  inputs are already frozen per impression.
- **P4-3 — Notification copy from the same hooks**, under the P1-3 stricter bar: a
  pushed trade must name its personal hook ("A rushing-QB deal just became possible in
  Dynasty Warriors") or it doesn't send.
- **P4-4 — "Your trading profile" surface (stretch).** Show the user their own P3-2
  decomposition, editable — corrections are free high-quality labels (declared taste),
  and it's a differentiating feature no competitor has.

---

## Data-to-source summary

| Data | Status today | Plan item |
|---|---|---|
| Deck interactions (view/dwell/like/pass/flag/propose) | ✅ captured (F1), partially modeled | P1-2 |
| Proposal accept/decline outcomes | logged, orphaned from impressions | P0-3 |
| 28 client event types (untouchable toggles, calc edits, …) | emitted, silently dropped | P0-1, P2-5 |
| Executed league trades | ✅ stored (`sleeper_trades`), zero readers | P2-1 |
| Waiver / free-agent history | fetched, discarded | P2-2 |
| Pre-join seasons (trades + FA via `previous_league_id`) | ❌ not sourced | P2-3 |
| Standings / matchups / points-for | code exists, flag-dead | P2-4 |
| Player usage stats → archetypes (nflverse) | ❌ not sourced | P3-1 |
| User board deltas vs consensus | ✅ stored, unread as a preference signal | P3-2 |
| MFL/ESPN transaction history | ❌ not sourced (no read surface) | later, after P2 proves value on Sleeper |

## Sequencing and dependencies

```
P0-1 ─┬─► P2-5 ─┐
P0-2 ─┼─► P1-1 ─┼─► P1-2 ─► P1-4
P0-3 ─┘         │
P0-4, P0-5, P0-6 (independent)      P1-3 (independent of P1-1/2)
P2-1 ─► P2-3 ─► P3-2 ─► P3-3 ─► P4-1..P4-4
P2-2 ─► P2-3    P3-1 ─► P3-2        P2-4 (independent)
```

Recommended order of attack: **P0-2 → P0-3 → P1-1** (the loop must cycle before
anything else compounds), then P2-1/P2-2/P2-3 (market + history data) in parallel with
P0-1/P0-4/P0-5, then P3, then P4. P1-2 lands whenever the P0-3 labels have volume.

## Measurement

- **Offline first:** every ranking change replays through `backend/eval/` (SNIPS, ESS
  gate) before any flag flips — that's what P0-2 exists for.
- **Online:** `experiments.py` A/B with exposure events; primary metric
  proposals-sent + matches-accepted per weekly active; guardrails: flag rate,
  suppression-undo rate, decline rate, first-session like rate (F9's metric), retention.
- **Honesty checks:** per-phase, one metric that would tell us to stop — e.g. P2-1
  market pacing should *reduce* served-but-never-viewed cards; P4-1 hooks should raise
  like-rate without raising flag-rate. If a phase moves minutes but not
  proposals/accepts, it violates the north star and gets rolled back.
