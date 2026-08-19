# PRD — Starter PPG delta on every trade card

**Date:** 2026-08-19
**Status:** active, not built
**Owner (product):** operator. **Owner (delivery):** EM, tickets in [README.md](README.md)
**Scope:** [scope.md](scope.md)
**Sisters:** [card-evidence](../card-evidence/PRD.md) E2 (dynasty-value ranks — different unit); [landability-challenger](../landability-challenger/PRD.md) (generation — do not mix)

This is the document an EM hands to engineering. Source research is in §2. If a line here disagrees with Slack, this file wins until the operator amends it.

---

## 1. One-page brief

Every suggested trade should show **what happens to starting-lineup points per game** if the deal closes — you and them, before → after, signed delta.

Example, on the card:

```text
Starters (proj PPG)
  You   118.4 → 121.1   +2.7
  Them  109.2 → 106.8   −2.4
  Sleeper 2026 projections · PPR
```

That is MyDynastyValues’ “weekly point change” and Dynasty Daddy’s contender-mode, on a *suggested* card instead of a calculator the user has to fill in. It is **not** dynasty value (that’s card-evidence E2). A win-now manager swapping a 22-year-old for a 29-year-old RB can be even on Elo and +4 PPG this year. We currently cannot say that.

**Do not put PPG into generation.** Annotate the cards already cut, after top-K, same rule as E2.

**Source (v1, free):** Sleeper’s unofficial weekly projections endpoint — already fetched in a committed fixture, already summed by `starting_lineup_value()`, **never shipped**. Fallback when a player has no 2026 projection: last completed season’s actual PPG from **nflverse** (CC-BY 4.0, commercial OK with attribution). Do not use RosterAudit, FantasyPros, ESPN scrape, or SportsDataIO.

Operator call required before merge: we take on one more unofficial Sleeper endpoint (same class of dependency as the rest of Sleeper). Flag-off is the kill. See §8.

---

## 2. Source research (free-first)

Prior FTF work is binding: [`docs/feedback/items/169-outlook-league-summary/projection-source-research.md`](../../feedback/items/169-outlook-league-summary/projection-source-research.md) (2026-07-21, corrected 2026-08-09). Re-checked 2026-08-19.

| Source | What it is | Cost | License / ToS | Forward-looking? | Stack fit | Verdict |
|---|---|---|---|---|---|---|
| **Sleeper projections** `GET api.sleeper.app/projections/nfl/<season>/<week>` | Per-player weekly fantasy pts (Sportradar/Rotowire under the hood). Fixture captured 2026-08-09: 14 weeks × ~485 players, `pts_ppr` + pos. URL template in that fixture. | Free, no key | **Unofficial.** Public Sleeper API is documented “non-commercial”; this path is not in docs.sleeper.com at all. Can vanish. FTF already depends on unofficial Sleeper for leagues. | **Yes** — 2026 weeks exist in August | Excellent. Sleeper ids. Diagnostic script already maps week rows → mean pts → `starting_lineup_value`. | **v1 production feed.** Same decision #169 recommended. Ship behind a flag. |
| **nflverse / `nflreadpy` `load_player_stats`** | Historical weekly/season `fantasy_points_ppr` (and std / half). | Free | **CC-BY 4.0** (attribution required), package MIT, commercial OK | **No.** Last season’s actuals, or in-season trailing. | Python-native. Join via DynastyProcess `db_playerids` (`sleeper_id` ↔ gsis). | **v1 fallback + in-season trailing.** Not a projection. |
| **Sleeper matchup `points` / `players_points`** | Realized weekly scores for *this league* | Free (existing league pull) | Same Sleeper posture as today | No (actuals only, team or player-week once scored) | Already in `outlook/league_state.py` at **team** grain | Team-level trailing for outlook sims. Too coarse for a *player* PPG delta. Use nflverse or Sleeper player-week stats for player PPG. |
| **RosterAudit `/projections/ppg-rankings`** | Multi-year PPG | Free | Mandatory attribution; keys revoked if stripped | Yes | Easy | **Never shippable.** Prototype-only. |
| **FantasyPros API** | Consensus projections | Free proto; prod is paid + “may not build a competing product” | Landmine | Yes | Easy | **Avoid.** |
| **ESPN / Yahoo unofficial** | Weekly/season projections | Free | ToS-gray scrape | Yes | Medium | No advantage over Sleeper. Skip. |
| **FantasyNerds / SportsDataIO / FantasyData** | Projections APIs | Paid | Commercial contracts | Yes | Easy | Out of “free sources.” |
| **Own model on nflverse** | Build projections from stats | Free data, expensive people | CC-BY | Yes, if we build it | `OwnModelStrength` stub already registered | **v2.** Real modeling project, not this PRD. |

