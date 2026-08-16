// rankImportBus — module-level mailbox for the premium in-app-browser
// handoff (Connected Rankings addendum §3.2 intake (iii), [D-058]).
//
// Same shape and same reason as espnConnectBus.ts: `ImportRankingsSheet` is
// a RN <Modal>, and a native-stack push (PremiumRankingsBrowserScreen with
// its WebView) lands on the navigator BEHIND that Modal — so the host closes
// the sheet before navigating, and the browser screen delivers the captured
// CSV back here rather than through navigation params.
//
// A capture delivered while nothing is subscribed is PARKED and flushed to
// the next subscriber: the browser screen pops as soon as it has the file,
// and dropping it would spend the user's export for nothing.

import type { PresetVia } from '../utils/rankPresets';

export interface CapturedCsv {
  /** Raw CSV text exactly as the site generated it. */
  text: string;
  /** Filename when the download surfaced one — DN's format/set live ONLY
   *  here (addendum §3.2), so it is carried through intake. */
  filename: string | null;
  via: PresetVia;
}

type Subscriber = (csv: CapturedCsv) => void;

let subscriber: Subscriber | null = null;
let pending: CapturedCsv | null = null;

/** The import host registers its receiver. Returns an unsubscribe. Last
 *  writer wins — only one import sheet is ever open at a time. */
export function onRankCsvCaptured(cb: Subscriber): () => void {
  subscriber = cb;
  if (pending) {
    const csv = pending;
    pending = null;
    cb(csv);
  }
  return () => {
    if (subscriber === cb) subscriber = null;
  };
}

/** PremiumRankingsBrowserScreen calls this once, with the file the user's
 *  own Export tap produced. */
export function deliverRankCsv(csv: CapturedCsv): void {
  if (subscriber) {
    subscriber(csv);
    return;
  }
  pending = csv;
}
