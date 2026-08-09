# Gotchas — Fantasy Trade Finder

> **Purpose:** known traps in *this* codebase. Symptoms, root causes, workarounds. Different from [`MISTAKES.md`](MISTAKES.md): mistakes are *approaches that failed*; gotchas are *bugs and quirks that bite*.
>
> **Read at:** before debugging anything that smells weird. **Write at:** the moment you waste >30 minutes on a non-obvious quirk.
>
> Companion files: [`../docs/runbook.md`](../docs/runbook.md) for operational runbook (longer-form).

---

<!-- GOTCHAS-INDEX:START -->
| ID | Symptom | Area |
|---|---|---|
| G-023 | Fixing a feedback item already fixed weeks ago | Feedback / process |
| G-022 | Worktree agents drift, duplicate edits, blow up EAS archive | Mobile / worktrees / EAS |
| G-021 | Native header back chevron renders but does nothing | Mobile / navigation |
| G-020 | Local build silently talks to prod API | Mobile / iOS build |
| G-019 | Experiment assignments wrong after setting the salt late | Backend / experiments |
| G-018 | Render env var added, never reaches the process | Infra / Render |
| G-017 | Analytics looked wired but zero rows landed | Backend / analytics |
| G-016 | Flag or targeting attribute registered but inert | Backend / feature flags |
| G-015 | Draft picks vanish with no error anywhere | Backend / draft picks |
| G-014 | Numeric league id misrouted to Sleeper-only code | Backend / platform routing |
| G-013 | iOS capability absent despite correct app.json config | Mobile / iOS native |
| G-012 | TestFlight build ships with wrong marketing version | Mobile / iOS build |
| G-011 | Wrapper's tap or long-press handler never fires | Mobile / PlayerCard |
| G-010 | Extension DOM-scraping breaks after a Sleeper UI change | Extension |
| G-009 | `/api/debug/log` returns empty after a restart | Backend / logging |
| G-008 | Recently added player missing from the picker | Backend / player cache |
| G-007 | Feature flag works on web but not mobile | Cross-client / feature flags |
| G-006 | Sleeper username lookup shows the wrong casing | Backend / auth |
| G-005 | KeyError or type error joining player data | Backend / data types |
| G-004 | `None` errors iterating `roster.players` | Backend / Sleeper API |
| G-003 | A player defaults to Elo 1500 unexpectedly | Backend / data seeding |
| G-002 | DB writes via CLI appear nowhere in the app | Backend / database |
| G-001 | Flask hangs or errors cryptically on start | Local dev / macOS |
<!-- GOTCHAS-INDEX:END -->

Full entries below — grep the ID. Read the entry before acting; this index is a lookup aid, not the content.

---

## 2026-05-21

### G-001 — macOS AirPlay Receiver hogs port 5000
- **Symptom:** `python3 run.py` hangs or errors cryptically. Flask doesn't say "port in use" clearly.
- **Cause:** macOS Monterey+ has AirPlay Receiver enabled by default, which uses port 5000.
- **Fix:** `lsof -ti:5000 | xargs kill -9` to free the port. Or disable AirPlay Receiver in System Settings → General → AirDrop & Handoff.
- **Prevention:** add a port-check at start of `run.py`? Or document prominently. Currently documented in [`../context.md`](../context.md) and [`DEPENDENCIES.md`](DEPENDENCIES.md).

### G-002 — Duplicate SQLite DB (root AND `data/`)
- **Symptom:** changes to the DB via CLI (`sqlite3 trade_finder.db`) don't appear in the app — or worse, the app's writes appear nowhere obvious.
- **Cause:** legacy duplicate. `trade_finder.db` exists at both `./` (legacy) and `data/trade_finder.db` (canonical). Code reads from `data/`.
- **Fix:** always open `data/trade_finder.db`. Cleanup pending — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) §Q-001.
- **Prevention:** archive or delete the root file. Add to `.gitignore`.

### G-003 — DynastyProcess CSV player names don't match Sleeper
- **Symptom:** a player has default Elo (1500) instead of consensus-value-derived seed.
- **Cause:** name string mismatch between DynastyProcess CSV and Sleeper player database. Apostrophes, abbreviated initials, edge cases.
- **Fix:** run `dump_mismatches.py` to identify; manual reconciliation in `data_loader.py` or via lookup table.
- **Prevention:** automate fuzzy matching — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) §Q-004.
- **History:** see [`MISTAKES.md`](MISTAKES.md) §M-004.

### G-004 — Sleeper `roster.players` can contain nulls
- **Symptom:** code that iterates `roster.players` and accesses player data hits `None` errors.
- **Cause:** Sleeper API returns null entries for empty roster slots.
- **Fix:** filter `roster.players` to non-null entries before processing.
- **Prevention:** wrap roster-iteration code in a small utility that filters.

