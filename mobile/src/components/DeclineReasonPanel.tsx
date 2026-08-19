import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  StyleSheet,
  Pressable,
  TextInput,
  Keyboard,
  Dimensions,
  type LayoutChangeEvent,
} from 'react-native';
import { ink, chalk, ice, space, radii, type, fonts } from '../theme/chalkline';
import { Text } from './chalkline';
import {
  FREE_TEXT_MAX,
  type Layer1Code,
  type Layer2Code,
} from '../api/declineReasons';

// DeclineReasonPanel — the trade card's two-layer pass capture.
// Flag `feedback.decline_reasons`; spec docs/plans/decline-reason-capture/SPEC.md;
// approved prototype mockups/decline-reason-capture/07-two-step-diagnostic.html.
//
// Layer 1 is three tiles on ONE row (Value · Fit · Neither) and it IS the pass:
// tapping a tile commits the disposition and the reason in a single gesture,
// which is why the card's ✕ is gone whenever this panel is mounted. Layer 2
// opens full-width beneath the tiles, notched to the tile that opened it —
// never a separate screen, never a sheet. Picking an option writes and the
// host advances the deck: there is NO receipt, the next trade is the
// confirmation.
//
// The panel owns only its OWN interaction state. Every commit is handed
// straight to the host (TradesScreen), which owns the writes, the analytics
// and the deck advance — see SPEC §3 for why nothing here batches.
//
// Two constructions the Chalkline system does not yet name (flagged in
// docs/plans/decline-reason-capture/scope-mobile.md §4 as components.md
// candidates): the SELECTABLE OPTION ROW (dot + wrapping label, ice on
// select) and the NOTCHED PANEL (ice-bordered ink-2 well with a rotated
// hairline square pointing at its opener). Both are built from existing
// tokens only — no new colors, radii or type sizes.

// ── Taxonomy (SPEC §2 — exact labels and codes, do not improvise) ─────────
interface OptionSpec {
  code: Layer2Code;
  label: string;
  /** "Other" rows: bank the code first, THEN reveal the text box (SPEC §3.3). */
  free?: boolean;
  testID: string;
}
interface TileSpec {
  key: Layer1Code;
  name: string;
  sub: string;
  options: OptionSpec[];
  testID: string;
  placeholder: string;
}

const TILES: readonly TileSpec[] = [
  {
    key: 'value',
    name: 'Value',
    sub: 'the price',
    testID: 'trades.pass-reason.value',
    placeholder: 'What was off about the value?',
    options: [
      { code: 'value_giving', label: 'Giving up too much', testID: 'trades.pass-reason.l2.value_giving' },
      { code: 'value_getting', label: 'Getting too much', testID: 'trades.pass-reason.l2.value_getting' },
      { code: 'value_other', label: 'Other', free: true, testID: 'trades.pass-reason.l2.value_other' },
    ],
  },
  {
    key: 'fit',
    name: 'Fit',
    sub: 'my roster',
    testID: 'trades.pass-reason.fit',
    placeholder: 'What was off about the fit?',
    options: [
      { code: 'fit_outlook', label: "Doesn't meet my team outlook", testID: 'trades.pass-reason.l2.fit_outlook' },
      { code: 'fit_new_weakness', label: 'Creating a new weakness', testID: 'trades.pass-reason.l2.fit_new_weakness' },
      { code: 'fit_duplicate', label: 'Addressing the same need twice', testID: 'trades.pass-reason.l2.fit_duplicate' },
      { code: 'fit_other', label: 'Other', free: true, testID: 'trades.pass-reason.l2.fit_other' },
    ],
  },
  // "Neither" was free-text-ONLY until 2026-08-19. It was the largest bucket
  // of the first production burst (9 of 19 passes, 47%), and its free text was
  // overwhelmingly one reason: the tester did not want to trade a SPECIFIC
  // PLAYER — "No need to move kelce", "Don't like Troy". That is neither a
  // price judgement nor a roster-construction one, so it had nowhere to land.
  // Two codes rather than one because the free text ran in both directions
  // and each implies a different engine fix (SPEC §2 amendment, D-080):
  // `keep` = stop building packages that send MY player; `avoid` = stop
  // sourcing THEIR player for me. Order mirrors the Value tile — my side
  // first, then theirs — and "Other" stays last, as on every tile.
  {
    key: 'other',
    name: 'Neither',
    sub: 'tell us',
    testID: 'trades.pass-reason.other',
    placeholder: 'What was wrong with this trade?',
    options: [
      { code: 'other_player_keep', label: "Won't trade one of my players", testID: 'trades.pass-reason.l2.other_player_keep' },
      { code: 'other_player_avoid', label: "Don't want one of their players", testID: 'trades.pass-reason.l2.other_player_avoid' },
      { code: 'other_text', label: 'Other', free: true, testID: 'trades.pass-reason.l2.other_text' },
    ],
  },
];

