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
