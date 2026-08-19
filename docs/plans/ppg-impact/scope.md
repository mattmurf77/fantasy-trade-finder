# Feature Scope — Starter PPG delta on trade cards

**Date:** 2026-08-19
**Entry point:** direct ask (operator: “add a PPG valuation change for each trade suggestion… ideally through free sources”)
**Builder:** unassigned — EM tasks from [PRD.md](PRD.md)
**Operator sign-off on waivers:** **required before F1 merge** — unofficial Sleeper projections in production (PRD §8). §1 (b) for Wave F1–F2; F3 is user-visible and not waived.

Parent: [PRD.md](PRD.md). Does not change generation. Does not light `outlook.odds`.

---

## 0. What this builds

A cached player→PPG map (Sleeper unofficial weekly projections, nflverse last-season fallback) and a `ppg_impact` object on served trade cards: greedy starting-lineup PPG before/after for both sides.

What it is not: a ranker feature, a projection model, playoff odds, RosterAudit/FantasyPros, E2 dynasty-value ranks.

---

## 1. Analytics scope

- [x] **(b) Existing events cover F1–F3.** Stamp `ppg_impact` into the card blob / `deck_impressions.features_json` when the flag is on (same pattern as proposed E1 `verdict.band`). Like-rate × `you.delta` sign is the question; no new event name required for Wave 1.
- [ ] **(a)** none unless the EM wants `ppg_strip_shown` — not required.

## 2. Schema & flag scope

- New tables:
  - `player_ppg_snapshots` (date UTC, season, source, payload_json or normalized player_id/scoring/ppg/pos). Append-only. Migration required for F1.
  - No change to `sleeper_trades`.
- New flags:
  - `trade.ppg_cache` default **false** → true after first successful prod fetch.
  - `trade.ppg_impact` default **false** → lit after F3 TestFlight.
- Knobs: `ppg_min_coverage` default 0.80; `ppg_trailing_blend_weeks` default 4 (F1b).
- Env: none new. Do not overload `FTF_OUTLOOK_STRENGTH_SOURCE` for the card stamp; cache is shared, flags are separate so outlook can stay off.
- Rollback: both flags false. Last snapshot remains on disk, unused.

## 3. Evidence scope

- [x] **Unit tests:** rebuild mean map from committed `sleeper-projections-2026.json`; before/after delta on a fixture 1-for-1; omit when coverage < 0.80; flag-off omits key; nflverse fallback on a player missing from the Sleeper map (mocked).
- [x] **Code-walk:** stamp is after top-K, not per candidate; generate path does not fetch HTTP.
- [ ] **Structural guard (F3):** `mobile/tests/check-ppg-impact.js` — strip renders only if `ppg_impact` present; caption includes source; both you and them rows.
- [ ] **TestFlight:** PPR Sleeper league, one card with a starter swapped, both deltas visible; flag off hides strip; TEP league shows the “PPR (TEP not applied)” caption or omits per PRD §6.
- `testID`s: `trade-ppg-you`, `trade-ppg-them`, `trade-ppg-source`.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | F2 | card shape `ppg_impact` |
| `docs/data-dictionary.md` | F1 | `player_ppg_snapshots` |
| `docs/config-reference.md` | F1 | both flags + knobs |
| `docs/cross-client-invariants.md` | F3 | source caption strings; CC-BY nflverse |
| `docs/glossary.md` | merge | starter PPG vs dynasty value |
| `docs/architecture.md` | F1 | cron → cache → card stamp |
| ADR / DECISIONS.md | F1 merge | D-094 (proposed): Sleeper unofficial proj as v1 PPG feed |
| #5 top20 | merge | retract the “no season projections” non-goal |
| card-evidence PRD | this session | E2 remains value; this is points |
| `outlook.odds` / #169 | n/a | not lit; stub may be filled against the same cache |

## 5. Ship gate declaration

- **CI green:** `backend-tests` including new ppg tests; mobile typecheck + new check file when F3 ships.
- **TEST_LEDGER:** live fetch coverage number; fixture tests; omit-under-coverage.
- **TestFlight:** §3 checklist, operator-run, F3.
- Express lane: **no.**
- **Operator §8 yes** recorded in DECISIONS or TEST_LEDGER before `trade.ppg_cache` goes true in prod `features.json`.
- **Generation math:** any diff in `_generate_trades_v2` gates fails review.

## 6. Open operator decisions

See PRD §8. F1 code can be written dark; **prod fetch ON is blocked** on decision 1.
