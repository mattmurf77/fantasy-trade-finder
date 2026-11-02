# Palette labs

## Where they live

A palette lab goes in `mockups/<slug>/`, for example `mockups/palette-<topic>-YYYY-MM-DD/`.
It never goes in `web/`.

`web/` is served as static files by Flask. `web/color-lab.html` and `web/color-lab-2.html`
are frozen ADR-005 records. The only thing keeping them out of production is
`_PROD_BLOCKED_STATIC` in `backend/server.py`, and
`backend/tests/test_prod_blocked_static.py` pins that list. A new lab in `web/` would be
public unless someone also extended the list. Leave both files alone.

## Method

Follow user-level `/brand-lab` Phase B1 and B2 and its `references/color-lab-pattern.md`,
with these repo overrides:

- `color-lab-pattern.md:42` keeps each round as `color-lab.html`, `color-lab-2.html`, and
  so on. Those are the names of this repo's two frozen `web/` records, and that is where
  ADR-005's rounds went. **This skill overrides that line for this repo:** each round is
  `mockups/<slug>/round-<N>.html`.
- `color-lab-pattern.md:7` loads Google Fonts. Labs here make no network requests; the
  font tokens fall back instead (`lab-layout.md` § Self-contained).
- Serve labs from the repo root (`lab-layout.md` § Viewing).

The method itself, unchanged:

- Use one real screen, the most information-dense one, because it exercises the accents,
  the data colors and the invariants together. That screen's frame follows the
  before-pane rule (`before-pane.md`).
- Vary **only palette tokens**. Type, layout and construction stay identical across
  frames. Build every frame from one template driven by a JS variants array.
- **Frame A is the baseline**: the current palette, with values copied from
  `web/css/tokens.css`. Record that file's sha.
- **Invariant colors stay fixed in every frame**: positions, the pick ladder and the
  semantic colors (`docs/cross-client-invariants.md`, `docs/design/design-system.md`
  § Preserved invariants). The lab shows how each candidate collides with them.
- Each frame shows where the primary accent lives (CTA, selected card, active tab, tick)
  and where the secondary lives (a delta, a count emphasis, an informational pill), with
  labelled hex chips above.
- Round 1 has 4 or 5 candidates. Each gets a one-line rationale that names its collision
  risks honestly, including the nearest occupied hue and whether its separation comes
  from hue or only from brightness.
- Round 2 uses crossovers: each liked primary is shown as the other's secondary.
- Rounds stay in the same lab (SKILL.md § Rounds).

## Out of scope: applying the winner

Applying a palette is user-level `/brand-lab` Phase B3: an honest token rename across
`web/`, `mobile/` and `extension/`, sweeps, typecheck, and a standalone revertible commit.
It also needs a superseding ADR in `docs/adr/`; ADR-005 is the current palette and stays
as history. That is code work, routed through `head-product`. Position and tier encodings
change only jointly with `head-eng` (`docs/cross-client-invariants.md`). The lab is the
decision record that the ADR cites.
