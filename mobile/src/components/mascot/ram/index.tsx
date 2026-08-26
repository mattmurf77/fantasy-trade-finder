import React from 'react';
import { Image, View } from 'react-native';
import type { AnalystPose } from '../../analyst';

/**
 * Fleeced — the ram mascot (D-155, D-156).
 *
 * Raster sprites, not `react-native-svg`. The art is painted (pebbled
 * leather, specular horns, glowing eyes) and does not vectorise into clean
 * paths, so `mobile/assets/CLAUDE.md` carries a scoped exception naming
 * exactly this folder. Everything else in the app stays vector.
 *
 * Sizing: `size` is the rendered WIDTH of the box, matching `AnalystAvatar`.
 * The sprites are square, so height === width — deliberately taller than the
 * Analyst, whose viewBoxes are 150–170 × 150. The guide row bottom-aligns
 * (`alignItems: 'flex-end'`), so the extra height grows upward and no call
 * site needs to change.
 *
 * The art inside each sprite is inset to ~70% of the box width so Fleeced
 * renders at the Analyst's scale (its ink is 62–90pt in a 96pt box). Do not
 * re-export these trimmed to the bounding box — that is what made the first
 * set render oversized. `mobile/tests/check-mascot-ram.js` asserts the inset.
 */

// Static requires — Metro resolves @2x/@3x by filename convention, so each
// entry below also picks up `<pose>@2x.png` and `<pose>@3x.png`.
const SPRITES: Record<AnalystPose, ReturnType<typeof require>> = {
  neutral: require('../../../../assets/mascot/ram/neutral.png'),
  point: require('../../../../assets/mascot/ram/point.png'),
  celebrate: require('../../../../assets/mascot/ram/celebrate.png'),
  computing: require('../../../../assets/mascot/ram/computing.png'),
  thinking: require('../../../../assets/mascot/ram/thinking.png'),
  oops: require('../../../../assets/mascot/ram/oops.png'),
};

/** Where the speech bubble would attach, as a fraction of the rendered box.
 *  Fleeced's horns occupy the top-centre strip, so this sits off-centre —
 *  top-LEFT, because `point` aims right by default and a right-hand anchor
 *  would have it pointing into its own bubble.
 *
 *  NOTE: like the Analyst's `BUBBLE_ANCHOR`, nothing consumes this today —
 *  `AnalystGuide` lays the bubble out BESIDE the avatar in a flex row, not
 *  above it with a tail. Kept as the mascot's declared anchor so the two
 *  mascots stay symmetrical if a tailed bubble is ever built. */
export const RAM_BUBBLE_ANCHOR = { x: 0.18, y: 0 } as const;

export function RamAvatar({
  pose,
  size = 96,
  flip,
}: {
  pose: AnalystPose;
  size?: number;
  flip?: boolean;
}) {
  const img = (
    <Image
      source={SPRITES[pose]}
      style={{ width: size, height: size }}
      resizeMode="contain"
      // Decorative: the guide bubble's own text carries the meaning, and
      // Team Review labels its rows. Matches the Analyst, which renders
      // SVG with no accessibility node either.
      accessible={false}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    />
  );
  if (!flip) return img;
  return <View style={{ transform: [{ scaleX: -1 }] }}>{img}</View>;
}
