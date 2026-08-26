import React from 'react';
import { View } from 'react-native';
import { useOnboardingFeature } from '../../state/useFeatureFlags';
import { RamAvatar } from '../mascot/ram';
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
 * Renders the guide mascot in the given pose. `size` is the rendered width
 * (default 96); height follows each pose's viewBox aspect ratio. `flip`
 * mirrors horizontally — e.g. the point pose points right by default; flip
 * it to point left.
 *
 * MASCOT SWITCH (D-155/D-156, `onboarding.mascot_ram`):
 * flag ON  → Fleeced, the painted ram (`components/mascot/ram`)
 * flag OFF → The Analyst, byte-identical to before the flag existed.
 *
 * The switch lives here on purpose: all three call sites
 * (`AnalystGuide`, `TeamReviewScreen`, `TeamReviewEntryCard`) go through
 * this one function, so neither they nor the tour script change. The pose
 * vocabulary is shared, so `guide_step_shown{pose}` analytics are untouched
 * in both states.
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
  // Read unconditionally — hooks cannot be called behind a branch.
  // `useOnboardingFeature` ANDs in the `onboarding.v2` master, which is the
  // required path for every `onboarding.*` key (mobile/src/CLAUDE.md).
  const ramOn = useOnboardingFeature('onboarding.mascot_ram');
  if (ramOn) return <RamAvatar pose={pose} size={size} flip={flip} />;

  const PoseComponent = POSE_COMPONENTS[pose];
  const rendered = <PoseComponent size={size} />;
  if (!flip) return rendered;
  return <View style={{ transform: [{ scaleX: -1 }] }}>{rendered}</View>;
}
