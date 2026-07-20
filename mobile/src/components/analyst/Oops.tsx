import React from 'react';
import Svg, { Circle, Ellipse, G, Path, Text } from 'react-native-svg';
import { FootballBody, Glasses } from './parts';

// Pose 6 · Oops — error states and honest bad news: Sleeper down, empty
// deck, N=0 re-rank (S0 errors, S5 zero-case, api_request_failed while
// guiding). Glasses knocked askew, one squint, sweat drop.
// viewBox 0 0 155 150. Asymmetric eyes stay inline (not the shared kit).
export function Oops({ size = 96 }: { size?: number }) {
  return (
    <Svg width={size} height={size * (150 / 155)} viewBox="0 0 155 150">
      <FootballBody cy={88} rotation="-7 75 88" />
      {/* wide worried eyes, one squint */}
      <Ellipse cx={60} cy={86} rx={13} ry={15} fill="#fff" stroke="#222" strokeWidth={2.5} />
      <Ellipse cx={92} cy={86} rx={11} ry={12} fill="#fff" stroke="#222" strokeWidth={2.5} />
      <Circle cx={61} cy={88} r={5.2} fill="#151515" />
      <Circle cx={93} cy={88} r={4} fill="#151515" />
      {/* glasses ASKEW */}
      <G transform="rotate(7 76 86)">
        <Glasses dy={4} />
      </G>
      {/* brows */}
      <Path d="M46 66 q9 -6 20 -4" stroke="#3A1F0F" strokeWidth={4} fill="none" strokeLinecap="round" />
      <Path d="M82 62 q9 -5 19 -1" stroke="#3A1F0F" strokeWidth={4} fill="none" strokeLinecap="round" />
      {/* grimace */}
      <Path d="M62 110 q6 -4 13 0 q7 4 14 -1" fill="none" stroke="#3A1F0F" strokeWidth={3} strokeLinecap="round" />
      {/* sweat drop + alert */}
      <Path d="M118 58 q6 8 0 12 q-6 -4 0 -12" fill="#4FD8EB" />
      <Text x={24} y={44} fontSize={26} fontWeight="700" fill="#F25CA2">
        !
      </Text>
    </Svg>
  );
}
