# Accessibility Release Checklist — Fantasy Trade Finder

Per-release regression pass (teardown 2026-07, S8 PRD-03). Target: ~30 minutes on a real
device once practiced. Run end-to-end **before every TestFlight submission**; record the
run (date, build, pass/fail per item, findings) in `qa/results/`. A failure on any item
that backs a declared Accessibility Nutrition Label line is a submission blocker — the
declaration must stay consistent with tested reality.

Findings are triaged on the backend charter's P0–P3 scale (see [README.md](README.md));
an a11y regression that makes a core-loop step unusable with VoiceOver is P1.

## The pass

### 1. VoiceOver walk — four tabs, screen curtain on

- [ ] **Rank** — complete one trio comparison and one Quick Set save by swipe navigation alone
- [ ] **Trades** — read a full trade card (both sides, verdict, fairness), then pass/like it
- [ ] **Matches** — open a match, read its detail, dismiss or accept
- [ ] **League** — read the summary rows and open one sub-surface

**How:** Settings → Accessibility → VoiceOver ON, then triple-tap with three fingers to
enable Screen Curtain (screen goes black — you hear only what a blind user gets). Swipe
right/left to move focus, double-tap to activate. Pass bar: every interactive element has
a label + role + state, focus order follows visual order, no trap, nothing reachable only
by an invisible gesture (long-press actions announce a visible twin).

### 2. AX5 screenshot set — core screens

- [ ] Capture Rank (trio + Quick Set), Trades deck card, Matches list + detail, League
      summary, Settings at **AX5** text size; compare against the previous release's set

**How:** Settings → Accessibility → Display & Text Size → Larger Text → enable
"Larger Accessibility Sizes", drag the slider to the largest (AX5). Screenshot each core
screen; store the set in `qa/results/` next to the run record. Pass bar: no clipped or
overlapping text, no truncated primary action, fixed-height containers grow, tab bar
labels legible.

### 3. Reduce Motion spot-check

- [ ] Card fling on Trades, toast entrances, and modal/sheet presentations use the
      reduced (fade/none) path; web: no animation loops running

**How:** Settings → Accessibility → Motion → Reduce Motion ON; on web, emulate
`prefers-reduced-motion: reduce` in devtools rendering settings. Exercise a swipe, a
toast (e.g. tier save), and one sheet open/close.

### 4. Increase Contrast spot-check

- [ ] Muted/secondary text, chip borders, and disabled states remain distinguishable on
      Trades and Tiers with Increase Contrast ON

**How:** Settings → Accessibility → Display & Text Size → Increase Contrast ON. Eyeball
the two densest screens; anything that visually vanishes is a finding.

### 5. Token-contrast check

- [ ] The Chalkline token-pair contrast test passes (every foreground/background token
      pair ≥ its WCAG floor: 4.5:1 body text, 3:1 large text/UI)

**How:** run the token-contrast unit test over `mobile/src/theme/chalkline.ts` (the
automation half of S8 PRD-03; seed data = the teardown's computed contrast tables). Until
that test exists in CI, run the check manually with a contrast calculator against any
token changed this release — and treat the missing test as an open P2.

## After the pass

- Update the run record in `qa/results/` and, at App Store launch, verify the
  **Accessibility Nutrition Label** declarations in App Store Connect still match what
  this pass demonstrated (declare only: Dark Interface, Differentiate Without Color
  Alone, Sufficient Contrast, Reduced Motion, Larger Text, VoiceOver — each backed by an
  item above).
- Dark-only appearance and Smart Invert verification are recorded decisions — see
  [ADR-008](../docs/adr/adr-008-teardown-remediation-wave.md).
