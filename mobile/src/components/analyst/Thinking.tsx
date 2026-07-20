import React from 'react';
import Svg, { Circle, Line, Path, Rect, Text } from 'react-native-svg';
import { Eyes, FootballBody, Glasses } from './parts';

// Pose 5 · Thinking — reacting to the user's input: pass streaks, odd tier
// saves, hesitation/idle nudges (S3 trigger line, S4 tier hints).
// viewBox 0 0 155 150.
export function Thinking({ size = 96 }: { size?: number }) {
  return (
    <Svg width={size} height={size * (150 / 155)} viewBox="0 0 155 150">
      <FootballBody cy={88} rotation="-4 75 88" />
      {/* eyes UP-LEFT, one brow raised */}
      <Eyes dy={4} pupilDx={-4} pupilDy={-6} />
      <Glasses dy={4} />
      <Path d="M46 62 q9 -9 21 -6" stroke="#3A1F0F" strokeWidth={4} fill="none" strokeLinecap="round" />
      <Line x1={82} y1={64} x2={100} y2={64} stroke="#3A1F0F" strokeWidth={4} strokeLinecap="round" />
      {/* squiggle mouth */}
      <Path d="M64 108 q5 3 10 0 q5 -3 10 0" fill="none" stroke="#3A1F0F" strokeWidth={3} strokeLinecap="round" />
      {/* pencil tucked in lace */}
      <Rect x={88} y={40} width={26} height={7} rx={3} fill="#F2B33D" stroke="#8A6516" strokeWidth={2} transform="rotate(-18 100 44)" />
      {/* floating figures */}
      <Text x={18} y={42} fontSize={13} fontWeight="700" fill="#4FD8EB">
        +14%?
      </Text>
      <Text x={112} y={26} fontSize={12} fontWeight="700" fill="#F25CA2">
        2-for-1
      </Text>
      <Circle cx={42} cy={52} r={2.5} fill="#4FD8EB" />
      <Circle cx={34} cy={60} r={2} fill="#4FD8EB" opacity={0.6} />
    </Svg>
  );
}
