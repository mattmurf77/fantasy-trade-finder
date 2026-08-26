// Trade values — the stud-tax segmented control.
//
// Extracted verbatim from SettingsScreen.tsx (origin/main):
//   • stud-tax state + fetch effect + `onStudTaxChange`      :120-155
//   • `STUD_TAX_OPTIONS` + `studTaxSection`                  :900-957
//
// SECTION BANNER: OWNED HERE. The stud-tax block renders the section's
// <TickLabel>Trade values</TickLabel>.
//
// **The pick-pricing segmented control was REMOVED on 2026-08-21 (D-144).**
// Operator ruling: *"Market slots should be default and not an opt-in or even
// an option to flip."* Pick pricing is unconditional server-side, so there is
// no setting left to render — the control is deleted, not flag-hidden, and
// `trade.slot_pricing` is no longer read by any client. `/api/settings/
// pick-pricing` still answers GET with the fixed state for builds in the
// field and 410s the PUT; this file calls neither.
//
// Behavior changes to the stud-tax control: NONE, deliberately including the
// loading posture — it renders its DEFAULT selection ('market') while the GET
// is in flight and corrects itself when it lands. That is shipped behavior,
// and swapping in a skeleton here would change what the user sees on open.

import React, { useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { TickLabel } from '../../../components/chalkline';
import {
  getStudTaxMode,
  setStudTaxMode,
} from '../../../api/accountPrefs';
import type { StudTaxMode } from '../../../api/calc';
import { track } from '../../../api/events';
import { styles } from '../styles';
import type { SettingsSectionProps } from './types';

// #214/#215 — how the trade engine values studs vs multi-piece packages.
// Three-option segmented control (Chalkline pills, ice = selected);
// plain-words sub copy describes the ACTIVE choice.
const STUD_TAX_OPTIONS: Array<{ key: StudTaxMode; label: string; desc: string }> = [
  { key: 'market', label: 'Market',
    desc: 'Market — matches market consensus (recommended).' },
  { key: 'heavy', label: 'Heavy',
    desc: 'Heavy — favors the single-stud side, like before.' },
  { key: 'off', label: 'Off',
    desc: 'Off — no value adjustments; totals are the plain sum of each side.' },
];


export default function TradeValuesSection({ onNotice }: SettingsSectionProps) {
  // ── #214/#215 — stud-tax mode ─────────────────────────────────────────
  // 'market' (retuned default) | 'heavy' (legacy math) | 'off'. Optimistic
  // like the notification switches: flip locally, PUT, revert on error.
  const [studTax, setStudTax] = useState<StudTaxMode>('market');
  const [studTaxBusy, setStudTaxBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    getStudTaxMode()
      .then((r) => {
        if (alive && (r.mode === 'market' || r.mode === 'heavy' || r.mode === 'off')) {
          setStudTax(r.mode);
        }
      })
      .catch(() => {
        /* stay on the market default — read failure is non-fatal */
      });
    return () => {
      alive = false;
    };
  }, []);

  async function onStudTaxChange(mode: StudTaxMode) {
    if (mode === studTax || studTaxBusy) return;
    const prev = studTax;
    setStudTax(mode);
    setStudTaxBusy(true);
    try {
      await setStudTaxMode(mode);
      track('stud_tax_mode_changed', { mode }, 'Settings');
    } catch {
      setStudTax(prev);
      onNotice('Could not save the stud tax setting', 'warn');
    } finally {
      setStudTaxBusy(false);
    }
  }

  // ── Draft-pick pricing mode — REMOVED 2026-08-21 (D-144) ──────────────
  // Operator ruling: "Market slots should be default and not an opt-in or
  // even an option to flip." The state, the GET, the optimistic PUT and the
  // `pick_pricing_mode_changed` emitter all died with the control.

  const studTaxSection = (
    <>
      <View style={styles.section}>
        <TickLabel>Trade values</TickLabel>
      </View>
      <View style={styles.studTaxBlock}>
        <Text style={styles.rowKey}>Stud tax</Text>
        <View style={styles.segRow}>
          {STUD_TAX_OPTIONS.map((o) => {
            const on = o.key === studTax;
            return (
              <Pressable
                key={o.key}
                testID={`settings.stud-tax.${o.key}`}
                accessibilityRole="button"
                accessibilityState={{ selected: on, disabled: studTaxBusy }}
                accessibilityLabel={o.desc}
                disabled={studTaxBusy}
                onPress={() => onStudTaxChange(o.key)}
                style={[styles.seg, on && styles.segOn, studTaxBusy && styles.segBusy]}
              >
                <Text style={[styles.segText, on && styles.segTextOn]}>{o.label}</Text>
              </Pressable>
            );
          })}
        </View>
        <Text style={styles.rowSub}>
          {STUD_TAX_OPTIONS.find((o) => o.key === studTax)?.desc} Applies to the
          calculator and trade suggestions.
        </Text>
      </View>
    </>
  );

  // The "Pick pricing" segmented control lived here until 2026-08-21 (D-144).
  // Removed, not hidden — see the header note.

  return studTaxSection;
}
