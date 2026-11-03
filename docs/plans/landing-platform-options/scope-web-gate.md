# Feature Scope — web ESPN/MFL chips hard-off (the web gate before ask 16)

**Date:** 2026-10-27
**Entry point:** direct ask (head-eng → onboarding-eng 2026-10-27, item 3: "the web ESPN/MFL chips stop reading landing.platform_options and stay off … A web proof-based sign-in is post-launch.")
**Builder:** onboarding-eng
**Operator sign-off on waivers:** surfaced through head-eng and this PR's description (the operator talks to the coordinator only). The waivers are §1 analytics and §3's TestFlight checklist, both for the reasons given.

**What changes.** `landing.platform_options` is going back ON (operator ask 16) to mean the APP's proof-based ESPN/MFL sign-in (#430). The web reads the same flag, so it would show its ESPN/MFL chips again. On main those chips only open a "continue in the app" panel; the web stopped calling `POST /api/entry/platform` earlier. The web has no proof-based sign-in until after launch, so its chips are now hard-off:
- `web/js/app.js` has `const WEB_PLATFORM_ENTRY = false`;
- the chip reveal (`_applyPlatformOptionsFlag`) and the chip handler (`selectEntryPlatform`) read it instead of the flag.

The ESPN/MFL panels' code stays for the post-launch web sign-in. ESPN/MFL-only visitors get `m3.web.espn_mfl_cta` (legal-approved copy) under the Sleeper door at the 11-18 flip, in #456. Until then they see the Sleeper door alone, as they do today while the flag is off for the purge.

**Hard-off, not a new web flag** (head-eng offered either):
- a constant adds no flag surface, and nothing in prod can turn the chips back on by accident;
- the web change that adds a proof-based sign-in flips it, in review.

---

## 1. Analytics scope

- [ ] (a) New events specced: none.
- [ ] (b) Existing events cover it: none apply.
- [x] **(c) WAIVED — no analytics needed because:** no web event fires from the chips or the ESPN/MFL panels (`git grep` over `web/js` and `backend/analytics_taxonomy.py`: no chip or entry-platform event). Hiding them removes no data. Web landing traffic is still counted by the existing page-view events.

## 2. Schema & flag scope

- New/changed tables or columns: none.
- New/changed feature flags: **none.** `landing.platform_options` is unchanged in `config/features.json`, on the server and on mobile. Only the web stops reading it. `docs/config-reference.md`'s row now says the web doesn't read it.
- New env vars / `model_config` keys: none. **Rollback:** revert this PR. The web then follows the flag again, which is main's behaviour today.

## 3. Evidence scope

- [x] **Structural guard:** `qa/web/check_web_structure.py` `GATE-web-espn-mfl-off[index.html]` pins:
  1. no web script or shipped page calls `FTF_FLAG('landing.platform_options')`;
  2. app.js declares exactly one `const WEB_PLATFORM_ENTRY = false;`;
  3. the chip reveal sets `optionsOn` from it, and `selectEntryPlatform` refuses ESPN/MFL through `!WEB_PLATFORM_ENTRY`;
  4. `#platform-row` and both ESPN/MFL chips ship with the `hidden` class.

  **Sabotage 8/8 red**, each restored byte-identical: the reveal or the handler reading the flag again, the constant set to true, the reveal or the handler bypassing the constant, either chip or the row unhidden in the markup, and an inline script reading the flag.
- [ ] Unit tests: none. Web has no JS unit harness; the checker (in CI's `web-structure` job) is the web's guard.
- [x] **The local browser harness** `qa/web/check_browser_auth_runtime.cjs` clicked `#platform-chip-espn` with the flag on. It now asserts the row and both chips are hidden and that there's no `/api/entry/platform` call.
  - **Not run here:** no Playwright install on this machine.
  - The lines it replaced were already stale on main: they waited for an ESPN/MyFantasyLeague sentence `web/` no longer has.
- [x] **Runtime proof (local browser, static serve of this worktree's `web/`):**
  - With `FTF_FLAG` forced to return true for every flag and `ftf:flags-ready` fired (the ask-16 state), `#platform-row` and both chips stay hidden. `selectEntryPlatform('espn')` changes nothing: the ESPN chip doesn't turn on and `#entry-mobile` stays hidden.
  - `WEB_PLATFORM_ENTRY` resolves, with no temporal-dead-zone error: it's declared above `_applyLandingFlags()`, which runs the chip reveal at once.
  - **Control:** the same script on the pre-change code shows the row and both chips, and selects ESPN.
  - Console: only the static server's `/api/feature-flags` 404.
- [x] **Code-walk:**
  - The chips reach the DOM only through `_applyPlatformOptionsFlag` (`web/js/app.js`, `classList.toggle('hidden', !espnOn)`).
  - The only other path to an ESPN/MFL panel is `selectEntryPlatform`. Its single writer of `_entryPlatformSel` is guarded by the gate; the chip `onclick`s and the Sleeper fallback call it.
  - Nothing else on web calls `/api/entry/platform` (comments only).
- [x] **Manual TestFlight checklist — WAIVED because:** this is web-only, with no mobile change.

  **Operator web check after deploy (optional):** with the flag ON, open the site signed out. Only the Sleeper username door shows, with no ESPN/MFL chips.
- `testID`s added/renamed: none (no mobile change).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route change. `POST /api/entry/platform` is untouched; #430 owns its proof-based rewrite. |
| `living-memory/LLD.md` | n/a | No schema, route or invariant convention shifts. A client stops reading one flag. |
| `docs/architecture.md` | n/a | No module wiring or data flow change. |
| `living-memory/HLD.md` | n/a | No architecture shift. |
| `docs/cross-client-invariants.md` | n/a | No shared constant changes. The web/mobile flag split is recorded in config-reference. |
| `docs/glossary.md` | n/a | No new term. |
| ADR or `DECISIONS.md` | n/a | Hard-off vs a web flag is recorded above and in config-reference. head-eng's decision, not a new architectural choice. |
| `docs/config-reference.md` | **updated** | `landing.platform_options` row: the web doesn't read it (history kept). |
| `web/CLAUDE.md` | **updated** | `index.html` row: Sleeper only on the landing. |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck`, testid-lint and `web-structure` (`qa/web/check_web_structure.py`, which carries the new pin) on the pushed sha.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry (this PR).
- **TestFlight verification:** n/a (web-only).
- **Must merge before ask 16** (`landing.platform_options` back ON). Merge stays with release-lead, on the operator's go.
- Express lane declared by the operator? No (full gates).
