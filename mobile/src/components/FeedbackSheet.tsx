import React, { useEffect, useRef, useState } from 'react';
import {
  Modal,
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import Constants from 'expo-constants';
import {
  ink,
  chalk,
  ice,
  semantic,
  space,
  radii,
  type,
  fonts,
  scrim,
  shadowSheet,
} from '../theme/chalkline';
import { Button } from './chalkline';
import { useFeedback, type FeedbackSeverity } from '../state/useFeedback';
import { FEEDBACK_TEXT_MAX } from '../api/feedback';
import { useFlag } from '../state/useFeatureFlags';

interface Props {
  visible: boolean;
  onClose: () => void;
  // Best-effort label of the screen the user was on when they opened the
  // sheet. Auto-filled by the FAB; the user can override before saving.
  defaultScreen: string;
}

const SEVERITY_OPTIONS: { value: FeedbackSeverity; label: string }[] = [
  { value: 'bug',    label: 'Bug'    },
  { value: 'polish', label: 'Polish' },
  { value: 'idea',   label: 'Idea'   },
];

// Thousands separators without Intl — Hermes may ship without full ICU (see
// the same caveat on X-User-TZ in api/client.ts).
function groupDigits(n: number): string {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

const MAX_LABEL = groupDigits(FEEDBACK_TEXT_MAX);

// Shown while the note exceeds the cap. Names the exact overshoot so the fix
// is concrete, and says the text is still there — Save is held, not the note.
function overflowMessage(length: number): string {
  const over = length - FEEDBACK_TEXT_MAX;
  return `Too long to send — trim ${groupDigits(over)} character${over === 1 ? '' : 's'}. Your text is still here.`;
}

// Shown when the note synced OK locally but the POST failed. Deliberately
// says "saved, not sent" — the item IS still in AsyncStorage and retrySync()
// will re-attempt it, so telling the user it was lost would be wrong.
const SAVE_FAILED_MESSAGE =
  'Saved on this device, but not sent yet. Nothing is lost — retry it from Settings → Testing → Test feedback.';

// Modal-based bottom sheet for capturing a single feedback note. Keyboard-
// avoiding so the text area doesn't get hidden on smaller phones.
//
// Flag `ux.sheet_guard` OFF (default): resets to defaults on open so
// reopening is always a clean slate — a stray backdrop tap loses the note.
// Flag ON (teardown PRD 01-01, S1A-02): the typed note is a DRAFT — any
// dismiss path (backdrop, Android back, Cancel) keeps it, and reopening
// restores it (the PRD's preferred no-dialog variant). Only a successful
// Save clears it. The sheet stays mounted with `visible` toggling, so
// component state IS the draft store — no persistence layer needed.
export default function FeedbackSheet({ visible, onClose, defaultScreen }: Props) {
  const [severity, setSeverity] = useState<FeedbackSeverity>('bug');
  const [screen, setScreen] = useState(defaultScreen);
  const [text, setText] = useState('');
  // In-flight POST (add() awaits the round-trip) and the failure notice from
  // the last Save attempt. Both are transient — cleared on edit and on open.
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const inputRef = useRef<TextInput>(null);
  const add = useFeedback((s) => s.add);
  const guardOn = useFlag('ux.sheet_guard');

  // Gate on the TRIMMED length: that's what onSave posts, and what the
  // backend measures. No `maxLength` on the input — silently truncating a
  // long note is the same data loss as silently dropping it. The user keeps
  // typing; the counter turns red and Save is held until they trim.
  const noteLength = text.trim().length;
  const overLimit = noteLength > FEEDBACK_TEXT_MAX;

  // Re-seed screen whenever the sheet opens (it may have changed since the
  // last open). Reset other fields too — unless the guard flag is on and a
  // draft note exists, in which case restore everything as the user left it.
  useEffect(() => {
    if (visible) {
      // Stale notice from a previous attempt — never greet a fresh open with it.
      setSaveFailed(false);
      if (guardOn && text.trim()) {
        // Draft restore: keep note + severity + screen override. Only
        // backfill the screen field if the user blanked it.
        if (!screen.trim()) setScreen(defaultScreen);
      } else {
        setScreen(defaultScreen);
        setText('');
        setSeverity('bug');
      }
      // Small delay so the modal animation finishes before the keyboard
      // pops — otherwise the keyboard appears before the modal is fully
      // settled and the layout jitters.
      const t = setTimeout(() => inputRef.current?.focus(), 250);
      return () => clearTimeout(t);
    }
    // `text`/`screen`/`guardOn` intentionally not in deps: this effect only
    // runs on open/close transitions and reads the values current at that
    // moment (the closure re-captures every render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, defaultScreen]);

  async function onSave() {
    const trimmed = text.trim();
    if (!trimmed) {
      onClose();
      return;
    }
    // Belt-and-braces: Save is already disabled past the cap.
    if (trimmed.length > FEEDBACK_TEXT_MAX) return;

    setSaveFailed(false);
    setSaving(true);
    try {
      const saved = await add({
        screen: screen.trim() || 'Unknown',
        severity,
        text: trimmed,
        app_version: Constants.expoConfig?.version,
      });
      if (!saved.synced) {
        // The note IS on the device (add() persisted it before POSTing), but
        // it never reached the backend. Keep the sheet open and the draft
        // intact and say so — clearing here is how long notes used to
        // vanish without a trace.
        setSaveFailed(true);
        return;
      }
      // Delivered — clear the draft so the next open starts clean (flag-off
      // gets the same net result via the reset-on-open effect above).
      setText('');
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <Pressable
        style={styles.backdrop}
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.kav}
      >
        <View style={styles.sheet}>
          <View style={styles.grabber} />
          <Text style={styles.title} accessibilityRole="header">Capture feedback</Text>
          <Text style={styles.sub}>Saved on this device. Share or export from Settings.</Text>

          <ScrollView keyboardShouldPersistTaps="handled">
            <Text style={styles.label}>Severity</Text>
            <View style={styles.sevRow}>
              {SEVERITY_OPTIONS.map((opt) => {
                const active = severity === opt.value;
                return (
                  <Pressable
                    key={opt.value}
                    testID={`feedback.severity.${opt.value}`}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: active, checked: active }}
                    accessibilityLabel={`Severity: ${opt.label}`}
                    onPress={() => setSeverity(opt.value)}
                    style={({ pressed }) => [
                      styles.sevChip,
                      active && styles.sevChipActive,
                      pressed && styles.sevChipPressed,
                    ]}
                  >
                    <Text style={[styles.sevText, active && styles.sevTextActive]}>
                      {opt.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>

            <Text style={styles.label}>Screen</Text>
            <TextInput
              value={screen}
              onChangeText={setScreen}
              accessibilityLabel="Screen"
              style={styles.screenInput}
              placeholder="e.g. Trades / Tiers / Rank-Trios"
              placeholderTextColor={chalk.faint}
              autoCorrect={false}
              autoCapitalize="none"
            />

            <Text style={styles.label}>Note</Text>
            <TextInput
              testID="feedback.note-input"
              ref={inputRef}
              value={text}
              onChangeText={(next) => {
                setText(next);
                // Any edit invalidates the previous attempt's verdict.
                if (saveFailed) setSaveFailed(false);
              }}
              accessibilityLabel="Note"
              style={[styles.noteInput, overLimit && styles.noteInputOver]}
              placeholder="What did you notice?"
              placeholderTextColor={chalk.faint}
              multiline
              textAlignVertical="top"
            />
            <Text
              testID="feedback.char-count"
              style={[styles.charCount, overLimit && styles.charCountOver]}
              accessibilityLabel={`${noteLength} of ${MAX_LABEL} characters used`}
            >
              {groupDigits(noteLength)} / {MAX_LABEL}
            </Text>
          </ScrollView>

          {overLimit ? (
            <Text testID="feedback.note-error" style={styles.notice}>
              {overflowMessage(noteLength)}
            </Text>
          ) : saveFailed ? (
            <Text testID="feedback.save-error" style={styles.notice}>
              {SAVE_FAILED_MESSAGE}
            </Text>
          ) : null}

          <View style={styles.actions}>
            <Button
              variant="secondary"
              label="Cancel"
              onPress={onClose}
              disabled={saving}
              style={styles.actionBtn}
            />
            <Button
              testID="feedback.save-btn"
              variant="primary"
              label="Save"
              onPress={onSave}
              loading={saving}
              disabled={!noteLength || overLimit}
              style={styles.actionBtn}
            />
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  kav: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    paddingBottom: space.xxl,
    maxHeight: '88%',
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  title: { ...type.heading },
  sub:   { ...type.bodySm, marginBottom: space.md },
  label: { ...type.label, marginTop: space.md, marginBottom: 6 },

  sevRow: { flexDirection: 'row', gap: space.sm },
  sevChip: {
    flex: 1,
    minHeight: 44,
    justifyContent: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: 'transparent',
    alignItems: 'center',
  },
  sevChipActive: {
    borderColor: ice.base,
  },
  // Pressed state = surface color change only (no opacity/scale).
  sevChipPressed: { backgroundColor: ink.ink3 },
  sevText:       { fontFamily: fonts.uiSemi, fontSize: 14, color: chalk.dim },
  sevTextActive: { color: ice.base },

  screenInput: {
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    minHeight: 44,
    padding: space.md,
    color: chalk.base,
    fontFamily: fonts.ui,
    fontSize: 14,
  },
  noteInput: {
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    padding: space.md,
    color: chalk.base,
    fontFamily: fonts.ui,
    fontSize: 14,
    minHeight: 120,
  },
  noteInputOver: { borderColor: semantic.neg },

  // Data numeral → Plex Mono tabular, 11px type floor (design-system.md).
  charCount: {
    alignSelf: 'flex-end',
    marginTop: 6,
    fontFamily: fonts.data,
    fontSize: 11,
    lineHeight: 14,
    fontVariant: ['tabular-nums'],
    color: chalk.dim,
  },
  charCountOver: { color: semantic.neg },

  // Pinned above the actions so it's readable with the keyboard up, whatever
  // the ScrollView is showing.
  notice: {
    ...type.bodySm,
    color: semantic.neg,
    marginTop: space.md,
  },

  actions: {
    flexDirection: 'row',
    gap: space.md,
    marginTop: space.lg,
  },
  actionBtn: { flex: 1 },
});
