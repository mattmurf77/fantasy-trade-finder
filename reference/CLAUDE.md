# reference/ — Notes for Claude

Competitor app/web screenshots captured for teardowns. **Reference captures only** — a
capture index may sit alongside the images, but the analysis lives in `docs/`.

| Capture set | Captured | Contents |
|---|---|---|
| `dynasty-nerds-app/` | 2026-08-04 | 32 full-page desktop screenshots (1440×844) of app.dynastynerds.com via the operator's logged-in session, plus `index.md` — a per-file page/URL/description index. Untracked in git. |

Where the analysis lives:

- [`docs/competitor-teardown-dynastygm.md`](../docs/competitor-teardown-dynastygm.md), `-dynastydealer.md`, `-ti-calc.md`, `-web-tools.md`
- [`docs/business/product/2026-07-26-dynastygm-app-teardown.md`](../docs/business/product/2026-07-26-dynastygm-app-teardown.md) and `2026-07-26-dynastydealer-dtf-teardowns.md`
- The `pm-competitor` skill owns the feature-gap matrix.

## Git status — read before adding anything

`reference/` is **not** in `.gitignore`. Only `CLAUDE.md` is tracked; everything else here
(`dynasty-nerds-app/`, 32 PNGs + `index.md`) is untracked and shows up as clutter in
`git status`. Either commit a capture set deliberately or add a `.gitignore` rule — do
not assume it is already ignored. Do not commit captures of paywalled or logged-in
competitor content without an operator decision.

Not to be confused with [`screens/`](../screens/CLAUDE.md), which is FTF's *own* app,
captured automatically.
