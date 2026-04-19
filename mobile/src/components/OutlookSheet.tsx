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
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import type { Outlook } from '../api/league';

interface Props {
  visible: boolean;
  initial?: Outlook;
  onClose: () => void;
  onSubmit: (outlook: NonNullable<Outlook>, acquirePositions: string[], tradeAwayPositions: string[]) => Promise<void>;
}

// First-time outlook bottom-sheet. Closely mirrors the web's
// outlook-overlay modal but simpler: one pick for outlook, optional
// multi-pick for position prefs.
const OUTLOOKS: {
  key: NonNullable<Outlook>;
  title: string;
  blurb: string;
  emoji: string;
}[] = [
  {
    key: 'championship',
    title: 'Go for the championship',
    blurb: 'Push for every win this year. Lean into vets, shed future picks.',
    emoji: '🏆',
  },
  {
    key: 'contender',
    title: 'Contender',
    blurb: "We're in the race but not all-in. Balanced moves only.",
    emoji: '⚡',
  },
  {
    key: 'rebuilder',
    title: 'Rebuilding',
    blurb: 'Prioritize youth + picks. Happy to move vets for future value.',
    emoji: '🌱',
  },
  {
    key: 'jets',
    title: 'Tanking (Jets mode)',
    blurb: 'Lose early, draft high. Young-at-all-costs.',
    emoji: '✈️',
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
        <View style={styles.handle} />
        <Text style={styles.title}>What's your team outlook?</Text>
        <Text style={styles.sub}>
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
                  pressed && { opacity: 0.7 },
                ]}
              >
                <Text style={styles.outlookEmoji}>{o.emoji}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.outlookTitle, selected && { color: colors.accent }]}>
                    {o.title}
                  </Text>
                  <Text style={styles.outlookBlurb}>{o.blurb}</Text>
                </View>
              </Pressable>
            );
          })}

          <Text style={styles.posHeader}>Positions you want to acquire</Text>
          <View style={styles.posRow}>
            {POSITIONS.map((p) => {
              const selected = acquire.includes(p);
              return (
                <Pressable
                  key={p}
                  onPress={() => toggle(acquire, setAcquire, p)}
                  style={[styles.posChip, selected && styles.posChipSel]}
                >
                  <Text style={[styles.posText, selected && { color: colors.accent }]}>
                    {p}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <Text style={styles.posHeader}>Positions you're willing to trade away</Text>
          <View style={styles.posRow}>
            {POSITIONS.map((p) => {
              const selected = away.includes(p);
              return (
                <Pressable
                  key={p}
                  onPress={() => toggle(away, setAway, p)}
                  style={[styles.posChip, selected && styles.posChipSel]}
                >
                  <Text style={[styles.posText, selected && { color: colors.accent }]}>
                    {p}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </ScrollView>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Pressable
          disabled={submitting}
          onPress={handleSubmit}
          style={({ pressed }) => [
            styles.submit,
            (pressed || submitting) && { opacity: 0.85 },
            submitting && { opacity: 0.5 },
          ]}
        >
          {submitting ? (
            <ActivityIndicator color="#fff" />
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
    backgroundColor: 'rgba(0,0,0,0.55)',
  },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '90%',
    backgroundColor: colors.bg,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.lg,
    gap: spacing.md,
  },
  handle: {
    alignSelf: 'center',
    width: 44,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.border,
    marginBottom: spacing.xs,
  },
  title: { color: colors.text, fontSize: fontSize.xl, fontWeight: '800' },
  sub: { color: colors.muted, fontSize: fontSize.sm },
  scroll: { maxHeight: 420 },
  outlookRow: {
    flexDirection: 'row',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
    alignItems: 'center',
  },
  outlookRowSel: {
    borderColor: colors.accent,
    backgroundColor: 'rgba(79,124,255,0.06)',
  },
  outlookEmoji: { fontSize: 28 },
  outlookTitle: { color: colors.text, fontSize: fontSize.base, fontWeight: '800' },
  outlookBlurb: { color: colors.muted, fontSize: fontSize.xs, marginTop: 2, lineHeight: 18 },
  posHeader: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  posRow: { flexDirection: 'row', gap: spacing.sm },
  posChip: {
    flex: 1,
    paddingVertical: spacing.sm,
    alignItems: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  posChipSel: {
    borderColor: colors.accent,
    backgroundColor: 'rgba(79,124,255,0.06)',
  },
  posText: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '700' },
  error: { color: colors.red, fontSize: fontSize.xs },
  submit: {
    backgroundColor: colors.accent,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: spacing.md,
  },
  submitText: { color: '#fff', fontSize: fontSize.base, fontWeight: '800' },
});
