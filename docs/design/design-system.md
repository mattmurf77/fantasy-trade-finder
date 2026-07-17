# Chalkline Design System — Tokens

Date: 2026-07-02
Applies to: `web/`, `mobile/`, `extension/`, `mockups/`. Live reference: [`web/style-guide.html`](../../web/style-guide.html).
React Native mirror: tokens in [`mobile/src/theme/chalkline.ts`](../../mobile/src/theme/chalkline.ts), primitives in [`mobile/src/components/chalkline/`](../../mobile/src/components/chalkline/) (TickLabel, Button, Badge, Card, Meter, StyleGuide screen). Keep the two in lockstep with this file.

Any Claude session or human touching UI reads this file first. When a component spec is needed, see [`components.md`](components.md).

---

## Prohibitions (enforced, not advisory)

These override any default tendency. If generated UI contains one of these, it is a bug.

1. No emoji in UI (icons, buttons, empty states, toasts). Use the Chalkline icon set.
2. No gradients (backgrounds, text, buttons, borders).
3. No `backdrop-filter` / glassmorphism / translucent `rgba(255,255,255,x)` surfaces. Surfaces are solid ink steps.
4. No Inter, Roboto, or bare system font stack. Fonts are Barlow Condensed / Archivo / IBM Plex Mono only.
5. No border-radius above 8px except true pills (`999px` on count badges and chips explicitly specced as pills).
6. No purple/indigo accent for brand or CTAs. The primary accent is ice; the secondary is flare, and flare appears ONLY on informational highlights, never on actions. (`#a855f7` and `#3b82f6` remain **only** as TE-position and WR-position data colors; ice is distinguishable from WR blue by brightness.)
7. No hover `translateY` lift on cards. State changes use border and surface color.
8. No box-shadow except `--shadow-sheet` on sheets/menus/toasts.
9. No new hues. If a color isn't in this file or `cross-client-invariants.md`, don't ship it.

## Color tokens

Dark-only (unchanged). All values hex; define as CSS variables in `web/css/styles.css`, mirror in `mobile/src/theme/colors.ts` and `extension/*.css`.

Palette v2 ("ice/flare", ADR-005) — graphite ink, ice-cyan primary, flare-pink secondary. Replaced v1's turf ink + volt lime after operator color review (`web/color-lab-2.html`, option B1).

### Ink (surfaces)

| Token | Hex | Use |
|---|---|---|
| `--ink-0` | `#0C0E11` | Page background |
| `--ink-1` | `#13161B` | Cards, panels |
| `--ink-2` | `#1A1E25` | Raised: sheets, menus, popovers, input fill |
| `--ink-3` | `#232833` | Hover fill, wells, pressed |
| `--line` | `#262C35` | Hairline rules, default borders |
| `--line-strong` | `#3D4654` | Interactive borders (inputs, secondary buttons) |

### Chalk (text)

| Token | Hex | Use |
|---|---|---|
| `--chalk` | `#ECEFF4` | Primary text |
| `--chalk-dim` | `#97A1AE` | Secondary text, labels |
| `--chalk-faint` | `#626C79` | Disabled, placeholders |

### Ice (primary accent — rationed, actions only)

| Token | Hex | Use |
|---|---|---|
| `--ice` | `#56D9EC` | Primary CTA fill, active tab, focus ring, ice tick, progress fill |
| `--ice-press` | `#3FC2D6` | Primary CTA hover/pressed |
| `--on-ice` | `#071013` | Text/icons on ice fill |

### Flare (secondary accent — informational highlights only)

| Token | Hex | Use |
|---|---|---|
| `--flare` | `#F0508C` | Likes-you pill, rookie badge, streak/heat chips, unread markers, count emphasis |
| `--flare-press` | `#D8437B` | Pressed state of flare-bordered interactive chips |
| `--on-flare` | `#170610` | Text/icons on flare fill (rare) |

Division of labor: **ice = what you can do** (CTAs, active states, focus, ticks, selection); **flare = what's worth noticing** (data callouts). Flare never appears on a button or actionable control's primary affordance.

### Semantic

| Token | Hex | Use |
|---|---|---|
| `--pos` | `#22C55E` | Like/accept, positive deltas (shared hex with RB — intentional) |
| `--neg` | `#EF4444` | Pass/decline, errors, destructive |
| `--warn` | `#F59E0B` | Warnings, injury Q (amber-500 — deeper than the tier gold `#fbbf24`) |

### Preserved invariants (do not restyle — see `docs/cross-client-invariants.md`)

