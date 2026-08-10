# screens/ — the screen library (exact ground truth)

Captures of every mobile app screen in every state (idle / loading / empty /
error / populated / …), taken hermetically from the REAL app on the canonical
simulator (FTF-iOS18, iOS 18.4, dark mode — the app is dark-only). **Only
`mobile/scripts/screen-capture.sh` writes here** — never hand-edit PNGs or
`manifest.json`.

## Layout

- `mobile/<screen>/<state>.png` — screen dirs use the testID prefixes
  (`signin`, `trades`, `tiers`, …); state names: `idle | loading | empty |
  error | populated | busy | done` + `--modifier` variants (`loading--slow`).
- `mobile/sheets-<sheet>/` — modal surfaces, same flat level with a `sheets-`
  prefix (`sheets-rank-menu`, `sheets-trade-dna`, …), not a nested `sheets/` dir.
- `manifest.json` — per capture: flow, profile, injections, captured_at; per
  screen: source files + hash (the freshness anchor); global: app sha + device.
- Fixed filenames, overwritten in place — git history stays bounded.

**Coverage is not total — `manifest.json` is the authority on what exists.** Some
surfaces are unreachable from a hermetic capture flow and are absent by design
(live WebViews such as SleeperConnect/EspnConnect can't be reproduced); others are
absent only until the flow that reaches them lands, or until a feature flag is on.
Before assuming a screen is deliberately excluded, check `manifest.json` — if it
isn't listed there and isn't a WebView, it's a coverage gap worth requesting, not a
policy. Never substitute a redrawn approximation for a missing capture.

## For mockup agents (load-bearing — see feedback lessons #256/#257)

Before designing any change to screen X, **open every PNG under
`mobile/<x>/`**. A polish-lab mockup's "current" pane embeds the actual capture
via relative `<img src="../../screens/mobile/<x>/<state>.png">` — never redraw
"current" from memory or from reading source alone. If a screen is missing or
`mobile/scripts/screen-freshness.sh` flags it stale, say so in the deliverable
and request a capture run first. Full mockup-side rule (including the exact
relative depth): `mockups/CLAUDE.md`.

## For the operator

Extraction is a plain folder copy: `cp -R screens/ ~/Desktop/` or drag in
Finder — ordinary PNGs, no LFS, no build step. To see a screen LIVE instead:
`mobile/scripts/screen-capture.sh --interactive --screen <x> [--state <y>]`
leaves the simulator running in that exact state.

## Freshness

`screen-freshness.sh` compares each screen's source hash vs the manifest;
stale screens are re-captured via `screen-capture.sh --screen <x>` (4–7 min).
The sim-gate tier matrix (runbook) and the feature-scope block carry the
capture-delta obligations; the pre-push hook warns (never blocks) when screen
source changes without a capture refresh. Prereq: `brew install pngquant`
(runner falls back to sips downscale with a warning).
