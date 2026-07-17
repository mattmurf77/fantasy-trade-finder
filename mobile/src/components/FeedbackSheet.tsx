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
  space,
  radii,
  type,
  fonts,
  scrim,
  shadowSheet,
} from '../theme/chalkline';
import { Button } from './chalkline';
import { useFeedback, type FeedbackSeverity } from '../state/useFeedback';

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

// Modal-based bottom sheet for capturing a single feedback note. Keyboard-
// avoiding so the text area doesn't get hidden on smaller phones. Resets
// to defaults on close so reopening is always a clean slate.
export default function FeedbackSheet({ visible, onClose, defaultScreen }: Props) {
  const [severity, setSeverity] = useState<FeedbackSeverity>('bug');
  const [screen, setScreen] = useState(defaultScreen);
  const [text, setText] = useState('');
  const inputRef = useRef<TextInput>(null);
  const add = useFeedback((s) => s.add);

  // Re-seed screen whenever the sheet opens (it may have changed since the
  // last open). Reset other fields too.
  useEffect(() => {
    if (visible) {
      setScreen(defaultScreen);
      setText('');
      setSeverity('bug');
      // Small delay so the modal animation finishes before the keyboard
      // pops — otherwise the keyboard appears before the modal is fully
      // settled and the layout jitters.
      const t = setTimeout(() => inputRef.current?.focus(), 250);
      return () => clearTimeout(t);
    }
  }, [visible, defaultScreen]);

  async function onSave() {
    const trimmed = text.trim();
    if (!trimmed) {
      onClose();
      return;
    }
    await add({
      screen: screen.trim() || 'Unknown',
      severity,
      text: trimmed,
      app_version: Constants.expoConfig?.version,
    });
    onClose();
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <Pressable style={styles.backdrop} onPress={onClose} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.kav}
      >
        <View style={styles.sheet}>
          <View style={styles.grabber} />
          <Text style={styles.title}>Capture feedback</Text>
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
              onChangeText={setText}
              style={styles.noteInput}
              placeholder="What did you notice?"
              placeholderTextColor={chalk.faint}
              multiline
              textAlignVertical="top"
            />
          </ScrollView>

          <View style={styles.actions}>
            <Button
              variant="secondary"
              label="Cancel"
              onPress={onClose}
              style={styles.actionBtn}
            />
            <Button
              testID="feedback.save-btn"
              variant="primary"
              label="Save"
              onPress={onSave}
              disabled={!text.trim()}
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

  actions: {
    flexDirection: 'row',
    gap: space.md,
    marginTop: space.lg,
  },
  actionBtn: { flex: 1 },
});
