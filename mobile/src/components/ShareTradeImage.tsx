import React, { useRef } from 'react';
import { Platform, Share, StyleSheet, Text, View } from 'react-native';
import { captureRef } from 'react-native-view-shot';

import PositionChip from './PositionChip';
import { Button } from './chalkline';
import { haptics } from '../utils/haptics';
import { chalk, fonts, ink, space, type } from '../theme/chalkline';

// Share-as-image (DynastyDealer teardown 2026-07-26, polish item 5): render
// a clean Chalkline share card of the trade — caption + both sides with
// values + verdict + a small text-only "Dynasty Trade Finder" watermark —
// to a PNG (react-native-view-shot) and hand it to the native share sheet.
// The capture view renders off-screen (absolute, far left) so it never
// affects layout; capture failure falls back to the plain text share
// (`fallbackText`) so the action always does something. Android's core
// Share API can't take a file url, so it shares the text fallback directly.
// testID `calc.share-image`. Used by TradeCalculatorScreen (live mode) and
// InLeagueCalculator (In-league mode).

export interface ShareAsset {
  id: string;
  name: string;
  position: string;
  value: number;
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
}

export default function ShareTradeImage(props: Props) {
  const shotRef = useRef<View>(null);

  const share = async () => {
    haptics.selection();
    try {
      if (Platform.OS === 'android') {
        // Core RN Share on Android is text-only — honest fallback.
        await Share.share({ message: props.fallbackText });
        return;
      }
      const uri = await captureRef(shotRef, {
        format: 'png',
        quality: 1,
        result: 'tmpfile',
      });
      await Share.share({ url: uri });
    } catch {
      try {
        await Share.share({ message: props.fallbackText });
      } catch {
        /* user dismissed or share unavailable — nothing to do */
      }
    }
  };

  const sideBlock = (title: string, assets: ShareAsset[], total: number) => (
    <View style={styles.side}>
      <Text style={styles.sideTitle}>{title}</Text>
      {assets.map((a) => (
        <View key={a.id} style={styles.assetRow}>
          <PositionChip position={a.position} size="sm" />
          <Text style={styles.assetName} numberOfLines={1}>
            {a.name}
          </Text>
          <Text style={styles.assetValue}>{Math.round(a.value).toLocaleString()}</Text>
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
          <Text style={styles.watermark}>Dynasty Trade Finder</Text>
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
  watermark: {
    fontFamily: fonts.uiSemi,
    fontSize: 11,
    lineHeight: 14,
    letterSpacing: 0.8,
    color: chalk.faint,
    textAlign: 'center',
  },
});
