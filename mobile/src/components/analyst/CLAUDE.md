# The Analyst — mascot pose components

React-native-svg renderings of "The Analyst," the football mascot that guides
the onboarding-conversion flow. Six poses (neutral, point, celebrate,
computing, thinking, oops) plus the `AnalystAvatar` switcher.

## This folder is no longer the only mascot

`AnalystAvatar` is now a **switch** (D-155/D-156, flag `onboarding.mascot_ram`,
read through `useOnboardingFeature` so the `onboarding.v2` master ANDs in):

| Flag | Renders |
|---|---|
| on | **Fleeced**, the painted ram — [`../mascot/ram/`](../mascot/ram/index.tsx), raster sprites |
| off | The Analyst in this folder, **byte-identical** to before the flag existed |

The switch lives in `index.tsx` on purpose: all three call sites
(`AnalystGuide`, `TeamReviewScreen`, `TeamReviewEntryCard`) go through that one
function, so neither they nor the tour script change. The pose union
`AnalystPose` is shared by both mascots, which is what keeps
`guide_step_shown{pose}` meaning the same thing in either state.
`mobile/tests/check-mascot-ram.js` pins all of that.

## `BUBBLE_ANCHOR` is exported and never consumed

It says "top-center", but nothing reads it. `AnalystGuide` lays the bubble out
**beside** the avatar in a flex row (`row: { flexDirection: 'row',
alignItems: 'flex-end' }`), not above it with a tail. Treat it as a declared
intention, not behaviour — and do not "fix" a layout on the strength of it
without checking who reads it first. `mascot/ram` declares its own
`RAM_BUBBLE_ANCHOR` for symmetry, equally unconsumed.

Bottom-alignment is also why Fleeced may be taller than the Analyst: the
avatar box is `{ width: AVATAR }` with no height constraint, so a square
sprite grows upward off a shared bottom edge.

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
