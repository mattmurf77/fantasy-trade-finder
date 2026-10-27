import { create } from 'zustand';

import {
  setOnProRequired,
  type GateKind,
  type GateOutcome,
  type GateSignal,
} from '../api/client';
import type { PaywallSource, VerifyPath } from '../copy/monetization';
import { useSession, type SavedUser } from './useSession';

// The paywall router (#393 M1; D1, D3, D9, D15–D18).
//
// `api/client.ts` classifies every failed USER-INITIATED call (a call made
// with `background: true` never reaches here) and hands this module one of:
//   paywall          402 pro_required, any gate but verify_required
//   verify           402 gate=verify_required, or 403 verification_required
//                    on a gated route
//   verify_mismatch  403 token_user_mismatch from the Sleeper verify link
//
// THE ROUTING READS NO ENTITLEMENT FIELD (legal R28.9, D15): it reads the
// signal, the session's `verification.session_verified` and `isDemo`, and
// nothing else. Whether this account subscribes never changes what opens,
// so the sheet can't tell a username-typer who pays.
//
//   openPaywall({source, gate?, kind?}) → the Paywall modal. A session the
//     server reported unverified gets the VerifySheet instead (D16a): an
//     unverified session never sees the paywall or the trial offer.
//   openVerify({onVerified?}) → the VerifySheet (components/VerifySheet,
//     mounted once in RootNav). Returns how it closed; client.ts holds the
//     original call on that promise and re-sends it once on `verified`, so
//     the SERVER decides what happens next (D18: the free page, a 402 → the
//     paywall, or entitled → the call just succeeds).

export type { GateKind, PaywallSource, VerifyPath };

export interface PaywallParams {
  source: PaywallSource | string;
  gate?: string;
  kind?: GateKind;
}

/** The slice of RootNav's `navigationRef` the gate uses. */
export interface GateNavigator {
  isReady(): boolean;
  navigate(...args: any[]): void;
  getCurrentRoute(): { name: string } | undefined;
  addListener(type: 'state', cb: () => void): () => void;
  reset(state: { index: number; routes: { name: string }[] }): void;
}

let _nav: GateNavigator | null = null;
export function getGateNavigator(): GateNavigator | null {
  return _nav;
}

/** A Sleeper session verifies through SleeperConnect; any other session (an
 *  ESPN/MFL entry session, a demo, an account session that somehow lost its
 *  verification) gets the Apple new-sign-in variant. Never MFL (D18 FINAL:
 *  the MFL login sits behind the same verify gate). */
export function verifyPathFor(
  user: Pick<SavedUser, 'user_id' | 'account_only'> | null | undefined,
  isDemo: boolean,
): VerifyPath {
  if (!user || isDemo || user.account_only) return 'apple';
  if (/^(demo_user_|entry:|acct_)/.test(user.user_id)) return 'apple';
  return 'sleeper';
}

/** The server reported this session unverified. Unknown (`verification`
 *  null, an older server) is not "unverified": the 402/403 still decides. */
export function isUnverifiedSession(): boolean {
  const { verification, isDemo } = useSession.getState();
  return !isDemo && verification?.session_verified === false;
}

interface GateState {
  /** The VerifySheet is up (or mid-flow, e.g. away in SleeperConnect). */
  verifyOpen: boolean;
  /** Bumps on every open, so the sheet resets its phase. */
  verifySeq: number;
  /** Bumps on a 403 token_user_mismatch while the sheet is open. */
  mismatchSeq: number;
}

export const usePaywallGate = create<GateState>(() => ({
  verifyOpen: false,
  verifySeq: 0,
  mismatchSeq: 0,
}));

let _pending: {
  promise: Promise<GateOutcome>;
  resolve: (o: GateOutcome) => void;
  onVerified: Array<() => void>;
} | null = null;

/** Open the VerifySheet. Concurrent callers share one sheet and one outcome. */
export function openVerify(opts: { onVerified?: () => void } = {}): Promise<GateOutcome> {
  if (!_pending) {
    let resolve!: (o: GateOutcome) => void;
    const promise = new Promise<GateOutcome>((r) => {
      resolve = r;
    });
    _pending = { promise, resolve, onVerified: [] };
    usePaywallGate.setState((s) => ({ verifyOpen: true, verifySeq: s.verifySeq + 1 }));
  }
  if (opts.onVerified) _pending.onVerified.push(opts.onVerified);
  return _pending.promise;
}

/** The VerifySheet's one exit. `verified` only after the server said so. */
export function settleVerify(outcome: GateOutcome): void {
  const p = _pending;
  _pending = null;
  usePaywallGate.setState({ verifyOpen: false });
  if (!p) return;
  if (outcome === 'verified') {
    for (const fn of p.onVerified) {
      try {
        fn();
      } catch {
        /* a caller's continuation never blocks the others */
      }
    }
  }
  p.resolve(outcome);
}

/** Open the paywall for a locked action (or a trigger, in M2). */
export function openPaywall(params: PaywallParams): Promise<GateOutcome> | void {
  if (isUnverifiedSession()) return openVerify();
  const nav = _nav;
  if (!nav || !nav.isReady()) return;
  // One paywall at a time: a second 402 while it's up opens nothing more.
  if (nav.getCurrentRoute()?.name === 'Paywall') return;
  nav.navigate('Paywall', {
    source: params.source,
    ...(params.gate ? { gate: params.gate } : {}),
    ...(params.kind ? { kind: params.kind } : {}),
  });
}

/** The client.ts seam handler. Exported for the structural check. */
export function handleGateSignal(signal: GateSignal): Promise<GateOutcome> | void {
  if (signal.action === 'paywall') {
    return openPaywall({ source: 'gate', gate: signal.gate ?? undefined, kind: signal.kind });
  }
  if (signal.action === 'verify') return openVerify();
  // verify_mismatch: only meaningful while the sheet is waiting on a verify.
  if (_pending) usePaywallGate.setState((s) => ({ mismatchSeq: s.mismatchSeq + 1 }));
}

/** App start (App.tsx): wire the client seam to this router. */
export function installPaywallGate(nav: GateNavigator): void {
  _nav = nav;
  setOnProRequired(handleGateSignal);
}
