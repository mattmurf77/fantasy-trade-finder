# ADR-005: Chalkline palette v2 — ice/flare replaces volt

Date: 2026-07-03
Status: Accepted (revises the palette section of ADR-004; all other Chalkline decisions stand)

## Context

The operator reviewed the v1 palette (turf-undertone ink + single volt-lime accent, shipped to TestFlight as 1.0.0 build 18) against alternatives rendered as identical Trios-screen mockups (`web/color-lab.html`, `web/color-lab-2.html`) and rejected volt. v1 also had no secondary accent — informational highlights borrowed volt or semantic colors, overloading their meaning.

## Decision

Option B1 from the color lab: **graphite ink** (`#0C0E11` family), **ice** cyan `#56D9EC` as the primary accent (actions: CTAs, active states, focus, ticks, selection), and **flare** pink `#F0508C` as a secondary accent restricted to informational highlights (likes-you pill, rookie badge, streaks, unread markers). Tokens renamed honestly (`volt` → `ice`, new `flare`) rather than leaving a lime-named token holding cyan. Position/tier hexes unchanged.

## Alternatives considered

- Keep volt (baseline A) — rejected by the operator on taste; also sits near RB green.
- Stadium yellow / Broadsheet cream primaries — presented, not chosen.
- Pink primary with cyan secondary (D1) — the inverse pairing; operator preferred cyan as the action color.
- Retaining token name `volt` with new values — cheaper diff, but a token named after lime holding cyan misleads every future reader.

## Consequences

- Easier: informational emphasis no longer overloads semantic green/warn or the primary accent.
- Ice vs WR-position blue (`#3B82F6`) is a brightness distinction, not a hue distinction — the accessibility floor (color never the only encoding) is what makes this safe.
- Ships as TestFlight 1.0.0 build 19; build 18 (volt) remains the visual v1 record.
