# FTF Visual Brand — "Chalkline"

Date: 2026-07-02
Status: Accepted (visual identity v1). Voice/copy rules live in [`living-memory/BRAND.md`](../../living-memory/BRAND.md) and are unchanged.

Companion files: [`design-system.md`](design-system.md) (tokens), [`components.md`](components.md) (component library), [`web/style-guide.html`](../../web/style-guide.html) (live reference page).

---

## Positioning

Fantasy Trade Finder is a **front office tool**. The user is a GM working a trade desk, not a fan being entertained. The visual language should read like the tools GMs respect: broadcast graphics packages, betting boards, terminal screens — dense, dark, confident, numeric.

Design language name: **Chalkline** — chalk on turf under stadium lights. Warm off-white text ("chalk") on a dark surface with a faint turf undertone ("ink"), one sharp lime-yellow signature ("volt"), and yard-line hairlines for structure.

## Why this exists

Research on AI-generated design tells (3.2M-post Reddit analysis; Anthropic's frontend-aesthetics cookbook) ranks the giveaways: shadcn/Tailwind defaults, AI-purple gradients, Inter/system fonts, emoji-as-icons, glassmorphism, uniform rounded cards, timid evenly-distributed palettes. The pre-Chalkline FTF UI had several (GitHub-dark palette, generic SaaS blue `#4f7cff`, system font stack, emoji iconography, blur overlays). Chalkline is the deliberate, domain-derived replacement. See ADR-004.

## Brand pillars

| Pillar | Meaning in UI |
|---|---|
| **Numbers are the product** | Elo, fairness %, value deltas set in mono type, always legible, never decorative |
| **Broadcast, not SaaS** | Condensed uppercase display type, scoreboard density, sharp corners |
| **One loud color** | Volt appears only where action or brand lives; everything else is chalk on ink |
| **Chalk on turf** | Warm neutrals, hairline rules (yard lines) for structure instead of shadows and blur |
| **Peer, not tutor** | Copy stays terse and dynasty-fluent per the voice charter |

## Signature moves

These are the recognizable, ownable details. Use them; don't invent parallel ones.

1. **Volt tick** — a 3px × 14px volt rectangle preceding section labels (the "yard marker"). This is the brand's smallest unit.
2. **Chalk rule** — 1px `--line` hairlines separate list rows and sections. Depth comes from surface steps + hairlines, never blur or heavy shadow.
3. **Scoreboard numerals** — every number that matters (Elo, fairness %, value, rank) is IBM Plex Mono, tabular.
4. **Position rail** — player cards carry a 3px full-height left rail in the position color (replaces the old top bar).
5. **Condensed caps** — screen titles and section headers are Barlow Condensed, uppercase, tracked. Body stays sentence case.

## Logo / wordmark direction

- Wordmark: `TRADE FINDER` in Barlow Condensed Bold caps, chalk, with a volt tick before the T. Short form `FTF` for the extension popup and favicons.
- No gradient, no glow, no icon-in-rounded-square app-store cliché for the web header.
- Mascot (fumbling RB, name pending Q-009 — Tommy Tumble vs Ricky Rumble) is an **illustration asset, not UI chrome**: allowed in empty states, celebration moments, and the auth page. Never inline with data.

## Color philosophy

- Dominant: ink surfaces (~90% of any screen).
- Chalk text carries hierarchy through weight and size, not color.
- Volt is rationed: primary CTA, active states, focus, the tick. If a screen has volt in more than ~3 places, remove some.
- Position colors (QB orange, RB green, WR blue, TE purple) and tier colors (gold/green/blue/purple/gray) are **preserved cross-client invariants** — see [`docs/cross-client-invariants.md`](../cross-client-invariants.md). They are data encodings, not brand colors, and the neutral ink field is what keeps them legible.

## Never list (brand level)

- No purple/indigo brand gradients; no gradients as decoration anywhere.
- No emoji as icons or in UI copy (voice charter already bans emoji in docs; this extends it to all clients).
- No glassmorphism, blur overlays, aurora backgrounds, neon glow.
- No Inter/Roboto/system-default typography.
- No centered-hero-plus-three-icon-cards marketing layout on the auth page.
- No hype copy ("league-winner!", exclamation defaults) — per voice charter.
