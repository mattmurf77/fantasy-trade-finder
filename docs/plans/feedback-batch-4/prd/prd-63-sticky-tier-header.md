# PRD FB4-63 — Sticky tier header on Tiers

**Feedback #63 (Tiers, polish):** "The tier of the current players viewed should be a permanent
floating header that stays on the page and updates based on the players shown."

## Requirement
As the user scrolls the Tiers list, a compact header pinned just under the position tabs shows
the **tier the topmost visible player belongs to** (label + count + the tier's accent color), and
updates live as scrolling moves a new tier into view. The existing inline tier-section headers stay.

## User story
Scrolling deep into a long tier, I always know which tier I'm looking at because a small floating
banner at the top tells me — it updates the moment a different tier's players scroll into view.

## Acceptance criteria
- [ ] A pinned banner sits between the position tabs/hint and the scrollable list; it does NOT scroll away.
- [ ] It shows the current tier's label (e.g. "Elite") + that tier's accent color (from `tierBands`)
      + the count of players in that tier. For the unassigned pool it reads "Unassigned".
- [ ] The banner updates as the user scrolls so it always reflects the tier of the FIRST (topmost)
      visible player row. Use the DraggableFlatList `onViewableItemsChanged` (or `viewabilityConfig`)
      to derive the topmost visible row's zone — do NOT add a competing scroll listener that could
      interfere with the drag gesture.
- [ ] When a drag is in progress the banner must not flicker/jump distractingly (debounce or freeze
      during active drag is acceptable).
- [ ] Empty state (no rankings) hides the banner.

## Implementation notes
- File: `mobile/src/screens/TiersScreen.tsx` (+ optionally a tiny presentational component under
  `mobile/src/components/`).
- The list data is the flat `Row[]` (`{kind:'header'|'player'|'empty', zone}`). The topmost visible
  player's `zone` is the value to show. `onViewableItemsChanged` gives visible items; pick the first
  whose `kind!=='header'` (fall back to the first header's zone).
- Reuse the tier accent + label helpers already in the file (`accentFor`, `TIER_LABEL`).
- Keep it lightweight — a `View` with a colored left border + `Text`, styled like the inline
  `tierHeader` but visually distinct as a pinned banner (e.g. subtle background + shadow).
