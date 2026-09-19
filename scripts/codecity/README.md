# Code City — a map of this repo as a 3D city

A local, offline web page that draws every git-tracked file in this repo as a building.
Directories are districts, files are buildings, and the whole thing is labelled so you can
read the codebase's shape at a glance.

| City | Code |
|---|---|
| District (plate) | A directory — nested directories are plates stacked on plates |
| Building | A file |
| Building height | Lines of code (or commits, or bytes — switchable) |
| Building footprint | Relative size within its directory (treemap-squarified) |
| Colour | Language, or file age, or commit churn |

## Run it

```bash
python3 scripts/codecity/generate.py && open scripts/codecity/city.html
```

The generator writes three derived, gitignored files:

- **`city.html`** — the whole city in one file, data inlined. Open this. Safari won't let a
  `file://` page load even a sibling `<script src>`, so `index.html` comes up blank on a
  double-click; `city.html` has no subresources and always works.
- `city-data.json` — the raw tree, for any other tool that wants it.
- `city-data.js` — the same data as a `window.CITY_DATA` assignment, loaded by `index.html`.

`index.html` is the source template — edit that, then re-run `generate.py` to rebuild
`city.html`. To serve it instead of opening the file, the `scripts/codecity` entry in
`.claude/launch.json` runs it on port 8770.

Re-run `generate.py` any time to refresh the city after the repo changes.

## Controls

| Input | Does |
|---|---|
| drag | rotate (yaw + pitch) |
| shift-drag | pan |
| wheel | zoom at the cursor |
| click | enter the district under the cursor (works on buildings too) |
| right-click / `Esc` | back up one level |
| `R` | reset the camera |
| hover | full path, lines, commits, size, last-touched date |

The sidebar switches the height metric and the colour mode, scales building heights,
controls label density, searches for files by path (matches glow gold), and filters
languages out of the layout by clicking legend rows.

## How it's built

- `generate.py` — walks `git ls-files`, counts lines, reads per-file commit counts and
  last-commit dates out of one `git log` pass, and emits a nested tree.
- `index.html` — self-contained viewer: squarified treemap layout, a hand-rolled
  isometric canvas renderer (painter's algorithm, back-face culling, per-yaw wall
  shading), and colour-buffer picking for hover/click. No dependencies, no CDN, no build
  step — it runs offline.

Only git-tracked files are drawn, so `node_modules`, worktrees, and other untracked
noise never enter the city.
