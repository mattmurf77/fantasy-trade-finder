// 4-point spacing scale so everything lines up.
// NOTE (teardown S2 PRD-03): the legacy `radius` and `fontSize` scales are
// deleted — radii and type come from theme/chalkline.ts (`radii`, `type`,
// `maxFontScale`). This numeric scale is identical to chalkline's `space`
// (which adds xxxl 48); prefer importing `space` from chalkline in new code.
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;
