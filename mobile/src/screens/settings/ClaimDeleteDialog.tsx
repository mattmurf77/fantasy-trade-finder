// The claim-only "Delete account" dialog (#354 M11; G4 strings).
//
// Shown instead of the two-step deletion alerts when the session is an
// unverified ESPN/MFL entry claim (claimOnlyCopy.claimPlatform + no verified
// session). It says what the server's claim-only branch actually does — sign
// out and remove what this device added — and asks for a typed DELETE before
// the destructive button enables. Bottom sheet on the FeedbackSheet pattern:
// Chalkline tokens, solid scrim (no blur), radius ≤ 8.
//
// Every visible string comes from claimOnlyCopy.ts. Never "Account deleted"
// here (the G4 hard rule), pinned by tests/check-account-delete-paths.js.

import React, { useEffect, useState } from 'react';
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';

import { ink, chalk, space, radii, type, fonts, scrim, shadowSheet } from '../../theme/chalkline';
import { Button, Text } from '../../components/chalkline';
import {
  G4_CONFIRM_CANCEL,
  G4_CONFIRM_PRIMARY,
  G4_CONFIRM_PROMPT,
  G4_CONFIRM_WORD,
  G4_DELETE_TITLE,
  g4DeleteBody,
  type ClaimPlatform,
} from './claimOnlyCopy';

interface Props {
  visible: boolean;
  platform: ClaimPlatform;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export default function ClaimDeleteDialog({ visible, platform, busy, onCancel, onConfirm }: Props) {
  const [typed, setTyped] = useState('');
  // A fresh, empty field on every open.
  useEffect(() => {
    if (visible) setTyped('');
  }, [visible]);
  const matches = typed.trim() === G4_CONFIRM_WORD;

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onCancel}>
      <Pressable style={styles.backdrop} onPress={busy ? undefined : onCancel} accessible={false} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.kav}
      >
        <View testID="settings.claim-delete.dialog" style={styles.sheet}>
          <View style={styles.grabber} />
          <Text variant="heading" accessibilityRole="header">{G4_DELETE_TITLE}</Text>
          <Text variant="bodySm" style={styles.body}>{g4DeleteBody(platform)}</Text>

          <Text variant="label" style={styles.label}>{G4_CONFIRM_PROMPT}</Text>
          <TextInput
            testID="settings.claim-delete.input"
            value={typed}
            onChangeText={setTyped}
            placeholder={G4_CONFIRM_WORD}
            placeholderTextColor={chalk.faint}
            accessibilityLabel={G4_CONFIRM_PROMPT}
            autoCapitalize="characters"
            autoCorrect={false}
            editable={!busy}
            style={styles.input}
          />

          <View style={styles.actions}>
            <Button
              testID="settings.claim-delete.cancel"
              variant="secondary"
              label={G4_CONFIRM_CANCEL}
              onPress={onCancel}
              disabled={busy}
              style={styles.actionBtn}
            />
            <Button
              testID="settings.claim-delete.confirm"
              variant="pass"
              label={G4_CONFIRM_PRIMARY}
              onPress={onConfirm}
              disabled={!matches}
              loading={busy}
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
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  body: { marginTop: space.sm },
  label: { ...type.label, marginTop: space.lg, marginBottom: 6 },
  input: {
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    minHeight: 44,
    padding: space.md,
    color: chalk.base,
    fontFamily: fonts.data,
    fontSize: 14,
  },
  actions: { flexDirection: 'row', gap: space.sm, marginTop: space.lg },
  actionBtn: { flex: 1 },
});