### G-005 — Player IDs from Sleeper are strings, not integers
- **Symptom:** `KeyError` or type-error when joining player data.
- **Cause:** Sleeper player IDs are returned as strings. Database columns may have been defined as integers somewhere.
- **Fix:** keep player IDs as strings throughout. If DB column is int, change it.
- **Prevention:** annotate `database.py` schema documentation explicitly.

### G-006 — Sleeper username case-sensitivity
- **Symptom:** user types "AlexSmith" but downstream code does case-insensitive lookups, eventually displaying "alexsmith" — confusing the user.
- **Cause:** Sleeper's `/v1/user/<username>` is case-insensitive but returns its canonical (often lowercased) username. Code may treat the response as the truth.
- **Fix:** preserve the user-typed username for display; use the Sleeper-returned ID for lookups.
- **Prevention:** distinguish `display_name` (user-facing) from `user_id` (joins).

### G-007 — `config/features.json` must stay in sync across clients
- **Symptom:** a feature flag works in web but mobile shows the old behavior.
- **Cause:** mobile or extension didn't pick up the latest `features.json`. Each client reads it differently (some at build time, some at runtime).
- **Fix:** confirm the feature flag is served via API (`GET /api/admin/config`) and all clients fetch fresh on session init.
- **Prevention:** centralize feature-flag access via the backend. Document the per-client mechanism in [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md).

### G-008 — `.sleeper_players_cache.json` staleness
- **Symptom:** a recently-traded rookie or new arrival isn't in the player picker.
- **Cause:** the player cache refreshes only when empty or >24h old. Mid-week roster moves don't trigger a refresh.
- **Fix:** manually delete `.sleeper_players_cache.json` to force refresh.
- **Prevention:** consider event-triggered refresh (e.g. on user roster import) for the affected user's league.

### G-009 — In-memory ring buffer lost on server restart
- **Symptom:** after `kill -9` or crash, `GET /api/debug/log` returns empty.
- **Cause:** by design — the ring buffer is in-memory only (D-008).
- **Fix:** capture log output to a file when running long sessions: `python3 run.py 2>&1 | tee /tmp/ftf-$(date +%F).log`.
- **Prevention:** see [`DECISIONS.md`](DECISIONS.md) §D-008. If production needs persistent logs, this needs revisiting.

### G-010 — Extension content-script breakage on Sleeper DOM changes
- **Symptom:** browser extension features that scrape the Sleeper UI suddenly stop working.
- **Cause:** Sleeper updated their DOM. No API contract for content scripts.
- **Fix:** inspect Sleeper's current DOM, update selectors in `extension/`.
- **Prevention:** minimize content-script reliance on DOM structure; prefer Sleeper API calls where possible.

## 2026-07-04

### G-011 — PlayerCard's inner Pressable swallows outer gestures
- **Symptom:** a tap/long-press handler on a wrapper around `PlayerCard` never fires (multi-select taps dead, drag long-press never lifts a row) — the row only scrolls.
- **Cause:** `mobile/src/components/PlayerCard.tsx` renders its OWN inner `<Pressable>`, which becomes the touch responder and eats the gesture before the outer Pressable/gesture-detector sees it.
- **Fix:** wrap the PlayerCard in `<View pointerEvents="none">` inside the outer Pressable (see TiersScreen for both call sites, with comments).
- **Prevention:** any new screen composing PlayerCard under its own touchable must use the `pointerEvents="none"` wrapper; ManualRanks avoids it by building rows inline.
- **History:** silently killed Tiers multi-select AND drag (June 2026); promoted here from the 2026-06-16 HANDOFF.

### G-012 — iOS marketing version comes from native `ios/`, NOT `app.json`
- **Symptom:** you bump `mobile/app.json` `version`, run `eas build`, and the build ships with an OLD/wrong `CFBundleShortVersionString` (e.g. app.json says 1.2.0 but the build goes out as 1.0.0 — a version regression that can get the TestFlight auto-submit rejected).
- **Cause:** `mobile/` has a **committed native `ios/` directory** (bare/prebuilt workflow). EAS logs it plainly: *"Specified value for `ios.bundleIdentifier` in app.json is ignored because an ios directory was detected."* The same applies to the version — the marketing version is read from `ios/DTFDynastyTradeFinder/Info.plist` (`CFBundleShortVersionString`, a literal here) and `project.pbxproj` (`MARKETING_VERSION`, Debug + Release). `app.json` `version` is ignored. `eas build:version:set` only manages the *build number* (remote, autoIncrement), not the marketing version — so it won't fix this either.
- **Fix:** set the version in all three native spots + app.json for sanity: `Info.plist` `CFBundleShortVersionString`, both `MARKETING_VERSION` lines in `project.pbxproj`, and `app.json` `version`. Commit (ios/ is tracked). See commit `e291a09`.
- **Prevention:** treat `ios/` (and `android/app/build.gradle` `versionName`) as the source of truth for version strings whenever a native dir is committed. NEXT.md #3 half-knew this ("app.json bumps don't apply") but attributed it to `appVersionSource: remote`; the real reason is the committed native project.
- **History:** hit 2026-07-06 — build 20 auto-submitted as 1.0.0, cancelled mid-flight, version fixed, rebuilt as 1.3.0.

