import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

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
// itself to the SAME key and SAME sparse-map format the card used before
// (`ftf_team_review_completed` → `{ [leagueId]: true }`). No migration: a
// device that completed a review under the old code hydrates as done.
//
// Persistence is read-merge-write, never a blind overwrite, so a `mark` that
// races `hydrate` cannot drop leagues the disk knew about and memory did not.

export const TEAM_REVIEW_DONE_KEY = 'ftf_team_review_completed';

type LeagueFlags = Record<string, true>;

const readStored = async (): Promise<LeagueFlags> => {
  try {
    const raw = await AsyncStorage.getItem(TEAM_REVIEW_DONE_KEY);
    return raw ? (JSON.parse(raw) as LeagueFlags) : {};
  } catch {
    return {};
  }
};

interface CompletionState {
  /** Sparse: only leagues whose review was completed appear, as `true`. */
  byLeague: LeagueFlags;
  /** False until the first `hydrate` has read the device; the card renders
   *  nothing before then so a completed league never flashes the full card. */
  hydrated: boolean;
  /** Read the persisted map once. Idempotent; concurrent calls share one read.
   *  Marks made before the read resolves win (merge, never overwrite). */
  hydrate: () => Promise<void>;
  /** Record completion for a league: memory first, synchronously, then the
   *  disk mirror fire-and-forget. A storage failure costs the next-launch
   *  minimization, never the current screen. */
  mark: (leagueId: string) => void;
}

let hydration: Promise<void> | null = null;

export const useTeamReviewCompletion = create<CompletionState>((set, get) => ({
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
  mark: (leagueId) => {
    if (!leagueId || get().byLeague[leagueId]) return;
    set((s) => ({ byLeague: { ...s.byLeague, [leagueId]: true } }));
    readStored()
      .then((stored) => AsyncStorage.setItem(
        TEAM_REVIEW_DONE_KEY, JSON.stringify({ ...stored, ...get().byLeague }),
      ))
      .catch(() => { /* quota or serialization failure is not fatal */ });
  },
}));
