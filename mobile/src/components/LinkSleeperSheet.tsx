import React, { useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Modal,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from 'react-native';
import { ink, chalk, semantic, space, radii, type, shadowSheet, scrim } from '../theme/chalkline';
import { Button } from './chalkline';
import { ApiError } from '../api/client';
import { linkSleeperUsername, type LinkSleeperResponse } from '../api/auth';

// ── The Sleeper-identity link form (account-first P2.6), extracted ────────
//
// P0-5 / S-20. This was inline in SettingsScreen; the account-only league
// picker needs the same form, and two copies of a flow whose failure mode is
// DELETING THE WRONG RANKING BOARD (the 409 `merge_choice_required` Alert
// below) is not a thing this codebase should own. Single owner, two mount
// points:
//
//   • SettingsScreen  → renders <LinkSleeperForm> inside its existing <Card>
//     (its surface is an inline card, not a modal — unchanged by the move).
//   • LeaguePicker    → renders <LinkSleeperSheet>, the Modal wrapper below,
//     because its companion state has no card to host a form.
//
// This is the SLEEPER IDENTITY link, not league linking: on success the
// session stops being account-only and becomes keyed to a real Sleeper user.
// Every session mutation (setUser / setLeague / invalidate) and any
// navigation belongs to the CALLER — Settings replaces into LeaguePicker,
// the picker stays put and repaints itself. That split is why `onLinked`
// hands the whole response back instead of doing the work here.
//
// Merge rules live server-side; a 409 merge_choice_required means both the
// account board AND the Sleeper username's board have data — the user must
// pick a side explicitly (no silent data loss).

export interface LinkSleeperFormProps {
  /** Fired after /api/account/link-sleeper succeeds. The caller owns every
   *  session mutation (setUser / setLeague / invalidate) and any navigation —
   *  Settings replaces into LeaguePicker, the picker stays put. */
  onLinked: (res: LinkSleeperResponse) => void | Promise<void>;
  /** Non-Alert failure surface. Settings passes its Toast; when omitted the
   *  form renders the message inline (testID `link-sleeper.error`). The 409
   *  two-boards case is ALWAYS an Alert and never routed here. */
  onNotice?: (msg: string, tone: 'warn') => void;
  /** Lets a host chrome refuse dismissal mid-request. Not state the form
   *  owns — a pure notification, used by the sheet below. */
  onBusyChange?: (busy: boolean) => void;
}

/** The form body only — no chrome. Settings renders it inside its existing
 *  <Card>; the sheet below wraps it in a Modal. */
export function LinkSleeperForm({ onLinked, onNotice, onBusyChange }: LinkSleeperFormProps) {
  const [linkUsername, setLinkUsername] = useState('');
  const [linkBusy, setLinkBusyState] = useState(false);
  const [inlineError, setInlineError] = useState<string | null>(null);

  function setLinkBusy(b: boolean) {
    setLinkBusyState(b);
    onBusyChange?.(b);
  }

  // The non-Alert failure surface. Deliberately KEPT AT THE `setToast(...)`
  // call shape the handler below used in SettingsScreen so that the moved
  // handler is a byte-for-byte diff against the region it came from — the
  // reviewer's whole job on this hunk (hld.md §8 R8). Routes to the host's
  // notice callback when there is one, inline text when there isn't.
  function setToast(t: { msg: string; tone: 'warn' }) {
    if (onNotice) onNotice(t.msg, t.tone);
    else setInlineError(t.msg);
  }

  // ── moved VERBATIM from SettingsScreen (only the four caller lines — the
  //    setUser / setLeague / invalidate / navigation.replace block — were
  //    removed, and replaced by the single onLinked hand-off). Do not
  //    reformat: this hunk is reviewed as a byte diff.
  async function handleLinkSleeper(strategy?: 'keep_sleeper' | 'keep_account') {
    const uname = linkUsername.trim();
    if (!uname || linkBusy) return;
    setLinkBusy(true);
    setInlineError(null);
    try {
      const res = await linkSleeperUsername(uname, strategy);
      // Session is now keyed to the real Sleeper user — the CALLER updates
      // the saved user, drops the sentinel league, and decides where (or
      // whether) to navigate.
      await onLinked(res);
    } catch (e: any) {
      const body = e instanceof ApiError ? (e.body as any) : null;
      if (body?.error === 'merge_choice_required') {
        const acctSwipes = body.account_board?.swipes ?? 0;
        const slpSwipes = body.sleeper_board?.swipes ?? 0;
        Alert.alert(
          'Two boards found',
          `Your account has rankings here (${acctSwipes} comparisons) and ` +
            `@${uname} already has rankings too (${slpSwipes} comparisons). ` +
            'Which board do you want to keep? The other is deleted.',
          [
            { text: 'Cancel', style: 'cancel' },
            {
              text: 'Keep this board',
              onPress: () => void handleLinkSleeper('keep_account'),
            },
            {
              text: `Keep @${uname}'s board`,
              onPress: () => void handleLinkSleeper('keep_sleeper'),
            },
          ],
        );
      } else if (body?.error === 'sleeper_already_claimed') {
        setToast({
          msg: 'That Sleeper account is already verified by another sign-in.',
          tone: 'warn',
        });
      } else {
        setToast({ msg: e?.message || "Couldn't link that username.", tone: 'warn' });
      }
    } finally {
      setLinkBusy(false);
    }
  }

  return (
    <View style={styles.connectBody}>
      <Text style={styles.connectHelp}>
        Link your Sleeper username to load your leagues. Your rankings come
        with you.
      </Text>
      <TextInput
        testID="settings.link-sleeper-input"
        value={linkUsername}
        onChangeText={setLinkUsername}
        placeholder="Sleeper username"
        placeholderTextColor={chalk.faint}
        autoCapitalize="none"
        autoCorrect={false}
        editable={!linkBusy}
        style={styles.connectInput}
      />
      {inlineError ? (
        <Text testID="link-sleeper.error" style={styles.error}>
          {inlineError}
        </Text>
      ) : null}
      <Button
        label={linkBusy ? 'Linking…' : 'Link Sleeper username'}
        onPress={() => void handleLinkSleeper()}
        disabled={!linkUsername.trim() || linkBusy}
      />
    </View>
  );
}

export interface LinkSleeperSheetProps extends LinkSleeperFormProps {
  visible: boolean;
  onClose: () => void;
}

/** Modal presentation for surfaces that have no card to host the form
 *  (LeaguePicker's companion state). Structurally the same shell as
 *  PlatformLinkSheet so the two sheets on that screen read as siblings.
 *
 *  Holds no state and no logic: the busy flag arrives from the form as a
 *  notification and lives in a ref purely so a dismissal cannot land
 *  mid-request — the same rule PlatformLinkSheet.requestClose applies, and
 *  the reason it matters here is the 409 two-boards Alert, which must never
 *  be yanked out from under a user who is choosing which board to delete. */
export default function LinkSleeperSheet({
  visible,
  onClose,
  onBusyChange,
  ...rest
}: LinkSleeperSheetProps) {
  const busyRef = useRef(false);

  function requestClose() {
    if (busyRef.current) return;
    onClose();
  }

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={requestClose}>
      <Pressable
        style={styles.backdrop}
        onPress={requestClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.kav}
      >
        <View style={styles.sheet}>
          <View style={styles.grabber} />
          <Text style={type.heading} accessibilityRole="header">
            Link your Sleeper username
          </Text>
          <LinkSleeperForm
            {...rest}
            onBusyChange={(b) => {
              busyRef.current = b;
              onBusyChange?.(b);
            }}
          />
          <Button
            label="Cancel"
            variant="ghost"
            onPress={requestClose}
            style={styles.cancel}
          />
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

// `connectBody` / `connectHelp` / `connectInput` are COPIED from
// SettingsScreen, not moved: three other Settings cards use the same styles
// and deleting them there would break unrelated UI.
const styles = StyleSheet.create({
  connectBody: { gap: space.md },
  connectHelp: type.bodySm,
  connectInput: {
    ...type.body,
    height: 44,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
  },
  error: { ...type.bodySm, color: semantic.neg },
  // Sheet shell — mirrors PlatformLinkSheet's.
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  kav: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    maxHeight: '88%',
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  cancel: { marginTop: space.xs },
});
