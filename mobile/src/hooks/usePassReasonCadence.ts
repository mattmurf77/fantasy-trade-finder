import { useCallback, useState } from 'react';
import { track } from '../api/events';
import { fetchedPassReasonCadence } from '../api/flags';
import { useFlag } from '../state/useFeatureFlags';
import {
  INITIAL_CADENCE,
  normalizeCadence,
  recordDisposition,
  shouldAsk,
  type PassReasonCadenceCard,
} from '../utils/passReasonCadence';

// usePassReasonCadence — the React half of utils/passReasonCadence.ts (flag
// `trade.pass_reason_cadence`, offer-learnings WS3). TradesScreen calls
// `record(decision)` once per deck disposition and spreads `cardProps` into the
// reason props it already builds. Flag off ⇒ `record` never moves the state and
// `cardProps` is `{}`, so the screen's objects are exactly what they were.
//
// State is per screen mount (in memory): a fresh deck screen starts a fresh run.
// N and M are re-read from the last flag fetch on every call, so a knob change
// lands on the next foreground refetch without an app release.

export function usePassReasonCadence(): {
  on: boolean;
  record: (decision: 'like' | 'pass') => void;
  cardProps: { cadence?: PassReasonCadenceCard };
} {
  const on = useFlag('trade.pass_reason_cadence');
  const [state, setState] = useState(INITIAL_CADENCE);

  const record = useCallback(
    (decision: 'like' | 'pass') => {
      if (!on) return;
      const cfg = normalizeCadence(fetchedPassReasonCadence());
      setState((s) => recordDisposition(on, s, decision, cfg));
    },
    [on],
  );

  if (!on) return { on, record, cardProps: {} };

  const ask = shouldAsk(on, state, normalizeCadence(fetchedPassReasonCadence()));
  const consecutivePasses = state.consecutivePasses;
  return {
    on,
    record,
    cardProps: {
      cadence: {
        mode: ask ? 'ask' : 'quiet',
        consecutivePasses,
        onShown: (tradeId: string) =>
          track(
            'pass_reason_prompt_shown',
            { trade_id: tradeId, consecutive_passes: consecutivePasses },
            'Trades',
          ),
        onDismissed: (tradeId: string) =>
          track('pass_reason_prompt_dismissed', { trade_id: tradeId }, 'Trades'),
      },
    },
  };
}
