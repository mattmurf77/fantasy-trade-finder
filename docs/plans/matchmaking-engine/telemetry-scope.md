# Feature Scope — Suggestion telemetry, ghost holdout & executed-trade tagging

<!-- Copied from docs/templates/feature-scope.md per root CLAUDE.md §Conventions
     "Feature gates". Matchmaking research program item 1 ("logging first —
     unlocks everything, retroactively impossible"); grounded in
     docs/research/matchmaking/round-2/03-sparse-data-learning-and-evaluation.md
     (§1.2 OPE logging contract, §1.3 ghost suggestions, §1.5 measured
     visibility) and round-1/02 §Transferable insight table. -->

**Date:** 2026-08-16
**Entry point:** direct ask (matchmaking research program, item 1)
**Builder:** build agent, branch `feat/suggestion-telemetry`
**Operator sign-off on waivers:** REQUIRED before ship — two waivers below (§1, §3)

---

## What this is

Everything OPE / incrementality measurement needs FTF to log **today**, built as a
delta on the existing F1 signal spine (`deck_impressions` / `deck_outcomes`), never
a parallel pipeline. Behind default-OFF flag **`suggestion.telemetry`**:

1. **Serve-time counterfactual columns** on `deck_impressions`: `policy_version`,
   `candidate_set_id` + `candidate_set_size` (joined to the new
   `deck_candidate_sets` table for full candidate-set reconstruction), and
   `assets_json` (first-class give/receive asset bundle — previously only
   recoverable by hash).
2. **Ghost-suggestion holdout**: deterministically (seeded per league × ISO week ×
   card identity) withhold ~1-in-N (default 10, `model_config
   ghost_holdout_one_in`) organic deck cards from display; log them fully with
   `is_ghost=1` at their would-have-been rank; they never appear in any published
   job snapshot (streaming or final).
3. **Executed-trade tagging**: when Sleeper league trades sync
   (`sleeper_trades_service`, flag `market.trade_capture`), each executed trade is
   matched against logged suggestions by the documented asset-set similarity rule
   and written to `suggestion_trade_links` (`was_recommended`, matched/ghost
   impression ids, overlap score). Always-on per-league ratio
   (executed-trades-that-were-suggested / all executed trades) via
   `GET /api/admin/suggestion-telemetry/ratio`.

Interaction-signal ladder (rendered → viewed → expanded → dismissed → saved →
sent-to-partner) **already exists** on the F1 spine and is reused untouched:
`deck_impressions` (rendered), `deck_card_viewed` ≥500ms front-of-deck →
`deck_outcomes.action='viewed'` (measured visibility — the deck UI equivalent of
FlatList viewability), `detail_expanded`/`calc_opened` engagement bits (expanded),
`pass`/`not_interested` (dismissed), `like` (saved), `propose` incl. MFL/ESPN
(sent-to-partner), `undo`, plus `dwell_ms` and serve-time `propensity`.

## 1. Analytics scope

- [x] **(b) Existing events cover it** — no new client events, no taxonomy change.
  The suggestion-interaction ladder is already specced field-by-field in
  `backend/analytics_taxonomy.py` and double-written to `deck_outcomes`:

  | Existing event / write | Fields | Question it answers |
  |---|---|---|
  | `deck_impressions` row (server, at job completion) | impression_id, user, league, job, card_index, trade_hash, features_json, propensity, base/final score, served_at (+ new telemetry columns) | rendered — the exposure denominator |
  | `deck_card_viewed` (client, ≥500ms front-of-deck; props `impression_id`, `trade_id`, `card_index`) → `deck_outcomes 'viewed'` | impression_id, dwell_ms | measured viewport visibility — card actually on screen, not just in the served deck |
  | `deck_outcomes 'like' / 'pass'` via `/api/trades/swipe` | impression_id, dwell_ms, detail_expanded, calc_opened | saved / dismissed (+ expanded as engagement bits) |
  | `deck_outcomes 'not_interested'` via `/api/trades/flag` | impression_id | strong negative |
  | `deck_outcomes 'propose'` via `/api/trades/propose[-mfl,-espn]` | impression_id | sent-to-partner |
  | `deck_outcomes 'undo'` via `swipe_undone` | impression_id | label correction |

- [x] **(c) partial WAIVER — no new analytics events for ghost/candidate-set/link
  writes because:** they are server-side counterfactual *training* data, not
  product analytics; they are queryable directly (`deck_impressions.is_ghost`,
  `deck_candidate_sets`, `suggestion_trade_links`) and firing user_events for
  never-rendered suggestions would poison funnel metrics with phantom exposures.
  → follow-through: `docs/data-dictionary.md` updated (new tables/columns).

## 2. Schema & flag scope

- New/changed tables or columns → `docs/data-dictionary.md` updated:
  - `deck_impressions` + 5 additive nullable columns (via `_migrate_db`, no
    backfill; NULL on all pre-telemetry rows): `is_ghost` INTEGER,
    `policy_version` VARCHAR, `candidate_set_id` VARCHAR, `candidate_set_size`
    INTEGER, `assets_json` TEXT.
  - New `deck_candidate_sets`: one row per generation job while the flag is on —
    candidate_set_id (uuid PK), deck_job_id, user_id, league_id, size, set_hash
    (sha256 over sorted member trade-hashes), candidates_json (full member list:
    trade_hash, partner, give, receive, base_score, in_deck), created_at.
  - New `suggestion_trade_links`: one row per executed Sleeper trade examined —
    transaction_id (unique), league_id, was_recommended, matched_impression_id,
    match_type, overlap_score, ghost_impression_id, ghost_match_type,
    ghost_overlap_score, traded_at, computed_at.
- New/changed feature flags: **`suggestion.telemetry`**, default **false** →
  `config/features.json` + `backend/feature_flags.py` FLAG_KEYS +
  `docs/config-reference.md`. Graduation criterion: operator flips ON after one
  TestFlight cycle confirms deck size/behavior unchanged with the flag off and a
  staging run shows ghost rows + candidate sets landing; ghost withholding only
  activates when `deck.signal_v2` is also ON (withholding without logging the
  counterfactual would be pure UX loss). Kill switch = flip back to false: no
  withholding, no new columns stamped, no candidate-set/link writes; rows already
  written are inert.
- New env vars / `model_config` keys → `docs/config-reference.md`:
  `ghost_holdout_one_in` (default 10; ≤0 disables ghosting — the deploy-free
  rollback lever *within* the flag), `suggestion_match_lookback_days` (default 14),
  `suggestion_match_min_overlap` (default 0.5). All in
  `trade_service._DEFAULT_CFG`, operator-tunable via `model_config` without deploy.

## 3. Test scope (mobile test platform)

- [x] **WAIVED (Maestro) because:** zero mobile code changes and zero user-visible
  behavior in this change. The client-side visibility instrumentation the research
  calls for (measured viewed, dwell, expand, dismiss/save/send) already shipped
  with F1 (`TradesScreen` `deck_card_viewed` timer + swipe/propose plumbing) and is
  exercised by the existing smoke set. Ghost withholding is server-side and, by
  design, unobservable in the UI (a withheld card simply isn't served; deck floor
  semantics unchanged — ghosting skips likes-you, wildcard, retest cards and
  pinned/targeted decks). Flag ships OFF, so TestFlight behavior is byte-identical.
  **Waiver needs operator sign-off before ship.**
- `testID`s added/renamed: none.
- **Capture delta:** none — no visual change.
- Smoke-suite impact: none of the 11 smoke flows change; trades flows unaffected
  with the flag off (and with it on, only ~1-in-10 organic cards are withheld
  server-side before serve).
- Backend: pytest added — `backend/tests/test_suggestion_telemetry.py`
  (logging round-trip incl. flag-off byte-identity, ghost determinism +
  never-rendered invariant, executed-trade matcher exact / near-miss / no-match /
  ghost cases, ratio computation, pick-token normalization).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | added `GET /api/admin/suggestion-telemetry/ratio` (admin/cron section) |
| `living-memory/LLD.md` | n/a | no convention shift — additive columns via the established `_migrate_db` seam, flag via the established FLAG_KEYS pattern, matcher rides the existing session-init background daemon |
| `docs/architecture.md` | n/a | no module re-wiring: `suggestion_telemetry.py` is a leaf module called from the two existing seams (trade job impression logging; post-`sync_league_trades` hook); data flow shape unchanged |
| `living-memory/HLD.md` | n/a | same as above — extends the existing F1 signal spine, no new client or major flow |
| `docs/cross-client-invariants.md` | n/a | no shared constants/enums/colors; all values are backend-only |
| `docs/glossary.md` | updated | ghost suggestion, was_recommended, candidate set, policy version |
| ADR or `DECISIONS.md` entry | in this scope block (§Decisions below); DECISIONS.md entry deferred to the shipping session | non-obvious choices recorded below |

## 5. Ship gate declaration

- **Simulator-gate tier:** proposed Tier 4 (none — CI only): backend-only change,
  flag ships OFF, zero mobile diff. Per the matrix this is the "no user-visible
  change, dark flag" class. **Operator confirms tier at ship** (this branch is not
  merged by the build agent).
