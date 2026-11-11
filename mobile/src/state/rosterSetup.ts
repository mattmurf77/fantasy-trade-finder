import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

import type { Position } from '../shared/types';
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

export const ROSTER_SETUP_KEY = 'ftf_roster_setup_v1';

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

const readStored = async (): Promise<ByLeague> => {
  try {
    const raw = await AsyncStorage.getItem(ROSTER_SETUP_KEY);
    return raw ? (JSON.parse(raw) as ByLeague) : {};
  } catch {
    return {};
  }
};

interface RosterSetupState {
  byLeague: ByLeague;
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

export const useRosterSetup = create<RosterSetupState>((set, get) => ({
  byLeague: {},
  hydrated: false,
  hydrate: () => {
    if (get().hydrated) return Promise.resolve();
    if (!hydration) {
      hydration = readStored().then((stored) => {
        set((s) => ({ hydrated: true, byLeague: { ...stored, ...s.byLeague } }));
      });
    }
    return hydration;
  },
  write: (leagueId, patch) => {
    if (!leagueId) return;
    const prev = get().byLeague[leagueId];
    const next: RosterSetupRecord = {
      status: patch.status ?? prev?.status ?? 'skipped',
      seenAssetIds: patch.seenAssetIds ?? prev?.seenAssetIds ?? [],
      rankedPositions: patch.rankedPositions ?? prev?.rankedPositions ?? [],
      prompt: patch.prompt !== undefined ? patch.prompt : prev?.prompt ?? null,
      at: new Date().toISOString(),
    };
    set((s) => ({ byLeague: { ...s.byLeague, [leagueId]: next } }));
    readStored()
      .then((stored) => AsyncStorage.setItem(
        ROSTER_SETUP_KEY, JSON.stringify({ ...stored, ...get().byLeague }),
      ))
      .catch(() => { /* quota or serialization failure is not fatal */ });
  },
}));

/** Non-hook read for event handlers. */
export function rosterSetupRecord(leagueId: string | null | undefined): RosterSetupRecord | undefined {
  return leagueId ? useRosterSetup.getState().byLeague[leagueId] : undefined;
}
