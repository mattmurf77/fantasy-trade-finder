// One-shot arrival notice for the Sign-in screen (#354 M11 claim-only delete).
//
// The same shape as leagueSummaryIntent: the flow that ends on SignIn sets the
// text just before it signs out, and SignInScreen consumes it once at mount
// and renders it in its notice slot, so a later ordinary visit shows nothing.
// Deliberately not part of useSession, and memory-only: a relaunch drops it,
// which is the right outcome for a one-time "signed out" line.

let pending: string | null = null;

export function setSignInNotice(text: string): void {
  pending = text || null;
}

/** Returns the pending notice (or null) and clears it. */
export function consumeSignInNotice(): string | null {
  const text = pending;
  pending = null;
  return text;
}
