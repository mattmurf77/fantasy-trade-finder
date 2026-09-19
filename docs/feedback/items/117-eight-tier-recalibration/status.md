# Status — #117 (Tiers) + #118 (QuickSetTiers)

**2026-07-12 — built, verified, unshipped (working tree on `trade-engine-v2`).**

Covers feedback #117 ("The tiers are still wrong… Tier 1: 4+ 1sts …
Tier 8: Waivers") and #118 (same, QuickSet walk). Operator decision:
"B + 8 tiers" — exact 8-tier ladder + consensus seed recalibration so
consensus assets reach the top tiers. See `plan.md` for the math,
before/after firsts readouts, and occupancy tables.

## Verification

- `python3 -m pytest backend/tests/` — **551 passed** (full suite).
  Pin changes, each itemized in plan.md: `test_tier_occupancy.py`
  rewritten for the 8-tier ladder + recalibrated seed map (bounds derived
  from the snapshot occupancy tables; new 3–4-firsts sanity test);
  `test_pick_anchor.py` scale section re-derived (default 4, γ = log4/logN,
  2_firsts → firsts_2); `test_seed_ui_test_db.py` seed-range pin 1800 →
  1927.5; `test_trio_variety.py`/`test_trio_boundary.py`/
  `test_elo_memoization.py` band tables + keys. Fairness-golden pins:
  **unchanged** (Elo-fixture-driven).
- `mobile: npx tsc --noEmit` — clean.
- `node --check` on extension/content.js, web/js/app.js + inline scripts of
  positional-tiers.html / profile.html — clean.
- QuickSet walk (#118) needs no key-level changes — it walks `TIERS` from
  `utils/tierBands.ts`, so it now runs 8 steps ("Tier N of 8") automatically.

## Surfaces migrated

Backend: tier_config.json · ranking_service (ORDERED_TIERS/docstrings) ·
data_loader (seed_elo_for_value) · trade_service (star-tax order + display
map, elo_to_value docstring) · og_image (order/labels/tints) · server.py
(anchor γ + default, /api/tier-config docstring) · database.py
(value-history rescale migration) · scripts/calibrate_elo_value docstring.
Mobile: shared/types · theme/colors · utils/tierBands · utils/playerValue ·
TierBadge · chalkline/Badge + StyleGuide · TiersScreen · QuickSetTiersScreen
(comment only) · ProfileScreen · PickAnchorScreen (default 4) · api/rankings
comments · TabNav rank-menu sub copy.
Web: positional-tiers.html (CSS/legend/rows/JS) · profile.html · js/app.js
(_eloToTierLabel) · style-guide.html · index/faq/ranking-method copy.
Extension: content.css (8 badge variants) · content.js labels · README.
Docs: cross-client-invariants (canonical table + banding + anchor keys) ·
design-system · components · glossary · data-dictionary · api-reference ·
runbook (migration + recalibration section) · mobile CLAUDE.md files.

## Watch items

- Personal `elo_history` trends span the recalibration unscaled (~30d
  distortion window; runbook).
- Deck-quality knobs (`min_side_surplus`, `waiver_slot_cost`,
  `mutual_gain_cap`) untouched — observe suggestion quality post-ship,
  retune via `model_config` if needed.
- `config/features.json` ↔ `flags/release.json` mirror is owned by the
  parallel ESPN agent (in flight during this build).