Positions: QB `#F97316` · RB `#22C55E` · WR `#3B82F6` · TE `#A855F7`.
Tiers (8-tier pick-value ladder, 2026-07-12): 4+ 1sts `#f87171` · 3 1sts `#e879f9` · 2 1sts `#fbbf24` · 1st `#2dd4bf` · 2nd `#38bdf8` · 3rd `#f472b6` · 4th `#a3e635` · FA `#7a7f96` (label renamed from "Waivers" 2026-07-17; key `waivers`). Tier hues never share a hue with a position color (tiers = bright 400-level family, positions = deeper 500-level; tier red-400 vs `--neg` red-500 and tier fuchsia-400 vs TE purple-500 rely on the same bright-vs-deep separation).
These are data encodings rendered on ink surfaces (rails, badges, meter segments), never used as chrome/brand colors.

## Typography

Web: load via Google Fonts (`Barlow Condensed:600,700`, `Archivo:400,500,600,700`, `IBM Plex Mono:500,600`). Mobile: bundle the same families via `expo-font`.

| Token | Family / weight | Size/line | Case | Use |
|---|---|---|---|---|
| `display` | Barlow Condensed 700 | 32/34 | UPPER, +0.02em | Screen titles, auth headline |
| `heading` | Barlow Condensed 600 | 22/26 | UPPER, +0.03em | Section headers, sheet titles |
| `label` | Archivo 600 | 11/14 | UPPER, +0.08em | Section labels (with ice tick), badge text |
| `title` | Archivo 600 | 16/22 | Sentence | Card titles, player names |
| `body` | Archivo 400 | 14/21 | Sentence | Default copy |
| `body-sm` | Archivo 400 | 13/18 | Sentence | Secondary copy, help text |
| `data-lg` | IBM Plex Mono 600 | 22/26 | — | Hero numbers (Elo, fairness %) |
| `data` | IBM Plex Mono 500 | 13/18 | — | Inline values, ranks, deltas |

Rules: numerals that represent data are always Plex Mono with `font-variant-numeric: tabular-nums`. Barlow Condensed never below 16px and never for body copy.

## Spacing

4-point scale, unchanged from `mobile/src/theme/spacing.ts`; web must adopt it in place of ad-hoc 24px:
`xs 4 · sm 8 · md 12 · lg 16 · xl 24 · xxl 32 · xxxl 48`

## Radii

| Token | Value | Use |
|---|---|---|
| `--r-xs` | 2px | Badges, chips, ticks |
| `--r-sm` | 4px | Buttons, inputs, selects |
| `--r-md` | 8px | Cards, panels, sheets (top corners) |
| `--r-pill` | 999px | Count badges, likes-you pill only |

## Depth

One shadow token: `--shadow-sheet: 0 12px 32px rgba(0,0,0,0.55)` — sheets, menus, toasts only. Everything else: surface step + hairline. Overlay scrim: solid `rgba(7,9,12,0.78)`, no blur.

## Motion

| Token | Value | Use |
|---|---|---|
| `--t-fast` | 120ms ease-out | Hover, press, focus |
| `--t-base` | 180ms ease-out | Tabs, toggles, meter fills |
| `--t-sheet` | 260ms cubic-bezier(0.32, 0.72, 0, 1) | Sheets, panels |

One orchestrated moment per screen: on load, stagger card/list entry 40ms apart (fade + 8px rise), max 6 items. No other scroll/hover animation. Elo changes count up in Plex Mono. Respect `prefers-reduced-motion`.

## Iconography

Inline SVG, 20×20 viewBox (16 in dense rows), `stroke: currentColor`, `stroke-width: 1.75`, square caps, no fills. Needed set (replaces emoji): `rank` (podium bars), `trade` (opposing arrows), `match` (interlocked links), `trends` (spark line), `bell`, `check`, `x`, `swap`, `plus`, `chevron-*`, `search`, `settings`, `eye` (they're-interested), `flag` (injury), `crown` (crown asset). Emoji → icon map: 📊→`rank`, 🔗→`match`, 👥→`trade`, 👀→`eye`, ❌→`x`, ✓→`check`, 🎯→`rank`.
Exception: the `👀 They're interested` pill copy is a verbatim cross-client string — migrate it to `eye` icon + `They're interested` in web and mobile **in the same change**, and update `docs/cross-client-invariants.md` when done.

## Accessibility floors

- Text contrast ≥ 4.5:1 on its surface (chalk on ink-0 ≈ 13:1; chalk-dim on ink-1 ≈ 5.5:1 — don't put chalk-faint on ink-3).
- Focus: 2px ice ring, 2px offset, on every interactive element.
- Hit targets ≥ 44px on touch clients.
- Position/tier color is never the only encoding — always paired with the text label (QB/RB/WR/TE, tier name).
