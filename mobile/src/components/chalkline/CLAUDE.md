# mobile/src/components/chalkline/

Chalkline design-system primitives (ADR-004). Reference implementation — existing screens still use the legacy components one directory up; migrate screen-by-screen.

Tokens: `../../theme/chalkline.ts`. Specs: `docs/design/design-system.md` + `docs/design/components.md`. Web mirror: `web/style-guide.html`.

| Component | Use |
|---|---|
| `TickLabel` | Volt tick + uppercase label (section headers, column headers) |
| `Button` | primary / secondary / like / pass / ghost |
| `Badge` (+ `PositionBadge`, `TierChalkBadge`, `RookieBadge`, `InjuryBadge`) | Border-in-encode-color + chalk text construction |
| `Card` | ink-1 surface, hairline, optional position rail, volt selected state |
| `Meter` (+ `fairnessColor`) | 4px square-end track; fairness/coverage/strength |
| `StyleGuide` | Renders everything; not in navigation — mount temporarily to view |

Rules (from the design system, enforced): no emoji, no gradients, no blur, no radius >8 except pills, volt ≤3 places per screen, data numbers always Plex Mono tabular. Fonts load via `@expo-google-fonts/*` (install command in `chalkline.ts` header); components degrade to platform fonts until loaded.
