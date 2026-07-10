# 1. Opponent outlook auto-classification

> Tier 1 · #1 · ENH · Effort M · Sources: OP / DD / DM

## Summary

The v2 engine's outlook blend (`trade.outlook_blend`, default ON) reweights now-vs-future value through `outlook_alpha_*` — but only for the logged-in user. Every opponent's side of every candidate trade is priced as if they were `not_sure` (α = 0.50): in `_generate_trades_v2` the blend is applied to `user_value` only, with the in-code comment "we don't know the opponent's outlook here (future: read their stored league preference)". The failure mode the operator flagged is direct: a rebuilder doesn't want an aging vet even if their personal rankings rate him, so the engine can call a vet-for-picks deal "mutual gain" when one side's window makes it a non-starter. Dynasty Daddy tiers every team (Contender / Frisky / Rebuilding); Dynasty Dealmaker markets "competitive window detection" as its core AI.

The fix is an inference function classifying every league team from observables FTF already has — roster age distribution against the existing `vet_age` (27) / `youth_age` (26) config, value concentration in 27+ players, pick-capital share from `draft_picks` (per-pick `pick_value` and `owner_user_id` are already synced), and league record/standing where available — then running each opponent's valuations through *their* inferred `outlook_alpha` instead of the 0.50 default. Self-declared outlook (the existing `league_preferences.team_outlook` row, when the opponent is also an FTF user) takes precedence over inference; the user's own team always uses their declared pref. This is the single highest-leverage change to suggestion quality: it makes "mutual gain" window-aware on both sides, reuses the alpha-blend machinery end-to-end, and produces the inferred labels that later power UI tier chips (#85) and per-league defaults (#8).

## PRD

### Problem & user story

The mutual-gain claim is only credible if "gain" is window-aware on both sides. Today `opp_surplus` is computed from the opponent's raw Elo-derived values (`_vo(pid) = elo_to_value(opp_elo[pid])`), unblended — equivalent to assuming every opponent is exactly half contending, half rebuilding.

*As a user*, I want suggested trades to target partners whose competitive window actually wants what I'm offering, so the deals I send don't get laughed out of league chat. *As a rebuilding opponent* (even one who never opens FTF), I should never be modeled as eager to receive a 29-year-old RB for picks.

### Goals / Non-goals

**Goals**

- Infer a contend/rebuild outlook label for every league team from synced data, no user action required.
- Apply each opponent's inferred (or declared) α to their side's valuation in candidate generation.
- Preserve declared outlook as authoritative for any team whose manager set one.
- Expose the inferred label + source on the trade payload so clients *can* render it later.

**Non-goals**

- Tier-chip UI and tier naming/personality — separate items (#85, #14).
- Per-league default for the *user's own* outlook — that is #8 (it consumes this classifier).
- Dynamic pick valuation conditioned on owner outlook — #15.
- Any learned/ML classifier; v1 is a transparent weighted-signal heuristic (fits the #20 transparency story).

### Functional requirements

1. **FR1** — New pure function `infer_team_outlook(roster_ids, players, pick_value_share, record) -> (outlook, score, signals)` in `backend/trade_service.py`, returning one of the existing enum strings (`championship | contender | not_sure | rebuilder | jets` — same strings validated by `_VALID_OUTLOOKS` in `backend/database.py`).
2. **FR2** — Signals, each normalized to a contend-vs-rebuild score: (a) share of roster dynasty value held by players aged ≥ `vet_age`; (b) youth share (≤ `youth_age`); (c) pick-capital share = team's total `pick_value` / league total (from `draft_picks`); (d) record/standing when available *(verify — see Open questions; not currently persisted)*. Weights are `model_config` keys so they're tunable without deploys.
3. **FR3** — In `_generate_trades_v2`, the opponent's value map (`_vo`, and the marginal `_mo` path when `trade.marginal_value` is ON) is multiplied by `outlook_blend_mult(pos, age, alpha_opp)` exactly mirroring the user-side blend at the top of the function.
4. **FR4** — Outlook resolution order per opponent: declared `league_preferences` row (if the member is an FTF user) → inferred → `not_sure`. Inference never overrides a declaration.
5. **FR5** — Inferred outlooks are computed once per generation job (per league), not per candidate.
6. **FR6** — Cards carry `match_context.opponent_outlook = {"value": str, "source": "declared"|"inferred"}` when the flag is ON.
7. **FR7** — Flag OFF ⇒ output byte-identical to today (opponents at `not_sure` 0.50).
8. **FR8** — Consensus fairness (`_fairness`, seed values + range overlap) stays *unblended* — fairness is a market-neutral gate by design; outlook affects surpluses only.

### UX notes

- **Web / mobile / extension:** no required UI in v1 — this ships as silent engine correctness. `match_context.opponent_outlook` is additive payload; clients ignore unknown keys. Tier chips on cards and league pages come with #85/#14.
- Narratives (`build_narrative`) *may* later reference the inferred window ("They're rebuilding; your 2027 1st fits"), but copy changes are out of scope here.

### Success metrics

- Share of cards offering a `vet_age`+ player TO an inferred rebuilder drops materially (measure via `GET /api/admin/engine-metrics` — extend per backlog #84).
- Like-rate on cards against inferred-rebuilder/contender opponents vs. baseline.
- When #8 ships its confirm prompt: classifier agreement rate with user self-declarations (ground truth).

### Acceptance criteria

- [ ] `infer_team_outlook` unit-tested across archetype fixtures (old+concentrated roster → contender/championship; young roster + pick hoard → rebuilder/jets; mixed → not_sure).
- [ ] With flag ON, a fixture league shows opponent-side surplus for an aging vet shrinking for a rebuilder opponent and growing for a contender, with user-side values unchanged.
- [ ] With flag OFF, golden-file card output identical to pre-change.
- [ ] Declared opponent preference overrides inference in resolution order test.
- [ ] `docs/config-reference.md` + `docs/glossary.md` updated (new config keys, "inferred outlook").

## HLD

### Components touched

- `backend/trade_service.py` — classifier + opponent-side blend in `_generate_trades_v2`; new `_DEFAULT_CFG` keys.
- `backend/trade_optimizer.py` — `generate_pair_trades_v3` computes opponent values internally; needs the resolved opponent α passed through *(verify exact plumbing — it receives `opponent: LeagueMember` and builds its own value maps)*.
- `backend/server.py` — `_run_trade_job` assembles per-opponent declared outlooks (batch `league_preferences` read) and pick-capital shares, passes them into `generate_trades`.
- `backend/database.py` — read-only consumers (`league_preferences`, `draft_picks`); plus optional standings columns (Open questions).

### Data flow

`POST /api/trades/generate` → `_kickoff_trade_job` → `_run_trade_job` loads league members + (new) per-member declared outlooks and pick shares → `TradeService.generate_trades(..., opponent_outlooks=...)` → `_generate_trades_v2` resolves α per opponent, blends `_vo`/`_mo` once per pair → surplus/fairness/composite as today → cards carry `opponent_outlook` in `match_context` → snapshot polled via `/api/trades/status`.

### Flags & config interplay

- **New flag:** `trade.outlook_infer` (dotted key in `config/features.json`; attr `trade_outlook_infer` auto-derived). Default **false**; flip after fixture verification.
- Requires `trade.outlook_blend` ON (it supplies `outlook_blend_mult`); if blend is OFF, infer is a no-op.
- Composes with `trade.marginal_value` (blend applied before marginal/replacement computation, same order as the user side) and `trade_engine.v3` (α forwarded to the optimizer).
- Kill switch: flag off → opponents revert to `not_sure` 0.50 instantly; no data migration to undo.

## LLD

### Engine changes

- New section in `backend/trade_service.py` adjacent to `outlook_alpha` / `outlook_blend_mult` / `_OUTLOOK_ALPHA_CFG_KEY`:
  - `infer_team_outlook(...)` — weighted sum of normalized signals; thresholds bucket the score into the five enum labels (extremes map to `championship` / `jets` sparingly).
  - Reuses `dynasty_value(player)` for value-share math (consensus-based, stable across users) and the existing `vet_age` / `youth_age` / `jets_age` cfg keys.
- `_generate_trades_v2`: after the user-side blend block (the `FLAGS.trade_outlook_blend` branch that multiplies `user_value` by `outlook_blend_mult`), resolve `alpha_opp` per member and fold the blend into `_vo` (cache per pair, mirroring `_vo_cache`) and into `_mo` inputs when `MARGINAL`.
- `_generate_consensus_for_pair` prices the opponent side from `seed_value` — apply the same per-opponent blend there so consensus-basis cards (unranked opponents) are window-aware too.
- New `_DEFAULT_CFG` keys (mirrored into `model_config` seed rows in `backend/database.py`): `infer_w_vet_share`, `infer_w_youth_share`, `infer_w_pick_share`, `infer_w_record`, `infer_contender_cut`, `infer_rebuilder_cut` (names final at implementation; cite in `docs/config-reference.md`).

### API changes

- No new routes. Additive payload only, flag-gated:

```json
"match_context": {
  "user_needs": ["RB"],
  "opponent_surplus": ["RB"],
  "opponent_outlook": {"value": "rebuilder", "source": "inferred"}
}
```

### Schema changes

- None required for v1 if the record signal is deferred. If included: add `wins`/`losses` (Integer, nullable) to `league_members` populated at roster sync from Sleeper `/v1/league/{id}/rosters` `settings` *(verify field availability)* — SQLAlchemy Core columns, SQLite + Postgres safe, plus `_migrate_db()` entry and `docs/data-dictionary.md` update.

### Client changes

- None required. Optional later: `mobile/src/components/TradeCard.tsx` and the web card renderer in `web/js/app.js` read `match_context.opponent_outlook` (with #85's naming).

### Rollout

- Flag `trade.outlook_infer`, default `false` in `config/features.json`. Enable locally → fixture league spot-check → prod ON. Kill switch = flag off (pure compute, no stored state).

### Open questions

1. **Record/standing signal:** standings are not persisted (`league_members` stores `roster_data` only) and are meaningless in the offseason. Ship v1 on age/value/pick signals and add record at season start?
2. **Declared-opponent trust:** should an opponent's *stale* declaration (e.g. `updated_at` > 6 months) fall back to inference? Proposed: declared always wins in v1; revisit with #8's re-confirm cadence.
3. **`championship`/`jets` extremes:** infer only the middle three labels and reserve the extremes for self-declaration? (Inference confidence rarely justifies α = 1.00 / 0.10.)
4. **v3 optimizer plumbing:** confirm where `generate_pair_trades_v3` derives opponent values and that the blend lands before sweetener/feasibility passes.

## As-built (2026-06-11)

Shipped behind `trade.outlook_infer` (default false). Deviations from the plan above, all deliberate:
- **Consensus-basis cards left market-neutral.** The plan suggested blending `_generate_consensus_for_pair` too; as built, the opponent blend is scoped to the two *divergence* paths (`_generate_for_pair_v2` `_vo` + `generate_pair_trades_v3` `_vo`), where the opponent has real rankings and the operator's failure mode (a *ranked* rebuilder offered a vet) actually bites. Consensus cards price both sides from market-neutral seed by design; injecting outlook there would change their fairness basis. Revisit if unranked-opponent windows matter.
- **Extremes not inferred.** `infer_team_outlook` returns only contender / not_sure / rebuilder; championship/jets stay self-declaration only (Open question 3 → resolved "yes").
- **Record signal deferred** (Open question 1) — v1 uses age-value-share + youth-share + pick-capital-share only; standings aren't persisted.
- **Inference runs in the engine, declared+pick-share assembled in server.** `infer_team_outlook` is a pure fn in `trade_service.py`; `server._run_trade_job` batch-loads declared `league_preferences` + computes pick shares from `draft_picks`, both only when the flag is on.
- Tests: `backend/tests/test_opponent_outlook_infer.py` (6 cases: archetypes, empty-roster guard, blend direction, flag-off identity, inferred stamp, declared override). Full suite 184 green.

## Dependencies & sequencing

- **Feeds:** #8 (per-league outlook defaults run this classifier on the user's own roster), #82 (first-run confirm = ground-truth collection), #85 (tier naming), #14 (league page chips), #15 (dynamic pick values keyed on owner outlook), #3 (window-aware swap candidates).
- **Depends on:** nothing in the top 20 — first in Wave 1 by design.
- **Watch interaction:** orthogonal to the fairness/`package_adj_gamma` tuning item (#10); outlook moves surpluses, not the fairness gate.
