# Feedback Batch 3 — v1.2.0 TestFlight testing (ids 49–58)

*Source: `GET /api/feedback/admin` ids 49–58, all from mattmurf77 on app v1.2.0, 2026-06-11. First-hour testing of the build shipped this morning.*

## Split

**Bugs → PRD + code — ✅ BUILT (commit d161b80, on branch; validated, awaiting on-device QA):**

| # | Screen | One-liner | PRD |
|---|---|---|---|
| 49 | Bottom nav | Double ▾ cue (icon + label) — regression from FB-28 | [prd-49](prd-49-double-arrow.md) |
| 51, 52 | Rank stack | Back button redirects to Trios / dead-clicks / greys out | [prd-51-52](prd-51-52-rank-back-button.md) |
| 55 | Tiers | Reset button "does nothing"; intent unclear | [prd-55](prd-55-tiers-reset.md) |
| 57 | Tiers | Scrolling fights the drag-activation gesture | [prd-57](prd-57-tiers-scroll.md) |

**Enhancements / polish → PRD written (research-backed), NO code yet:**

| # | Screen | One-liner | PRD |
|---|---|---|---|
| 53 | Overall Ranks | Positional rank (QB1/RB4) prominent, value secondary | [prd-53](prd-53-positional-rank-display.md) |
| 54 | Overall Ranks | Too-tight separation → display on 0–10k curve + tiers (Ph1); curve/uncertainty tuning (Ph2) | [prd-54](prd-54-value-separation.md) |
| 50 | Trends | Possessive title + ≤2-sentence explainer + self-describing sections | [prd-50](prd-50-trends-framing.md) |
| 56 | Tiers | Tap-a-tier bulk move in select mode + follow-the-move feedback | [prd-56](prd-56-tiers-quick-move.md) |
| 58 | Tiers | Compact one-line rows — **blocked on operator screenshots** | [prd-58](prd-58-tile-density.md) |

Research behind the enhancement PRDs: [research-synthesis.md](research-synthesis.md).

### Key cross-cutting recommendation
**#53 + #54 (Phase 1) + #58 are one coordinated "player value display" change:** show the **0–10,000 `elo_to_value`** number (not raw Elo) with **positional rank prominent** and **tiers + color**, then reflow the row to compact density. Build #53/#54-Ph1 together (shared display helper), then #58 after the operator's screenshots. #54 Phase 2 (re-tuning the actual rating separation via `ktc_k`/confidence ranges) is a separate model change needing offline validation — operator decision pending.

## Honest note

**#49 is a regression I shipped this morning** (FB-28): I added the `Rank ▾` label on top of the icon chevron that already existed, doubling the cue. Fixed under this batch.

## Sequencing

1. Bug PRDs written → 2 code subagents (Group A: nav 49/51/52 = `TabNav.tsx`; Group B: Tiers 55/57 = `TiersScreen.tsx`). Disjoint files, run in parallel, I validate the combined diff + `tsc` before committing.
2. In parallel: 2 research subagents parse the competitor docs + external best-practices for the 5 enhancement/polish items.
3. Research returns → I write enhancement/polish PRDs (no code subagents yet).

## Risk flag

#57 touches the **same gesture layer** as the tiers drag the operator JUST confirmed working (ids 16/27/29/32/43). The fix must NOT regress drag activation — conservative tuning + on-device verification required.
