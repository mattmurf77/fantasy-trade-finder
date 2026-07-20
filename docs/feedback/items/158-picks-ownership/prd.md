# PRD — Draft picks in the calculator & suggestions (#158 + #170)

**Feedback IDs:** #158 "Picks don't show up in calculator" (jonbonjourvi), #170 "Don't
think it includes picks ever in the suggestions."
**Operator framing:** "probably the most important item for any league. Need to solve for
Sleeper draft picks owned per team and hook in MFL owned picks per team."
**Status:** planning. PLAN ONLY — no code in this folder.
**Owns:** DATA layer (owned-picks resolution + store + sync), calculator inclusion,
suggestion-pool DATA inclusion. **Does NOT own:** trade-engine scoring/weighting math (the
trade-logic thread owns that — see §7 Engine-hook boundary).

---

## 1. Problem & current state (researched, not assumed)

Draft picks are dynasty's second currency, but the app treats them inconsistently:

1. **Generic picks already exist in the pool.** `build_universal_pool`
   (`backend/server.py` ~953) injects 12 generic pick pseudo-players
   (`generic_pick_{round}_{tier}`, rounds 1–4 × Early/Mid/Late) from `GENERIC_PICK_SEEDS`.
   These flow into `GET /api/trade/values`, so the calculator *can* show "Mid 1st Round
   Pick" etc. But they are **generic, league-agnostic** — not "your 2027 1st." A user
   looking for their actual owned picks does not find them → reads as "picks don't show up."

2. **Per-league owned picks are effectively dead.** `database.sync_draft_picks()` +
   `draft_picks_table` + `load_draft_picks()` exist and are *correct in shape*, but
   `sync_draft_picks(` is **never called** anywhere in the codebase (confirmed by grep —
   only the definition and an orphaned import at `server.py:95`). The sync ran historically
   (removed during the trade-engine-v2 rebuild). The live DB proves it: `draft_picks` holds
   302 rows for only 2 leagues, all `synced_at` = **2026-04-12** (3+ months stale). Any
   league synced after April has **zero** owned-pick rows. `GET /api/league/picks` therefore
   returns empty for current leagues.

