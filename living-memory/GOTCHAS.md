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
| G-035 | A JSX "is this gated on X?" test passes on a build where X is ignored | Mobile / structural tests / AST |
| G-034 | A seeded UI-test fixture is silently rewritten at Flask boot | Backend / test fixtures / migrations |
| G-033 | A sim run goes red on an unrelated screen after adding one API call | Mobile / Maestro harness / VCR |
| G-032 | Account-only session shows "No 2026 NFL leagues found" (or a 503) | Mobile / account auth / Sleeper |
| G-031 | Client events look wired, land nowhere, and every response is 200 | Backend / analytics taxonomy |
| G-030 | MFL/Fleaflicker leagues take the Sleeper-only code path | Mobile / platform routing |
| G-029 | Trade deck stuck on a skeleton card that never resolves | Mobile / TradesScreen |
| G-028 | Six rookie-scope tests fail only in checkouts carrying real data | Backend / tests / hermeticity |
| G-027 | Sim build fails at CpResource on a dead `expo/node_modules/…` path after `npm ci` | Mobile / iOS build / CocoaPods |
| G-026 | Half a roster silently prices at 0.0 in an IDP or K league | Backend / outlook / values |
| G-025 | "No historical data exists" for a GitHub-hosted CSV | Research / external data |
| G-024 | Sleeper W/L is double the games played | Backend / Sleeper ingestion (fixed in `backend/outlook/` 2026-08-09; still live elsewhere) |
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

### G-025 — "there is no historical data" for a file that lives in a git repo
- **Symptom:** three independent 2026-08-09 analyses ([calibration report](../docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md), pick-capital, bench-depth) each concluded that the preseason `RosterValueStrength` source was **untestable** because "FTF has no dated value snapshots", and two of them substituted a weaker metric on that basis. It cost a full validation gap in a shipping decision.
- **Cause:** the DynastyProcess values feed was reasoned about as a *live endpoint* (`raw.githubusercontent.com/.../master/files/values-players.csv`) rather than as a *file in a public git repository*. `master` is one ref; every past revision is equally fetchable.
- **Fix:** for any GitHub-hosted data file, `api.github.com/repos/<owner>/<repo>/commits?path=<file>&per_page=1&until=<ISO date>` resolves the nearest revision at-or-before a date, and `raw.githubusercontent.com/<owner>/<repo>/<sha>/<file>` fetches it. **Send a `User-Agent`** — a bare `curl` on `raw.` gets a redirect stub, which is easy to misread as "no data". DP's history runs to ~2020-09 with a stable column shape.
- **Generalisation:** before writing "no historical data exists", check whether the source is version-controlled, has a Wayback capture, or publishes dated files. In this repo that also applies to `db_playerids.csv` and `values.csv` — same repo, same history.
- **Where it lives now:** `backend/dp_values_history.py` + 24 committed boards in `backend/tests/fixtures/dp-values-history/`. Full writeup: `docs/feedback/items/169-outlook-league-summary/dated-values-revalidation-2026-08-09.md`.

---

