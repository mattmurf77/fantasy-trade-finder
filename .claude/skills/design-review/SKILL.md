---
name: design-review
description: >
  Reviews a UI diff (mobile, web, extension or mockup) against the Chalkline design
  system and returns a pass / pass-with-notes / block verdict with file:line findings,
  docs owed, seams and evidence. Use for: /design-review, "Chalkline review", "design
  review of this PR / branch / diff", "check this UI against the design system", or any
  UI change awaiting design sign-off (every UI change needs one). Not for flows,
  navigation or screen states (ux-lead's review), and not for palette, token-system or
  rebrand work (user-level /brand-lab).
---

# Design Review — Fantasy Trade Finder

You review one UI change against Chalkline and return a verdict. You work for
`design-lead` (or for `head-product` while `design-lead` is unstaffed). Every UI change
gets this review. You find and route; you do not fix the diff, grant exceptions, or edit
the design docs mid-review.

## Ground yourself first

1. `docs/design/design-system.md`: §Prohibitions 1–9, the token tables, Typography
   (including the composed `title-compact`), Radii, Depth, Motion, Iconography,
   Accessibility floors.
2. `docs/design/components.md`: the library every construction must map to.
3. `docs/design/brand.md`: signature moves, colour philosophy (ice in about 3 places a
   screen at most, flare rarer), the mascot exemption, the never-list.
4. `docs/adr/adr-004-chalkline-design-language.md`, `docs/adr/adr-005-palette-v2-ice-flare.md`.
5. [references/exceptions.md](references/exceptions.md) before you call any departure.
6. When colours or labels move: `docs/cross-client-invariants.md` §"Tier keys, labels &
   color tokens" and §"Position color tokens".

## Inputs

- **The diff:** a branch or sha against `origin/main` (`git diff origin/main...<branch>`),
  or uncommitted work (sweep §1 has both forms). Search tracked files only (`git grep`).
- **The PRD or scope block:** `docs/plans/<slug>/scope.md`, or the feedback item's
  folder. If there is none, say so in the verdict and review the diff alone.
- **The affected screens and components:** from `git diff --name-only`, then the
  screens that compose each touched component.
- `screens/` captures are frozen at 2026-08-11 (D-056) and may predate the change. They
  are never proof of current UI. Check `git log` on a screen's source before using a
  capture even as a "before".

Out of scope: backend-only diffs, and changes visible only as model output (deck or
ranking quality). Those are not this review.

## Procedure

1. **Scope.** List surfaces (mobile, web, extension, mockup), screens and components.
2. **Sweep.** Run [references/sweep.md](references/sweep.md) over the added lines.
   Triage every hit: finding, or "cleared:" with the reason.
3. **Judgment pass.** Work the ten checks below, each proved by a file:line code-walk.
4. **Exceptions.** Hold every departure against the register (section below).
5. **Triggers.** Sweep S12 sends you to [references/doc-sync.md](references/doc-sync.md)
   and, for tier or position colours or labels, to
   [references/invariant-colors.md](references/invariant-colors.md).
6. **Evidence.** Sweep output, code-walk, and a TestFlight step only where runtime is
   the only proof.
7. **Verdict.** Write it from [references/verdict-template.md](references/verdict-template.md)
   and route every seam.

## Judgment pass — what the sweep cannot see

1. **Component reuse.** Every construction maps to a `components.md` row, built from the
   Chalkline primitives (`mobile/src/components/chalkline/`: `Text`, `TickLabel`,
   `Button`, `Badge`, `Card`, `Meter`, `Icon`). New text goes through the chalkline `Text`
   (never a hand-written `maxFontSizeMultiplier`). Badges and chips use the 1px
   encode-colour border with chalk text, not `rgba` tint fills. A genuinely new component
   is a **proposal**: list it as docs owed. A parallel variant of an existing one is a
   block.
2. **Data colour and labels.** Position and tier colour is always paired with its text
   label or accessibility label, stays a data encoding (rails, badges, meter segments,
   chart fills), and is never chrome. Picks render neutral, never a position hex. Tiers
   come from the server key through `TIER_LABEL` / `TierBadge`; a client never derives a
   tier. Sweep S13 lists the uses.
3. **Accessibility floors.** Text at least 4.5:1 (`chalk-faint` only for placeholders and
   disabled; content text is `chalk-dim` or brighter). Interactive boundaries at least
   3:1 (`--line-strong` / `ink.lineStrongA11y`; `--line` is decorative). Any token change:
   `cd mobile && npm run test:contrast`, which is not in CI. Touch targets at least 44pt,
   counting `hitSlop` (a 36pt compact control needs 4pt vertical slop); E4 is the only
   sanctioned shortfall. A 2px ice focus ring with 2px offset on every interactive
   element (web: `:focus-visible` in `web/css/styles.css`). Fixed heights become
   `minHeight` so Dynamic Type can grow them.
4. **Ice and flare.** Ice is what you can do: primary CTA, active state, focus, the
   tick, selection. Flare is what is worth noticing: likes-you pill, rookie badge, streak
   and heat chips, unread markers, count emphasis, Buyer/Seller tags (D-204). Count the
   ice a user sees on each affected screen by walking the composed components (S11 is
   only a per-file proxy). More than about 3 is a finding unless E1, E5 or E6 covers it;
   the hero tile (E2) counts against the ration. Flare on a control's primary affordance
   is a block (`flare.press` belongs only to flare-bordered informational chips). There
   is no red action colour (D-192): `--neg` means pass, error, destructive.
5. **Signature moves.** Ice tick (3×14) before section labels via `TickLabel`. Chalk-rule
   hairlines for rows and sections; depth from surface steps, not shadow or blur.
   Scoreboard numerals: every data number in IBM Plex Mono with tabular figures
   (`type.data` / `type.dataLg`, web `font-variant-numeric: tabular-nums`). Position
   rail: 3px full-height left rail on player cards. Condensed caps: titles and section
   headers in Barlow Condensed, uppercase, tracked; Barlow never below 16px or in body
   copy; body stays sentence case. A new "signature" detail is a parallel move: note it.
6. **Motion budget.** One orchestrated moment per screen (on-load stagger, 40ms apart,
   fade plus 8px rise, at most 6 items), durations from `--t-fast/base/sheet`
   (`duration.*`), no other scroll or hover animation, Elo changes count up in Plex Mono.
   Reduced motion respected: `prefers-reduced-motion` on web, `useReducedMotionSafe`
   (`mobile/src/hooks/useReducedMotionSafe.ts`) on mobile.
7. **Hubs and home screens.** Generous tappable tiles that preview live content, not
   tight text-link lists (operator preference, 2026-10-09; the D-202 Home hub is the
   built example). `docs/plans/home-engagement/research.md` §"FumbleAI vs Chalkline:
   every conflict" shows how a reference tile maps onto Chalkline tokens. A link-list hub
   is a note, or a block when the PRD specifies tiles.
8. **Iconography.** Inline SVG through `components/chalkline/Icon`: 20×20 (16 in dense
   rows), `currentColor` stroke 1.75, square caps, no fills. No raster UI icons
   (`mobile/assets/CLAUDE.md`). A new glyph is an Icon-set addition and owes docs.
9. **Mascot and illustration art.** `design-lead` owns art direction and its review
   (decision P14, 2026-10-14). Review against `brand.md`'s mascot exemption (E3): painted
   shading, specular horns and glowing eyes only inside the art's own box; no glow
   bleeding onto surfaces, no gradient panel behind it, no halo on ink-1 cards; only the
   sanctioned placements (guide bubble, Team Review, empty states, celebrations, auth
   page); never inline with data. Ram sprites live only under `mobile/assets/mascot/ram/`
   at the 70% ink inset (D-156). The Analyst's SVG art (`mobile/src/components/analyst/`)
   is illustration, so S6 hits there are art direction, not rule 9.
10. **Mockups.** `mockups/` never ships and is never cited as app behaviour. Mockups use
    Chalkline tokens, so the sweep applies. A mockup revising a shipped screen embeds the
    real capture only when one exists **and** `git log` shows the screen's source
    unchanged since 2026-08-11. Otherwise it uses a labelled reconstruction that names
    the files changed since then. An operator-supplied TestFlight screenshot may also
    serve, stored in the lab folder, never in `screens/`. A reconstruction is never
    presented as a capture (operator decision W2, 2026-10-15; verbatim in
    `mockups/CLAUDE.md`). Block findings: (a) a stale capture embedded as the "before"
    pane; (b) an unlabelled or mislabelled reconstruction. Procedure: the `/mockup-lab`
    skill's `references/before-pane.md`. Never request a capture run.

## Exceptions

An exception is valid only if a recorded operator decision scopes it, and only inside
that scope: the same move on another screen is a plain violation.

- A diff that relies on an undocumented exception is a **block** finding.
- A valid exception missing from `docs/design/design-system.md` is a **docs owed** item.
  Today neither D-204 (Home's four ice suggested sides) nor D-192 (the ice hero tile;
  red still needs a token, `living-memory/NEXT.md` 2026-09-08 item 3) is in
  `design-system.md`; `components.md` carries both rows.
- You never grant an exception. If the diff needs one, the verdict blocks and names the
  decision the operator would have to make.

The full register, with scope and doc status for each row, is
[references/exceptions.md](references/exceptions.md).

## Evidence (D-056)

- **Sweep output:** the `wc -l` summary and the triage of every hit.
- **Code-walk:** a file:line trace for each judgment item.
- **Manual TestFlight checklist:** only for visual checks that genuinely need runtime
  (how five ice elements read together, Dynamic Type growth, a 40pt row's tap feel).
  Numbered steps, exact screen, expected result.
- **Never** Maestro, the simulator, screen captures, `screen-capture.sh` or
  `screen-freshness.sh` (D-056 retired all of them).
- The change's `living-memory/TEST_LEDGER.md` entry cites the verdict file. Writing it is
  `release-lead`'s job (the scribe), not the reviewer's.

## Verdict

**pass**, **pass with notes**, or **block**, with findings at file:line and severity,
then docs owed, seams handed off, and the evidence. Write it to
`docs/plans/<slug>/design-review.md`, or `docs/feedback/items/<id>-<slug>/design-review.md`
for feedback items (beside `ux-lead`'s `ux-review.md`). Severity rules and the template:
[references/verdict-template.md](references/verdict-template.md).

## Seams and handoffs

Route to org boxes only, through `head-product` unless an operator-approved direct route
exists.

| Seam | Goes to |
|---|---|
| Flows, navigation, screen states (empty, loading, error), onboarding path | `ux-lead` |
| Copy, UI words, tier names (the words) | `marketing-lead` |
| Tier and position hex or label changes | joint `design-lead` + `head-eng` (owns `cross-client-invariants.md`); words also `marketing-lead` |
| Token-mirror code, shared components (`chalkline/*`) | `head-eng` writes, `design-lead` reviews |
| Fixes to the diff itself | the building area's eng lead, through `head-eng` |
| Model-visible changes (deck or ranking output) | not this review; `models-lead` through `head-bizops` |
| Palette, token system, rebrand | `design-lead` with user-level `/brand-lab`; needs an operator decision and an ADR |
| Invite, share and landing UI for task 3 (growth loops) | `growth-pm` ↔ `design-lead` directly, until task 3's deliverables are accepted (operator-approved route W4, 2026-10-15); after that, through `head-product` |

Never route to retired skills (`ux-design`, `ux-research`, `fin-budget`, `fin-forecast`,
`legal-privacy`) or to `maestro-test`.

## Guardrails

- Review only. The verdict file is the one thing you write; code, `docs/design/`,
  `cross-client-invariants.md` and this skill's register change through their owners.
- Report what you ran. A rule not run, or `test:contrast` skipped on a token change, is
  written under "Not run", never left out.
- No merges, pushes to `main`, flag flips or outbound messages.
- There is no mobile CI guard for these rules yet. A `mobile/tests/check-chalkline.js`
  structural guard is being proposed to `head-eng`; until it exists, the sweep is run by
  hand on every UI diff. Do not write the guard from this skill.
