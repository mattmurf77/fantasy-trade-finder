import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

import type { Position } from '../shared/types';
import { useSession } from './useSession';
import type { PromptLadder } from '../utils/rosterSetup';

// rosterSetup — which leagues have been through roster-first setup for Find
// a Trade (flag `trades.roster_setup`; prd §3.4, Q6: device-side by design).
//
// Modelled on `teamReviewCompletion.ts`, for the same reason: the writer
// (RosterSetupScreen, pushed in the Trades stack) and the readers (the
// first-pass trigger + RosterSetupEntryCard) sit in ONE stack with
// TradesHome MOUNTED beneath the push. A once-per-mount AsyncStorage read
// could not see a record written while it sat underneath, and a focus re-read
// would race the fire-and-forget write. So: memory updates SYNCHRONOUSLY,
// disk mirrors by read-merge-write, hydrate is idempotent and merges disk
// UNDER memory so an early write wins.
//
// Persisted because no server row records "has seen the setup" — the
// asset-prefs rows say what the user tagged, not that they were asked. The
// cost (prd Q6): a reinstall or second device sees the step again,
// pre-filled with the saved tags, so it is one tap to dismiss.
//
// The per-league `prompt` ladder backs the TradesHome return card's snooze
// grammar (prd §3.3); the decisions over it are pure functions in
// `utils/rosterSetup.ts`. This store only remembers.

//
// PER ACCOUNT (2026-11-22). A league's record holds that account's roster
// (`seenAssetIds`) and its done/skipped answer, so a second account on this
// device in the same league must not read it. Stored per signed-in user under
// `ftf_roster_setup_v1:<user_id>`; the pre-split device-wide map is adopted
// once by the first account that hydrates after the update, then removed (the
// teamReviewCompletion construction). The account reset (state/accountReset.ts)
// drops the in-memory copy so the next account re-reads.

export const ROSTER_SETUP_KEY = 'ftf_roster_setup_v1';
export const rosterSetupKey = (userId: string): string => `${ROSTER_SETUP_KEY}:${userId}`;

export type RosterSetupStatus = 'done' | 'skipped';

export interface RosterSetupRecord {
  status: RosterSetupStatus;
  /** Player ids + owned pick ids on the roster when the user last saw it. */
  seenAssetIds: string[];
  /** ISO timestamp of the last write. */
  at: string;
  rankedPositions: Position[];
  /** Return-card snooze ladder; absent until the first "Not now". */
  prompt?: PromptLadder | null;
}

type ByLeague = Record<string, RosterSetupRecord>;

const currentUserId = (): string | null => useSession.getState().user?.user_id ?? null;

const readStored = async (userId: string): Promise<ByLeague> => {
  try {
    const raw = await AsyncStorage.getItem(rosterSetupKey(userId));
    if (raw) return JSON.parse(raw) as ByLeague;
    const legacy = await AsyncStorage.getItem(ROSTER_SETUP_KEY);
    if (!legacy) return {};
    await AsyncStorage.setItem(rosterSetupKey(userId), legacy);
    await AsyncStorage.removeItem(ROSTER_SETUP_KEY);
    return JSON.parse(legacy) as ByLeague;
  } catch {
    return {};
  }
};

interface RosterSetupState {
  byLeague: ByLeague;
  /** The account `byLeague` belongs to (null before the first hydrate/write). */
  userId: string | null;
  /** False until the first `hydrate` has read the device. Readers make no
   *  entry decision before then — "no record" is not knowable earlier. */
  hydrated: boolean;
  hydrate: () => Promise<void>;
  /** Merge a patch into a league's record (creating it when absent): memory
   *  first, synchronously, then the disk mirror fire-and-forget. A storage
   *  failure costs next-launch memory, never the current screen. */
  write: (leagueId: string, patch: Partial<RosterSetupRecord> & { status?: RosterSetupStatus }) => void;
}

let hydration: Promise<void> | null = null;
let hydrationFor: string | null = null;

export const useRosterSetup = create<RosterSetupState>((set, get) => ({
  byLeague: {},
  userId: null,
  hydrated: false,
  hydrate: () => {
    const uid = currentUserId();
    // No account, nothing to read: stay un-hydrated so the next account's
    // first call reads its own map.
    if (!uid) return Promise.resolve();
    if (get().hydrated && get().userId === uid) return Promise.resolve();
    if (!hydration || hydrationFor !== uid) {
      hydrationFor = uid;
      const read: Promise<void> = readStored(uid).then((stored) => {
        if (hydrationFor !== uid) return;
        set((s) => ({
          hydrated: true,
          userId: uid,
          byLeague: { ...stored, ...(s.userId === uid ? s.byLeague : {}) },
        }));
      }).finally(() => { if (hydration === read) hydration = null; });
      hydration = read;
    }
    return hydration;
  },
  write: (leagueId, patch) => {
    const uid = currentUserId();
    if (!leagueId || !uid) return;
    const mine = get().userId === uid ? get().byLeague : {};
    const prev = mine[leagueId];
    const next: RosterSetupRecord = {
      status: patch.status ?? prev?.status ?? 'skipped',
      seenAssetIds: patch.seenAssetIds ?? prev?.seenAssetIds ?? [],
      rankedPositions: patch.rankedPositions ?? prev?.rankedPositions ?? [],
      prompt: patch.prompt !== undefined ? patch.prompt : prev?.prompt ?? null,
      at: new Date().toISOString(),
    };
    set({ userId: uid, byLeague: { ...mine, [leagueId]: next } });
    readStored(uid)
      .then((stored) => AsyncStorage.setItem(
        rosterSetupKey(uid), JSON.stringify({ ...stored, ...get().byLeague }),
      ))
      .catch(() => { /* quota or serialization failure is not fatal */ });
  },
}));

/** Account reset (state/accountReset.ts): forget the leaving account's records
 *  in memory; the next account's `hydrate` reads its own. Disk is untouched —
 *  the map is keyed by account. */
export function resetRosterSetup(): void {
  hydration = null;
  hydrationFor = null;
  useRosterSetup.setState({ byLeague: {}, userId: null, hydrated: false });
}

/** Non-hook read for event handlers. */
export function rosterSetupRecord(leagueId: string | null | undefined): RosterSetupRecord | undefined {
  return leagueId ? useRosterSetup.getState().byLeague[leagueId] : undefined;
}
