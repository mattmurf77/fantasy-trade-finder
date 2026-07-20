import React from 'react';
import Svg, { Line, Path } from 'react-native-svg';
import { Eyes, FootballBody, Glasses } from './parts';

// Pose 1 · Neutral — default talking state (S0 intro, S1, S7, any un-posed
// line). Deadpan-flat mouth by identity; dialogue carries the emotion.
// viewBox 0 0 150 150.
export function Neutral({ size = 96 }: { size?: number }) {
  return (
    <Svg width={size} height={size * (150 / 150)} viewBox="0 0 150 150">
      <FootballBody rotation="-4 75 84" />
      <Eyes />
      <Glasses />
      {/* brows */}
      <Path d="M48 62 q9 -6 20 -3" stroke="#3A1F0F" strokeWidth={4} fill="none" strokeLinecap="round" />
      <Line x1={81} y1={58} x2={100} y2={59} stroke="#3A1F0F" strokeWidth={4} strokeLinecap="round" />
      {/* deadpan mouth */}
      <Path d="M66 104 l 20 -1" stroke="#3A1F0F" strokeWidth={3.5} fill="none" strokeLinecap="round" />
    </Svg>
  );
}
