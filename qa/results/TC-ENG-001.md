# TC-ENG-001 — Trade-engine kill-switch regression (legacy / v2 / v3)

| Field | Value |
|---|---|
| **Status** | PASS (30/30 checks) |
| **Date executed** | 2026-06-11 |
| **Layer** | engine |
| **Component(s)** | `trade_service.py` legacy + `_generate_trades_v2`, `trade_optimizer.py::generate_pair_trades_v3`, engine dispatch at trade_service.py:1054/1299; session_init opponent-valuation branch (server.py:5197/5208) |
| **Requirement / doc ref** | docs/runbook.md kill-switch order; docs/architecture.md engine tiers; "v3 beats v2 on lower cards, not the top" |
| **Engine path & flags** | Three pinned instances via `FTF_FLAGS`: legacy (`v2=off`), v2 (`v2=on,v3=off`), v3 (`v2=on,v3=on`); `thompson_deck` + `deck_diversity` OFF in all for deterministic, comparable decks |

### Objective
Verify the engine kill-switch: each of legacy / v2 / v3 produces a valid,
non-empty deck (so flipping the flag can never strand users with a broken or
empty Trades tab), the flags actually route to different code, and enabling v3
does not regress the top of the v2 deck.

### Scope
- **In scope:** per-engine card-quality battery (non-empty, fairness ∈ [0,1],
  basis enum, no null ids, give-on-my-roster, receive-on-target-roster, unique
  ids); flag-routing proof via `/api/feature-flags`; legacy≠v2 deck divergence;
  v2→v3 top-card stability (v3 keeps v2's #1; top-10 overlap metric).
- **Out of scope:** exact composite-score math (unit-tested), three-team cycles
  (`trade.three_team` off), Tier-2 reorderings (pinned off for determinism),
  legacy↔v2 numeric comparison (legacy uses random opponent Elo by design —
  validity-checked only, not compared).

### Preconditions / Setup
- Scratch copy of `data/trade_finder.db`; three local Flask instances on ports
  5111–5113, each pinned via `FTF_FLAGS` JSON env (repo `config/features.json`
  untouched). Same user (`test_user_fp_1`) + league (`test_league_lakeview`).

### Inputs / Steps
Automated: [qa/eng/tc_eng_001.py](../eng/tc_eng_001.py). Per engine: boot →
assert reported flags → session_init → generate → poll to completion → validity
battery. Then cross-engine: legacy≠v2 divergence, v2→v3 top-card stability.

### Expected Result
All three engines: ≥1 valid card, full battery clean. Reported flags match the
pin. Legacy deck ≠ v2 deck. v2's #1 trade present in v3; ≥5/10 of v2 top-10
survive into v3.

### Actual Result
**30/30 PASS**, stable across 3 runs. Deck sizes: legacy 13, v2 33, v3 33.
v2's #1 trade present in v3 on every run; v2 top-10 → v3 overlap a deterministic
5/10. All roster-ownership checks clean on all three engines. Evidence:
`qa/eng/scratch/TC-ENG-001-run.json`.

### Outcome
**PASS** — kill-switch is safe in all three positions; v3 preserves v2's best
trade and diverges only in the mid/lower deck, matching the documented intent.

### Findings requiring attention
| ID | Severity | Finding | Evidence | Suggested action |
|---|---|---|---|---|
| — | — | No defects. | | |

### Observations & feedback (no change required)
- **Legacy deck is markedly smaller (13 vs 33).** Expected — legacy injects
  *random* opponent Elo for unranked members (server.py:5208) and uses the older
  pruning/scoring path, so fewer candidates clear the gates. Not a bug, but it
  means the kill-switch is a genuine UX downgrade (fewer, noisier trades), not a
  transparent fallback. Worth knowing before pulling it in an incident.
- **v2→v3 top-10 overlap is exactly 50%** (deterministic). v3's exact
  enumeration + sweeteners legitimately reshuffles the mid-deck; the #1 is
  stable. If product wants tighter top-of-deck continuity across an engine
  migration, that 50% is the number to watch — consider a documented threshold.
- **Determinism with ordering flags off is solid** — identical decks across
  runs for v2 and v3, which makes this a reliable regression gate. In production
  both Tier-2 ordering flags are ON, so the *served* order is intentionally
  stochastic (see TC-E2E-001 S3.11); this test isolates the scoring layer below
  that.
- The `FTF_FLAGS` env override is an excellent test seam — per-instance engine
  pinning with zero repo mutation. Reusable for any flag-matrix regression.
