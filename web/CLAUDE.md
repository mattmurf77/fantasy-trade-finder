# web/ — Notes for Claude

Vanilla HTML/CSS/JS, no build step. One `.html` file per page, linked from `index.html`. Shared code in `js/` (app.js, events.js) and `css/` (styles.css). `admin/` is operator-only (analytics.html). `color-lab.html` / `color-lab-2.html` are scratch, not shipped pages.

`style-guide.html` is the LIVE Chalkline design-system reference — check it before styling anything.

UI token rules: root `CLAUDE.md` §Conventions "UI rules" + `docs/design/design-system.md` + `docs/design/components.md`. Route triggers: new page → `docs/CLAUDE.md`; any UI change → `docs/design/`.