**Correction the 07-21 research already made and this PRD inherits:** nflverse does **not** ship forward projections. “Use nflverse for projections” means *build a model*. Do not write a ticket that `pip install nflreadpy` and expect 2026 PPG.

**What we already have in-repo (do not rebuild):**

- `backend.outlook.strength.starting_lineup_value` / `select_starting_lineup` — greedy best legal lineup given a `player_id → number` map and the league’s `roster_slots`. IDP *slots* are selected; DP *values* don’t price them (BUG-5). A points feed **does** price K/DL/LB/DB if the projection row exists — better than E2’s dynasty board.
- `SleeperProjectionsStrength` — **registered stub**. `scripts/outlook_strength_source_compare.py` is the working implementation, marked NEVER SHIPPED, living outside `backend/outlook/` on purpose.
- Fixture `backend/tests/fixtures/outlook-calibration/sleeper-projections-2026.json` (`_url_template` is the fetch contract).
- `outlook.odds` flag still **false**. This PRD does **not** light playoff odds. It reuses the lineup helper and, if we implement the stub, outlook can later consume the same cache.

---

## 3. Product definition

**PPG here = projected (or trailing) fantasy points of the greedy starting lineup, per week, in this league’s scoring family.**

Not: sum of the whole roster. Not: dynasty Elo converted through the unvalidated `outlook_mean_points` affine map. Not: rest-of-season totals (we can show `delta_ppg × remaining_weeks` as a footnote later; v1 is PPG).

For each served card, after top-K:

1. Build user roster and partner roster **before**.
2. Apply give/receive → **after**.
3. `ppg = starting_lineup_value(ids, ppg_map, pos, roster_slots)`.
4. Stamp:

```json
"ppg_impact": {
  "source": "sleeper_proj" | "nflverse_trailing" | "blend",
  "scoring": "ppr" | "half_ppr" | "std",
  "season": 2026,
  "you":  {"before": 118.4, "after": 121.1, "delta": 2.7},
  "them": {"before": 109.2, "after": 106.8, "delta": -2.4},
  "coverage": 0.96
}
```

`coverage` = share of *selected starters* (both teams, both snapshots) that had a real PPG number (not the 0.0 default). If coverage < 0.80, **omit the strip** rather than show a fake 0.

**Picks:** 0 PPG. A pick-only side is an honest “starters unchanged” on that axis. Do not invent a pick→points curve.

**Copy rules:**

- Always say **proj** when `source` is `sleeper_proj` (preseason and in-season remaining weeks).
- Say **trailing** when the number is last-N actuals.
- Never “+2.7 PPG” without whose lineup and which source.
- Partner delta is required. A you-only number reopens the viewer-wins problem on the presentment side.

**Not in v1:** rest-of-season win probability, playoff-odds delta, 1y/3y NPV, per-position PPG (E2 already does per-position *value*). One pair of lineup numbers.

---

## 4. Goals and non-goals

### Goals

- **G1.** Every served trade card *can* carry `ppg_impact` for you and them.
- **G2.** One cached player→PPG map per scoring family, refreshed on a cron, not per generate.
- **G3.** Scoring family follows the league: PPR / half / std. Superflex is a *slot* problem (`starting_lineup_value` already). TEP: see known gap in §8.
- **G4.** Flag-off payloads are byte-identical to today.
- **G5.** Same object on the calculator / E4 offer analyzer once those exist.

### Non-goals