---

## 2026-08-08

*Recorded retroactively during the living-memory revival pass, covering 2026-07-09 → 2026-08-06. Each entry is traced to the commit that fixed it.*

### G-013 — the bare workflow ignores ALL of `app.json`'s iOS config, not just `version`
- **Symptom:** an Expo config plugin or `ios.*` key appears correct in `app.json`, the build succeeds, and the capability is simply absent at runtime.
- **Cause:** the same committed native `ios/` directory as [G-012](#g-012--ios-marketing-version-comes-from-native-ios-not-appjson) — but the blast radius is wider than the version string. Confirmed casualties: `com.apple.developer.applesignin` (**builds 40 and 41 shipped unsigned for Apple**, FB-131, `2b5e07a`); `com.apple.developer.associated-domains` (**every invite Universal Link opened the browser instead of the app**, #239, `c0e99ba`); marketing version again (**build 51 shipped as 1.10.0 after the app.json bump to 1.11.0**, `af798c4`).
- **Fix:** edit the native project directly — `ios/DTFDynastyTradeFinder/*.entitlements`, `Info.plist`, `project.pbxproj` — and commit; `ios/` is tracked.
- **Prevention:** when adding any Expo plugin that grants an iOS capability, verify it landed in the native entitlements file before building. Treat "the plugin is in app.json" as zero evidence.

### G-014 — `league_id.isdigit()` is not a platform test
- **Symptom:** first, ESPN/MFL/Fleaflicker leagues returned 404 from the Sleeper roster proxies and the trade-away picker came up empty. Later, and much worse, **an MFL league's `draft_picks` were wiped on every single app open**.
- **Cause:** numeric league ids are not Sleeper-exclusive. Routes and the session-init daemon both branched on `league_id.isdigit()`, so a numeric MFL id (league 62846) was fed into the Sleeper grid sync, whose empty REPLACE deleted the rows.
- **Fix:** `database.is_linked_platform_league()` reads the DB membership snapshot. Applied at both sites — `52be577` (routes) and `0106aba` (daemon).
- **Prevention:** never infer platform from id shape. The link is recorded in the DB; ask it.

### G-015 — an empty `roster_ids` grid silently wipes picks through a REPLACE-sync
- **Symptom:** a league's owned draft picks vanish with no error anywhere.
- **Cause:** `sync_draft_picks` is a REPLACE. Hand it an empty roster grid and it faithfully replaces everything with nothing. The only realistic producer of an empty grid is an **upstream Sleeper fetch that flaked** — so a transient network blip destroys durable data.
- **Fix:** `2b8ecca` — `sync_draft_picks` no-ops on empty `roster_ids`, and the daemon step skips entirely when the rosters/meta read is unavailable.
- **Prevention:** any REPLACE-style sync needs an explicit "the source said nothing" guard distinct from "the source said empty". This is the same class as the #200 clobber.

### G-016 — a flag or targeting attribute can be registered and still be inert
- **Symptom:** the flag is in `config/features.json`, or the targeting attribute is registered, and behavior never changes for anyone.
- **Cause:** two separate versions of the same trap. (1) A key in `config/features.json` that isn't also in `feature_flags.FLAG_KEYS` is silently ignored (`bd3d8c5`). (2) A registered targeting attribute with **no resolver** matches nobody rather than erroring — `is_tester_allowlist` gated the entire onboarding_v2 rollout to zero users (`51ca4cb`).
- **Fix:** add to `FLAG_KEYS`; implement the resolver.
- **Prevention:** after registering either, assert one positive case actually resolves. Currently live: `outlook.odds` is in neither `LAUNCHED_FLAG_DEFAULTS` nor `features.json`, so `GET /api/league/outlook` is unreachable.

### G-017 — paired client/server gates fail silently when only one is on
- **Symptom:** analytics looked wired end-to-end; zero rows had ever landed.
- **Cause:** the client emission gate was ON while `analytics.ingest` was OFF, so the server rejected every batch with disposition `disabled` — a success-shaped response. No error surfaced on either side.
- **Fix:** `315fccc`. Clients had retained their queues, so history flushed on enable — the data wasn't lost, just invisible.
- **Prevention:** for any two-sided gate, verify a row at the destination, not a 200 at the source.

### G-018 — Render ignores `render.yaml` for dashboard-created services
- **Symptom:** you add an env var to `render.yaml`, deploy succeeds, and the variable is not in the environment.
- **Cause:** services created through the Render dashboard don't take `envVars` from the blueprint. `FTF_TESTER_ALLOWLIST` was added in `4404c60` and never reached the process; the fix-the-fix chain ran `4404c60` → `d86cbb7` (runbook) → `b689f28` (moved the allowlist to a git-committed `config/tester_allowlist.json`, unioned with env).
- **Related Render traps:** new blueprint **cron services are billable and need account approval**, so blueprint sync fails (`1e50d3e`); and a DB plan upgraded in the dashboard must be mirrored in `render.yaml` or sync fails with "cannot downgrade database from Basic-256mb to Free" (`1f7eeb3`).
- **Prevention:** config that must survive a deploy belongs in a committed file, not a blueprint env var.

### G-019 — `EXPERIMENT_SALT_KEY` is immutable once experiments run, and boot-seeding hides that
- **Symptom:** experiment assignments look wrong or unreproducible after the env var is finally set.
- **Cause:** `_seed_experiment_layers` uses INSERT-OR-IGNORE at boot. A deploy that started before the key existed persists **dev-fallback salts forever**, and the later, correct env var is ignored because the rows already exist.
- **Fix:** `POST /api/admin/experiments/reseed-layers` (`a55c19e`), guarded on zero assignments.
- **Prevention:** changing the salt after real assignments exist rebuckets every user. Treat it as immutable; use the reseed route only before traffic.

### G-020 — CocoaPods `EXConstants` breaks twice on a repo path containing spaces
- **Symptom:** a locally built app silently talks to the PROD `apiBaseUrl` regardless of your dev config.
- **Cause:** the "Generate app.config" build phase fails in two stages. The podspec's `bash -l -c` word-splits on the space; once quoted, `basename $PROJECT_DIR` yields "Fantasy" ≠ "Pods", so the phase **silently no-ops** and the app falls back to prod.
- **Fix:** `920a638` replaces the build phase wholesale in `mobile/ios/Podfile`.
- **Prevention:** this project's path has a space in it and always will. Use the no-space clone at `../ftf-test-clone` for local native builds — and note this failure is silent, so a "working" local build proves nothing about which backend it hit.

### G-021 — iOS 26 native header back is dead when the previous screen hides its header
- **Symptom:** the back chevron renders and does nothing.
- **Cause:** upstream react-native-screens#3294; the app pins 4.16.0.
- **Fix:** explicit JS `HeaderBack` with `headerBackVisible: false`. Rolled out to LeagueSummary / Profile / TestStages in `0eb1061`.
- **Prevention:** don't rely on the native back button on any screen pushed from a header-less one.

### G-022 — parallel-agent worktrees drift, duplicate, and blow up the EAS archive
- **Symptom:** a wave of agent work merges cleanly but behaves oddly; or an EAS upload 400s.
- **Cause:** several distinct problems, all from the same source. Worktree agents branch from an **older commit than branch HEAD** (merge-base `20548ff` vs HEAD `30492ac`). Disjoint source-file ownership holds, but agents independently edit the same **shared docs** (`docs/cross-client-invariants.md`, per-folder `CLAUDE.md`). Every worktree lacks `mobile/node_modules`, so each agent symlinks the main checkout's. And 71 worktrees (8.6 GB) pushed the EAS archive from 228 MB to **1.2 GB**, failing the upload.
- **Fix:** `.easignore` (note: an earlier version globbed `*.png`, stripped the app icon and splash, and failed the Bundle JavaScript phase — scope it narrowly). Check `git merge-base` per branch and rebase before merging. Assign shared docs a single owner per wave.
- **Prevention:** always branch from a freshly fetched `origin/main`, per the convention in [`../CLAUDE.md`](../CLAUDE.md).

### G-023 — testers report against the shipped binary, not your branch
- **Symptom:** you write a careful fix for a feedback item that was already fixed weeks ago.
- **Cause:** TestFlight builds lag a long-lived unshipped branch by weeks. Items #208 and #262 were both already fixed in the repo when reported.
- **Fix:** before writing any fix, ask whether it still reproduces on current code.
- **Related:** `activeScreen` in a feedback report is a **route name, not a file** — grep the TabNav registrations before concluding a screen doesn't exist.

---

## Gotcha Template

```markdown
### G-NNN — <Short title>
- **Symptom:** <what you'll see if you don't know>
- **Cause:** <why it happens>
- **Fix:** <how to recover>
- **Prevention:** <how to keep it from happening again>
- **History (optional):** <prior instances and links to MISTAKES.md>
```

Number sequentially. Don't delete entries even if "obviously fixed by now" — future-you will appreciate the history.
