import React from 'react';
import Svg, { Path, Circle } from 'react-native-svg';
import { chalk } from '../../theme/chalkline';

// Chalkline icon set — RN mirror of the web/style-guide.html icons.
// 20×20 viewBox, stroke-only, 1.75 weight, square caps. Replaces ALL emoji.
// Emoji map: 📊→rank · 🔗→match · 👥→trade · 👀→eye · ❌/✗→x · ✓→check · 🎯→rank

export type IconName =
  | 'rank'
  | 'trade'
  | 'match'
  | 'trends'
  | 'bell'
  | 'eye'
  | 'check'
  | 'x'
  | 'crown'
  | 'chevron-left'
  | 'chevron-right'
  | 'chevron-down'
  | 'chevron-up'
  | 'expand'
  | 'collapse'
  | 'search'
  | 'settings'
  | 'plus'
  | 'swap'
  | 'flag';

interface Props {
  name: IconName;
  size?: number; // 20 default, 16 in dense rows
  color?: string;
}

export default function Icon({ name, size = 20, color = chalk.dim }: Props) {
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke={color}
      strokeWidth={1.75}
      strokeLinecap="square"
    >
      {GLYPHS[name]}
    </Svg>
  );
}

const GLYPHS: Record<IconName, React.ReactNode> = {
  rank: <Path d="M3 17V9M10 17V3M17 17v-6" />,
  trade: <Path d="M3 7h11M11 3l4 4-4 4M17 13H6M9 17l-4-4 4-4" />,
  match: (
    <Path d="M8 12a4 4 0 010-6l2-2a4 4 0 016 6l-1 1M12 8a4 4 0 010 6l-2 2a4 4 0 01-6-6l1-1" />
  ),
  trends: <Path d="M3 14l4-5 3 3 4-6 3 4" />,
  bell: <Path d="M10 3a5 5 0 015 5v3l2 3H3l2-3V8a5 5 0 015-5zM8 17a2 2 0 004 0" />,
  eye: (
    <>
      <Path d="M2 10s3-5 8-5 8 5 8 5-3 5-8 5-8-5-8-5z" />
      <Circle cx={10} cy={10} r={2.5} />
    </>
  ),
  check: <Path d="M4 11l4 4 8-9" />,
  x: <Path d="M5 5l10 10M15 5L5 15" />,
  crown: <Path d="M3 16l2-9 4 3 1-6 1 6 4-3 2 9z" />,
  'chevron-left': <Path d="M12 4l-6 6 6 6" />,
  'chevron-right': <Path d="M8 4l6 6-6 6" />,
  'chevron-down': <Path d="M4 8l6 6 6-6" />,
  'chevron-up': <Path d="M4 12l6-6 6 6" />,
  expand: <Path d="M11 3h6v6M17 3l-6 6M9 17H3v-6M3 17l6-6" />,
  collapse: <Path d="M16 9h-5V4M17 3l-6 6M4 11h5v5M3 17l6-6" />,
  search: (
    <>
      <Circle cx={8.5} cy={8.5} r={5.5} />
      <Path d="M13 13l4 4" />
    </>
  ),
  // #120 — gear (hub + rim + 8 teeth). Replaced the old sun/spokes glyph,
  // which read as brightness, not settings. Mirrored in web/style-guide.html.
  settings: (
    <>
      <Circle cx={10} cy={10} r={3} />
      <Circle cx={10} cy={10} r={5.5} />
      <Path d="M10 2v2.5M10 15.5V18M2 10h2.5M15.5 10H18M4.3 4.3l1.8 1.8M13.9 13.9l1.8 1.8M15.7 4.3l-1.8 1.8M6.1 13.9l-1.8 1.8" />
    </>
  ),
  plus: <Path d="M10 4v12M4 10h12" />,
  swap: <Path d="M4 7h12M13 4l3 3-3 3M16 13H4M7 10l-3 3 3 3" />,
  flag: <Path d="M5 3v14M5 4h9l-2 3 2 3H5" />,
};