3. **Picks are never candidates in generated trades (#170).** Trade generation
   (`trade_service.generate_trades`) enumerates each team's assets from `user_roster` /
   `member.roster` — **Sleeper player-id lists only**. No pick pseudo-asset is ever appended
   to a roster, so a pick can never appear on the give or receive side of a suggestion. The
   engine *can price* a `position=="PICK"` asset (`trade_service.dynasty_value` bridges
   `pick_value` into value space), but nothing puts one in the candidate pool.

4. **Two incompatible pick-value scales.** `database.compute_pick_value` returns mid-1st =
   **67.5** on a "0–100 round-tier" scale; the pool's generic ladder implies mid-1st
   pick_value = **(1650−1200)/6 = 75**. Both bridge to value space via `elo = 1200 + 6·pv`,
   but 67.5 → value ≈ 1690 while 75 → value ≈ 2117. The `dynasty_value` docstring *claims*
   they "price identically" — they do not (~20% gap), and `compute_pick_value` collapses
   Early/Mid/Late into one round midpoint. This must be reconciled before picks enter the
   calculator/engine, or a "2026 1st" will read as worth less than the generic "Mid 1st."

5. **Sleeper `traded_picks` uses roster_ids, and rounds default is wrong.** Probed live
   (`/v1/league/1312076055586050048/traded_picks`, 55 rows): each entry is
   `{round, season(str), roster_id, owner_id, previous_owner_id}` where **all three ids are
   integer roster_ids, not user_ids**. `roster_id` = original owner (pick identity),
   `owner_id` = current holder. The league's `settings.draft_rounds` = **4**, but
   `sync_draft_picks` defaults `rounds=3` → it would silently drop every 4th-round pick.

6. **MFL picks stored but unnormalized.** `leagues.platform_future_picks` (JSON list of
   `{franchise_id, year, round, original_owner}`, populated by `mfl_service.parse_bundle`)
   is stored raw (0 rows in the live DB today, but the write path exists and is tested).
   Nothing maps it into the `draft_picks` per-team owned structure.

7. **ESPN has no pick data.** The ESPN adapter is players-only; the unofficial v3 reads
   don't carry future draft-pick ownership. ESPN leagues get **no picks** — stated honestly.

## 2. Goals

- **G1 (#158):** A user's actual owned picks per league (e.g. "2027 1st", "2026 2nd
  (from Team X)") appear as selectable assets in the calculator, priced consistently with
  the pick-value tier ladder / consensus values.
- **G2 (#170):** Owned picks are eligible give/receive assets in generated trade
  suggestions — a suggestion can include "you send Player A + your 2027 2nd" or "you
  receive their 2026 1st."
- **G3:** Owned-pick ownership is resolved per team per league for the next ~3 draft years,
  correctly attributing traded picks (original-owner nuance).
- **G4:** Coverage is honest per platform: **Sleeper full, MFL full, ESPN none**, and each
  client communicates the ESPN gap rather than silently showing nothing.
- **G5:** Sync is revived and runs on the existing league-sync path (not a one-off).
- **G6:** All additive per project conventions; flag-gated; flag-off = byte-identical
  today's behavior.

## 3. Non-goals

- **Slot-level pick values** (1.01 vs 1.12). Sleeper `traded_picks` and MFL
  `futureDraftPicks` are **round-level** only; no draft-order/standings projection.
  Round + years-out is the granularity. (Slot precision is a later item; note it.)
- **Trade-engine scoring changes.** How much a pick *should* sway a suggestion's ranking,
  taxes, consolidation weighting — owned by the trade-logic thread. This PRD delivers the
  pick asset + its value into the candidate pool and names the engine hook.
- **Rookie draft board / #157 pick-denominated values** — ties noted (§8), not built here.
- **Writing pick trades back to Sleeper.** `propose_trade` already accepts a `draft_picks[]`
  passthrough; wiring the calculator's pick selections into that send is a follow-up, not
  required for #158/#170 (which are about *seeing* picks).

## 4. Per-platform coverage (the honest table)

| Platform | Pick source | Ownership resolution | Coverage |
|---|---|---|---|
| **Sleeper** | `GET /v1/league/<id>/traded_picks` + `/rosters` + league `settings.draft_rounds` | pristine grid (every team's own picks) overlaid with traded picks (roster_id keyed) | **Full** — next 3 seasons × all rounds |
| **MFL** | `leagues.platform_future_picks` (already stored from `futureDraftPicks`) | franchise-owned list normalized into the same store | **Full** — whatever MFL exports (owned list is explicit) |
| **ESPN** | none | n/a | **None** — leagues show a "picks unavailable for ESPN" note |

## 5. Functional requirements

### FR-1 — Revive & correct Sleeper owned-pick sync
- Call the (fixed) `sync_draft_picks` during league sync (see HLD §3 for placement).
- Pass `rounds = league settings.draft_rounds` (not hard-coded 3); `current_season` and
  `league_size` from league meta; keep `seasons_ahead = 3`.
- Fetch `traded_picks` server-side (public, unauthenticated) — do not depend on the client
  passing it.
- Resolve `roster_id → user_id → username` from the same rosters/users the session already
  loads. Store both the current owner and the original owner (already in the schema).

### FR-2 — Normalize MFL picks into the same store
- When a league is MFL-linked, read `leagues.platform_future_picks`, map
  `franchise_id → sleeper user_id` (via the existing MFL crosswalk / franchise→member map),
  and write rows into the **same normalized owned-picks structure** as Sleeper, so all
  downstream reads (calculator, suggestions, pick-share) are platform-agnostic.
- MFL `original_owner` (`originalPickFor`) populates the original-owner columns.

### FR-3 — ESPN gap is explicit
- ESPN leagues produce no owned-pick rows. `GET /api/league/picks` returns
  `{my_picks: [], all_picks: [], picks_supported: false}` for ESPN so clients can render a
  one-line "Draft picks aren't available for ESPN leagues" note instead of a blank.

### FR-4 — Reconcile pick value onto the ladder scale (blocking for FR-5/FR-6)
- League picks must price on the **same scale as the generic-pick ladder** so a "2026 1st"
  reads consistently with "Mid 1st Round Pick" and with player consensus values.
- Decision D1 (§7): a league pick of `(round, years_out)` maps to the generic ladder's
  **Mid** tier of that round, then a year-discount is applied **in value space** (mirroring
  the anchor wizard's value→elo round-trip), producing a pool-scale value. Store this as a
  new `pool_value` alongside the legacy `pick_value` (which stays for pick-share ratios).

### FR-5 — Picks in the calculator (#158)
- **Generic picks:** already in `/api/trade/values`; ensure the mobile picker surfaces them
  (they are pool players with `team == "PICK"`), and `/api/trade/evaluate` already values
  them (verified: pick ids resolve in `seed`). Low lift — mostly a picker/label affordance.
- **Owned (league) picks:** surfaced in the **In-league** calculator mode
  (`InLeagueCalculator`, Mode B) — league-scoped, where owned picks are meaningful. Source =
  enriched `GET /api/league/picks` (adds `pool_value` + display label + `owner_user_id`).
  The picker lists the caller's owned picks on Side A and the opponent's owned picks on Side
  B. `POST /api/trade/evaluate` must accept league-pick pseudo-ids on either side and value
  them by `pool_value` (with per-format scaling, §6).
- The public "Real values" mode stays league-agnostic: generic picks only (no ownership).

### FR-6 — Picks in suggestions (#170)
- During trade generation, inject each team's **owned** picks as pick pseudo-assets into
  that team's candidate asset list, registered in the engine's player dict with
  `position="PICK"` and the reconciled `pool_value`. The engine already prices PICK assets;
  this is purely **data inclusion**.
- The counterparty's owned picks likewise surface on the receive side.
- **Combinatorial guard (FR-6a):** picks multiply the per-team asset count (a 12-team
  Sleeper league adds up to `seasons_ahead × rounds` ≈ 12 picks per team). Cap the picks
  entering the candidate pool per team (proposed: top-N by `pool_value`, N≈6, config knob)
  so package enumeration cost stays bounded. Engine cost + cap detail in HLD §6.

### FR-7 — Format-scoped values
- Pick value is scoring-format-scoped (a 1st is worth more in SF). The generic ladder is a
  single Elo seed today; §6 specifies how the per-format value is derived so 1QB PPR and SF
  TEP calculators show format-appropriate pick values.

## 6. Value-scale reconciliation (the load-bearing detail)

Two scales exist and must be unified:

| | mid-1st | scale | consumer |
|---|---|---|---|
| `compute_pick_value` (stored `pick_value`) | 67.5 | "0–100 round-tier" | pick-**share** ratios (`_user_pick_share`, outlook seeds) — *internally consistent, leave as-is* |
| generic ladder (`GENERIC_PICK_SEEDS`) | pv 75 → elo 1650 → value ≈2117 | pool/engine value space | calculator + suggestions |

**Resolution:** introduce `pool_value` for each owned pick = the generic-ladder value of the
round's **Mid** tier, year-discounted in value space:

```
base_elo   = GENERIC_PICK_SEEDS[(round, "Mid")]          # e.g. 1650 for a 1st
base_value = elo_to_value(base_elo)
pool_value = base_value * (YEAR_DISCOUNT ** years_out)   # discount in VALUE space
```

- `years_out = 0` → exactly the generic Mid-tier twin (reconciled by construction).
- Format: recompute `base_value` from the format's pool (the generic pick seeds are the
  same Elo across formats today, but `elo_to_value` is format-independent; the SF premium
  for picks is a known gap — see Open Decision D3).
- `pick_value` (compute_pick_value) is **untouched** — pick-share math keeps working
  byte-for-byte.

This is the answer to task item 4's "reconcile with the value scale so a pick's value reads
consistently with the pick-value tier ladder."

## 7. Open decisions

- **D1 (round→tier default):** absent slot info, map every league round-N pick to the
  **Mid** tier of round N. Alternative: infer Early/Late from the *original owner's* current
  standings/roster strength (rebuilders' picks skew early). **Recommend Mid-default now**
  (honest, no projection); flag the standings-based refinement as a follow-up. *Owner: this
  thread + operator.*
- **D2 (owned-picks store):** extend `draft_picks_table` with `pool_value` + a `platform`
  column and keep it as the single normalized store (Sleeper + MFL write into it), **or** a
  new `owned_picks` table. **Recommend extend `draft_picks_table`** (additive columns; reuses
  `load_draft_picks`, `/api/league/picks`, pick-share). *Owner: eng-architect.*
- **D3 (SF pick premium):** picks arguably worth more in SF/2QB. Today the generic seed is
  format-agnostic. **Recommend ship format-agnostic pick value v1**, note the premium as a
  calibration follow-up. *Owner: trade-logic thread (values), operator.*
- **D4 (suggestion pick cap N):** proposed N=6 top picks per team by `pool_value`. Needs a
  perf check against `v3_pool_size`/`max_candidates`. *Owner: trade-logic thread (perf).*
- **D5 (engine weighting):** how strongly picks should influence ranking/consolidation/taxes
  — **explicitly deferred to the trade-logic thread.** This PRD stops at "the pick is a
  priced candidate."

## 8. Cross-cutting ties

- Picks are **per-league** (ownership differs by league) and their value is
  **league-format-scoped** — never cache a pick's ownership/value across leagues.
- **Identity crosswalk:** Sleeper picks are keyed by **roster_id** (→ user_id via the
  league's rosters); MFL picks by **franchise_id** (→ user_id via the MFL franchise→member
  map). The normalized store keys everything to **user_id** (owner) + original user_id, so
  downstream is platform-agnostic.
- **#157 (pick-denominated values):** the `pool_value`/ladder reconciliation here is the
  same ladder #157 leans on; keep the mapping in one place (`GENERIC_PICK_SEEDS` + a shared
  helper) so #157 and this item can't drift.

## 9. Test plan (Maestro + backend)

**Backend (pytest, offline fixtures — no live Sleeper):**
- `sync_draft_picks` with the probed `traded_picks` fixture (roster_id-keyed) → correct
  current-owner attribution incl. a pick traded twice (`previous_owner_id` ignored, final
  `owner_id` wins); 4-round league yields 4 rounds/season.
- `pool_value` reconciliation: a `(1, years_out=0)` league 1st equals the generic Mid-1st
  pool value within rounding; year-discount monotonic.
- MFL normalization: `platform_future_picks` fixture → same row shape as Sleeper; franchise
  original_owner preserved.
- ESPN league → `picks_supported: false`, zero rows.

**Maestro (mobile):**
- Calculator → In-league mode → open Side A picker → **owned picks listed** with values →
  add "2027 1st" → verdict updates (`calc.verdict`).
- Calculator → add a pick to each side → evaluate returns a numeric value for the pick (not
  dropped) — assert the pick id is not in `dropped_player_ids`.
- Suggestions: with `trade.picks_in_pool` flag on, generate trades in a Sleeper league and
  assert at least one card whose give or receive side contains a pick label.
- ESPN league → calculator shows the "picks unavailable for ESPN" note.
- Flag-off regression: `trade.picks_in_pool` off → no pick appears in suggestions; calculator
  behaves exactly as today.

## 10. Rollout / flags

- `picks.owned_sync` (default off) — gates reviving `sync_draft_picks` on the league-sync
  path + MFL normalization.
- `trade.picks_in_pool` (default off) — gates injecting owned picks into the suggestion
  candidate pool (#170).
- Calculator owned-pick display gated on `picks.owned_sync` (no data to show otherwise).
- Docs to update on build: `docs/data-dictionary.md` (draft_picks columns),
  `docs/api-reference.md` (`/api/league/picks`, `/api/trade/evaluate` pick ids),
  `docs/config-reference.md` (flags), `docs/cross-client-invariants.md` (pick ladder /
  pool_value formula), `docs/architecture.md` (sync placement).

## Operator decision — pick pricing (2026-07-18)
- **Rankable set:** Early/Mid/Late distinctions for 1sts AND 2nds are exposed for users to rank (these already exist in `GENERIC_PICK_SEEDS` — 1st Early/Mid/Late, 2nd Early/Mid/Late; surface them as rankable assets).
- **Owned picks in SUGGESTIONS:** every user-owned 1st and 2nd is valued at the **`(round, "Mid")`** seed at launch (we cannot yet resolve a pick's slot). A user's "2027 1st" → Mid 1st value in the candidate pool + calculator.
- **Future enhancement (gated on #169 league-outlook):** assign Early/Mid/Late to *owned* picks by projected standing/schedule, replacing the flat Mid default.