- **N1.** Do not change generation, surplus, fairness, or `_tier_mult`.
- **N2.** Do not light `outlook.odds` or implement the Monte-Carlo.
- **N3.** Do not call RosterAudit or FantasyPros.
- **N4.** Do not build an own projection model (`OwnModelStrength`).
- **N5.** Do not scrape ESPN/Yahoo/CBS projection pages.
- **N6.** Do not put PPG in the ranker as a feature. Annotation only.
- **N7.** Do not show a number when coverage is bad. Omit.

---

## 5. Tickets

### F1 — Player PPG cache
**Who:** backend. **Est:** 1.5d. **Depends:** operator yes on unofficial Sleeper (§8).

- New module `backend/ppg_cache.py` (or `backend/outlook/ppg.py` if the EM wants one home with the stub).
- Daily (or on `hourly-tick` with a 24h idempotent guard, same pattern as value snapshots):
  1. Fetch Sleeper weekly projections for current NFL season, weeks 1–18, positions QB/RB/WR/TE/K/DL/LB/DB. URL = fixture `_url_template` with season substituted.
  2. Reduce to `player_id → {ppr, half, std, pos}` = mean of weeks that have a row. Drop weeks with null/0-for-everyone (pre-bye artifacts).
  3. Persist `player_ppg_weekly` (or a JSON blob keyed by `season` + `scoring`) — append-only snapshot by UTC date so we can replay.
- **Fallback per player:** if no 2026 projection, last completed season actual PPG from nflverse `load_player_stats(seasons=[Y-1], summary_level="player")` joined through `db_playerids.sleeper_id`. Tag those ids `source_player = "nflverse_trailing"` so the card’s mix can become `blend`.
- **In-season (week ≥ 3):** optional blend `w * trailing_actual + (1-w) * remaining_week_proj` with `w = min(completed_weeks/4, 1)`. Trailing actuals from nflverse current-season weekly or Sleeper player-week stats if we already ingest them. v1 may ship preseason-only (proj mean) and add blend as F1b.
- Cron failure: serve yesterday’s snapshot; never block `generate_trades`. If no snapshot at all, omit `ppg_impact` fleet-wide.
- Flag `trade.ppg_cache` default **false** until the first successful prod fetch is in TEST_LEDGER. Then ON. Kill = no fetch, cards omit the field.

**Done when:** a unit test rebuilds the mean map from the committed 2026 fixture; a dry-run cron against live Sleeper writes a snapshot with coverage ≥ 90% of the universal pool’s skill players; nflverse fallback is tested on a 2025-only id.

### F2 — Stamp `ppg_impact` on served cards
**Who:** backend. **Est:** 1d. **Depends:** F1.

- After top-K (same loop E2 will use; if E2 hasn’t merged, a sibling loop next to `match_context` stamping).
- Read league scoring family (already on the league row). Pick `ppr` / `half_ppr` / `std` from the cache.
- `you`/`them` before/after via `starting_lineup_value`.
- Omit when coverage < 0.80 or cache empty.
- Flag `trade.ppg_impact` default **false**. Requires cache ON. Payload omit-when-flag-off.
- Implement `SleeperProjectionsStrength.estimate` against the **same cache** so outlook is not a second fetch. Do not flip `outlook.odds`.

**Done when:** a fixture 1-for-1 that upgrades the user’s RB1 shows `you.delta > 0` and `them.delta` the opposite sign (or zero if they received a non-starter); flag off = no key; a pick-for-pick card can omit or show ~0.

### F3 — Card / calculator UI
**Who:** mobile + web. **Est:** 1.5d. **Depends:** F2.

- Two-row strip under E1 verdict (or under E2 if that shipped). Source + scoring as caption.
- Green/red on the signed delta. Don’t color the before number.
- `testID`s: `trade-ppg-you`, `trade-ppg-them`, `trade-ppg-source`.
- Calculator (`POST /api/trade/evaluate`): same object when the flag is on (evaluate already has rosters if league-scoped; if not, user-only).

**Done when:** TestFlight card shows both rows; flag off hides the strip; a coverage-fail card has no strip (not “0.0”).

---

## 6. Scoring and format