- Evidence: backend suite run recorded in the final build report; TEST_LEDGER entry
  + `qa/sim-runs/last-sim-run.json` to be written by the shipping session at merge.
- Operator deviation from the matrix (if any) and why: none proposed.

---

## Decisions (non-obvious, recorded here for the shipping session)

- **D-scope-1 — extend the F1 spine, don't build a parallel suggestion log.** The
  mission's "suggestion log" and "interaction events" already exist as
  `deck_impressions`/`deck_outcomes` (TikTok-discovery F1). New counterfactual
  fields land as additive nullable columns on `deck_impressions`, stamped only
  while `suggestion.telemetry` is on, so flag-off insert rows stay byte-identical.
- **D-scope-2 — ghost identity is per (league, ISO week, trade_hash), not
  per-job-RNG.** `sha256("ghost|{league_id}|{iso_week}|{trade_hash}") % N == 0`.
  Deterministic across regenerations within the week, so a withheld trade cannot
  leak via deck refresh; rotates weekly so no trade is permanently invisible.
- **D-scope-3 — ghosts are exempted for:** likes-you cards (counterparty already
  acted; withholding breaks matching), wildcard/exploration cards (they ARE the
  exploration arm and carry their own propensity contract), fatigue-retest cards
  (F3 grants exactly one retest — swallowing it re-arms suppression forever), and
  pinned / opponent-targeted decks (explicit user intent; withholding is user harm,
  and those decks are excluded from likes-you/exploration for the same reason).
  Demo league excluded like every other telemetry write.
