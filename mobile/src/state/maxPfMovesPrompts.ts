import AsyncStorage from '@react-native-async-storage/async-storage';
import { RULES_NOTE_KEY, draftOrderAskedKey } from '../utils/maxPfMoves';

// Max PF moves' two once-only device prompts (contract §6.4). Plain
// AsyncStorage reads/writes in the `outlookStrip` posture: failures are
// swallowed (an unreadable store reads as "never shown"), writes are
// fire-and-forget. Device-wide, not user-scoped: the contract's keys are
// `maxpf.rulesNoteShown` (one per device) and
// `maxpf.draftOrderAsked.<leagueId>`.

export interface MaxPfPrompts {
  rulesNoteShown: boolean;
  draftOrderAsked: boolean;
}

export async function readMaxPfPrompts(leagueId: string): Promise<MaxPfPrompts> {
  try {
    const [rules, asked] = await Promise.all([
      AsyncStorage.getItem(RULES_NOTE_KEY),
      AsyncStorage.getItem(draftOrderAskedKey(leagueId)),
    ]);
    return { rulesNoteShown: rules != null, draftOrderAsked: asked != null };
  } catch {
    return { rulesNoteShown: false, draftOrderAsked: false };
  }
}

export function markRulesNoteShown(): void {
  AsyncStorage.setItem(RULES_NOTE_KEY, '1').catch(() => {});
}

export function markDraftOrderAsked(leagueId: string): void {
  AsyncStorage.setItem(draftOrderAskedKey(leagueId), '1').catch(() => {});
}
