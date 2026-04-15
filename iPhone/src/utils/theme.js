export const colors = {
  bg: '#0f1117',
  surface: '#1a1d27',
  border: '#2a2d3a',
  text: '#e8eaf0',
  muted: '#7a7f96',
  accent: '#4f7cff',
  green: '#22c55e',
  red: '#ef4444',
  qb: '#f97316',
  rb: '#22c55e',
  wr: '#3b82f6',
  te: '#a855f7',
  gold: '#f59e0b',
  silver: '#94a3b8',
  bronze: '#b45309',
  pick: '#f59e0b',
};

export const positionColor = (pos) => {
  const p = (pos || '').toUpperCase();
  return colors[p.toLowerCase()] || colors.muted;
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
};

export const fontSize = {
  xs: 11,
  sm: 13,
  md: 15,
  lg: 18,
  xl: 22,
  xxl: 28,
};

export const borderRadius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
};
