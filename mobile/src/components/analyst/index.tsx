import React from 'react';
import { View } from 'react-native';
import { Celebrate } from './Celebrate';
import { Computing } from './Computing';
import { Neutral } from './Neutral';
import { Oops } from './Oops';
import { Point } from './Point';
import { Thinking } from './Thinking';

export { Celebrate, Computing, Neutral, Oops, Point, Thinking };

export type AnalystPose = 'neutral' | 'point' | 'celebrate' | 'computing' | 'thinking' | 'oops';

/**
 * Where the speech bubble attaches, as a fraction of the avatar's rendered
 * box: top-center (per the pose sheet).
 */
export const BUBBLE_ANCHOR = { x: 0.5, y: 0 } as const;

const POSE_COMPONENTS: Record<AnalystPose, React.ComponentType<{ size?: number }>> = {
  neutral: Neutral,
  point: Point,
  celebrate: Celebrate,
  computing: Computing,
  thinking: Thinking,
  oops: Oops,
};

/**
 * Renders The Analyst in the given pose. `size` is the rendered width
 * (default 96); height follows each pose's viewBox aspect ratio. `flip`
 * mirrors horizontally — e.g. the point pose points right by default; flip
 * it to point left.
 */
export function AnalystAvatar({
  pose,
  size,
  flip,
}: {
  pose: AnalystPose;
  size?: number;
  flip?: boolean;
}) {
  const PoseComponent = POSE_COMPONENTS[pose];
  const rendered = <PoseComponent size={size} />;
  if (!flip) return rendered;
  return <View style={{ transform: [{ scaleX: -1 }] }}>{rendered}</View>;
}
