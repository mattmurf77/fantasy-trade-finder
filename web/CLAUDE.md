# web/ — Notes for Claude

Vanilla HTML/CSS/JS, **no build step, no framework, no package.json**. One `.html` file
per page; shared logic in `js/`, shared tokens/styles in `css/styles.css`. Served by the
Flask backend (`run.py`), so a page is live the moment the file exists.

## Pages

| File | Shipped? | What it is |
|---|---|---|
| `index.html` | yes | Single-page app entry — Dynasty Rankings. Only page that links out to `faq`, `league-rankings`, `positional-tiers` |
| `league-rankings.html` | yes | Per-league ranking view |
| `positional-tiers.html` | yes | Positional tier boards |
| `player.html` | yes | Player profile |
| `profile.html` | yes | User profile |
| `ranking-method.html` | yes | "Set your rankings" explainer |
| `faq.html` | yes | FAQ |
| `privacy.html` / `terms.html` | yes | Legal pages (App Store / Play listing links point here) |
| `style-guide.html` | reference | **LIVE Chalkline design-system reference — check it before styling anything** |
| `admin/analytics.html` | operator-only | Analytics dashboard; not linked from any public page |
| `color-lab.html`, `color-lab-2.html` | no | Frozen palette-exploration scratch from the Chalkline brand pass. Historical — do not treat as current tokens |

## Shared code

| File | Size | Role |
|---|---|---|
| `js/app.js` | ~6.2k lines | Everything: fetch layer, rendering, page routing |
| `js/events.js` | ~175 lines | Analytics emission. Events must match `backend/analytics_taxonomy.py`; gated on the `analytics.client_events` flag |
| `css/styles.css` | ~4.6k lines | Chalkline tokens + all page styles |

## Rules

- **UI tokens:** root `CLAUDE.md` §Conventions "UI rules" + [`docs/design/design-system.md`](../docs/design/design-system.md) + [`docs/design/components.md`](../docs/design/components.md). Never emoji-as-icons, gradients, blur, system font stacks, radius >8px.
- **Doc triggers:** new page → [`docs/CLAUDE.md`](../docs/CLAUDE.md); any UI change → `docs/design/`; new/changed route consumed here → [`docs/api-reference.md`](../docs/api-reference.md).
- **No automated web tests.** Verify by running `python run.py` and loading `http://127.0.0.1:5000/`.
- Web screen captures are not part of the screen library yet — see [`screens/web/README.md`](../screens/web/README.md).
