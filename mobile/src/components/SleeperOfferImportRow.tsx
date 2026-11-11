// Offer-learnings WS2b — Settings › Leagues: "Use my Sleeper trade offers to
// improve suggestions". One switch, OFF by default, self-contained (it reads
// and writes its own state; the host only mounts it).
//
// Shown only while the flag `trade.sleeper_offer_import` is on AND the server
// answers the GET (a 404 / 403 reads as nothing to show) AND the user has a
// Send-in-Sleeper link (`linked`): the import reads with that credential, so
// without it the switch would promise something that cannot happen.
//
// Every word comes from the server (`label`, `terms_line`, the withdrawal
// `notice`), so the Terms draft can change without a release. Switching on
// sends the `terms_version` the user was shown; a 409 `terms_changed` reloads
// the row with the new wording and leaves the switch off. Switching off
// withdraws and the server deletes every imported offer in the same
// transaction; the notice replaces the sub copy. A failed write leaves the
// switch where it was, with a line saying so.

import React, { useState } from 'react';
import { StyleSheet, Switch, View } from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { Text } from './chalkline';
import { ApiError } from '../api/client';
import {
  grantOfferImport,
  readOfferImport,
  withdrawOfferImport,
  type OfferImportState,
} from '../api/offerImport';
import { useFlag } from '../state/useFeatureFlags';
import { chalk, ice, ink, space, type } from '../theme/chalkline';

export const OFFER_IMPORT_QUERY_KEY = ['sleeper-offer-import'] as const;
const FAILED_LINE = "That didn't save. Try again.";

export default function SleeperOfferImportRow() {
  const enabled = useFlag('trade.sleeper_offer_import');
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: OFFER_IMPORT_QUERY_KEY,
    queryFn: readOfferImport,
    enabled,
    staleTime: 60_000,
    retry: false,
  });
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const state: OfferImportState | null | undefined = query.data;
  if (!enabled || !state || !state.linked) return null;

  async function toggle(next: boolean) {
    if (saving || !state) return;
    setSaving(true);
    setFailed(false);
    setNotice(null);
    try {
      if (next) {
        const out = await grantOfferImport(state.terms_version);
        queryClient.setQueryData(OFFER_IMPORT_QUERY_KEY, out);
      } else {
        const out = await withdrawOfferImport();
        queryClient.setQueryData(OFFER_IMPORT_QUERY_KEY, { ...state, consented: false });
        setNotice(typeof out?.notice === 'string' && out.notice ? out.notice : null);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // The wording changed (or the link went): show the server's state.
        void queryClient.invalidateQueries({ queryKey: OFFER_IMPORT_QUERY_KEY });
      } else {
        setFailed(true);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={s.row}>
      <View style={s.copy}>
        <Text style={s.title}>{state.label}</Text>
        <Text style={s.sub}>{notice ?? state.terms_line}</Text>
        {failed ? (
          <Text style={s.sub} accessibilityLiveRegion="polite">
            {FAILED_LINE}
          </Text>
        ) : null}
      </View>
      <Switch
        testID="settings.sleeper-offer-import.switch"
        value={state.consented}
        disabled={saving}
        onValueChange={(v) => void toggle(v)}
        accessibilityLabel={state.label}
        accessibilityHint={state.terms_line}
        trackColor={{ false: ink.ink3, true: ice.base }}
        thumbColor={chalk.base}
      />
    </View>
  );
}

const s = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  copy: { flex: 1, paddingRight: space.md },
  title: { ...type.label, color: chalk.base },
  sub: { ...type.bodySm, color: chalk.dim, marginTop: space.xs },
});