/** Tile-centre positions for the layer-2 notch, as a share of the row width
 *  ((i*2+1)/6 — the prototype's arithmetic, three equal tiles). */
const NOTCH_LEFT = ['16.67%', '50%', '83.33%'] as const;
const NOTCH_SIZE = 10;

/** Clearance kept between the send button's bottom edge and the keyboard. */
const REVEAL_GAP = 12;

export interface DeclineReasonPanelProps {
  /** Layer-1 tile tap — commits the pass disposition AND the reason. */
  onLayer1: (reason: Layer1Code, switchedFrom: Layer1Code | 'none') => void;
  /** Fixed layer-2 option — commits the detail and advances the deck. */
  onLayer2Select: (reason: Layer1Code, detail: Layer2Code) => void;
  /** "Other" tapped — banks the code BEFORE the text box opens. No advance. */
  onLayer2Bank: (reason: Layer1Code, detail: Layer2Code) => void;
  /** Free-text send — upgrades the banked row and advances the deck. */
  onLayer2Send: (reason: Layer1Code, detail: Layer2Code, freeText: string) => void;
  /** Ask the host to scroll `dy` px further down so the send button clears
   *  the keyboard. Optional: without it the panel still works, the host just
   *  does not scroll. */
  onRevealRequest?: (dy: number) => void;
}

