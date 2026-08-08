// espnConnectBus — module-level mailbox for the ESPN Connect WebView handoff
// (Phase 1b, docs/plans/espn-connect-webview/scope.md).
//
// EspnLinkSheet is a RN <Modal>. A native-stack push (EspnConnectScreen with
// its WebView) lands on the navigator BEHIND that Modal, so the sheet hides
// its own Modal while the WebView is up. When the Modal's `visible` is false
// RN unmounts its children — so the sheet subscribes here from its component
// body (which stays mounted regardless of Modal visibility) rather than
// through navigation focus, which it can't observe from inside a Modal.
//
// EspnConnectScreen delivers the captured pair (or null on abandon) back
// through this one subscriber. Module state, not navigation params, because
// the two live on opposite sides of a Modal boundary — the same reason
// onboardingBus.ts exists for the Rank↔Trades handoff.

import type { EspnCookiePair } from '../utils/espnCookies';

type Subscriber = (pair: EspnCookiePair | null) => void;

let subscriber: Subscriber | null = null;

/** EspnLinkSheet registers its receiver. Returns an unsubscribe. Last writer
 *  wins — only one sheet is ever open at a time. */
export function onEspnCookiesCaptured(cb: Subscriber): () => void {
  subscriber = cb;
  return () => {
    if (subscriber === cb) subscriber = null;
  };
}

/** EspnConnectScreen calls this exactly once with the pair on capture, or
 *  with null when it leaves without capturing (so the sheet un-hides). */
export function deliverEspnCookies(pair: EspnCookiePair | null): void {
  subscriber?.(pair);
}
