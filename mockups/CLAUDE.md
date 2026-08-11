# mockups/ — Notes for Claude

Design scratch/prototypes — hand-built, self-contained HTML (Chalkline tokens, no
frameworks): avatar-lab, calc-value-clarity, outlook-odds, picks-quickrank,
polish-lab-2026-08, quickset-cards, tier-density, trade-calc, trade-finding-hub.
**NOT shipped code:** never import from here or cite it as current app behavior.
Live design truth is `docs/design/` + `web/style-guide.html`.

## The one hard rule: embed the real capture

Any mockup revising an **existing** screen must show that screen's actual capture as
its "current"/"before" pane — not a redrawn approximation, not a reading of source:

```html
<!-- from mockups/<project>/index.html — two levels deep, so ../../ reaches the repo root -->
<img src="../../screens/mobile/<screen>/<state>.png">
```

`mockups/` and `screens/` are siblings at the repo root, so a file at
`mockups/<project>/index.html` — the normal case, and where all but one mockup lives —
uses exactly `../../screens/mobile/…`. A top-level `mockups/x.html` uses `../screens/…`;
one level deeper (`mockups/<project>/sub/x.html`) needs `../../../`. Count the depth; a
broken `<img>` silently degrades the mockup back into a from-memory drawing.

Missing capture, or `mobile/scripts/screen-freshness.sh` flags it stale? Say so in the
deliverable and request `mobile/scripts/screen-capture.sh --screen <x>` (4–7 min)
before designing. See `screens/CLAUDE.md`.

**Why this rule exists (#256/#257):** the TradesHome full-sheet mockups carried
placeholder copy invented from memory — lane pills labelled "Win-now moves" when the
shipped screen said "Team-fit moves" / "Value moves" — and the divergence had to be
caught and corrected by operator decision at build time
(`docs/feedback/items/257-edit-full-sheet/status.md`, decision Q3). Embedding the real
capture makes that class of drift impossible.

## Housekeeping

`mockups/` and `screens/` are both listed in `.easignore`, so neither ships in the EAS
build archive. Keep mockups self-contained (inline CSS/JS); the capture `<img>` is the
only expected cross-directory reference.