| League | Cache field | Notes |
|---|---|---|
| PPR | `pts_ppr` | Fixture already this |
| Half PPR | `pts_half_ppr` if present in raw; else `0.5*ppr + 0.5*std` if both exist; else omit half leagues rather than lie | Verify raw keys on first live fetch (fixture was slimmed to `pts_ppr` only) |
| Std | `pts_std` | Same |
| Superflex | slots, not points | `SUPER_FLEX` already in `_FLEX_ELIGIBLE` |
| TEP | **known gap** | Sleeper `pts_*` is not TE-premium. v1 ship PPR/half/std only; TEP leagues still show PPR PPG with caption “PPR (TEP not applied)”. v1b: if raw rows include `rec`, add `(tep-1)*rec` for TEs |
| IDP | priced if projection exists | Better than dynasty E2. Missing IDP row → 0 in that slot; coverage accounts for it |
| K | priced if projection exists | Same |

Do not invent a custom scorer from league `scoring_settings` in v1. That’s MDV’s whole product. Caption the family we actually used.

---

## 7. Sequencing vs other PRDs

```text
operator yes on Sleeper proj     (this PRD §8)
        │
        ▼
F1 cache (can start while E2 is in flight)
        │
        ▼
F2 stamp  ── shares the after-top-K loop with card-evidence E2 if both land
        │
        ▼
F3 clients
```

Independent of landability-challenger. Independent of E1 copy. Complements E2 (value ranks vs points). If only one presentment strip ships first, **this one is the win-now tell** E2 cannot provide.

#5’s old non-goal (“Contender Mode-style current-season vs dynasty toggle (needs season projections FTF doesn't have)”) is **this PRD**. Update that sentence at merge.

---

## 8. Operator decisions (block F1 merge, not F1 coding)

1. **Unofficial Sleeper projections in production?** Research #169 question 1, still open. Recommendation: **yes, flag-gated**, same posture as the rest of Sleeper. Alternative if no: nflverse-trailing-only, and the strip is “2025 actual PPG” until week 3 of 2026 — honest but weak for rookies and role-changes.
2. **Visible attribution** if nflverse fallback fires: CC-BY requires it. Recommendation: caption “Sleeper proj” / “2025 nflverse” / “blend (Sleeper + nflverse)” — three short strings, documented in cross-client-invariants.
3. TEP caption vs delay TEP leagues: recommendation **caption and ship**.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Sleeper kills the projections path | Flag off. Cache serves last snapshot until TTL, then omit strip. nflverse trailing still works in-season. |
| Preseason projections are noise | Caption “proj”. Do not call them actuals. Same honesty bar as outlook’s preseason ribbon. |
| Coverage holes (rookies, IDP) | Omit under 0.80. Don’t zero-fill a lineup and call it −8 PPG. |
| TEP lie | Caption. Don’t silently use PPR in a 1.5-PPR-TE league as if it were native. |
| Job cost | Cache is a cron. Stamp is O(top-K × greedy lineup), cheap, after cut. |
| Double fetch vs outlook | One cache. Stub `SleeperProjectionsStrength` reads it. |
| Commercial Sleeper ToS | Already an accepted operator posture for league reads. This endpoint is extra-undocumented — that’s why the flag exists. |

---

## 10. Acceptance

Initiative accepted when a TestFlight deck in a PPR Sleeper league shows both-side starter PPG deltas sourced from the cache, flag-off is byte-identical, and TEST_LEDGER records (a) live fetch coverage, (b) fixture unit tests, (c) the omit-under-0.80 case.

Not accepted: RA/FP keys in prod, PPG as a ranker feature, playoff-odds lighting, or a from-scratch projection model.

---

## 11. References

- #169 projection research (binding).
- Fixture + URL: `backend/tests/fixtures/outlook-calibration/sleeper-projections-2026.json`.
- Lineup math: `backend/outlook/strength.py` `starting_lineup_value`.
- Diagnostic (do not ship as-is): `scripts/outlook_strength_source_compare.py`.
- Card-evidence E2: dynasty value, not points.
- nflverse: https://nflreadpy.nflverse.com/ · CC-BY 4.0.
- Sleeper projections (unofficial): `https://api.sleeper.app/projections/nfl/<season>/<week>?season_type=regular&position[]=QB&…&order_by=pts_ppr`
