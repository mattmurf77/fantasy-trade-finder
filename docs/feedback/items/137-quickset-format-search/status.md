# #137 + #138 — Quick set: SF/PPR format toggle + search bar

**Status: built, typecheck clean — simulator verification DEFERRED to the batch QA round (orchestrator directive 2026-07-17: fleet-wide sim/harness contention).**

Owner: mattmurf77 · Screens: QuickSetTiersScreen + QuickRankScreen (shared walk patterns) · Branch: trade-engine-v2

## What was built

### #137 — "Give ability to switch between SF and ppr"
- `FormatToggle` (the existing SF/1QB segmented control from Tiers/Trios) is mounted on **both** guided walks — Quick set and Quick rank — in the same slot convention as TiersScreen: a `formatRow` above the position switcher.
- Wiring matches TiersScreen: `useScoringFormat().setFormat` flips the server session first, persists local mirrors, marks the choice explicit (league-default applier won't stomp it), and sweeps format-scoped query caches. Failure → warn toast, walk state untouched.
- **Switching restarts the walk for the new format's board**: tier index → 0, selection / click-order cleared, and (Quick set) `savedByTier` cleared — the tiers committed earlier in the run were saves against the *previous* format's session, so they must not feed `cleared_pids` or grid-claiming on the new board. The pool query is format-scoped (`['rankings', activeFormat, position]` + server-session format), confirmed the same key TabNav documents for these screens.
- Toggle is disabled while a switch or a tier save is in flight.

### #138 — "Add a search bar"
- Compact `TextInput` between the step header and the chip grid on both walks; design-system Input construction (ink-2 fill, 1px line-strong border, radius sm, chalk text, chalk-faint placeholder, ice focus border), placeholder `Search QBs…` etc.
- Filters the chip grid by case-insensitive substring on player name. **View-only narrowing**: Quick set's save still reads the full `gridPlayers` + `selected` set, Quick rank's save still reads the full member list + click order — a picked/stamped player can never drop out of a save because the filter hid it.
- **Clears on every step advance/back, position switch, and format switch** (per-step filter per spec).
- Search-empty state: "No {POS} here matches "…"." (Quick set keeps its existing claimed-elsewhere empty copy when no filter is active).
- Keyboard handling: whole screen wrapped in `KeyboardAvoidingView` (`padding` on iOS — EspnLinkSheet/#129 pattern) so the absolute-bottom Back/Skip/Save action row lifts above the keyboard; `keyboardShouldPersistTaps="handled"` on the grid so chip taps land while the keyboard is up; `returnKeyType="done"` + iOS clear button on the input.

## Files changed
- `mobile/src/screens/QuickSetTiersScreen.tsx` — #137 toggle + restart semantics, #138 search + KAV
- `mobile/src/screens/QuickRankScreen.tsx` — same pair, mirrored
- `mobile/src/components/CLAUDE.md` — testID registry append (see below)

## New testIDs
- `quick-set.format-toggle` · `quick-set.search`
- `quick-rank.format-toggle` · `quick-rank.search`
- FormatToggle segments text-match in Maestro via their accessibilityLabels `"1QB PPR scoring format"` / `"SF TEP scoring format"` (the Pressable label swallows the child text — do NOT assert on the bare "1QB PPR").

## Verification done
- `cd mobile && npx tsc --noEmit` — clean.
- Partial live evidence before the stop-order: a Release harness build (sim-build.sh, localhost config verified embedded) was driven on FTF-iOS18 far enough that Maestro asserted **`quick-set.search` visible** on the real Quick set walk (fixture profile `standard`, signin → league → rankmenu.quickset). The run then collided with a parallel agent's Maestro session on the same sim (driver port conflict, app backgrounded) — no further steps are trustworthy, so treated as deferred, not passed.

## Deferred to batch QA — exact checks
A ready-made flow is in this folder: `qa-flow-quickset-137-138.yaml` (profile `standard`, flags release; label-based toggle asserts already corrected). QA must verify on the combined build:

1. **Toggle present on both walks** — `quick-set.format-toggle` / `quick-rank.format-toggle` render above the position tabs; segments read "1QB PPR" / "SF TEP" with active state on the session format.
2. **#137 restart semantics** — on Quick set: Skip to "Tier 2 of 8", tap "SF TEP scoring format" → walk returns to "Tier 1 of 8" with an empty selection, and the grid shows the SF board's current tiers (chips' tier micro-labels change where SF/1QB boards differ). Same restart on Quick rank (step 1 of M).
3. **#137 persistence isolation** — tiers saved before the switch stay saved on the OLD format's board (check Tiers board in 1QB after saving a tier, switching to SF, and finishing); no cross-format bleed.
4. **#138 filtering** — typing in `quick-set.search` narrows the grid live; a chip selected *before* filtering it out still counts in Save (save count label unchanged) and lands in the tier; clearing the filter shows it selected.
5. **#138 per-step clear** — Save/Skip/Back/position-switch/format-switch all reset the filter to empty.
6. **#138 keyboard** — with the keyboard open, Back/Skip/Save remain visible and tappable (KAV lift), and a chip tap registers on the first touch (`keyboardShouldPersistTaps`).
7. **Search-empty copy** — a no-match query shows "No {POS} here matches …", distinct from the claimed-elsewhere empty state.
8. **Format-switch failure path** — with the backend down, tapping the other format shows the "Could not switch format" toast and does NOT reset the walk.
