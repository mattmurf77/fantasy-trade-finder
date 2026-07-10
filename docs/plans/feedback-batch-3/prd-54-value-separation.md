# PRD — #54 Value separation: elite vs depth feels too tight

**Severity:** polish (with a real modeling question underneath) · **Screens:** Overall Ranks, Tiers, anywhere a value is shown · **Effort:** Phase 1 small (display); Phase 2 medium (curve/uncertainty)

## Problem
User on the manual-rank board: "It's concerning that Elo is only 1 point higher per rank decrease. This feels too tight and doesn't effectively separate top-tier players from lower-tier players. Is that because I have so many players in 'elite'? Wondering if even in-tier Elo needs refining."

Two real issues: (a) the **displayed** raw Elo spreads ~1 pt/rank so elite and depth look identical; (b) a deeper question about whether in-tier Elo separation is meaningful.

## Why (research)
Dynasty values are deliberately **exponential** — a value-5000 player ≈ 26% of a value-9999 player (~4 ≈ 1 elite). A ~1-pt-per-rank **linear** spread destroys that. FTF already has `elo_to_value` (exponential), so **displaying that instead of raw Elo restores the cliff with zero math change.** Perceptual guidance (Cleveland–McGill / NN/g): encode value with position-on-scale + length + tiers; color alone can't carry fine separation — when levels exceed a channel's resolution, aggregate into tiers. CAUTION (top20 #16): at low matchup counts the Elo separation is partly **noise** — confidence ranges may be more honest than fake-precise gaps. [research-synthesis.md #54]

## Root cause in our code
The manual-reorder path (`ranking_service.apply_reorder`) spreads Elo **linearly** between pool max/min (min 100 spread), so adjacent ranks differ by ~`spread/N` — tiny when N is large. Tier bands (`tier_config.json`) are also relatively narrow. And we display raw Elo. So the complaint is real on all three fronts.

## Phased plan

**Phase 1 — Display fix (cheap, ship first; merges with #53):**
- Show the **0–10,000 `elo_to_value`** number instead of raw Elo everywhere a value is user-facing. The exponential mapping makes elite-vs-depth gaps read as hundreds/thousands of points.
- Lean on **tiers + color** (reuse `analyze_roster_strengths` bins / `tier_config.json`) for the perceptual cliff between bands.
- This likely resolves the user's surface complaint without touching the ranking engine.

**Phase 2 — Modeling (only if Phase 1 isn't enough; bigger, test offline first):**
- Tune the value-curve steepness via the `ktc_k` / `elo_value_k` family (backlog #40), optionally league-size-aware (DTC pattern: bump elite in 10-team, weight depth in 16-team).
- Consider **confidence ranges** (top20 #16) on under-sampled players instead of fake-precise gaps — shows "5,800–6,400" until enough comparisons accumulate. Directly answers "is the separation real?"
- Re-examine `apply_reorder`'s linear spread and the "stuffed elite tier" effect (the user's own hypothesis) — a fuller elite tier compresses everyone below.

## Acceptance criteria
**Phase 1:** user-facing values render on the 0–10k scale; elite vs depth visibly separated; tiers/color reinforce. Verify on device that a top player and a depth player look clearly different.
**Phase 2 (if pursued):** offline replay shows the retuned curve doesn't regress trade-engine quality (use the existing replay harness); confidence ranges appear only for under-sampled players.

## Files (anticipated)
- Phase 1: `mobile/src/utils/` value-format helper (shared with #53), the rank/tier screens.
- Phase 2: `backend/ranking_service.py` (apply_reorder spread), `tier_config.json`, `model_config` (`elo_value_k`/`ktc_k`), the trade-engine replay script.

## Dependencies
Phase 1 is the same display helper as #53 — build together. Phase 2 is its own initiative; don't start without offline validation (it touches the live ranking + trade math).

## Open question for operator
Phase 1 (display on 0–10k) is almost certainly enough for the surface complaint. Confirm whether you also want Phase 2 (actually re-tuning how separated the underlying ratings are) — that's a model change with A/B implications, not just polish.
