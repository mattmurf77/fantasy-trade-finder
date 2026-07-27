# FB-159 — Quick Set empty-tier CTA — status

**Implemented 2026-07-27** (branch `teardown-remediation`), per prd.md
R-1/R-2/R-3. `QuickSetTiersScreen`'s primary CTA (existing testID
`quick-set.save-btn`):

- **R-1:** zero selected chips → label becomes **"No players for this tier"**;
  on the last tier the PRD's short-fit discretion is used — **"No players here
  & finish"** — because the full string plus the " & finish" suffix would
  overflow the button. Tap behavior unchanged: same `onSave` press.
- **R-2:** with ≥1 selection the CTA renders its exact previous content
  (`Save <tier> (N)` + finish suffix) and behavior.
- **R-3:** the swap is driven directly by the existing selection state
  (`selected.size` → `selectedCount`), so it flips instantly on
  select/deselect with no reload. The accessibilityLabel mirrors the state
  ("No players for this tier, save it empty…").

**#161 interaction verified against the shipped code:** `onSave`'s demotion
branch computes `demoted` only when `ids.length ≥ 1` (`QuickSetTiersScreen`,
"clear-only save — restores the suggested tier, no demotion" guard), and an
empty save with nothing to un-pick short-circuits to `goTo` (pure skip, no
request). So the empty-CTA tap keeps pure skip semantics — it can never
trigger #161 demotion.

**Quick Rank (R-3 conditional) — confirmed not shared:** `QuickRankScreen`
skips tiers with <2 players entirely, and zero clicks there means "current
order stands" (a meaningful state, not an empty tier), so the empty-tier
label rule does not apply; no change made.

Test plan: covered by the PRD's manual steps; Maestro label assertions ride
the existing `quick-set.save-btn` id (CTA copy is asserted via visible text).
