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

// Mailbox for a capture delivered while NO sheet is subscribed (host screen
// remounting across a background/foreground cycle, sheet torn down mid-
// delivery). The WebView side treats delivery as done and pops immediately,
// so a dropped pair would strand the user on an empty sheet with their login
// spent. Park it and flush to the next subscriber. Abandon (null) is NOT
// parked: its only job is un-hiding a live sheet, and a sheet that mounts
// later starts un-hidden anyway.
let pending: EspnCookiePair | null = null;

/** EspnLinkSheet registers its receiver. Returns an unsubscribe. Last writer
 *  wins — only one sheet is ever open at a time. A pair delivered while no
 *  receiver was mounted is flushed (once) to the new receiver immediately. */
export function onEspnCookiesCaptured(cb: Subscriber): () => void {
  subscriber = cb;
  if (pending) {
    const pair = pending;
    pending = null;
    cb(pair);
  }
  return () => {
    if (subscriber === cb) subscriber = null;
  };
}

/** EspnConnectScreen calls this exactly once with the pair on capture, or
 *  with null when it leaves without capturing (so the sheet un-hides). */
export function deliverEspnCookies(pair: EspnCookiePair | null): void {
  if (subscriber) {
    subscriber(pair);
    return;
  }
  if (pair) pending = pair;
}
