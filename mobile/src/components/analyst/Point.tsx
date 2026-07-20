import React from 'react';
import Svg, { Path, Text } from 'react-native-svg';
import { Eyes, FootballBody, Glasses } from './parts';

// Pose 2 · Point (foam finger) — directs the user's tap; pupils track the
// target; fingertip pulses in sync with the spotlight (S0 field, S2 deck,
// S3 chip, S6 share, S7 trio). Points RIGHT; use AnalystAvatar's `flip` for
// left targets. viewBox 0 0 170 150. No right body stripe (arm side).
export function Point({ size = 96 }: { size?: number }) {
  return (
    <Svg width={size} height={size * (150 / 170)} viewBox="0 0 170 150">
      <FootballBody rotation="-4 75 84" rightStripe={false} />
      {/* eyes track the point (pupils right) */}
      <Eyes pupilDx={6} pupilDy={2} />
      <Glasses />
      {/* brows */}
      <Path d="M48 62 q9 -6 20 -3" stroke="#3A1F0F" strokeWidth={4} fill="none" strokeLinecap="round" />
      <Path d="M81 56 q10 -4 19 1" stroke="#3A1F0F" strokeWidth={4} fill="none" strokeLinecap="round" />
      {/* slight smile */}
      <Path d="M66 104 q10 6 20 0" stroke="#3A1F0F" strokeWidth={3.5} fill="none" strokeLinecap="round" />
      {/* stub arm: curves from the body UNDER the mitt — wrist meets the
          foam finger's bottom edge (drawn first so the mitt overlaps the cap) */}
      <Path d="M116 98 q18 14 35 8" stroke="#5C2E16" strokeWidth={6.5} fill="none" strokeLinecap="round" />
      {/* FOAM FINGER: index on the LEADING edge, short — classic silhouette */}
      <Path
        d="M138 96 L138 68 q0 -5 5 -5 q5 0 5 5 L148 80 L156 80 q8 0 8 8 L164 96 q0 8 -8 8 L146 104 q-8 0 -8 -8 Z"
        fill="#F5EFE6"
        stroke="#8E9AA8"
        strokeWidth={3}
        strokeLinejoin="round"
      />
      <Text x={143} y={99} fontSize={12} fontWeight="700" fill="#F25CA2">
        #1
      </Text>
      {/* pulse ticks at the raised fingertip */}
      <Path d="M143 58 l0 -8 M152 62 l6 -6 M134 62 l-6 -6" stroke="#4FD8EB" strokeWidth={3} fill="none" strokeLinecap="round" />
    </Svg>
  );
}
