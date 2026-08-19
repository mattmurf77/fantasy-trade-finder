// Trade values — the stud-tax segmented control + the pick-pricing one.
//
// Extracted verbatim from SettingsScreen.tsx (origin/main):
//   • stud-tax state + fetch effect + `onStudTaxChange`      :120-155
//   • pick-pricing state + fetch effect + `onPickPricingChange` :157-189
//   • `STUD_TAX_OPTIONS` + `studTaxSection`                  :900-957
//   • `PICK_PRICING_OPTIONS` + `pickPricingSection`          :959-1004
//   • the `trade.slot_pricing` flag                          :110
//
// SECTION BANNER: OWNED HERE. The shipped stud-tax block renders its own
// <TickLabel>Trade values</TickLabel> (SettingsScreen.tsx:914-916); pick
// pricing deliberately has no second banner — it sits directly beneath.
//
// The `trade.slot_pricing` gate is preserved exactly: flag off ⇒ the pick
// pricing block is not rendered AND getPickPricingMode() is never called (the
// route 404s server-side while dark).
//
// Behavior changes: NONE, deliberately including the loading posture. Both
// controls render their DEFAULT selection ('market' / 'tier_ladder') while the
// GET is in flight and correct themselves when it lands — that is shipped
// behavior, and swapping in a skeleton here would change what the user sees on
// open. (Flagged for the plan's later phases: a default shown as selected
// before the real value arrives is the one honest-preview problem this
// section still has.)

import React, { useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { TickLabel } from '../../../components/chalkline';
import {
  getPickPricingMode,
  getStudTaxMode,
  setPickPricingMode,
  setStudTaxMode,
  type PickPricingMode,
} from '../../../api/accountPrefs';
import type { StudTaxMode } from '../../../api/calc';
import { track } from '../../../api/events';
import { useFlag } from '../../../state/useFeatureFlags';
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

// M6b — how the trade engine prices DRAFT PICKS. Same segmented control as
// the stud tax, one row below it, behind `trade.slot_pricing`.
// `tier_ladder` is the DEFAULT and is today's behaviour exactly; the market
// curve is opt-in (operator decision O2 authorised the toggle, not a
// default change — contrast #214/#215, where the retuned mode shipped ON).
const PICK_PRICING_OPTIONS: Array<{
  key: PickPricingMode; label: string; desc: string;
}> = [
  { key: 'tier_ladder', label: 'Tier ladder',
    desc: 'Tier ladder — every pick prices at its round\u2019s tier value (current behaviour).' },
  { key: 'market_slots', label: 'Market',
    desc: 'Market — picks price off the live dynasty market curve, which is steeper: a 1.01 costs more, and 2nds and 3rds cost less.' },
];

export default function TradeValuesSection({ onNotice }: SettingsSectionProps) {
  // M6b — gates the pick-pricing segmented control. Off (shipped) ⇒ the
  // section is not rendered AND /api/settings/pick-pricing is never called
  // (it 404s server-side while dark).
  const slotPricingOn = useFlag('trade.slot_pricing');

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

  // ── M6b — draft-pick pricing mode (flag `trade.slot_pricing`) ─────────
  // 'tier_ladder' (DEFAULT — today's pick ladder) | 'market_slots'
  // (DynastyProcess per-slot market curve). Same optimistic pattern as the
  // stud-tax control. NOTE the default differs from #215's: the market mode
  // is opt-in here, so a read failure must land on 'tier_ladder'.
  const [pickPricing, setPickPricing] = useState<PickPricingMode>('tier_ladder');
  const [pickPricingBusy, setPickPricingBusy] = useState(false);
  useEffect(() => {
    if (!slotPricingOn) return;
    let alive = true;
    getPickPricingMode()
      .then((r) => {
        if (alive && (r.mode === 'tier_ladder' || r.mode === 'market_slots')) {
          setPickPricing(r.mode);
        }
      })
      .catch(() => {
        /* stay on the tier_ladder default — read failure is non-fatal */
      });
    return () => {
      alive = false;
    };
  }, [slotPricingOn]);

  async function onPickPricingChange(mode: PickPricingMode) {
    if (mode === pickPricing || pickPricingBusy) return;
    const prev = pickPricing;
    setPickPricing(mode);
    setPickPricingBusy(true);
    try {
      await setPickPricingMode(mode);
      track('pick_pricing_mode_changed', { mode }, 'Settings');
    } catch {
      setPickPricing(prev);
      onNotice('Could not save the pick pricing setting', 'warn');
    } finally {
      setPickPricingBusy(false);
    }
  }

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

  const pickPricingSection = slotPricingOn ? (
    <>
      <View style={styles.studTaxBlock}>
        <Text style={styles.rowKey}>Pick pricing</Text>
        <View style={styles.segRow}>
          {PICK_PRICING_OPTIONS.map((o) => {
            const on = o.key === pickPricing;
            return (
              <Pressable
                key={o.key}
                testID={`settings.pick-pricing.${o.key}`}
                accessibilityRole="button"
                accessibilityState={{ selected: on, disabled: pickPricingBusy }}
                accessibilityLabel={o.desc}
                disabled={pickPricingBusy}
                onPress={() => onPickPricingChange(o.key)}
                style={[styles.seg, on && styles.segOn, pickPricingBusy && styles.segBusy]}
              >
                <Text style={[styles.segText, on && styles.segTextOn]}>{o.label}</Text>
              </Pressable>
            );
          })}
        </View>
        <Text style={styles.rowSub}>
          {PICK_PRICING_OPTIONS.find((o) => o.key === pickPricing)?.desc} Applies
          to the calculator and trade suggestions.
        </Text>
      </View>
    </>
  ) : null;

  return (
    <>
      {studTaxSection}
      {pickPricingSection}
    </>
  );
}
