// Shared prop contract for every Settings section module.
//
// Phase 0 of docs/plans/settings-ia-hub/plan.md. The section blocks that used
// to live inline in SettingsScreen.tsx (1,712 lines, all state hoisted to the
// top) are now standalone components that own their own queries and state
// (plan §6). What they DON'T own is the two things a host page must supply:
//
//   • `onNotice` — replaces the screen-level `setToast` state. The host mounts
//     the single <Toast/> and decides where it sits; a section only announces.
//   • `navigate` — replaces `navigateFromSettings` (SettingsScreen.tsx:227).
//     While Settings is a modal the host still dismisses first; once Phase 1
//     flips it to a push this collapses to navigation.navigate. Sections are
//     indifferent either way.
//
// Sections that need more than this take it as an ADDITIONAL prop; they never
// take queries or server state as props.

export interface SettingsSectionProps {
  /** Surface a transient message. Replaces SettingsScreen's `setToast`. */
  onNotice: (msg: string, tone?: 'success' | 'warn') => void;
  /** Navigate to a root route. Replaces `navigateFromSettings`. */
  navigate: (route: string, params?: object) => void;
}
