# PRD — #51/#52 Back button on Rank sub-screens is broken & inconsistent

**Severity:** bug · **Screens:** Tiers, Overall Ranks, Trends (all Rank-stack sub-screens) · **Effort:** small–medium

## Problem
Reported on v1.2.0:
- #51 (Tiers): "The back button redirects to Trios and is inconsistent. Only some launches it is greyed out. In some it works fine. In others it shows content but is a dead click."
- #52 (Overall Ranks): "Same issue with the back button on all pages under the Rank category."

So across every Rank sub-screen the native header back button is: (a) sometimes greyed/absent, (b) sometimes a dead click, (c) when it works, it always lands on Trios rather than where the user came from.

## Root cause (navigation architecture)
`mobile/src/navigation/TabNav.tsx`:
- The Rank tab is a native-stack (`RankStack`) with `Trios` (headerless) as the **first/root** screen and `Tiers` / `ManualRanks` / `Trends` as pushed screens with `headerShown: true` (default back button).
- Tapping the Rank tab is intercepted (`tabPress` → `e.preventDefault()` → opens `RankMenu`). The menu navigates with `CommonActions.navigate({ name: 'Rank', params: { screen } })`.

Why the symptoms appear:
- `CommonActions.navigate` to a stack screen **navigates to** that route in the existing stack rather than reliably pushing a fresh entry. Depending on current stack state the target screen may become the only entry (no back target → header back greyed/absent) or may resolve without re-rendering the header (dead click).
- When a back target does exist it's always `Trios` (the root), never the previously-viewed sub-screen — so "back" never means "where I was."

## Goal / intended behavior
The Rank sub-screens are **siblings reached from a menu**, not a linear drill-down. "Back" from a sub-screen should return the user to a predictable place, and the control must never be a dead click or silently disabled.

## Decision (pick the lower-risk of these during implementation; A preferred)
**Option A — replace the native back button with an explicit "Done / Close" that pops to a stable home.** Since the menu is the real navigator, a back arrow implies history that doesn't exist. Give each sub-screen a header-left control that always works: `navigation.canGoBack() ? navigation.goBack() : navigation.navigate('Trios')`. Wire via `navigation.setOptions({ headerLeft: ... })` or the stack `screenOptions`. Result: always tappable, predictable destination, no greying.

**Option B — make the menu navigation deterministic.** Use `navigation.navigate('Rank', { screen })` from a held nav ref and ensure each menu jump `push`es so a back entry always exists; standardize the header back to `goBack`. Higher chance of subtle stack bugs than A.

Either way: the control must be **always enabled** and land on a **defined** screen (Trios is an acceptable home).

## Acceptance criteria
- On Tiers, Overall Ranks, and Trends, the header-left control is always present and tappable (never greyed, never a dead click) across repeated entries (open menu → screen → back, ×5, including cold launch).
- Tapping it lands on a defined, consistent destination every time.
- Re-entering a sub-screen from the Rank menu still works and shows its data.
- No regression to the Rank menu itself or to tab switching.
- `tsc --noEmit` clean. Verify on device/simulator: repeat the open→back loop on each of the three screens.

## Files
- `mobile/src/navigation/TabNav.tsx` (RankStack screen options + RankMenu navigation).
- May add a small shared `headerLeft` component; keep it in `TabNav.tsx` unless it grows.

## Risk / guardrails
- Do **not** change the Trios swipe screen or the screens' bodies (those are owned by the Tiers bug group). Touch only navigation/header config.
- Preserve the existing prefetch-on-menu-select behavior.
