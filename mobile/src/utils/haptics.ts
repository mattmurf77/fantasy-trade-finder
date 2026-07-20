import * as Haptics from 'expo-haptics';

// Semantic haptics taxonomy — call sites should use these, not expo-haptics
// directly, so feedback stays consistent across screens.
//
//   selection — tapping a selectable UI element (chip, card, button)
//   swipe     — confirming a swipe gesture (light, in-flight feedback)
//   pickup    — picking up a draggable item (heavier "grab" feel)
//   success   — an action completed (trade liked, tier saved, rank submitted)
//   warning   — destructive or undo (dismiss player, decline match)
//
// All calls are fire-and-forget; native APIs are async but we never await.
//
// Teardown S3 PRD-04 wiring guidance (wave-2 screen agents):
//   • `pickup()` is defined but uncalled today — fire it in `onDragBegin` on
//     BOTH drag boards (TiersScreen, ManualRanksScreen) so the 220ms lift
//     gets tactile confirmation and scroll-vs-drag stops being ambiguous.
//   • Drag END is routine — use `swipe()` (impact-light), NOT `success()`.
//     Reserve `success()` for server-confirmed outcomes.
//   • Zero direct expo-haptics imports outside this file: route
//     SendInSleeperButton (current offender) through this taxonomy.

export const haptics = {
  selection: () => {
    void Haptics.selectionAsync();
  },
  swipe: () => {
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  },
  pickup: () => {
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
  },
  success: () => {
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  },
  warning: () => {
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  },
};
