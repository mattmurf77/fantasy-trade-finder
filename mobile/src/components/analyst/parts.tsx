import React from 'react';
import { Circle, Ellipse, G, Line, Path, Rect } from 'react-native-svg';

// Shared part-kit for The Analyst mascot. Geometry is a 1:1 translation of
// mockups/avatar-lab/analyst-poses.html (source of truth — see CLAUDE.md in
// this directory). Only parts that are identical across poses up to a
// translation/rotation live here; pose-unique geometry stays in the pose file.

/**
 * Football body + white side stripes + lace "hair".
 * Base geometry matches the neutral pose (cx=75, cy=84); other poses pass
 * their own center and rotation. The Computing pose uses a smaller body
 * (rx=48/ry=34) with different lace offsets, so it keeps its body inline.
 */
export function FootballBody({
  cx = 75,
  cy = 84,
  rotation,
  rightStripe = true,
}: {
  cx?: number;
  cy?: number;
  /** SVG rotate() arguments, e.g. "-4 75 84" (angle centerX centerY). */
  rotation: string;
  /** The point pose omits the right stripe (arm side). */
  rightStripe?: boolean;
}) {
  return (
    <G transform={`rotate(${rotation})`}>
      <Ellipse cx={cx} cy={cy} rx={50} ry={36} fill="#9C5528" stroke="#5C2E16" strokeWidth={3.5} />
      <Path d={`M${cx - 42} ${cy - 14} q-3 8 0 24`} stroke="#F5EFE6" strokeWidth={4} fill="none" strokeLinecap="round" />
      {rightStripe && (
        <Path d={`M${cx + 42} ${cy - 14} q3 8 0 24`} stroke="#F5EFE6" strokeWidth={4} fill="none" strokeLinecap="round" />
      )}
      <Line x1={cx - 18} y1={cy - 28} x2={cx + 20} y2={cy - 28} stroke="#F5EFE6" strokeWidth={4} strokeLinecap="round" />
      <Line x1={cx - 11} y1={cy - 33} x2={cx - 11} y2={cy - 23} stroke="#F5EFE6" strokeWidth={3} strokeLinecap="round" />
      <Line x1={cx} y1={cy - 33} x2={cx} y2={cy - 23} stroke="#F5EFE6" strokeWidth={3} strokeLinecap="round" />
      <Line x1={cx + 11} y1={cy - 33} x2={cx + 11} y2={cy - 23} stroke="#F5EFE6" strokeWidth={3} strokeLinecap="round" />
    </G>
  );
}

/**
 * Standard open eyes (white ellipses + round pupils). Base position matches
 * the neutral pose; `dy` shifts the whole pair, `pupilDx`/`pupilDy` offset
 * the pupils from each eye's center (gaze direction). Computing and Oops use
 * differently sized eyeballs and keep theirs inline.
 */
export function Eyes({
  dy = 0,
  pupilDx = 3,
  pupilDy = 3,
}: {
  dy?: number;
  pupilDx?: number;
  pupilDy?: number;
}) {
  return (
    <>
      <Ellipse cx={60} cy={82 + dy} rx={12.5} ry={14} fill="#fff" stroke="#222" strokeWidth={2.5} />
      <Ellipse cx={92} cy={80 + dy} rx={12.5} ry={14} fill="#fff" stroke="#222" strokeWidth={2.5} />
      <Circle cx={60 + pupilDx} cy={82 + dy + pupilDy} r={4.8} fill="#151515" />
      <Circle cx={92 + pupilDx} cy={80 + dy + pupilDy} r={4.8} fill="#151515" />
    </>
  );
}

/**
 * Square-rim glasses (two rects + bridge). Base position matches the neutral
 * pose; `dx`/`dy` translate the whole unit. Oops wraps this in a rotated <G>
 * for the askew look; Computing uses smaller 32x27 rims and keeps its inline.
 */
export function Glasses({ dx = 0, dy = 0 }: { dx?: number; dy?: number }) {
  return (
    <>
      <Rect x={44 + dx} y={68 + dy} width={33} height={28} rx={6} fill="none" stroke="#173A43" strokeWidth={3.5} />
      <Rect x={79 + dx} y={66 + dy} width={33} height={28} rx={6} fill="none" stroke="#173A43" strokeWidth={3.5} />
      <Line x1={77 + dx} y1={80 + dy} x2={79 + dx} y2={80 + dy} stroke="#173A43" strokeWidth={3.5} />
    </>
  );
}
