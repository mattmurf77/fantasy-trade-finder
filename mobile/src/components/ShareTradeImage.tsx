import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Platform, Share, StyleSheet, Text, View } from 'react-native';
import { captureRef } from 'react-native-view-shot';

import PositionChip from './PositionChip';
import TierBadge from './TierBadge';
import { Button } from './chalkline';
import { track } from '../api/events';
import { haptics } from '../utils/haptics';
import {
  displayUrl,
  refShareUrl,
  resolveShareUrl,
  type ResolvedShareUrl,
  type ShareSurface,
} from '../utils/shareLinks';
import { useFlag } from '../state/useFeatureFlags';
import { useSession } from '../state/useSession';
import { chalk, fonts, ink, space, type } from '../theme/chalkline';
import type { Tier } from '../shared/types';

// Share-as-image (DynastyDealer teardown 2026-07-26, polish item 5): render
// a clean Chalkline share card of the trade — caption + both sides with
// values + verdict + a "Dynasty Trade Finder" wordmark AND the share URL —
// to a PNG (react-native-view-shot) and hand it to the native share sheet.
//
// audit P1-1: the card used to carry no link at all, so a recipient of the
// screenshot had nothing to type. Every artifact this component produces
// now carries a URL — the PNG footer, the iOS share message alongside the
// image, the Android text share, and the capture-failure fallback.
//
// Ordering is mint → paint → capture (LLD-p1-1-2 §5): pressing share
// resolves the best link the ladder can deliver (utils/shareLinks.ts —
// /s/p/<id> when a package can be minted, ?ref= otherwise), commits it to
// state, waits for the native view hierarchy to draw it, and only then
// captures. The URL state is SEEDED with the ?ref= rung at mount, so a lost
// race degrades rung A → rung B and the card is never link-free.
//
// The capture view renders off-screen (absolute, far left) so it never
// affects layout; capture failure falls back to the plain text share
// (`fallbackText`) so the action always does something. Android's core
// Share API can't take a file url, so it shares the text fallback directly.
// testID `calc.share-image`. Used by TradeCalculatorScreen (live mode) and
// InLeagueCalculator (In-league mode).

/** Two rAFs, not one: one yields a JS frame, which is usually but not
 *  reliably enough for the UI thread to have processed the mount. Two
 *  guarantee at least one complete UI-thread frame after the commit. A
 *  fixed setTimeout would be the "sleep and hope" pattern this codebase
 *  bans in Maestro flows, and it is no better here. */
const nextPaint = () =>
  new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));

/** Ceiling on the mint before the share proceeds with the ?ref= rung. A
 *  share that hangs is worse than a share that degrades. */
const MINT_DEADLINE_MS = 6000;

export interface ShareAsset {
  id: string;
  name: string;
  position: string;
  value: number;
  /** #277/#280 — pick-value ladder tier for PLAYER rows (same source as
   *  the calculator's TradeSide badges). Null/absent (picks, old data)
   *  falls back to the numeric value. */
  tier?: Tier | null;
}

interface Props {
  /** e.g. "The Big League · SF TEP" or "Trade idea · 1QB PPR". */
  caption: string;
  sendTitle: string;
  receiveTitle: string;
  sendAssets: ShareAsset[];
  receiveAssets: ShareAsset[];
  sendTotal: number;
  receiveTotal: number;
  /** One-line verdict, e.g. "Win–win by both boards" or "Verdict: fair". */
  verdictLine: string;
  /** Plain-text share used when image capture fails (and on Android). */
  fallbackText: string;
  /** P1-1 — the package to mint, in server order. */
  giveIds: string[];
  receiveIds: string[];
  surface: ShareSurface;
  /** P1-1 / PR-14 — true when either side holds a league draft pick. Those
   *  packages skip the mint: the landing renders picks as "Unknown player".
   *  Computed by the host from its own rows, never sniffed from the id. */
  hasPickAssets: boolean;
}

