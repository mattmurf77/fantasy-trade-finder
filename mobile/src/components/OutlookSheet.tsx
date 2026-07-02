import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Modal,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { ink, chalk, volt, semantic, space, radii, type, fonts, shadowSheet, scrim } from '../theme/chalkline';
import type { Outlook } from '../api/league';

interface Props {
  visible: boolean;
  initial?: Outlook;
  onClose: () => void;
  onSubmit: (outlook: NonNullable<Outlook>, acquirePositions: string[], tradeAwayPositions: string[]) => Promise<void>;
}

// First-time outlook bottom-sheet. Closely mirrors the web's
// outlook-overlay modal but simpler: one pick for outlook, optional
// multi-pick for position prefs. Chalkline sheet construction: ink-2
// surface, hairline border, sheet shadow, line-strong grabber, solid scrim.
const OUTLOOKS: {
  key: NonNullable<Outlook>;
  title: string;
  blurb: string;
}[] = [
  {
    key: 'championship',
    title: 'Go for the championship',
    blurb: 'Push for every win this year. Lean into vets, shed future picks.',
  },
  {
    key: 'contender',
    title: 'Contender',
    blurb: "We're in the race but not all-in. Balanced moves only.",
  },
  {
    key: 'rebuilder',
    title: 'Rebuilding',
    blurb: 'Prioritize youth + picks. Happy to move vets for future value.',
  },
  {
    key: 'jets',
    title: 'Tanking (Jets mode)',
    blurb: 'Lose early, draft high. Young-at-all-costs.',
  },
];

const POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const;

export default function OutlookSheet({ visible, initial, onClose, onSubmit }: Props) {
  const [outlook, setOutlook] = useState<NonNullable<Outlook>>(
    (initial as NonNullable<Outlook>) || 'contender',
  );
  const [acquire, setAcquire] = useState<string[]>([]);
  const [away, setAway] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (list: string[], setList: (l: string[]) => void, pos: string) => {
    setList(list.includes(pos) ? list.filter((p) => p !== pos) : [...list, pos]);
  };

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(outlook, acquire, away);
      onClose();
    } catch (e: any) {
      setError(e?.message || 'Could not save outlook');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} />
      <View style={styles.sheet}>
        <View style={styles.grabber} />
        <Text style={type.heading}>What's your team outlook?</Text>
        <Text style={type.bodySm}>
          We'll use this to bias trade suggestions toward what you actually want.
        </Text>

        <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
          {OUTLOOKS.map((o) => {
            const selected = o.key === outlook;
            return (
              <Pressable
                key={o.key}
                onPress={() => setOutlook(o.key)}
                style={({ pressed }) => [
                  styles.outlookRow,
                  selected && styles.outlookRowSel,
                  pressed && styles.outlookRowPressed,
                ]}
              >
                <View style={{ flex: 1 }}>
                  <Text style={type.title}>{o.title}</Text>
                  <Text style={[type.bodySm, styles.outlookBlurb]}>{o.blurb}</Text>
                </View>
              </Pressable>
            );
          })}

          <Text style={[type.label, styles.posHeader]}>Positions you want to acquire</Text>
          <View style={styles.posRow}>
            {POSITIONS.map((p) => {
              const selected = acquire.includes(p);
              return (
                <Pressable
                  key={p}
                  onPress={() => toggle(acquire, setAcquire, p)}
                  style={({ pressed }) => [
                    styles.posChip,
                    (selected || pressed) && styles.posChipSel,
                  ]}
                >
                  <Text style={[type.label, selected && styles.posTextSel]}>{p}</Text>
                </Pressable>
              );
            })}
          </View>

          <Text style={[type.label, styles.posHeader]}>Positions you're willing to trade away</Text>
          <View style={styles.posRow}>
            {POSITIONS.map((p) => {
              const selected = away.includes(p);
              return (
                <Pressable
                  key={p}
                  onPress={() => toggle(away, setAway, p)}
                  style={({ pressed }) => [
                    styles.posChip,
                    (selected || pressed) && styles.posChipSel,
                  ]}
                >
                  <Text style={[type.label, selected && styles.posTextSel]}>{p}</Text>
                </Pressable>
              );
            })}
          </View>
        </ScrollView>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        {/* Composed primary button: the chalkline Button has no loading/spinner
            state, and we keep the in-flight spinner behavior. */}
        <Pressable
          disabled={submitting}
          onPress={handleSubmit}
          style={({ pressed }) => [
            styles.submit,
            pressed && styles.submitPressed,
            submitting && styles.submitDisabled,
          ]}
        >
          {submitting ? (
            <ActivityIndicator color={volt.on} />
          ) : (
            <Text style={styles.submitText}>Save outlook</Text>
          )}
        </Pressable>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: scrim,
  },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '90%',
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    padding: space.lg,
    gap: space.md,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.xs,
  },
  scroll: { maxHeight: 420 },
  outlookRow: {
    flexDirection: 'row',
    gap: space.md,
    padding: space.md,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
    marginBottom: space.sm,
    alignItems: 'center',
    minHeight: 44,
  },
  outlookRowSel: { borderColor: volt.base },
  outlookRowPressed: { backgroundColor: ink.ink3 },
  outlookBlurb: { marginTop: 2 },
  posHeader: {
    marginTop: space.lg,
    marginBottom: space.sm,
  },
  posRow: { flexDirection: 'row', gap: space.sm },
  posChip: {
    flex: 1,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  posChipSel: {
    borderColor: ink.lineStrong,
    backgroundColor: ink.ink3,
  },
  posTextSel: { color: chalk.base },
  error: { ...type.bodySm, color: semantic.neg },
  submit: {
    backgroundColor: volt.base,
    borderRadius: radii.sm,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: space.md,
  },
  submitPressed: { backgroundColor: volt.press },
  submitDisabled: { opacity: 0.45 },
  submitText: {
    fontFamily: fonts.uiSemi,
    fontSize: 14,
    color: volt.on,
  },
});
