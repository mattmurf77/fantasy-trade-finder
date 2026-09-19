# #218/#219 — Trade-Finding Hub fits above the fold

**Status: built (worktree branch, pending merge) — 2026-08-01**

Operator ask: "There is a very small scroll on this page… reduce the margins
slightly to make it fit on screen without scroll."

Approved mock (verbatim, "No further edits needed. This works."):
`mockups/polish-lab-2026-08/hub-fit-to-screen.html`. Pure density pass on
`mobile/src/screens/TradeFinderHubScreen.tsx` — nothing deleted, nothing
reordered, all testIDs intact. The `ScrollView` stays as a Dynamic-Type /
small-device safety net; in the nominal layout it no longer scrolls.

## Spacing changes (mock → code)

| Element | Before | After | Source |
|---|---|---|---|
| Screen padding | `space.lg` (16) | `space.md` (12) | token |
| Stack gap | `space.md` (12) | `space.sm` (8) | token |
| DNA panel padding | `space.md` (12) | `10` | literal — no 4-pt token between sm 8 / md 12 |
| DNA panel inner gap | `space.sm` (8) | `6` | literal — no token between xs 4 / sm 8 |
| Chasing/Shopping labels | stacked above chips (`marginTop: space.xs`) | inline beside chips, 64pt label column | `64` literal — no token |
| Section label top margin | `space.sm` (8) | none | removed; stack gap separates it |
| Mode-card padding | `space.md` (12) all sides | vertical `9` / horizontal `space.md` (12) | `9` literal — no token |
| Icon well | 40×40 | 34×34 | literal (was literal) |
| Icon glyph | 22 | 20 | literal prop |

Mock bullet #2 (LeaguePill → compact variant, −17pt) is **moot**: the #223
header build already removed the "Trading in" pill row from this screen
entirely (−63pt row − 12pt gap = −75pt), which the mock itself anticipated
("If the #223 header-league-switcher ships, this row disappears entirely").

## Measured budget arithmetic (iPhone 15 Pro class, 393×852pt)

Viewport for hub content
= 852 − 59 (top safe inset) − **52 (TopBar, 44→52 post-#223)** − 49 (tab bar)
− 34 (bottom inset) = **658pt**.

Content column, nominal state (1-line outlook row, one chip row per DNA
group, 1-line card bodies; heights from Chalkline `type` lineHeights +
paddings + 1pt borders):

| Block | Pre-#223 | Post-#223, pre-#218 | After #218 |
|---|---|---|---|
| Screen padding (top+bottom) | 32 | 32 | 24 |
| "Find a Trade" title | 26 | 26 | 26 |
| LeaguePill row | 63 | — | — |
| Trade DNA panel | 197 | 197 | 135 |
| Section label | 22 | 22 | 14 |
| 4 mode cards | 4×67 = 268 | 268 | 4×61 = 244 |
| Stack gaps | 7×12 = 84 | 6×12 = 72 | 6×8 = 48 |
| **Total** | **692** | **617** | **491** |
| vs 658pt viewport | **+34 overflow** (the "very small scroll") | fits, 41pt spare | **fits, 167pt spare** |

Density pass alone reclaims 617 − 491 = **126pt** (≈ the mock's ~120pt):
padding 8 + gaps 24 + DNA 62 + section label 8 + cards 24. The 167pt
headroom absorbs Dynamic-Type growth, a second chip line per DNA group
(+~34 each), and the "(inferred)" outlook wrap without the scroll returning.

Card block detail: 61pt = 2 border + 18 padV + 41 text (title 22 + 1 +
bodySm 18); the 34pt icon well is shorter than the text block, so tap
targets stay ≥61pt — well over the 44pt floor.

## Verification

- `cd mobile && npx tsc --noEmit` — clean.
- Built on top of merge `0f7e86e` (#223/#224), so the arithmetic above uses
  the shipped 52pt TopBar and the already-removed pill row.