### G-026 — the dynasty value board is offence-only, so IDP and K roster slots price at 0.0
- **Symptom:** anything that sums "roster value" or "starting-lineup value" reports a plausible-looking number that is silently missing half the lineup in an IDP or kicker league. The outlook engine's preseason strength source ranked the operator's FFv3 teams on **7 of their 15 starting slots** for four backtested seasons, and its own coverage table read "100 %" — because that table counted QB/RB/WR/TE slots only.
- **Cause:** every value path in FTF is seeded from DynastyProcess `values-players.csv`, which contains **QB/RB/WR/TE and nothing else** (676 rows, 2026-08-09). `backend/data_loader.py::VALID_POSITIONS` is literally `{"QB","RB","WR","TE"}`, so the universal player pool has no defender or kicker in it at all — such a player resolves to value `0.0` **and** position `"?"`. An unpriced player is indistinguishable from a missing one.
- **Second trap, same function:** Sleeper names a defensive starting **slot** after the fantasy position *group* (`DL`, `LB`, `DB`, `IDP_FLEX`) while a player's `position` is his NFL position (`DE`, `DT`, `NT`, `OLB`, `CB`, `SS`, `FS`). Matching the slot name against the position string — which is correct for QB/RB/WR/TE/K — leaves every defensive slot empty. Fixed in `backend/outlook/strength.py::eligible_positions`.
- **Fix / non-fix:** there is **no license-clean dynasty IDP value board** to price them with (DynastyProcess publishes none; FantasyCalc none; nflverse none; the `dynasty-idp` rows inside DP's `db_fpecr` are a FantasyPros scrape, 100 players deep, and ranks not values). Do **not** invent one. `backend/outlook/strength.py::lineup_pricing()` measures which slots a board cannot price — call it and label the output rather than presenting an unqualified whole-lineup figure.
- **Prevention:** before summing player values across a roster, ask what the league *starts*. `roster_positions` containing any of `K`, `DL`, `LB`, `DB`, `IDP_FLEX`, `DEF` means the board covers a minority of the lineup. Note the cancellation that saves you: a **cross-team z-score** within one league is unaffected (the gap is identical for every team), but an **absolute** value — a displayed lineup total, a fraction-of-value share, a cross-league comparison — is not.
- **Full writeup:** `docs/feedback/items/169-outlook-league-summary/idp-pricing-2026-08-09.md` (BUG-5), incl. the measured before/after showing no available fix beats the status quo.

---

### G-024 — a Sleeper league's W/L can be double its games played (median match)
- **Symptom:** a 14-week Sleeper season reports a 13-15 record (28 decisions). Anything that assumes one win per week silently runs on the wrong scale — e.g. the outlook simulator emitting `projected_wins = 22.29` for a 14-week season.
- **Cause:** `settings.league_average_match == 1` ("median match"): every team plays its head-to-head opponent **and** the league median each week, so Sleeper books two W/L decisions per week. `/rosters` reports the combined total; `/matchups/{week}` still shows only the head-to-head pairing.
- **Fix:** read `settings.league_average_match` whenever you consume `settings.wins/losses/ties`. To reconstruct standings from weekly scores, add the median game: compare each team's week score to the league median that week. Verified to reproduce Sleeper's own totals exactly on 24 median-league rosters.
- **Where it bites today:** the operator's **Lakeview** league has it on in 2024, 2025 and the live 2026 season; Fantasy Football V3 does not.
- **RESOLVED in `backend/outlook/` on 2026-08-09.** Phase 1 reads the setting into `LeagueState.median_match` (with a `decisions_per_week` helper) and Phase 3 (`simulator.py`) books the second decision each simulated week against the **median of that week's drawn scores** — computed inside the simulation loop, not from history. The strict `xfail` is now a passing test (`test_median_match_leagues_are_ingested_on_the_simulated_win_scale`). Measured: playoff Brier on the median-match league-seasons 0.1017 → 0.0666 (−34.5 %); head-to-head leagues bit-identical. **Still a live gotcha everywhere else** — any other code path that consumes `settings.wins/losses/ties` must read `league_average_match` too.
- **Related:** `settings.playoff_seed_type` (1 on Lakeview) is likewise unread by `backend/outlook/playoff_format.py` — still open. Full writeup: `docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md`.

---

### G-023 — testers report against the shipped binary, not your branch
- **Symptom:** you write a careful fix for a feedback item that was already fixed weeks ago.
- **Cause:** TestFlight builds lag a long-lived unshipped branch by weeks. Items #208 and #262 were both already fixed in the repo when reported.
- **Fix:** before writing any fix, ask whether it still reproduces on current code.
- **Related:** `activeScreen` in a feedback report is a **route name, not a file** — grep the TabNav registrations before concluding a screen doesn't exist.

---

## 2026-08-11

### G-028 — six rookie-scope tests fail only in checkouts that carry real data
- **Symptom:** `backend/tests/test_rookie_scope.py` fails 6 tests (`KeyError: 'player_a'` from `/api/trio?scope=rookie`) in the main checkout, while the same commit passes 34/34 in a fresh worktree and CI. Looks like your diff broke it; it didn't.
- **Cause:** the route's rookie-id resolution (`server.py:1923 _rookie_player_ids` → `load_rookie_player_ids`, memoized by `pool_generation()`) reads checkout-local player data the `client` fixture never pins — the fixture patches `db_module.engine` only. With the real 2026 class present, the rookie-id set no longer matches the fixture's synthetic ids.
- **Fix (for a green run):** run the suite in a clean worktree; or prove innocence by `git checkout origin/main -- <your backend files>` and re-running in place (both done 2026-08-11).
- **Prevention:** fixture should pin the data source (task chip filed 2026-08-11). Until then, don't chase these 6 in a data-carrying checkout.

### G-027 — `npm ci` re-hoists packages and strands the Pods project on dead nested paths
- **Symptom:** `sim-build.sh` fails at a `CpResource` step referencing `mobile/node_modules/expo/node_modules/<pkg>/…` (e.g. `expo-file-system`'s `PrivacyInfo.xcprivacy`) — a path that no longer exists.
- **Cause:** the generated Pods project bakes in absolute package paths from the `pod install` that produced it. A later `npm ci` may hoist a previously-nested package to top level (`mobile/node_modules/<pkg>`), and the stale Pods reference dangles.
- **Fix:** `cd mobile/ios && pod install`, then rebuild. CocoaPods itself crashes under a non-UTF-8 shell (`Unicode Normalization not appropriate for ASCII-8BIT`) — run it as `LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 pod install`.
- **Prevention:** treat `npm ci` + sim build as a pair: if `npm ci` ran since the last `pod install`, re-run `pod install` before `sim-build.sh`. Also: capture the build's exit code directly — `sim-build.sh … | tail` reports `tail`'s exit 0 over a failed build (the maestro-test skill already warns about this; it still happened).
### G-029 — first run + four failed polls = a skeleton card that never resolves
- **Symptom:** on a first-ever trade search that fails, `TradesScreen` renders a `SkeletonTradeCard` forever. No error, no empty state, no retry — the app just looks like it is still thinking.
- **Cause:** three things line up. The deck ladder's first-run branch excludes `job?.status === 'error'`, but the poll-abandon path sets `job` to **`null`**, so that guard never matches. `autoGenFailed` is only set from the POST path, not the poll path. And the auto-start effect refuses to re-kick once it has fired. Nothing in the chain can move the screen off the skeleton.
- **Fix:** the `!deckFailure` guard on the ladder's first-run branch (P0-2). `deckFailure` is set from **every** failure path, including poll-abandon, so it sees what `job` cannot.
- **Prevention:** when a guard tests a *status field*, check what the abandon/timeout path actually writes. A path that nulls the whole object defeats every field-level guard downstream. See [D-027](DECISIONS.md).
- **History:** found by the P0-2 build's pre-fix control run — the audit's own repro did not surface it, which is the argument for control runs.

### G-030 — MFL and Fleaflicker league ids are numeric, so `isdigit()` does not exclude them
- **Symptom:** an MFL or Fleaflicker user sees a live "Send in Sleeper" button that always fails with a 400.
- **Cause:** the client gated on `league_id.isdigit()` as a proxy for "this is a Sleeper league". Sleeper ids are numeric — but so are MFL's and Fleaflicker's. The predicate tests the wrong property.
- **Fix:** gate on the league's **platform**, not the shape of its id (P0-6, `resolveSendPlatform`). Backend equivalent: `backend/server.py:12336`.
- **Prevention:** **this is the third instance of the same bug class in this repo** — see G-014, feedback #200 and #220. Any `isdigit()` / numeric-shape test standing in for "Sleeper" is wrong. There is a platform field; use it.
- **Related:** the propose route still lacks an `is_linked_platform_league` guard — see [`NEXT.md`](NEXT.md).

### G-031 — a client `track()` name absent from the taxonomy is counted and dropped in silence
- **Symptom:** instrumentation looks correct in the client, `POST /api/events` returns **200**, and the dashboard has no rows. No client error, no server error, no log line anyone reads.
- **Cause:** `backend/analytics_taxonomy.py`'s `ALLOWED_CLIENT_EVENTS` is **default-deny**. An unregistered `event_type` is counted into a drop counter and discarded behind the 200. Registered-but-unspecced *props* are stripped the same way.
- **Fix:** register the name in `ALLOWED_CLIENT_EVENTS` (and its props in `CLIENT_EVENT_PROPS`) **before** shipping the emitter, and write the tracking-plan addendum first — the registry's own comments make the addendum the stated precondition.
- **Prevention:** the scale of this is the point. A 2026-08-11 sweep of every `track('<name>'` literal in `mobile/src` found **33 of 73 emitted names unregistered**. This batch fixed three (`invite_shared`, `deck_regenerated`, and `celebration_fired` by renaming the client to the registered `celebration_shown`), leaving **29** — full list in [`NEXT.md`](NEXT.md) and `docs/plans/audit-p0-remediation/lld-p0-8-9.md` §4.3. Note `quickset_completed` cannot be fixed by registration: it is server-authoritative, and the two namespaces are disjoint by an import-time assertion, so the client emitter has to go.
- **History:** G-016 and G-017 are the same failure mode one layer up (flag registered but inert; analytics wired but zero rows). This is its third recorded occurrence.

### G-032 — an account-only session must never trigger the Sleeper league fetch
- **Symptom:** a user who signed in with Apple/Google and has no linked Sleeper account sees "No 2026 NFL leagues found" live, or a 503 `sleeper_unavailable` under the hermetic test harness.
- **Cause:** account-only users carry the synthetic working key `acct_<account_id>`. `GET /api/sleeper/leagues/<user_id>` proxies that id straight to Sleeper, which has never heard of it. The failure is honest at the network layer and completely misleading at the UI layer — it reads as "you have no leagues" rather than "you have no Sleeper account".
- **Fix:** gate the fetch on the `no_league` sentinel. An account-only session renders the picker's companion state instead of calling out.
- **Prevention:** any call that takes `user_id` and forwards it to a platform API needs an `acct_` check. The sentinel is documented in [`../docs/cross-client-invariants.md`](../docs/cross-client-invariants.md#no_league--the-account-only-league-sentinel).

### G-033 — one new API call on any screen can turn a whole sim run red
- **Symptom:** a Maestro sim run fails after a change that touched an unrelated screen, with no assertion failure in the flow itself.
- **Cause:** the harness is hermetic. `mobile/scripts/sim-run.sh:178` **fails the run when `vcr_misses > 0`**, and an unseeded Sleeper id raises 599 and increments that counter (`server.py:529-536`). Any new client call site that reaches Sleeper with an id the seeder did not write breaks every flow in the run, not just its own.
- **Fix:** either seed the id in the fixture profile, or keep the call to a **single call site** whose ids are always seeded and cache the result for downstream screens. P0-3 took the second route: `fetchInviteMeta` has exactly one call site (the sign-in banner) and caches the resolved name into the persisted invite intent, because the non-member leg walks unseeded ids.
- **Prevention:** `vcr_misses` is a **load-bearing rail, not a warning**. Before adding a platform-touching call, ask which fixture profile covers the ids that screen can see. A reviewer adding a second `invite-meta` call site would reintroduce this.

### G-034 — a boot-time backfill silently rewrites your seeded test fixtures
- **Symptom:** a Maestro flow or capture that asserts a pre-fix state fails on the seeded backend, and the fixture JSON on disk looks correct.
- **Cause:** `backfill_ranking_method_from_tiers()` runs inside `_migrate_db()`, which runs on **every** Flask boot — including the seeded UI-test backend. It rewrites the seeded `quickset-done` user before the first test request arrives.
- **Fix:** ship the fixture in the **post**-backfill shape and invert the seeder guard (`_validate_quickset`) and the capture in the **same commit** as the migration. Three coupled edits, not one.
- **Prevention:** any migration that runs at boot is part of the test-fixture contract. When adding one, grep `backend/tests/fixtures/` for rows in its cohort and move them with it — otherwise a green flow documents behaviour that no longer exists, or a red one has no visible cause. See [D-026](DECISIONS.md).

### G-035 — a JSX "is this gated on X?" test that walks ancestors will false-pass
- **Symptom:** a structural test asserting some element is conditional on a prop passes on a build where that element is deliberately unconditional. Nothing looks wrong in review.
- **Cause:** the assertion collected the conditions of *several* JSX ancestors and regex-matched the token anywhere in the concatenation. In `check-league-drill-in.js`, the relocated tier badge sits inside the cluster's own `posRank || (denseSingleLine && tier) ? …` ternary, so the token `denseSingleLine` was present in an ancestor regardless of the badge's own gate.
- **Fix:** read the **innermost** conditional only, and stop walking at the enclosing JSX element boundary (`nearestConditionText()`, fixed in `ba30464`).
- **Prevention:** run every new assertion against a deliberately sabotaged tree before trusting it. This one was found *only* because the falsification pass was executed — it would not have surfaced in review, and unfixed it would have shipped the Tiers and FreeAgents rows rendering the tier badge twice. Four false-passing tests were caught this way in the #297–#302 batch alone; treat "my test passes" as unproven until the sabotage fails it. See [D-036](DECISIONS.md).

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