export default function DeclineReasonPanel({
  onLayer1,
  onLayer2Select,
  onLayer2Bank,
  onLayer2Send,
  onRevealRequest,
}: DeclineReasonPanelProps) {
  const [open, setOpen] = useState<Layer1Code | null>(null);
  // The layer-1 answer already written. Kept so a tile switch can report
  // `switched_from` — a refinement, never a reset (SPEC §3).
  const [banked, setBanked] = useState<Layer1Code | null>(null);
  const [openText, setOpenText] = useState<Layer2Code | null>(null);
  const [text, setText] = useState('');
  // Once a layer-2 commit has fired, the host is advancing the deck; ignore
  // any further taps that land during the transition.
  const committedRef = useRef(false);

  const sendRef = useRef<View>(null);
  const keyboardTopRef = useRef<number | null>(null);

  const tile = TILES.find((t) => t.key === open) ?? null;

  // ── Keyboard: the send button must never sit behind it ───────────────────
  // The composer opens BELOW the text box, so focusing the input is not
  // enough — RN's own focused-input scroll would leave the button under the
  // keyboard. We measure the button against the keyboard's top edge and ask
  // the host ScrollView for exactly the overlap. Runs on keyboardDidShow AND
  // on the button's first layout (the prototype's `scrollIntoView` on open).
  const revealSend = useCallback(() => {
    const node = sendRef.current;
    if (!node || !onRevealRequest) return;
    node.measureInWindow((_x, y, _w, h) => {
      const limit = keyboardTopRef.current ?? Dimensions.get('window').height;
      const overlap = y + h + REVEAL_GAP - limit;
      if (overlap > 0) onRevealRequest(overlap);
    });
  }, [onRevealRequest]);

  useEffect(() => {
    const show = Keyboard.addListener('keyboardDidShow', (e) => {
      keyboardTopRef.current = e.endCoordinates.screenY;
      revealSend();
    });
    const hide = Keyboard.addListener('keyboardDidHide', () => {
      keyboardTopRef.current = null;
    });
    return () => {
      show.remove();
      hide.remove();
    };
  }, [revealSend]);

  const onSendLayout = useCallback((_e: LayoutChangeEvent) => revealSend(), [revealSend]);

  // ── Commits ──────────────────────────────────────────────────────────────
  function tapTile(key: Layer1Code) {
    if (committedRef.current) return;
    // Re-tapping the OPEN tile used to collapse layer 2. Once the pass is
    // banked that strands the user: the host disables ✓ and makes the swipe
    // gesture and the VoiceOver actions inert on this card, so layer 2 is the
    // only way forward and collapsing it leaves nothing to tap. Banked ⇒ the
    // re-tap is a no-op and the panel stays open (no second write either).
    if (open === key && banked) return;
    const next = open === key ? null : key; // tapping the open tile collapses it
    setOpen(next);
    setOpenText(null);
    setText('');
    if (!next) return;
    // Banked on tap — ALWAYS. A tester who stops here still leaves a complete
    // row: passed, on value. This is the whole reason there is no ✕.
    onLayer1(next, banked && banked !== next ? banked : 'none');
    setBanked(next);
  }

  function tapOption(o: OptionSpec) {
    if (committedRef.current || !tile) return;
    if (o.free) {
      // Toggle closed without a write — the code is already banked.
      if (openText === o.code) {
        setOpenText(null);
        return;
      }
      setOpenText(o.code);
      setText('');
      onLayer2Bank(tile.key, o.code); // banks BEFORE the box opens (SPEC §3.3)
      return;
    }
    committedRef.current = true;
    onLayer2Select(tile.key, o.code);
  }

  function tapSend() {
    if (committedRef.current || !tile) return;
    committedRef.current = true;
    // The composer only renders under an open "Other" row, so `openText` is
    // always set here; the fallback is the type-safe backstop and names the
    // terminal free-text code that the pre-2026-08-19 "Neither" flow wrote.
    const detail: Layer2Code = openText ?? 'other_text';
    onLayer2Send(tile.key, detail, text.trim());
  }

  // ── Free-text composer (shared by "Other" rows and Neither) ──────────────
  function composer(placeholder: string) {
    return (
      <>
        <TextInput
          testID="trades.pass-reason.text"
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder={placeholder}
          placeholderTextColor={chalk.faint}
          multiline
          autoFocus
          maxLength={FREE_TEXT_MAX}
          accessibilityLabel={placeholder}
        />
        <Pressable
          ref={sendRef}
          testID="trades.pass-reason.send"
          onLayout={onSendLayout}
          onPress={tapSend}
          accessibilityRole="button"
          accessibilityLabel="Send and go to the next trade"
          style={({ pressed }) => [styles.send, pressed && styles.sendPressed]}
        >
          <Text scale="body" style={styles.sendLabel}>
            Send &amp; next trade
          </Text>
        </Pressable>
      </>
    );
  }

  return (
    <View style={styles.block} testID="trades.pass-reasons">
      <Text scale="dense" style={styles.blockLabel}>
        PASS — WHAT&apos;S OFF?
      </Text>

      <View style={styles.tileRow}>
        {TILES.map((t) => {
          const isOpen = open === t.key;
          return (
            <Pressable
              key={t.key}
              testID={t.testID}
              onPress={() => tapTile(t.key)}
              accessibilityRole="button"
              accessibilityLabel={`Pass — ${t.name}, ${t.sub}`}
              accessibilityHint="Records the pass and opens the specific reasons"
              accessibilityState={{ expanded: isOpen, selected: banked === t.key }}
              style={({ pressed }) => [
                styles.tile,
                (pressed || isOpen) && styles.tileOpen,
              ]}
            >
              <Text scale="body" style={[styles.tileName, isOpen && styles.tileNameOpen]}>
                {t.name}
              </Text>
              <Text scale="dense" style={[styles.tileSub, isOpen && styles.tileSubOpen]}>
                {t.sub.toUpperCase()}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {tile ? (
        <View style={styles.l2}>
          <View
            style={[styles.notch, { left: NOTCH_LEFT[TILES.indexOf(tile)] }]}
            pointerEvents="none"
          />
          <Text scale="dense" style={styles.l2Label}>
            WHICH ONE?
          </Text>
          {tile.options.map((o) => {
            const sel = openText === o.code;
            return (
              <React.Fragment key={o.code}>
                <Pressable
                  testID={o.testID}
                  onPress={() => tapOption(o)}
                  accessibilityRole="button"
                  accessibilityLabel={o.label}
                  accessibilityState={{ selected: sel }}
                  style={({ pressed }) => [
                    styles.option,
                    (pressed || sel) && styles.optionSel,
                  ]}
                >
                  <View style={[styles.dot, sel && styles.dotSel]} />
                  <Text scale="body" style={styles.optionLabel}>
                    {o.label}
                  </Text>
                </Pressable>
                {sel ? composer(tile.placeholder) : null}
              </React.Fragment>
            );
          })}
        </View>
      ) : null}
    </View>
  );
}

// Mono micro-label at the Chalkline 11px type floor (teardown S2 PRD-04 — the
// prototype's 8.5–9px mono is below it). Plex Mono + uppercase + wide tracking
// is the shipped micro-label convention (TopBar's LEAGUE, tier headers).
const micro = {
  fontFamily: fonts.data,
  fontSize: 11,
  lineHeight: 14,
  letterSpacing: 1.1,
  textTransform: 'uppercase',
} as const;

const styles = StyleSheet.create({
  // Sits directly beneath the card's ✓, separated by the card's own hairline
  // rhythm — the ✕ used to be inside that row.
  block: {
    marginTop: space.md,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: ink.line,
    gap: space.sm,
  },
  blockLabel: {
    ...micro,
    color: chalk.faint,
  },
  tileRow: {
    flexDirection: 'row',
    gap: space.sm,
  },
  // 58pt floor clears the 44pt touch minimum with room for the two-line
  // label to grow under Dynamic Type (minHeight, never a fixed height).
  tile: {
    flex: 1,
    minHeight: 58,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
    paddingVertical: space.sm,
    paddingHorizontal: space.xs,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
  },
  tileOpen: {
    borderColor: ice.base,
    backgroundColor: ink.ink3,
  },
  tileName: {
    ...type.title,
    fontFamily: fonts.uiSemi,
    fontSize: 15,
    lineHeight: 20,
    textAlign: 'center',
  },
  tileNameOpen: { color: ice.base },
  tileSub: {
    ...micro,
    color: chalk.faint,
    textAlign: 'center',
  },
  tileSubOpen: { color: ice.base },

  // NOTCHED PANEL — ice-bordered ink-2 well, full width beneath the row.
  l2: {
    position: 'relative',
    borderWidth: 1,
    borderColor: ice.base,
    borderRadius: radii.sm,
    backgroundColor: ink.ink2,
    padding: space.md,
    gap: space.sm,
  },
  // Rotated hairline square, half-buried in the panel's top edge, pointing at
  // the tile that opened it. `left` is set per-tile at the call site.
  notch: {
    position: 'absolute',
    top: -(NOTCH_SIZE / 2) - 1,
    marginLeft: -(NOTCH_SIZE / 2),
    width: NOTCH_SIZE,
    height: NOTCH_SIZE,
    backgroundColor: ink.ink2,
    borderLeftWidth: 1,
    borderTopWidth: 1,
    borderLeftColor: ice.base,
    borderTopColor: ice.base,
    transform: [{ rotate: '45deg' }],
  },
  l2Label: {
    ...micro,
    color: chalk.faint,
  },

  // SELECTABLE OPTION ROW — dot + wrapping label; ice on select.
  option: {
    minHeight: 46,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
    paddingHorizontal: space.md,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
  },
  optionSel: {
    borderColor: ice.base,
    backgroundColor: ink.ink3,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrongA11y,
  },
  dotSel: { backgroundColor: ice.base },
  optionLabel: {
    ...type.body,
    // Wraps rather than truncates — no numberOfLines anywhere in this panel.
    flexShrink: 1,
  },

  input: {
    ...type.body,
    minHeight: 84,
    padding: space.md,
    textAlignVertical: 'top',
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.sm,
  },
  send: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
    backgroundColor: ice.base,
    borderRadius: radii.sm,
  },
  sendPressed: { backgroundColor: ice.press },
  sendLabel: {
    ...type.body,
    fontFamily: fonts.uiSemi,
    color: ice.on,
    textAlign: 'center',
  },
});
