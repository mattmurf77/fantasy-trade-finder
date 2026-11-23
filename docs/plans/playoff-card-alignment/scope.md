# Feature Scope — Playoff card: one value line

**Date:** 2026-11-22
**Entry point:** direct ask (operator TestFlight report on the Home playoff card with "Playoff chance" and "Projected pick")
**Builder:** builder agent, branch `fix/playoff-card-alignment`
**Operator sign-off on waivers:** not needed (no waivers)

Operator report: the spacing is off; the percentage, the pick and "View" should sit on the same line at the same height.

**Cause (from the code; not seen on a device).** In `mobile/src/components/home/HomePlayoffBanner.tsx`, with `league.direction_card` on (the block branch):

1. The outer row was `alignItems: 'center'`. Each figure is a column (label, then a 40pt value line), so "View ›" was centred on the whole two-line block. That put it between the label line and the value line, higher than the percentage and the pick.
2. When the forecast is not current, a "last saved" note sat on each value line. The arithmetic below shows this pushed the two figures past the room on a 375pt screen, so the pick wrapped under the percentage at default text size.

**Fix (layout only; no copy, flag, event or server change).**

- The block branch's row adds `figuresRow: { alignItems: 'flex-start' }`. The no-block row (`styles.row`) is unchanged.
- "View ›" sits in a new `viewColumn`: `flexShrink: 0`, the same `paddingVertical: space.xs` as `figures` and the same `gap: 2` as `figure`. The column holds a spacer `Text` with the label's own style and scale (`type.label`, `scale="dense"`). The spacer holds a no-break space and is hidden from accessibility (`aria-hidden`, `accessibilityElementsHidden`, `importantForAccessibility="no-hide-descendants"`). After it comes the unchanged 40pt `home.playoff.view` Pressable. The spacer grows with Dynamic Type exactly as the label does. Nothing is positioned absolutely and no pixel offset is hard-coded.
- Both "last saved" notes and the "owned by" note now sit under their value line inside their own figure, in this order: value line, "last saved", "owned by". The lines now hold only the percentage with the info button, and the pick value.
- Unchanged: testIDs, roles, labels, hit slops, events, the "info, then View" order, and the H-10 wrap at large text (`figures` still wraps, `figure` still has `minWidth: 120`).

**Width arithmetic** (both hosts pad 16pt; widths are measured from the app's bundled TTFs, advance widths without kerning):

| Item | Width |
|---|---|
| Row content at 375pt: 375 − 2×16 host − 2×1 border − 2×12 row padding | 317 |
| Row content at 390pt | 332 |
| "View ›" column: "View" (Archivo Medium 13) 28.5 + gap 2 + chevron 14 | 44.5 |
| Room for the figures (content − 8 row gap − 44.5) | 264.5 at 375, 279.5 at 390 |
| "PLAYOFF CHANCE" / "PROJECTED PICK" labels (11pt, tracking 0.88) | 112.6 / 108.4 |
| "62.4%" (Plex Mono Semi 14), "100.0%" | 42, 50.4 |
| Info button / "last saved" (Archivo 12) | 32 / 53.5 |

- **Before, current:** playoff figure max(120, 112.6, 42+8+32=82) = 120; pick 120. Total 120 + 16 + 120 = 256. Fits at 375 (8.5 to spare) and at 390.
- **Before, last saved:** playoff line 42+8+53.5+8+32 = 143.5; pick 120. Total 279.5. **Wraps at 375** (15 over). At 390 it fills the room exactly (0 to spare), so any rounding or "100.0%" wraps it.
- **After, both states:** neither line holds a note, so the total is 256 (264.4 with "100.0%"). Fits at 375 and at 390.

Known limit, not changed here: a long "owned by" team name widens the pick figure. That figure has 128.5pt at 375 (143.5 at 390). "owned by " takes 53.5pt, which leaves about 12 lowercase characters of name at 375, or about 15 at 390. Past that, the pick figure wraps under the playoff figure, as it already did before this fix. Fixing that would need a different wrap rule (H-10) and is left for a follow-up.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `direction_card_shown` and `home_tile_tapped` are unchanged. This is a layout fix with no new interaction.

## 2. Schema & flag scope

- New/changed tables or columns: none
- New/changed feature flags: none. This fixes the shipped `league.direction_card` layout.
- New env vars / `model_config` keys: none

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-direction-card.js` § M (M1–M6, each run for current, owned, last saved, and last saved + owned). It pins:
  - M1: the row is top-aligned and "View ›" ends it inside its own column, after the spacer.
  - M2: the column mirrors a figure (padding, gap), and the spacer uses the label's style and scale, holds no words and is hidden from accessibility.
  - M3: the percentage line and the pick line share one style (40pt minimum, centred), and the View control has the same minimum height and centring.
  - M4: the lines hold only the details link, the info button and the pick value.
  - M5: "last saved" and "owned by" sit under the value, outside the line.
  - M6: the no-block row is still centred, with no spacer.
- [x] **Unit tests:** none. No backend change.
- [x] **Code-walk proof:** "View ›" centre = column padding (xs) + label line + gap 2 + half of 40. The percentage and the pick have the same centre: figures padding (xs) + the same label line + gap 2 + half of the 40pt `figureLine`. The spacer is the same `Text` style and scale as the label, so both grow together under Dynamic Type.
- [x] **Manual TestFlight checklist:** see §6.
- `testID`s added: `home.playoff.figure.playoff.line`, `home.playoff.pick.line`, `home.playoff.view.column`, `home.playoff.view.spacer`. They pass `testid-lint.sh`.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route change |
| `living-memory/LLD.md` | n/a | no convention shift |
| `docs/architecture.md` | n/a | no wiring change |
| `living-memory/HLD.md` | n/a | no architecture change |
| `docs/cross-client-invariants.md` | n/a | no shared constant |
| `docs/glossary.md` | n/a | no new term |
| ADR or `DECISIONS.md` | n/a | no real decision: a layout bug fix to the shipped spec (H-1 to H-10) |

## 5. Ship gate declaration

- **CI green:** required on the pushed sha (`tsc --noEmit`, testid-lint, backend tests).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, 2026-11-22 entry.
- **TestFlight verification:** §6, run by the operator.
- Express lane declared by the operator? No.

## 6. Manual TestFlight checklist (default text size, then the largest)

1. On an iPhone with a 375pt or 390pt screen (for example iPhone SE / 13 mini, or iPhone 13 / 14), open Home with a Sleeper league whose card shows "Playoff chance" and "Projected pick". **Expect:** the percentage, the info icon, the pick (for example "1.08") and "View ›" sit on one line at the same height, with each label above its own figure.
2. Use a league whose forecast is not current, so "last saved" shows. **Expect:** the pick stays beside the percentage, not wrapped under it. Each figure shows "last saved" on its own line under the value, and "View ›" stays level with the values. If the pick is owned by another team, "owned by …" is under the pick's "last saved", and the value line does not move.
3. Set Settings > Accessibility > Larger Text to the largest size and reopen Home. **Expect:** the pick may wrap under the playoff figure (allowed, H-10). "View ›" stays level with the percentage line, not centred on the labels. VoiceOver reads no empty element next to "View".
