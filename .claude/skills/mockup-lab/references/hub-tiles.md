# Hub and home surfaces: start from tiles

## The preference

The operator stated this on 2026-10-09. Home and hub screens use generous, tappable tiles
that preview live content. Tight lists of text links are out.

## The reference

The visual reference is the operator's local FumbleAI homeowner-app mockup. It is the
operator's own project, not a competitor. Don't copy its files into this repo and don't
cite its paths as FTF code. The translation is already done in
`docs/plans/home-engagement/research.md`:

- §1 "FumbleAI (primary reference)" describes what its Home hub does and what to take
  from it.
- § "FumbleAI vs Chalkline: every conflict" lists each FumbleAI value, the Chalkline rule
  it breaks, and how to render it instead. **That table is authoritative.** Read it
  before drawing.

## The rule

Every direction for a hub or home surface starts from a tile layout rendered in Chalkline
tokens. No direction falls back to a link list. A link list appears only as the labelled
before pane, when that is what ships today.

The rule covers Home (`mobile/src/screens/HomeScreen.tsx`), the Trade-Finding Hub
(`TradeFinderHubScreen.tsx`), the Settings hub (`settings/SettingsHubScreen.tsx`), Rank
home (`RankHomeScreen.tsx`), and any new hub.

## What a tile carries

These come from research.md § "Synthesis: what we carried over".

- A title, a live preview (a count, a value or a named item), and one tap to its
  destination.
- A badge that hides at zero, with urgency ranked above totals.
- A setup prompt in place of the preview when data is missing ("Link a league", "Not
  enough rosters yet").
- When the surface has one primary job, a single hero chosen from the user's state, above
  a grid of equal tiles.
- A live summary line ordered by urgency, with an all-clear fallback, so it is never
  empty.

## Chalkline translation (summary)

The research.md table is the full version.

- Radii: cards 8, icon wells 4, badges 2. Pills only where the spec calls for one.
- Tiles carry no shadow. The pressed state is an ink-3 fill, never a scale or lift.
- Ice appears in at most about 3 places per screen (the hero CTA, the YOU marker, the
  active tab). Flare is for counts and attention only, never the tile's tap affordance.
- Barlow Condensed for headings, Archivo for UI, IBM Plex Mono for every number. Icon
  wells are ink-2 with chalk-dim glyphs from the Chalkline icon set.
- Hit targets are 44pt or larger. The 2-column grid collapses to 1 column at
  accessibility text sizes.
- States to draw: no league, thin league, loading (a static skeleton with no shimmer),
  error, populated.

## Precedent

- `mockups/home-engagement/`: Directions A to C are all tile-based. Round 2's Direction D
  is the operator's revision and the current candidate.
- `mockups/settings-ia-hub/`: Settings as a hub with second-level pages.
