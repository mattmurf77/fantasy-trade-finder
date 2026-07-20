import React from 'react';
import Svg, { Path, Rect } from 'react-native-svg';
import { FootballBody, Glasses } from './parts';

// Pose 3 · Celebrate — win moments: happy-arc eyes, tie mid-jump, confetti
// (S5 re-rank reveal, S6 first like, S8 sign-off). viewBox 0 0 160 150.
export function Celebrate({ size = 96 }: { size?: number }) {
  return (
    <Svg width={size} height={size * (150 / 160)} viewBox="0 0 160 150">
      <FootballBody cx={80} cy={82} rotation="4 80 84" />
      {/* happy closed-arc eyes */}
      <Path d="M52 82 a 12 12 0 0 1 22 0" fill="none" stroke="#222" strokeWidth={4} strokeLinecap="round" />
      <Path d="M86 80 a 12 12 0 0 1 22 0" fill="none" stroke="#222" strokeWidth={4} strokeLinecap="round" />
      <Glasses dx={2} dy={-2} />
      {/* open grin */}
      <Path d="M64 102 q16 14 32 2 q-6 12 -17 12 q-11 0 -15 -14 Z" fill="#3A1F0F" />
      {/* confetti */}
      <Rect x={26} y={30} width={7} height={7} fill="#F25CA2" transform="rotate(20 29 33)" />
      <Rect x={126} y={24} width={7} height={7} fill="#4FD8EB" transform="rotate(-15 129 27)" />
      <Rect x={40} y={14} width={6} height={6} fill="#4FD8EB" transform="rotate(40 43 17)" />
      <Rect x={104} y={10} width={6} height={6} fill="#F25CA2" transform="rotate(10 107 13)" />
      <Path d="M20 52 l8 -4 M140 46 l-8 -4 M74 8 l4 8" stroke="#F5EFE6" strokeWidth={3} fill="none" strokeLinecap="round" />
      {/* bounce lines */}
      <Path d="M56 138 l12 0 M92 138 l12 0" stroke="#5F6B78" strokeWidth={3} fill="none" strokeLinecap="round" />
    </Svg>
  );
}
