import { useEffect, useRef, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

// #169 frame E — per-user, per-league memory of the League Summary outlook
// strip's expanded/collapsed state. Plain React hook + AsyncStorage, NOT a
// zustand store — the only thing borrowed from `useTradeQueue` is its
// error-swallowing persist posture (fire-and-forget writes, quota failures
// non-fatal) and its user-scoped key shape (`ftf_trade_queue_<user_id>`), so
// two accounts on one device never share strip state.
//
// Value under the key: Record<string, true> — the league_ids whose strip is
// EXPANDED. Absent key / absent league id = collapsed (the default).
// Collapsing DELETES the league's entry rather than writing false — sparse
// record, so the blob only ever names leagues the user opted into.

const STORAGE_KEY_PREFIX = 'ftf_outlook_strip_';

function storageKey(userId: string): string {
  return `${STORAGE_KEY_PREFIX}${userId}`;
}

/** Expanded/collapsed state for one league's outlook strip. Hydrates on
 *  mount (and on user switch); toggles are optimistic local state with a
 *  fire-and-forget persist. No user or no league → collapsed, no writes. */
export function useOutlookStripExpanded(
  userId: string | null | undefined,
  leagueId: string | null | undefined,
): [boolean, (next: boolean) => void] {
  const [byLeague, setByLeague] = useState<Record<string, true>>({});
  // Latest map for the setter — a stale closure after hydrate would clobber
  // other leagues' entries on the first toggle.
  const byLeagueRef = useRef(byLeague);
  byLeagueRef.current = byLeague;

  useEffect(() => {
    let cancelled = false;
    if (!userId) {
      // No user — reset so a previous session's state doesn't leak across
      // a sign-out/sign-in (same posture as useTradeQueue.hydrate).
      setByLeague({});
      return;
    }
    AsyncStorage.getItem(storageKey(userId))
      .then((raw) => {
        if (cancelled || !raw) return;
        // Defensive: accept only the sparse `Record<string, true>` shape;
        // anything else (drifted version, corruption) resets to collapsed.
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          const clean: Record<string, true> = {};
          for (const [lid, v] of Object.entries(parsed)) {
            if (v === true) clean[lid] = true;
          }
          setByLeague(clean);
        }
      })
      .catch(() => {
        // Unreadable storage — stay at the collapsed default.
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const setExpanded = (next: boolean) => {
    if (!leagueId) return;
    const nextMap = { ...byLeagueRef.current };
    if (next) nextMap[leagueId] = true;
    else delete nextMap[leagueId];
    setByLeague(nextMap);
    if (!userId) return; // toggle works this session; nothing to persist to
    AsyncStorage.setItem(storageKey(userId), JSON.stringify(nextMap)).catch(() => {
      // Quota full / disabled — non-fatal; state survives this session only.
    });
  };

  const expanded = !!(leagueId && byLeague[leagueId]);
  return [expanded, setExpanded];
}
