# The Analyst — mascot pose components

React-native-svg renderings of "The Analyst," the football mascot that guides
the onboarding-conversion flow. Six poses (neutral, point, celebrate,
computing, thinking, oops) plus the `AnalystAvatar` switcher and
`BUBBLE_ANCHOR` (speech bubble attaches top-center).

## Source of truth

- **Art:** `mockups/avatar-lab/analyst-poses.html` (repo root). The SVGs
  there are the operator-approved originals; these components are 1:1
  translations (same coordinates, colors, stroke widths, transforms).
- **Script / usage per scene:** `docs/plans/onboarding-conversion/guided-avatar-script.md`.

## Rule: mockup first

Do NOT edit the art directly in these components. Change the SVG in the
mockup HTML first, get it approved there, then re-translate the affected
pose here. The only intentional divergences from the mockup are: no
`font-family` on `<Text>` (RN SVG font-family support is unreliable — weight
and size carry the look) and the shared part-kit in `parts.tsx`
(`FootballBody`, `Eyes`, `Glasses`), which factors out geometry that is
identical across poses up to translation/rotation. Pose-unique geometry
(Computing's smaller body/eyes/glasses, Oops's asymmetric eyes) stays inline
in the pose file.

Character colors are hardcoded by design (theme-independent art) — do not
migrate them to Chalkline tokens.