- **D-scope-4 — ghost rows keep would-have-been `card_index`; served rows keep
  true served positions.** Existing consumers (F2/F3/F7/F9) read `card_index` as
  served position; ghosts are additive rows that never receive outcomes, so
  outcome-joined reads ignore them naturally. Documented in the data dictionary.
- **D-scope-5 — similarity rule** (glossary + `suggestion_telemetry.py`): a
  suggestion matches an executed trade iff same unordered manager pair AND
  `served_at ≤ traded_at ≤ served_at + lookback` (14d default), compared as
  direction-aligned asset-token sets (players by id; owned picks normalized to
  `pick:{season}:r{round}:{original_roster_id}`; generic-ladder picks relax to
  round-only pairing). **exact** = both sides fully pair off; **partial** =
  matched/max(|suggested|,|executed|) ≥ 0.5 AND ≥1 asset matched on each side.
  Best candidate: exact > highest overlap > most recent. `was_recommended` counts
  only non-ghost (actually rendered) matches; the best ghost match is linked
  separately (`ghost_impression_id`) — that column IS the incrementality read.
  2-team trades only in v1; multi-team trades are linked with `match_type='none'`
  and stay in the ratio denominator.
- **D-scope-6 — candidate set = full post-gate pre-withhold deck + the untrimmed
  exploration over-generation pool.** That is the true action set the serving
  policy chose from at ordering time; anything upstream of the fairness/preference
  gates is not a legal action and doesn't belong in an OPE candidate set.
- **D-scope-7 — `policy_version`** is composed at serve time from the engine
  version + active ordering-layer flags + a code-side revision constant
  (`suggestion_telemetry.POLICY_REV`, bumped on any scoring/ordering change), so
  logged decks are attributable to a serving policy without a new config surface.
- **D-scope-8 — no list-length caps in the telemetry layer (operator direction,
  2026-08-16).** Mid-build the operator directed trade-gen-v2 toward exhaustive
  generation: no engine-baked top-k truncation; the full ranked survivor set is
  returnable with tier metadata (`endorsed` / `featured` / `browse`), list-length
  limits belonging to presentation config only (counterparty exposure caps stay —
  congestion control, not list length). This layer was audited against that and
  encodes **no truncation and no length assumptions**: impression logging iterates
  every card the engine emits; `deck_candidate_sets` scales with the emitted set
  (when trimming disappears, the pool contribution simply goes to zero and the
  candidate set equals the full survivor set — no code change needed);
  `card_index` remains "rank in the full ranked list"; the ghost holdout is a
  randomized counterfactual withholding, not a cap, and its ~1-in-N rate is
  independent of list length. When the tier field ships, it belongs in
  `features_json` (frozen at serve) like every other card attribute; ghost
  exemptions should then also exempt the single `endorsed` card per team-pair
  (same reasoning as likes-you — scarce, high-intent slots are not holdout
  material). That wiring lands with the trade-gen-v2 change, not here.
