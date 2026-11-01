# Feature Scope — A shared package's card names the calculator's generic picks

**Date:** 2026-11-01
**Entry point:** follow-up found by release-lead in #566's QA, routed to trades-eng ("yours to scope separately").
**Builder:** trades-eng
**Operator sign-off on waivers:** not needed. The waivers below are for things this change doesn't touch.

**Why:**
- The live calculator's pool holds the 12 generic pick rungs (`generic_pick_<round>_<early|mid|late>`, `server.py`'s universal pool), and its share passes them through (`hasPickAssets={false}`: they aren't league picks).
- The `/s/p/<id>` landing's OG card looks names up in the `players` table, which has no generic picks, so it drew **"Unknown player"**. That's the PR-14 failure in another place.
- **The change** (server-only, live with the next Render deploy; no app binary): `og_image.render_package_card` resolves a `generic_pick_*` id to the label the calculator shows (`pick_values.generic_pick_label`, e.g. "Mid 1st Round Pick") with the PICK chip. Any other unknown id still says "Unknown player".
- **Unchanged:** league picks. The in-league share skips the mint for those (`hasPickAssets`, PR-14).

## 1. Analytics scope
- [x] **(c) WAIVED. No analytics needed:** no event is added or changed.

## 2. Schema & flag scope
- **New/changed tables, columns, flags, env vars or `model_config` keys:** none. The card is behind `growth.share_landing` as before.

## 3. Evidence scope
- [x] **Unit test:** `backend/tests/test_share_link_previews.py::test_og_package_card_names_the_calculators_generic_picks`. Through `/og/p`, two generic picks draw "Mid 1st Round Pick" / "Late 2nd Round Pick" with PICK chips, and an id nothing knows draws "Unknown player". It fails on main's code.
- [x] **Before/after:** `before-after.png`, rendered by the real `og_image.render_package_card` (not a mock) for one package, before and after.
- [x] **Manual check** (operator, after the Render deploy, with `growth.share_landing` on): in the live calculator, put a generic pick (PICK filter) on a side → **Share** → open the "Build your own" link. The preview card names the pick ("Mid 1st Round Pick") with a PICK chip, not "Unknown player".
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | `/og/p/<id>.png` keeps its contract; only a name it draws changes |
| `living-memory/LLD.md` / `docs/architecture.md` / `living-memory/HLD.md` | n/a | no convention, wiring or module change |
| `docs/cross-client-invariants.md` / `docs/glossary.md` | n/a | the label is the calculator's existing one |
| ADR / `DECISIONS.md` | n/a | a bug fix |

## 5. Ship gate declaration
- **CI green:** `backend-tests`, `mobile-typecheck`, `testid-lint`.
- **Evidence recorded:** TEST_LEDGER.
- **Verification:** the manual check above, after the Render deploy.
- Express lane declared by the operator? No.
