# 15. Pick capital dashboard + dynamic pick values
> Tier 1 · #15 · NEW · Effort L · Sources: GM

## Summary

DynastyGM's pick treatment is the benchmark: a dedicated Draft Picks card per team with an inventory summary header (`(20: 9 1st, 4 2nd, 4 3rd, 3 4th)` + total value + league rank `29,988 (1/12)`), individually valued picks, original-owner annotation on traded picks (`2027 Mid 1st (twilson2320)`), and the footnote *"Pick proj using Contender rank and in-season performance"* — i.e. future-pick values conditioned on the original owner's projected finish. FTF already syncs the full pick grid: `sync_draft_picks` (`backend/database.py`) generates every (season, round, roster) pick for 3 rounds × current+3 seasons, overlays Sleeper's traded picks, tracks `original_user_id`/`original_username`/`is_traded`, and stores a `pick_value`. `GET /api/league/picks` serves it. But nothing renders it, and the valuation is static: `compute_pick_value` is a flat per-round midpoint (round 1 = 67.5 base) × league-size scale × 0.85/year-out discount — blind to who owns the pick.

Two halves. **(a) Dashboard:** a pick-capital view per team — inventory summary, individual pick values, total + league rank, original-owner tracking — as a section of the power-rankings drill-down (#14) and the league page. **(b) Engine:** dynamic future-pick valuation conditioned on the *original owner's* projected finish from #1's outlook classifier — a rebuilder's 2027 1st projects early (worth more); a contender's projects late (worth less). This materially improves every suggestion involving picks, which in dynasty is most of the interesting ones. A prerequisite discovered in code: FTF currently has **two pick-valuation systems on different scales** (see Open questions) — this plan reconciles them.

## PRD

### Problem & user story
As a dynasty manager, picks are half my tradable wealth, but FTF shows me nothing about them and prices a rebuilder's 2027 1st identically to a contender's. I want to see every team's pick capital at a glance and trust that suggested trades price future picks the way the market does — by whose pick it originally was.

### Goals / Non-goals
**Goals**
- Per-team pick inventory dashboard: summary string, per-pick values, total value + league rank, traded-pick provenance.
- Dynamic pick valuation: round × projected-slot-band (early/mid/late) × year discount, slot band inferred from the original owner's outlook (#1).
- One pick-value scale consistent with the player value space (`elo_to_value` / `dynasty_value`, 0–10000).

**Non-goals**
- No in-season performance signal in v1 (DynastyGM's footnote includes it; FTF starts with outlook-classifier rank only).
- No draft-day live tooling (#54/#55 build on this later).
- No slot-exact projections (1.02 vs 1.03); band granularity (early/mid/late) only — matches the universal pool's existing Early/Mid/Late pick assets.

### Functional requirements
- FR1: Dashboard data per team: `summary` ("20: 9 1st, 4 2nd, 4 3rd, 3 4th"), picks sorted season→round→value (the `load_draft_picks` ordering), each with `season, round, value, is_traded, original_username`, plus `total_value` and `league_rank`.
- FR2: Traded picks always display original owner: "2027 Mid 1st (via twilson2320)" — provenance is already in `draft_picks.original_username`.
- FR3: Dynamic valuation: `value = slot_band_base(round, band) * league_size_scale * year_discount^years_out`, where `band` for a future pick = f(original owner's classified outlook): rebuilder/jets → early, not_sure/unclassified → mid, contender/championship → late. Current-season picks with known slots keep slot-derived band (verify whether Sleeper exposes assigned slots for the current draft in the synced data).
- FR4: Slot-band bases live in `model_config` (new keys, see LLD) on the **player value scale**, seeded from the universal pool's pick-asset seed Elo via `elo_to_value` so a "2026 Early 1st" prices identically whether it appears as a rankable asset or a league pick.
- FR5: Engine consumption: wherever the engine values a pick (`dynasty_value` PICK branch reads `player.pick_value`), it must read the dynamic value. Flag-gated; flag OFF preserves current behavior bit-for-bit.
- FR6: Classifier unavailability degrades to `mid` band (today's behavior, rescaled) — never blocks sync.
- FR7: Dashboard exposes the valuation basis ("projected from {username}'s outlook: Rebuilder") — transparency feeds #20.

### UX notes
- **Web:** pick section inside `web/league-rankings.html` team drill-down (the DynastyGM placement) plus a "Pick Capital" league-wide table view: teams ranked by total pick value. Collapsible card header copies the benchmark format.
- **Mobile:** same section in `LeagueRankingsScreen.tsx` drill-down; a compact inventory chip ("9× 1st") on team rows.
- Footnote on every pick value: "Projected using team outlook" — honesty pattern lifted from DynastyGM.
- Picks the user holds get highlighted rows (existing `/api/league/picks` already splits `my_picks`).

### Success metrics
- % of trade suggestions involving ≥1 pick that get a right-swipe, before vs after dynamic valuation (flag A/B) — the engine half's whole point.
- Pick dashboard viewed in ≥25% of power-rankings sessions.
- Zero regressions in suggestion latency (valuation precomputed at sync, not per-candidate).

### Acceptance criteria
- [ ] Dashboard totals and ranks correct on a fixture league with traded picks.
- [ ] A rebuilder's 2027 1st values strictly above a contender's 2027 1st, both above their 2028 equivalents (discount).
- [ ] Pick values and player values share one scale: a mid-1st lands near the seed value of the universal "Mid 1st" pick asset (verify exact seed Elo).
- [ ] Flag OFF: `compute_pick_value` output unchanged; engine output unchanged (snapshot test on a fixture league).
- [ ] Re-sync is idempotent (existing `uq_draft_pick_id` guarantee preserved).
- [ ] `docs/data-dictionary.md` (new columns), `docs/api-reference.md`, `docs/config-reference.md` (new keys + flag) updated; ADR for the scale reconciliation.

## HLD

### Components touched
`backend/database.py` (`compute_pick_value` successor, `sync_draft_picks`, schema), `backend/trade_service.py` (`dynasty_value` PICK branch unchanged in signature; reads the new stored value), new classifier hook from #1, `backend/server.py` (route), `web/league-rankings.html`, `mobile/src/screens/LeagueRankingsScreen.tsx`.

### Data flow
League sync → `sync_draft_picks` builds grid + overlays trades → for each pick, look up original owner's outlook (from #1's classifier output; cached per league) → compute `pick_value_dynamic` → upsert. Dashboard route reads `draft_picks` and aggregates. Engine: pick assets reaching trade math carry the dynamic value (verify the path by which league picks enter candidate pools today — rosters are player-ID lists; pick assets exist in the universal pool as rankable Early/Mid/Late items from `build_universal_pool`, and `dynasty_value` handles `position == "PICK"`; whether real league picks are currently tradable by the v2 generator needs confirmation and is itself a gap this feature should close or explicitly defer).

### Flags & config interplay
- New flag `trade.dynamic_pick_values` (engine half) and `league.pick_dashboard` (UI half) — independent rollout; dashboard can ship first showing static values.
- New `model_config` keys: `pick_base_r{1..4}_{early,mid,late}` (12 keys, player-scale), `pick_year_discount` (default 0.85, replacing the `_PICK_YEAR_DISCOUNT` constant), `pick_league_size_clamp` retained behavior.
- Depends on #1's classifier output format (proposal: per-league `{user_id: outlook}` map, persisted — #1 owns the storage decision).

## LLD

### Engine/backend changes
- `backend/database.py`: `compute_pick_value_dynamic(round_, season, current_season, league_size, band)` alongside the legacy function; `sync_draft_picks` gains an optional `outlooks: dict[str, str] | None` parameter and writes both `pick_value` (legacy) and `pick_value_dynamic` + `projected_band`.
- Re-valuation trigger: outlooks change between syncs → a lightweight `revalue_league_picks(league_id, outlooks)` that updates the dynamic columns without rebuilding the grid; call it from #1's classification pass.
- `backend/trade_service.py`: `dynasty_value` PICK branch reads `pick_value_dynamic` when `FLAGS.trade_dynamic_pick_values` and the attribute is set, else `pick_value`. (Keep the read on the player object — no new DB hits in the hot path.)

### API changes
- `GET /api/league/pick-capital?league_id=...`:
```json
{
  "league_id": "12345",
  "teams": [{
    "user_id": "u1", "username": "bkey5",
    "summary": "20: 9 1st, 4 2nd, 4 3rd, 3 4th",
    "total_value": 29988, "league_rank": 1,
    "picks": [{
      "pick_id": "12345_2027_1_3", "season": 2027, "round": 1,
      "value": 5835, "band": "early", "is_traded": true,
      "original_username": "twilson2320",
      "basis": "projected from twilson2320's outlook: rebuilder"
    }]
  }]
}
```
- `/api/league/picks` unchanged (existing consumers); add `pick_value_dynamic`/`projected_band` fields to its rows.

### Schema changes
SQLAlchemy Core, SQLite+Postgres safe (additive columns, nullable):
```python
# draft_picks_table additions
Column("pick_value_dynamic", Float),    # outlook-conditioned value, player scale
Column("projected_band",     String),   # 'early' | 'mid' | 'late'
Column("valued_at",          String),   # ISO timestamp of last (re)valuation
```
Migration: additive `ALTER TABLE ... ADD COLUMN` per the project's existing additive-column pattern (verify how prior column additions were applied — e.g. `users` activity columns).

### Client changes
- `web/league-rankings.html`: Pick Capital section + drill-down group; `web/js/app.js` untouched unless chips added to league cards.
- `mobile/src/screens/LeagueRankingsScreen.tsx`: pick group card.

### Rollout (flag name proposal, default state)
`league.pick_dashboard` (false) → ship dashboard with static values rescaled to player scale (display-only conversion until reconciliation lands). `trade.dynamic_pick_values` (false) → flip after engine snapshot A/B on the operator's leagues; this changes live suggestion output, so treat like the v2/v3 flag flips (dark → operator QA → on).

### Open questions
1. **Scale bug/ambiguity (found during this plan):** `trade_service.dynasty_value` docstring claims `player.pick_value` is "already on a 0-10000 scale," but `compute_pick_value` produces ~67.5 for a mid-1st (with a 1000 fallback when the attribute is missing). If league pick assets ever reach v2 math today, mid-1sts are priced near zero. Confirm actual runtime behavior and whether the in-memory pick objects used by the engine carry `compute_pick_value` output or universal-pool seed values. This reconciliation is FR4's reason to exist and should be fixed even if the rest of #15 slips.
   - **RESOLVED 2026-06-13 (scale bug confirmed + fixed):** Two scales, exactly as suspected. (a) `compute_pick_value` (`database.py`) → `draft_picks.pick_value` on a **0–100 round-tier scale** (mid-1st = 67.5, league-size scaled, 0.85^yrs discount). (b) The universal pool's *generic* picks (`server.py build_universal_pool`) carry a different `pick_value = (seed_elo − 1200)/6` (mid-1st → pv 75 from Elo 1650), reverse-engineered so `dynasty_value` would lift it correctly — but `dynasty_value` returned `pick_value` **raw**, so even generic picks were under-lifted and any DB pick (67.5) priced as bench scrap next to players in the thousands. **Fix:** `dynasty_value` PICK branch now bridges via `elo_to_value(1200 + 6·pick_value)` (the inverse of the generic-pick calibration), so a league pick and its universal-pool twin price identically; missing `pick_value` → neutral 1000.0 (preserves the old fallback magnitude). Regression test: `backend/tests/test_dynasty_value_pick_scale.py`. `database.py`/`compute_pick_value` and `draft_picks.pick_value` are **unchanged** — the producer scale stays 0–100; only the consumer was wrong. Data-dictionary updated to document the scale. **NOTE:** this corrects the *transform*; FR4 (seeding slot-band bases on the player scale so the dynamic valuation is right) still stands.
2. Do real league picks currently enter v2 candidate pools at all (rosters are player-ID lists)? If not, "engine consumption" means: picks become roster assets in the generator — a larger change; scope it explicitly with #3/#54.
   - **RESOLVED 2026-06-13: No.** v2 candidate pools come straight from `league.members[*].roster`, which are Sleeper **player-ID lists only** (`_generate_trades_v2`, `server.py session/init`). `draft_picks` rows are loaded solely for the `/api/league/picks` dashboard read — they are never injected into `self._players` or any roster, so `dynasty_value`'s PICK branch is currently reached only by the *generic* universal-pool pseudo-picks (when a user ranks them), never by real league picks. So the scale fix above is correct-but-latent for league picks today; making league picks tradable is the larger generator change to scope with #3/#54 (this plan's "engine consumption" half). The fix is still worth landing now: it removes the standing bug for generic picks and unblocks #14/#15 building on a single scale.
3. Outlook of the *current* owner matters for who wants the pick; original owner determines its value. Does #1's classifier output persist per league member, and where? (#1 plan owns this; coordinate.)
4. 2028+ picks: DynastyGM values far-future picks at 0/NR; FTF's 0.85^2 discount keeps them meaningful. Keep the discount (recommended) or floor them?

## Dependencies & sequencing
- **Hard dependency:** #1 (outlook classifier) for the dynamic half; dashboard half ships independently.
- **Coordinate with:** #14 (dashboard renders inside the power-rankings drill-down; agree on pick scale before #14 puts picks in the stacked bars), #20 (the pick-valuation rule gets a transparency card once dynamic values ship).
- **Feeds:** #54 (draft-day pick-trade suggestions), #55 (rookie draft hub), #3 (swap builder must offer picks as swap candidates eventually).
- Wave 3 per backlog sequencing; the scale reconciliation (open question 1) should be triaged immediately as a possible standing engine bug.
