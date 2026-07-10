# ADR-004: Chalkline design language replaces the default dark theme

Date: 2026-07-02
Status: Accepted

## Context

The UI across web/mobile/extension was functional and cross-client consistent but visually generic, exhibiting several of the highest-ranked "AI-generated" design tells (per a 3.2M-post Reddit analysis and Anthropic's frontend-aesthetics cookbook): GitHub-dark palette, generic SaaS blue accent (`#4f7cff`), system font stack, emoji-as-icons, glassmorphism/blur overlays, uniform border radii, tinted-rgba badge fills, and a centered-hero auth layout. The operator wants the product to read as designed, not generated.

Constraint: tier colors, position colors, Elo cutoffs, K-factors, enum strings, and verbatim trade-card copy are cross-client invariants (`docs/cross-client-invariants.md`) and cannot drift.

## Decision

Adopt **Chalkline** (specs in `docs/design/`): ink surfaces with a turf undertone, chalk text, a single rationed volt accent, Barlow Condensed / Archivo / IBM Plex Mono type, sharp radii (≤8px), hairline-rule depth instead of shadows/blur, a stroke SVG icon set replacing emoji, and explicit prohibitions enforced via `CLAUDE.md`. Position/tier hexes are preserved as data encodings.

## Alternatives considered

- **Keep current theme, fix only emoji/fonts** — cheapest, but leaves the palette and construction patterns that are the strongest tells.
- **Cream-plus-serif editorial light theme** — distinctive but is itself becoming a traded-in AI default ("cream+serif+sage"), and dark-first is right for a data-dense sports tool used at night.
- **Clone Sleeper's design language** — familiar to users but derivative, legally/brand awkward, and the extension injects into sleeper.com where visual distinction matters.

## Consequences

- Easier: consistent future UI generation (docs are the style-guide contract every session reads); brand recognition; extension badges visually distinct on Sleeper.
- Harder: web fonts add a load dependency (Google Fonts on web, bundled via expo-font on mobile); migration of existing screens is a real project (not done in this ADR); the `👀 They're interested` invariant string changes to icon+text and must land in web+mobile together.
- Risk: volt/lime reads close to RB green if overused — mitigated by the "volt in ≤3 places" ration rule and mono construction (border+text, not fills).
