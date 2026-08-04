# #243 — Build: Trios 3-up mini-cards (Variant A)

**Status: built 2026-08-03.** Implements the operator-approved design
"Trios 3-up, Variant A" from `mockups/polish-lab-2026-08/trios-three-up-v2.html`
(frames A1 idle + A2 winner tap-state; V3 lineage from
`mockups/polish-lab-2026-08/trios-three-up.html`), addressing the biggest
single lever in the #243 rank-surfaces scroll audit
(`docs/feedback/items/243-scroll-audit/rank-surfaces.md` § RankScreen).

## Change

`mobile/src/screens/RankScreen.tsx` only. `PlayerCard.tsx` untouched — the
mini-card is Trios-specific (fixed 2-line name box, winner tick/label,
A2 dim state), so it lives inline as the rewritten `TrioPlayerCard` rather
than as a new PlayerCard variant.

- The three vertically stacked full `PlayerCard`s are replaced by three
  side-by-side mini-cards: `styles.cards` is now `flexDirection:'row',
  gap: space.sm`; each `trioCardWrap` is `flex:1` (≈115pt wide on a 393pt
  device) and every card is a fixed **128pt** tall.
- Mini-card layout (top → bottom, mock Variant A): 3px position rail →
  badge row (`PositionBadge` + `RookieBadge` when applicable) → name in a
  **reserved two-line box** → `TEAM · AGE` meta. The mock's illustrative
  `value` line is not rendered — Variant A frames A1/A2 omit it, and the
  Trio payload's `Player` shape carries no value field today.
- **A2 winner tap-state:** a ranked card gets the ice border + ink2 surface
  step, a 20×20 ice check tick top-right, and a bottom "RANKED 1ST/2ND/3RD"
  label (`type.label` metrics in ice); once ≥1 pick exists, un-ranked cards
  dim to 55% opacity (the mock's "loser" state). Tapping a ranked card
  still removes that rank + later picks.
- **Pick/submit semantics byte-identical:** `rankSide()` / `submitCurrent()`
  / speed-mode auto-submit / Confirm-at-3 / Skip / long-press info sheet /
  the S3 PRD-02 ⓘ twin overlay are all untouched — only the card visuals
  changed. No confirm step was added or removed.
- Skeleton tiles updated to the same 3-up 128pt shape so the page shape
  stays stable during the `/api/trio` round-trip (Mobile #M1 pattern kept).
- testIDs preserved: `trios.card.a|b|c`, `trios.pos-tab.*`,
  `trios.speed-toggle`, `trios.confirm-btn`, `trios.skip-btn`,
  `trios.info.<side>`, `rank.unlock-payoff`. No new IDs needed — each card
  already carries its own.

## Pt table (audit math, 393×852pt reference device)

| Block | Before | After |
|---|---:|---:|
| Screen padding (top+bottom) | 32 | 32 |
| `modeHint` | 14 | 14 |
| `FormatToggle` | 38 | 38 |
| Position `switcher` | 50 | 50 |
| `progressWrap` | 28 | 28 |
| `instruction` | 37 | 37 |
| **Cards block** | **≈324** (3 × ~104pt + 2 × 12 gaps) | **128** (one fixed row) |
| `speedTile` | 80 | 80 |
| `actions` row | 60 | 60 |
| Inter-block gaps (7 × 12) | 84 | 84 |
| **Total** | **≈747** | **≈551** |
| vs 614pt Rank-stack budget | **overflow ≈133pt** | **spare ≈63pt** |

Savings on the card block: **≈196pt** — clears the operator's ~180pt+ bar.
Tap targets: 115×128pt per card, well above the 44pt floor on both axes.
(Nominal state; the streak chip / unlock-payoff caption / Confirm button /
unlocked banner add height in their respective states, as before — the
budget now absorbs the payoff caption and Confirm with room left.)

## Wrapping-rule implementation notes (operator hard requirements)

1. **Whole-word wrapping only — never hyphenate/split a word.** The name
   `Text` gets `numberOfLines={2}`, `textBreakStrategy="simple"` (Android:
   greedy word-boundary breaking, no mid-word splits) and
   `android_hyphenationFrequency="none"` (re-asserting the default so a
   future style tweak can't silently reintroduce hyphenation). iOS wraps
   at word boundaries by default and never auto-hyphenates without an
   explicit hyphenationFactor.
2. **Suffix glued to surname.** `glueSuffix()` rewrites the LAST space
   before a recognized suffix (`Jr.`/`Jr`/`Sr.`/`Sr`/`II`/`III`/`IV`/`V`,
   end-anchored) to an explicit `' '` non-breaking space, so
   "Marvin Harrison Jr." wraps **"Marvin" / "Harrison Jr."** and "Jr." can
   never orphan onto its own line. The escape sequence is used in source
   (not a literal NBSP char) so it survives future edits visibly.
3. **Single-line names top-aligned in the 2-line box; equal card heights.**
   `miniName` has a fixed `height: 36` = exactly 2 × the 18pt `type.bodySm`
   line height (fontSize 13 = bodySm size at `uiSemi` weight — no literal
   below the 11px floor; meta line is 11px, the floor itself, matching the
   `PlayerCard.denseTeam` precedent). RN renders text from the top of a
   fixed-height box, so "Bo Nix" sits flush under the badge row exactly
   like a wrapped name's first line, and all three cards are always the
   same 128pt regardless of name length.
4. Dynamic Type: name/meta/winner label ride the chalkline `Text`
   primitive at the `dense` cap tier (×1.35 under `a11y.text_scaling`) —
   the fixed-pitch-card tier, same policy as the Tiers board's 60pt rows.

Note vs the mock's raw CSS: the mock draws the name box at 13/15 (30pt);
the build uses the token metrics 13/18 (36pt box) per the "type.bodySm
metrics, no literals below the floor" instruction — the 128pt card has
~40pt of reserved slack below the meta line either way, so the winner
label never collides.

## Verification

- `cd mobile && npx tsc --noEmit` — **passes clean** (exit 0).
- Static review: prompt (`instruction`) above and Skip below are
  byte-identical in behavior; `rankSide`/`submitCurrent`/speed-mode paths
  untouched (visual-only diff around them); error + loading branches keep
  their testIDs and shapes.
- Not run here: simulator screenshot pass (no booted simulator in this
  worktree session) — the QA loop should eyeball the A1/A2 states against
  the mock frames, especially "Marvin Harrison Jr."-class names at 2 lines
  and the winner-state flash under I-AM-SPEED.
