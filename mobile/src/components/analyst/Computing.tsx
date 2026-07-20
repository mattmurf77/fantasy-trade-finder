import React from 'react';
import Svg, { Circle, Ellipse, G, Line, Path, Rect } from 'react-native-svg';

// Pose 4 · Computing — any wait state: deck generation, re-rank, server wake
// (S2 pre-deck, S5 regen, cold-start mask). viewBox 0 0 160 150.
// This pose's body is smaller (rx=48/ry=34) with its own lace offsets, and
// its eyes/glasses are differently sized, so the geometry stays inline
// rather than reusing the part-kit.
export function Computing({ size = 96 }: { size?: number }) {
  return (
    <Svg width={size} height={size * (150 / 160)} viewBox="0 0 160 150">
      <G transform="rotate(-2 78 76)">
        <Ellipse cx={78} cy={76} rx={48} ry={34} fill="#9C5528" stroke="#5C2E16" strokeWidth={3.5} />
        <Path d="M38 64 q-3 8 0 22" stroke="#F5EFE6" strokeWidth={4} fill="none" strokeLinecap="round" />
        <Path d="M118 64 q3 8 0 22" stroke="#F5EFE6" strokeWidth={4} fill="none" strokeLinecap="round" />
        <Line x1={61} y1={50} x2={97} y2={50} stroke="#F5EFE6" strokeWidth={4} strokeLinecap="round" />
        <Line x1={68} y1={45} x2={68} y2={55} stroke="#F5EFE6" strokeWidth={3} strokeLinecap="round" />
        <Line x1={79} y1={45} x2={79} y2={55} stroke="#F5EFE6" strokeWidth={3} strokeLinecap="round" />
        <Line x1={90} y1={45} x2={90} y2={55} stroke="#F5EFE6" strokeWidth={3} strokeLinecap="round" />
      </G>
      {/* eyes DOWN at the screen */}
      <Ellipse cx={63} cy={74} rx={12} ry={13.5} fill="#fff" stroke="#222" strokeWidth={2.5} />
      <Ellipse cx={94} cy={72} rx={12} ry={13.5} fill="#fff" stroke="#222" strokeWidth={2.5} />
      <Circle cx={63} cy={80} r={4.6} fill="#151515" />
      <Circle cx={94} cy={78} r={4.6} fill="#151515" />
      <Rect x={47} y={60} width={32} height={27} rx={6} fill="none" stroke="#173A43" strokeWidth={3.5} />
      <Rect x={81} y={58} width={32} height={27} rx={6} fill="none" stroke="#173A43" strokeWidth={3.5} />
      <Line x1={79} y1={72} x2={81} y2={72} stroke="#173A43" strokeWidth={3.5} />
      {/* brows */}
      <Path d="M51 54 q9 -5 19 -2" stroke="#3A1F0F" strokeWidth={4} fill="none" strokeLinecap="round" />
      <Path d="M84 50 q9 -3 18 2" stroke="#3A1F0F" strokeWidth={4} fill="none" strokeLinecap="round" />
      {/* concentration mouth */}
      <Path d="M70 96 l 16 0" stroke="#3A1F0F" strokeWidth={3.5} fill="none" strokeLinecap="round" />
      {/* BIG open laptop */}
      <Rect x={40} y={104} width={76} height={30} rx={4} fill="#10141A" stroke="#4A5563" strokeWidth={3} />
      <Path d="M34 134 l88 0 l8 12 l-104 0 Z" fill="#6E7B8A" stroke="#4A5563" strokeWidth={3} />
      {/* animated-feel chart + progress */}
      <Line x1={52} y1={128} x2={52} y2={118} stroke="#4FD8EB" strokeWidth={4} />
      <Line x1={63} y1={128} x2={63} y2={113} stroke="#4FD8EB" strokeWidth={4} />
      <Line x1={74} y1={128} x2={74} y2={120} stroke="#4FD8EB" strokeWidth={4} />
      <Line x1={85} y1={128} x2={85} y2={110} stroke="#F25CA2" strokeWidth={4} />
      <Circle cx={100} cy={112} r={2.5} fill="#4FD8EB" />
      <Circle cx={107} cy={112} r={2.5} fill="#4FD8EB" opacity={0.6} />
      <Circle cx={114} cy={112} r={2.5} fill="#4FD8EB" opacity={0.3} />
    </Svg>
  );
}
