// Mock setup — a CONFIRMATION, not an interrogation (draft-extensions W2).
//
// Three controls, two of them pre-filled from the board payload the room
// already holds, and one that is deliberately read-only:
//
//   · "You're drafting for" — read-only. `user_owner_id` IS the session
//     user and drafting for another team is explicitly out of v1; a
//     disabled-looking picker would advertise a capability the engine does
//     not have.
//   · Rounds — stepper, 1..8 (`ROOKIE_MAX_ROUNDS`; the route 400s
//     `not_rookie_draft` outside that, so the stepper's clamp IS the
//     contract). Pre-filled from the real draft's round count when the
//     board knows it — the route's own default is a flat 4 (gap G9), so
//     passing it is the client's job.
//   · Linear | Snake — pre-filled from... nothing, today. The board payload
//     carries `rounds` but NOT the draft `type` (gap G6), so this defaults
//     to linear and the sheet says so rather than implying it read the
//     league.
//
// The honest-state rule lands BEFORE the commit: when the platform has not
// published an order we say we will shuffle one and label it, rather than
// inventing an order and calling it real (KD-6).
//
// Modal ⇒ no FeedbackFAB (root CLAUDE.md: "Exceptions: modals/sheets").

import React, { useEffect, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '../chalkline';
import {
  chalk,
  flare,
  ice,
  ink,
  radii,
  scrim,
  semantic,
  shadowSheet,
  space,
  type,
} from '../../theme/chalkline';
import type { MockDraftMode, MockDraftType } from '../../api/mockDraft';

/** Mirrors `mock_draft_service._ROOKIE_MAX_ROUNDS` / `DEFAULT_ROUNDS`. */
export const MOCK_MIN_ROUNDS = 1;
export const MOCK_MAX_ROUNDS = 8;
export const MOCK_DEFAULT_ROUNDS = 4;

export interface MockSetupResult {
  rounds: number;
  type: MockDraftType;
  mode: MockDraftMode;
}

export default function MockSetupSheet({
  visible,
  teamLabel,
  teams,
  defaultRounds,
  orderAssigned,
  busy = false,
  error,
  onClose,
  onStart,
}: {
  visible: boolean;
  /** "Matt — Lakeview Dynasty". Read-only by design. */
  teamLabel: string;
  teams: number | null;
  /** The real draft's round count when the board published one. */
  defaultRounds: number | null;
  /** `order_confidence === 'assigned'` — drives the KD-6 disclosure. */
  orderAssigned: boolean;
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
  onStart: (result: MockSetupResult) => void;
}) {
  const [rounds, setRounds] = useState(defaultRounds ?? MOCK_DEFAULT_ROUNDS);
  const [draftType, setDraftType] = useState<MockDraftType>('linear');
  // #305 — default CPU (plan §10 Q2): the sim loop is the feature's core,
  // and defaulting to manual would hide the repaired CPU loop the same
  // reports asked for.
  const [mode, setMode] = useState<MockDraftMode>('cpu');

  // Re-seed each time the sheet opens: the board may have refreshed since
  // the last open, and a stale pre-fill is worse than no pre-fill.
  useEffect(() => {
    if (!visible) return;
    setRounds(clampRounds(defaultRounds ?? MOCK_DEFAULT_ROUNDS));
    setDraftType('linear');
    setMode('cpu');
  }, [visible, defaultRounds]);

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <Pressable
        style={styles.backdrop}
        onPress={busy ? undefined : onClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <View style={styles.sheet} testID="mock-setup-sheet">
        <SafeAreaView edges={['bottom']} style={styles.sheetBody}>
          <View style={styles.grabber} />
          <Text style={styles.title}>Start a mock</Text>

          <View style={styles.field}>
            <Text style={styles.fieldLabel}>You’re drafting for</Text>
            <View style={styles.readonly}>
              <Text style={styles.readonlyValue} numberOfLines={1}>
                {teamLabel}
              </Text>
              <Text style={styles.readonlyTag}>fixed</Text>
            </View>
          </View>

          <View style={styles.field}>
            <Text style={styles.fieldLabel}>Rounds</Text>
            <View style={styles.stepper}>
              <StepBtn
                testID="mock-setup.rounds.minus"
                label="−"
                a11y="One fewer round"
                disabled={busy || rounds <= MOCK_MIN_ROUNDS}
                onPress={() => setRounds((r) => clampRounds(r - 1))}
              />
              <Text testID="mock-setup.rounds.value" style={styles.stepperValue}>
                {rounds}
              </Text>
              <StepBtn
                testID="mock-setup.rounds.plus"
                label="+"
                a11y="One more round"
                disabled={busy || rounds >= MOCK_MAX_ROUNDS}
                onPress={() => setRounds((r) => clampRounds(r + 1))}
              />
            </View>
          </View>

          <View style={styles.field}>
            <Text style={styles.fieldLabel}>Pick order</Text>
            <View style={styles.seg}>
              <TypeSeg
                testID="mock-setup.type.linear"
                label="Linear"
                active={draftType === 'linear'}
                disabled={busy}
                onPress={() => setDraftType('linear')}
              />
              <TypeSeg
                testID="mock-setup.type.snake"
                label="Snake"
                active={draftType === 'snake'}
                disabled={busy}
                onPress={() => setDraftType('snake')}
              />
            </View>
            <Text style={styles.fieldHint}>
              We can’t read your league’s draft type yet, so this starts on
              linear — change it if your rookie draft snakes.
            </Text>
          </View>

          {/* #305 — who makes the picks. The field label + segment reads as
              one sentence ("You pick for → Your team / Every team"), so the
              choice is self-evident without knowing how the app works. */}
          <View style={styles.field}>
            <Text style={styles.fieldLabel}>You pick for</Text>
            <View style={styles.seg}>
              <TypeSeg
                testID="mock-setup.mode.cpu"
                label="Your team"
                active={mode === 'cpu'}
                disabled={busy}
                onPress={() => setMode('cpu')}
              />
              <TypeSeg
                testID="mock-setup.mode.manual"
                label="Every team"
                active={mode === 'manual'}
                disabled={busy}
                onPress={() => setMode('manual')}
              />
            </View>
            <Text style={styles.fieldHint}>
              {mode === 'manual'
                ? 'You make each team’s pick, in draft order, from first to last.'
                : 'Computer drafters handle the other teams and stop when you’re up.'}
            </Text>
          </View>

          {!orderAssigned ? (
            <Text testID="mock-setup.order-notice" style={styles.orderNotice}>
              Your league hasn’t set a draft order, so we’ll shuffle one and
              label it. We won’t invent an order and call it real.
            </Text>
          ) : null}

          {error ? (
            <Text testID="mock-setup.error" style={styles.error}>
              {error}
            </Text>
          ) : null}

          <Button
            testID="mock-setup.start"
            label="Start"
            variant="primary"
            loading={busy}
            onPress={() => onStart({ rounds, type: draftType, mode })}
          />
          {mode === 'manual' ? (
            <Text style={styles.footNote}>
              Nothing here is written to your league. You’re making every pick
              in this mock.
            </Text>
          ) : (
            <Text style={styles.footNote}>
              Nothing here is written to your league. Computer drafters pick for
              the other {teams != null && teams > 1 ? teams - 1 : ''} teams.
            </Text>
          )}
          <Button
            testID="mock-setup.cancel"
            label="Cancel"
            variant="ghost"
            disabled={busy}
            onPress={onClose}
          />
        </SafeAreaView>
      </View>
    </Modal>
  );
}

function clampRounds(n: number): number {
  if (!Number.isFinite(n)) return MOCK_DEFAULT_ROUNDS;
  return Math.max(MOCK_MIN_ROUNDS, Math.min(MOCK_MAX_ROUNDS, Math.round(n)));
}

function StepBtn({
  label,
  a11y,
  disabled,
  onPress,
  testID,
}: {
  label: string;
  a11y: string;
  disabled: boolean;
  onPress: () => void;
  testID: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={a11y}
      accessibilityState={{ disabled }}
      style={({ pressed }) => [
        styles.stepBtn,
        pressed && { backgroundColor: ink.ink3 },
        disabled && { opacity: 0.4 },
      ]}
    >
      <Text style={styles.stepBtnText}>{label}</Text>
    </Pressable>
  );
}

function TypeSeg({
  label,
  active,
  disabled,
  onPress,
  testID,
}: {
  label: string;
  active: boolean;
  disabled: boolean;
  onPress: () => void;
  testID: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityState={{ selected: active, disabled }}
      style={({ pressed }) => [
        styles.segItem,
        active && styles.segItemActive,
        pressed && { backgroundColor: ink.ink2 },
      ]}
    >
      <Text style={[type.label, active ? styles.segTextActive : null]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    paddingHorizontal: space.lg,
    paddingBottom: space.md,
    ...shadowSheet,
  },
  sheetBody: { gap: space.md },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginTop: space.sm,
  },
  title: { ...type.title },

  field: { gap: space.sm },
  fieldLabel: { ...type.label, color: chalk.dim },
  fieldHint: { ...type.bodySm, fontSize: 11, color: chalk.faint },

  readonly: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minHeight: 44,
  },
  readonlyValue: { ...type.bodySm, color: chalk.base, flex: 1 },
  readonlyTag: { ...type.bodySm, fontSize: 11, color: chalk.faint },

  stepper: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  stepBtn: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: ink.ink1,
  },
  stepBtnText: { ...type.data, color: ice.base },
  stepperValue: {
    ...type.data,
    color: chalk.base,
    minWidth: 64,
    textAlign: 'center',
  },

  seg: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  segItem: {
    flex: 1,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  segItemActive: { backgroundColor: ink.ink3, borderBottomColor: ice.base },
  segTextActive: { color: chalk.base },

  orderNotice: {
    ...type.bodySm,
    color: chalk.base,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: flare.base,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  error: { ...type.bodySm, color: semantic.neg },
  footNote: { ...type.bodySm, fontSize: 11, color: chalk.faint, textAlign: 'center' },
});
