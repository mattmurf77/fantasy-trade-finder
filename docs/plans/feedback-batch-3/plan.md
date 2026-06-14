# Feedback Batch 3 — v1.2.0 TestFlight testing (ids 49–58)

*Source: `GET /api/feedback/admin` ids 49–58, all from mattmurf77 on app v1.2.0, 2026-06-11. First-hour testing of the build shipped this morning.*

## Split

**Bugs → PRD + code now** (this folder, subagent-built, validated in merge):

| # | Screen | One-liner | PRD |
|---|---|---|---|
| 49 | Bottom nav | Double ▾ cue (icon + label) — regression from FB-28 | [prd-49-double-arrow.md](prd-49-double-arrow.md) |
| 51, 52 | Rank stack | Back button on Rank sub-screens redirects to Trios / dead-clicks / greys out | [prd-51-52-rank-back-button.md](prd-51-52-rank-back-button.md) |
| 55 | Tiers | Reset button "does nothing"; intent (undo vs reset) unclear | [prd-55-tiers-reset.md](prd-55-tiers-reset.md) |
| 57 | Tiers | Scrolling fights the drag-activation gesture | [prd-57-tiers-scroll.md](prd-57-tiers-scroll.md) |

**Enhancements / polish → PRD only after research** (no code yet):

| # | Screen | One-liner |
|---|---|---|
| 50 | Trends | Page needs a 1–2 sentence "what am I looking at" explainer |
| 53 | Overall Ranks | Show positional rank (QB1, RB4) as the prominent value, not Elo |
| 54 | Overall Ranks | Elo separation feels too tight (~1 pt/rank); doesn't separate elite from depth — possible ranking-engine refinement |
| 56 | Tiers | Multiselect move is hard to follow; idea: tap-a-tier quick-move with hidden tier buttons in select mode |
| 58 | Tiers | Tiles too big — operator will share screenshots from a reference app |

## Honest note

**#49 is a regression I shipped this morning** (FB-28): I added the `Rank ▾` label on top of the icon chevron that already existed, doubling the cue. Fixed under this batch.

## Sequencing

1. Bug PRDs written → 2 code subagents (Group A: nav 49/51/52 = `TabNav.tsx`; Group B: Tiers 55/57 = `TiersScreen.tsx`). Disjoint files, run in parallel, I validate the combined diff + `tsc` before committing.
2. In parallel: 2 research subagents parse the competitor docs + external best-practices for the 5 enhancement/polish items.
3. Research returns → I write enhancement/polish PRDs (no code subagents yet).

## Risk flag

#57 touches the **same gesture layer** as the tiers drag the operator JUST confirmed working (ids 16/27/29/32/43). The fix must NOT regress drag activation — conservative tuning + on-device verification required.
