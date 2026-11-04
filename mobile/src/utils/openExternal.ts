import { Alert, Linking } from 'react-native';
import { copyText } from './clipboard';

// The ONE place mobile opens a link outside the app (eng-external-links §4,
// recommendation B). tests/check-external-links.js pins that every
// `Linking.openURL` in src/ lives here, with a ratcheting allowlist for the
// call sites other leads haven't migrated yet.
//
// Order: copy → schemeUrl → httpsUrl.
//   • The copy goes first: once another app is in the foreground, FTF's JS
//     may be suspended (#351 F9), so it can't wait for the open.
//   • Detection is by `Linking.openURL` REJECTING, never `canOpenURL`.
//     RN 0.81's openURL rejects when nothing can handle the URL, with no
//     Info.plist entry; canOpenURL rejects for any custom scheme missing
//     from LSApplicationQueriesSchemes (#351 F7/F8). No native change.
//   • Never silent. A rejected scheme with `appMissing: 'alert'` shows the
//     "isn't installed" alert with an App Store button (operator D2,
//     2026-10-20). When nothing opens at all, a failure alert.
//
// One open at a time: a re-tap while an open is in flight gets the
// in-flight promise back and opens nothing, until that open settles or
// LOCK_MS passes (an app switch can suspend JS before openURL settles).
//
// Impure (react-native Linking + Alert, ./clipboard, a module-level lock).
// check-external-links.js and check-sleeper-handoff.js transpile and run it
// under node with stubs.

export type ExternalPlatform = 'sleeper' | 'espn' | 'mfl';

// Which control opened the link. sleeperHandoff.ts reports it on the granted
// `sleeper_handoff_resolved` (Sleeper only; ESPN and MFL emit nothing).
// 'unspecified' is for an openInSleeperApp caller that names no surface
// (#351 PRD §3.2 keeps it optional), so it can't be mislabelled; it emits
// nothing. `external_link_opened` is not granted.
export type ExternalSurface =
  | 'send_button'
  | 'free_agents'
  | 'usage_trends'
  | 'trade_queue'
  | 'unspecified';

// 'app'      schemeUrl opened
// 'web'      httpsUrl opened
// 'fallback' schemeUrl rejected; the "isn't installed" alert is showing
// 'failed'   nothing opened; the failure alert is showing
export type OpenOutcome = 'app' | 'web' | 'fallback' | 'failed';

export interface ExternalTarget {
  platform: ExternalPlatform;
  /** A custom scheme, or a universal link the app's AASA claims. Tried first. */
  schemeUrl?: string;
  /** Tried when there's no schemeUrl, or when it rejects and appMissing is 'https'. */
  httpsUrl?: string;
  /** Copied before any open. */
  clipboardText?: string;
  surface: ExternalSurface;
  /** What a rejected schemeUrl does: fall back to httpsUrl, or the D2 alert. */
  appMissing: 'https' | 'alert';
  /** Called synchronously when the schemeUrl open settles (true = opened),
   *  before any fallback and with no further await: the seam
   *  sleeper_handoff_resolved fires from (analytics-lead G3). Not called for
   *  a re-tap that gets the in-flight promise back. */
  onSchemeSettled?: (opened: boolean) => void;
}

export const LOCK_MS = 2000;

// D2's App Store targets. Sleeper's id was verified in #351 F6. A platform
// with no entry here falls through to httpsUrl / the failure alert.
const APP_STORE: Partial<Record<ExternalPlatform, { name: string; url: string }>> = {
  sleeper: { name: 'Sleeper', url: 'https://apps.apple.com/app/id987367543' },
};

let inFlight: Promise<OpenOutcome> | null = null;

export function openPlatform(target: ExternalTarget): Promise<OpenOutcome> {
  if (inFlight) return inFlight;
  const run = attempt(target);
  inFlight = run;
  const release = () => {
    clearTimeout(timer);
    if (inFlight === run) inFlight = null;
  };
  const timer = setTimeout(release, LOCK_MS);
  run.then(release, release);
  return run;
}

async function attempt(t: ExternalTarget): Promise<OpenOutcome> {
  if (t.clipboardText) copyText(t.clipboardText);
  if (t.schemeUrl) {
    const ok = await opened(t.schemeUrl);
    try {
      t.onSchemeSettled?.(ok);
    } catch {
      // Analytics never stops the open or the D2 alert.
    }
    if (ok) return 'app';
    const store = APP_STORE[t.platform];
    if (t.appMissing === 'alert' && store) {
      showAppMissing(store);
      return 'fallback';
    }
  }
  if (t.httpsUrl && (await opened(t.httpsUrl))) return 'web';
  showOpenFailed();
  return 'failed';
}

// false on rejection. The rejection IS the "can't open" signal (F8), and
// every caller turns false into an alert, so nothing is swallowed.
async function opened(url: string): Promise<boolean> {
  try {
    await Linking.openURL(url);
    return true;
  } catch {
    return false;
  }
}

// Copy: #351 PRD §4.4 option (ii), verbatim. Wording is design-lead's.
function showAppMissing(store: { name: string; url: string }): void {
  Alert.alert(
    `${store.name} isn’t installed`,
    `Get the ${store.name} app to finish this in your league.`,
    [
      { text: 'Cancel', style: 'cancel' },
      {
        text: `Get ${store.name}`,
        onPress: () => {
          void opened(store.url).then((ok) => {
            if (!ok) showOpenFailed();
          });
        },
      },
    ],
  );
}

// Copy: the app's existing "Couldn't open that link" (RootNav's deep-link
// toast). Placeholder pending design-lead.
function showOpenFailed(): void {
  Alert.alert('Couldn’t open that link');
}
