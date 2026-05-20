import * as Linking from 'expo-linking';
import { useSession } from '../state/useSession';
import { navigationRef } from '../navigation/RootNav';

// ── Bundle 8: Deep link handling ──────────────────────────────────────────
// Two surfaces today:
//   • ?ref=<username>  — referral attribution. Stash in useSession so the
//     next /api/session/init carries invited_by. Web uses the same param
//     name (`ref`) and the same backend column.
//   • /u/<username>    — public profile. We navigate to the Profile screen
//     in the auth stack; react-navigation's Linking config maps the same
//     path to the same screen so cold-start tapped links land there too.
//
// Accepts both the app's custom scheme (dtf://…) and the production
// universal-link host. Tolerant of trailing slashes + uppercase chars.

/** True if the navigation container is mounted and ready to handle a navigate(). */
function _navReady(): boolean {
  try {
    return navigationRef.isReady();
  } catch {
    return false;
  }
}

/** Parse a deep link, capture any referral, and route public-profile URLs.
 *  Safe to call repeatedly with the same URL — both side effects are
 *  idempotent (setInvitedBy is last-write-wins; navigate to the same
 *  screen is a no-op on react-navigation). */
export function handleDeepLink(url: string | null | undefined): void {
  if (!url) return;
  let parsed: ReturnType<typeof Linking.parse>;
  try {
    parsed = Linking.parse(url);
  } catch {
    return;
  }

  // Referral: ?ref=<username>. queryParams may be Record<string, string | string[]>
  const ref = parsed.queryParams?.ref;
  const refStr = Array.isArray(ref) ? ref[0] : ref;
  if (typeof refStr === 'string' && refStr.trim()) {
    useSession.getState().setInvitedBy(refStr);
  }

  // Public profile: /u/<username>. expo-linking sets `path` without a
  // leading slash, so "u/teresa" matches the published route.
  const path = (parsed.path || '').replace(/^\/+/, '');
  const m = /^u\/([^\/?#]+)/i.exec(path);
  if (m && m[1]) {
    const username = decodeURIComponent(m[1]);
    if (_navReady()) {
      try {
        navigationRef.navigate('Profile', { username });
      } catch {
        /* navigator mid-transition; non-fatal */
      }
    }
  }
}
