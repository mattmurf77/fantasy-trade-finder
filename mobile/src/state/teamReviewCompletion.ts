import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { useSession } from './useSession';

// teamReviewCompletion — which leagues' Team Review has been gone through
// (#423; operator 2026-08-20: "track user completion of the experience. Once
// they've gone through it, it should be minimized by default").
//
// WHY A STORE AND NOT A READ-ON-MOUNT. The writer (TeamReviewScreen, on
// reaching the `plan` beat) and the reader (TeamReviewEntryCard on TradesHome)
// are two screens in the same stack, and TradesHome stays MOUNTED beneath the
// pushed review. A card that reads AsyncStorage once per mount therefore
// cannot see a completion until relaunch or league switch — even on the happy
// path — which is #423 verbatim. A focus-effect re-read would not fix it
// either: the marker write is fire-and-forget (two awaits) and the pop back
// to TradesHome runs synchronously after it, so a focus read can land before
// the write. An in-memory store updated SYNCHRONOUSLY has neither problem.
//
// WHY IT IS PERSISTED. Unlike `presentationDismissed`, there is no server
// record of this fact — it is device-local UI memory — so the store mirrors
// itself to the SAME sparse-map format the card used before
// (`{ [leagueId]: true }`), now under a per-account key (below). A device that
// completed a review under the old code still hydrates as done: the old
// device-wide `ftf_team_review_completed` map is adopted once.
//
// Persistence is read-merge-write, never a blind overwrite, so a `mark` that
// races `hydrate` cannot drop leagues the disk knew about and memory did not.
//
// PER ACCOUNT (2026-11-22). The map used to be device-wide, so a second
// account signed in on the same device in the same league read "Team review ·
// done" for a review it never ran. It is now stored per signed-in user under
// `ftf_team_review_completed:<user_id>`, still the sparse `{[leagueId]: true}`
// map. The pre-split device-wide map is adopted ONCE by the first account that
// hydrates after the update (almost always the account that completed it) and
// then removed, so no later account can inherit it. The account reset
// (state/accountReset.ts) drops the in-memory copy so the next account re-reads.

export const TEAM_REVIEW_DONE_KEY = 'ftf_team_review_completed';
export const teamReviewDoneKey = (userId: string): string => `${TEAM_REVIEW_DONE_KEY}:${userId}`;

type LeagueFlags = Record<string, true>;

const currentUserId = (): string | null => useSession.getState().user?.user_id ?? null;

const readStored = async (userId: string): Promise<LeagueFlags> => {
  try {
    const raw = await AsyncStorage.getItem(teamReviewDoneKey(userId));
    if (raw) return JSON.parse(raw) as LeagueFlags;
    const legacy = await AsyncStorage.getItem(TEAM_REVIEW_DONE_KEY);
    if (!legacy) return {};
    await AsyncStorage.setItem(teamReviewDoneKey(userId), legacy);
    await AsyncStorage.removeItem(TEAM_REVIEW_DONE_KEY);
    return JSON.parse(legacy) as LeagueFlags;
  } catch {
    return {};
  }
};

interface CompletionState {
  /** Sparse: only leagues whose review was completed appear, as `true`. */
  byLeague: LeagueFlags;
  /** The account `byLeague` belongs to (null before the first hydrate/mark). */
  userId: string | null;
  /** False until the first `hydrate` has read the device; the card renders
   *  nothing before then so a completed league never flashes the full card. */
  hydrated: boolean;
  /** Read the signed-in account's persisted map once. Idempotent per account;
   *  concurrent calls share one read. Marks made before the read resolves win
   *  (merge, never overwrite). */
  hydrate: () => Promise<void>;
  /** Record completion for a league: memory first, synchronously, then the
   *  disk mirror fire-and-forget. A storage failure costs the next-launch
   *  minimization, never the current screen. */
  mark: (leagueId: string) => void;
}

let hydration: Promise<void> | null = null;
let hydrationFor: string | null = null;

export const useTeamReviewCompletion = create<CompletionState>((set, get) => ({
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
  mark: (leagueId) => {
    const uid = currentUserId();
    if (!leagueId || !uid) return;
    const mine = get().userId === uid ? get().byLeague : {};
    if (mine[leagueId]) return;
    set({ userId: uid, byLeague: { ...mine, [leagueId]: true } });
    readStored(uid)
      .then((stored) => AsyncStorage.setItem(
        teamReviewDoneKey(uid), JSON.stringify({ ...stored, ...get().byLeague }),
      ))
      .catch(() => { /* quota or serialization failure is not fatal */ });
  },
}));

/** Account reset (state/accountReset.ts): forget the leaving account's map in
 *  memory; the next account's `hydrate` reads its own. Disk is untouched — the
 *  map is keyed by account. */
export function resetTeamReviewCompletion(): void {
  hydration = null;
  hydrationFor = null;
  useTeamReviewCompletion.setState({ byLeague: {}, userId: null, hydrated: false });
}
