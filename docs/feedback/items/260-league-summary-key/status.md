# #260 — League summary key: explain the "^3" numbers — status

Operator polish item: "Need something in the key to explain the numbers on the league summary (the ^3)."

**Status: fixed (mobile), 2026-08-08.** Express fix — legend-only, no scope block (no user-visible behavior change, only a clarifying legend entry for existing display).

## What the numbers are

The small colored numbers the operator saw (e.g. `▲3`) are the **rank-swing delta chips** on the League tab's chart (`mobile/src/screens/LeagueSummaryScreen.tsx`, `BarColumn`, shipped under #248). Each chart column can show a chip floating above its bar reading `▲N` or `▼N`:

- `delta = otherBasisRank - currentBasisRank` for that team, computed from the same tick/delta math as the dashed ghost-tick overlay.
- Only rendered when the two ranking bases (Consensus vs. My board) are both loaded, differ, and the swing is **≥2 rank spots** (`Math.abs(delta) >= 2`) — small swings render no chip at all.
- `▲N` (positive/ice-toned `semantic.pos`) = this team ranks **N spots better** under the basis currently sorting the chart than under the other basis.
- `▼N` (negative-toned `semantic.neg`) = this team ranks **N spots worse** under the currently-sorting basis than under the other basis.

The existing legend already explained the *dashed ice tick* (`{otherLabel} rank`, e.g. "consensus rank") but never explained the delta chip sitting above it — that gap is what the operator was reading as unexplained "^3"-style numbers (the `▲`/`▼` triangle glyph next to a small number).

## What shipped

- `mobile/src/screens/LeagueSummaryScreen.tsx` — added a legend entry next to the existing ghost-tick entry, gated the same way (`ticksOn`, matching the delta chip's own render condition): a neutral `▲▼N` glyph + label `"rank swing ≥2 vs {otherLabel}"` (lowercase `consensus` / `my board`, reusing the existing `otherLabel` string so wording stays in sync with the tick entry above it).
- New style `legendDeltaGlyph` (small mono glyph, `chalk.dim` — neutral, since the legend swatch can't be both pos/neg-tinted at once; the live chips keep their semantic color).
- Display itself is unchanged — this is a legend-only fix per the surgical-change guideline; the chip's `▲`/`▼` + number encoding was already clear once explained, no rendering ambiguity to fix.

## Gates

- `cd mobile && npx tsc --noEmit` — clean, 0 errors.
- `python3 -m pytest backend/tests -q` — **2041 passed, 1 skipped** (matches baseline exactly; no backend touched by this change).
- No Maestro delta — pure legend text/style addition to an existing screen, no new interactive surface or `testID`.

## Docs

- No `docs/glossary.md` entry — "rank swing" isn't a new domain term, it's inline legend copy for an existing #248 chip.
- No API/schema/architecture doc changes — mobile-only, presentational.
