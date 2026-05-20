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
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { useFeedback, type FeedbackSeverity } from '../state/useFeedback';

interface Props {
  visible: boolean;
  onClose: () => void;
  // Best-effort label of the screen the user was on when they opened the
  // sheet. Auto-filled by the FAB; the user can override before saving.
  defaultScreen: string;
}

const SEVERITY_OPTIONS: { value: FeedbackSeverity; label: string; emoji: string }[] = [
  { value: 'bug',    label: 'Bug',    emoji: '🐞' },
  { value: 'polish', label: 'Polish', emoji: '✨' },
  { value: 'idea',   label: 'Idea',   emoji: '💡' },
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
          <View style={styles.handle} />
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
                    onPress={() => setSeverity(opt.value)}
                    style={({ pressed }) => [
                      styles.sevChip,
                      active && styles.sevChipActive,
                      pressed && { opacity: 0.7 },
                    ]}
                  >
                    <Text style={[styles.sevText, active && styles.sevTextActive]}>
                      {opt.emoji}  {opt.label}
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
              placeholderTextColor={colors.muted}
              autoCorrect={false}
              autoCapitalize="none"
            />

            <Text style={styles.label}>Note</Text>
            <TextInput
              ref={inputRef}
              value={text}
              onChangeText={setText}
              style={styles.noteInput}
              placeholder="What did you notice?"
              placeholderTextColor={colors.muted}
              multiline
              textAlignVertical="top"
            />
          </ScrollView>

          <View style={styles.actions}>
            <Pressable
              onPress={onClose}
              style={({ pressed }) => [styles.cancel, pressed && { opacity: 0.7 }]}
            >
              <Text style={styles.cancelText}>Cancel</Text>
            </Pressable>
            <Pressable
              onPress={onSave}
              disabled={!text.trim()}
              style={({ pressed }) => [
                styles.save,
                !text.trim() && styles.saveDisabled,
                pressed && text.trim() && { opacity: 0.85 },
              ]}
            >
              <Text style={styles.saveText}>Save</Text>
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.55)' },
  kav: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: colors.bg,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xxl,
    maxHeight: '88%',
  },
  handle: {
    alignSelf: 'center',
    width: 44,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.border,
    marginBottom: spacing.sm,
  },
  title:    { color: colors.text,  fontSize: fontSize.xl, fontWeight: '800' },
  sub:      { color: colors.muted, fontSize: fontSize.sm, marginBottom: spacing.md },
  label:    { color: colors.muted, fontSize: fontSize.xs, marginTop: spacing.md, marginBottom: 6, fontWeight: '700', letterSpacing: 0.4, textTransform: 'uppercase' },

  sevRow: { flexDirection: 'row', gap: spacing.sm },
  sevChip: {
    flex: 1,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: 'center',
  },
  sevChipActive: {
    borderColor: colors.accent,
    backgroundColor: 'rgba(79,124,255,0.18)',
  },
  sevText:       { color: colors.text, fontSize: fontSize.sm, fontWeight: '700' },
  sevTextActive: { color: colors.accent },

  screenInput: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.text,
    fontSize: fontSize.base,
  },
  noteInput: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.text,
    fontSize: fontSize.base,
    minHeight: 120,
  },

  actions: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.lg,
  },
  cancel: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  cancelText: { color: colors.muted, fontWeight: '700' },
  save: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.accent,
  },
  saveDisabled: { opacity: 0.4 },
  saveText: { color: '#fff', fontWeight: '800' },
});