/** The mint → paint → capture states. One transition each. The armed state
 *  carries the message body decided at press time, so a prop change while
 *  the sheet is opening can't re-arm the effect and open a second sheet. */
type SharePhase =
  | { kind: 'idle' }
  | { kind: 'minting' }
  | { kind: 'armed'; message: string };

export default function ShareTradeImage(props: Props) {
  const shotRef = useRef<View>(null);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Read session + flag here rather than taking four more props — both
  // hosts already do exactly this, so it is the house pattern.
  const user = useSession((s) => s.user);
  const isDemo = useSession((s) => s.isDemo);
  const shareLandingOn = useFlag('growth.share_landing');

  // SEEDED FLOOR: the card carries the referral rung from first paint, so
  // there is no instant at which the footer is link-free — not before the
  // press, not during the mint, not if the paint barrier is wrong.
  const [link, setLink] = useState<ResolvedShareUrl>(() => refShareUrl(user?.username));
  useEffect(() => {
    setLink((cur) => (cur.rung === 'package' ? cur : refShareUrl(user?.username)));
  }, [user?.username]);

  const [phase, setPhase] = useState<SharePhase>({ kind: 'idle' });

  // Every Share.share call site in this component takes `message`, and
  // `message` always ends in the resolved URL — that is the whole point of
  // P1-1. Do not add a branch here that shares an image with no message.
  const doCapture = useCallback(async (message: string) => {
    try {
      if (Platform.OS === 'android') {
        // Core RN Share on Android is text-only — honest fallback.
        await Share.share({ message });
        return;
      }
      const uri = await captureRef(shotRef, {
        format: 'png',
        quality: 1,
        result: 'tmpfile',
      });
      // `message` alongside `url`: some share targets take both activity
      // items, some drop one. A target that drops the message still ships
      // a visible link — it is drawn into the PNG's footer.
      await Share.share({ message, url: uri });
    } catch {
      try {
        await Share.share({ message });
      } catch {
        /* user dismissed or share unavailable — nothing to do */
      }
    }
  }, []);

  const share = async () => {
    if (phase.kind !== 'idle') return; // a second tap mid-mint is a no-op
    haptics.selection();
    setPhase({ kind: 'minting' });
    const ctrl = new AbortController();
    const deadline = setTimeout(() => ctrl.abort(), MINT_DEADLINE_MS);
    const resolved = await resolveShareUrl({
      giveIds: props.giveIds,
      receiveIds: props.receiveIds,
      username: user?.username,
      enabled: shareLandingOn,
      isDemo,
      surface: props.surface,
      hasPickAssets: props.hasPickAssets,
      signal: ctrl.signal,
      onOutcome: (outcome, give_n, receive_n) =>
        track(
          'share_package_created',
          { surface: props.surface, give_n, receive_n, outcome },
          'Calculator',
        ),
    }); // never throws
    clearTimeout(deadline);
    if (!mountedRef.current) return;
    setLink(resolved);
    setPhase({ kind: 'armed', message: `${props.fallbackText}\n${resolved.url}` });
  };

  // The capture CANNOT live in `share`: captureRef snapshots the NATIVE view
  // hierarchy, and a value awaited inside the handler is not in that
  // hierarchy until React commits and the batched mount operations have been
  // flushed to the UI thread. This effect runs after the commit; nextPaint()
  // waits for the draw.
  useEffect(() => {
    if (phase.kind !== 'armed') return;
    let cancelled = false;
    void (async () => {
      await nextPaint();
      if (cancelled || !mountedRef.current) return;
      await doCapture(phase.message);
      if (!cancelled && mountedRef.current) setPhase({ kind: 'idle' });
    })();
    return () => {
      cancelled = true;
    };
  }, [phase, doCapture]);

  const sideBlock = (title: string, assets: ShareAsset[], total: number) => (
    <View style={styles.side}>
      <Text style={styles.sideTitle}>{title}</Text>
      {assets.map((a) => (
        <View key={a.id} style={styles.assetRow}>
          <PositionChip position={a.position} size="sm" />
          <Text style={styles.assetName} numberOfLines={1}>
            {a.name}
          </Text>
          {/* #277/#280 — per-player rows carry the tier label; picks keep
              the numeric value (a pick's name already reads as a rung).
              Package TOTALS below stay numeric — a sum of tiers is
              meaningless. */}
          {a.tier ? (
            // TierBadge hardcodes alignSelf:'flex-start'; re-center it in
            // this vertically-centered row.
            <View style={styles.tierSlot}>
              <TierBadge tier={a.tier} size="sm" />
            </View>
          ) : (
            <Text style={styles.assetValue}>{Math.round(a.value).toLocaleString()}</Text>
          )}
        </View>
      ))}
      <View style={styles.totalRow}>
        <Text style={styles.totalLabel}>TOTAL</Text>
        <Text style={styles.totalValue}>{Math.round(total).toLocaleString()}</Text>
      </View>
    </View>
  );

  return (
    <>
      <Button
        label="Share image"
        variant="secondary"
        testID="calc.share-image"
        // Button.loading already swaps the label for a spinner and implies
        // disabled — no new prop and no new copy for the in-flight state.
        loading={phase.kind !== 'idle'}
        onPress={share}
      />
      {/* Off-screen capture surface — rendered but never visible. */}
      <View style={styles.offscreen} pointerEvents="none">
        <View ref={shotRef} collapsable={false} style={styles.card}>
          <Text style={styles.caption}>{props.caption}</Text>
          {sideBlock(props.sendTitle, props.sendAssets, props.sendTotal)}
          <View style={styles.divider} />
          {sideBlock(props.receiveTitle, props.receiveAssets, props.receiveTotal)}
          <Text style={styles.verdict}>{props.verdictLine}</Text>
          {/* P1-1 — the footer mirrors the server's own OG card footer
              (backend/og_image.py _draw_footer) so the two artifacts read
              as one product, and so a screenshot has somewhere to go. */}
          <View style={styles.footer}>
            <Text style={styles.watermark}>Dynasty Trade Finder</Text>
            <Text
              testID="share.card-url"
              style={styles.footerUrl}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.8}
            >
              {displayUrl(link.url)}
            </Text>
          </View>
        </View>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  offscreen: { position: 'absolute', left: -9999, top: 0 },
  card: {
    width: 360,
    backgroundColor: ink.ink0,
    borderWidth: 1,
    borderColor: ink.line,
    padding: space.lg,
    gap: space.md,
  },
  caption: { ...type.label, color: chalk.dim },
  side: { gap: space.xs },
  sideTitle: { ...type.label, color: chalk.base },
  assetRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  assetName: { ...type.bodySm, color: chalk.base, flex: 1 },
  assetValue: { ...type.data, color: chalk.base },
  tierSlot: { alignSelf: 'center' },
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: ink.line,
    paddingTop: space.xs,
  },
  totalLabel: { ...type.label, color: chalk.dim },
  totalValue: { ...type.data, color: chalk.base },
  divider: { height: 1, backgroundColor: ink.line },
  verdict: { ...type.title, color: chalk.base, textAlign: 'center' },
  // The card's own gap is space.md; the wordmark and the URL are one block,
  // so they sit tighter than that and read as a single footer.
  footer: { gap: 2, alignItems: 'stretch' },
  // The watermark treatment minus the tracking — a URL is not a wordmark.
  footerUrl: {
    fontFamily: fonts.uiSemi,
    fontSize: 11,
    lineHeight: 14,
    color: chalk.faint,
    textAlign: 'center',
  },
  watermark: {
    fontFamily: fonts.uiSemi,
    fontSize: 11,
    lineHeight: 14,
    letterSpacing: 0.8,
    color: chalk.faint,
    textAlign: 'center',
  },
});
