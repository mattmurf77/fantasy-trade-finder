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
| G-060 | A sabotage-and-restore in the same mtime second at identical size keeps the stale `.pyc` — the test stays red after a byte-clean restore | Python / pytest / bytecode cache |
| G-061 | The daily tick's Aug-25 `season_start` fan-out `continue`s past every winback — the three winback tests fail exactly one day a year (found live 2026-08-25) | backend / cron / pytest |
| G-059 | A breaker payload test flakes only on a loaded CI runner — the 250 ms wall-clock budget is a hidden test input | Backend tests / breaker / determinism |
| G-058 | Loosening a trade-engine knob measures "no effect" three different ways, all of them lies | Trade engine / knob tuning |
| G-055 | A feedback note over the length cap vanishes: no error, draft cleared, retry loops forever | In-app feedback / silent failure |
| G-056 | `navigate('TradesHome')` from a pushed Trades-stack screen PUSHES a second instance — it does not pop back (RN routers 7.5, no `getId`/`pop`) | Mobile navigation / code-walk proofs |
| G-057 | A Release simulator build SIGSEGVs ~2 s after launch inside `hermes` ← `ReactInstance::initializeRuntime` after a `pod install` — `Pods/.last_build_configuration` says `Release` while `destroot` holds the DEBUG Hermes | Local iOS builds / CocoaPods |
| G-054 | A blanket decision-ID find-and-replace rewrites headings but not their anchors | Living-memory / doc hygiene |
| G-053 | `measure_gap_distribution.py` reports different numbers run-to-run unless `PYTHONHASHSEED` is pinned | Bake-off measurement / determinism |
| G-052 | A pick badges one tier too high: the wrong value→Elo inverse, silent near a 1st, worse downward | Pick badges / value scales |
| G-051 | A tier-band edit that looks backend-only silently drifts `web/js/app.js`, which fetches nothing | Tier bands / client mirrors |
| G-050 | A test that asserts inside a swallowed `try` can never fail | Testing / defensive error handling |
| G-049 | A duplicate pass double-counts Elo — the harm is in `swipe_decisions`, not `trade_decisions` | Trade decisions / Elo replay |
| G-048 | Next living-memory ID computed from a stale checkout collides on main | Living-memory / concurrent sessions |
| G-047 | "no checks reported" on a PR reads as a pass to a naive poller | CI / gh / merge gating |
| G-046 | A follow-up PR off a squash-merged branch is born CONFLICTING | Git / squash-merge / branch hygiene |
| G-045 | A whole league-mate silently missing from the deck, not just their cards | Backend / trade engine / pool prune |
| G-044 | A killed `sim-run.sh` leaves Flask on :5001; the next run aborts stale | Mobile / test harness / Flask |
| G-043 | `sim-build.sh` fails at the JS bundle phase on a symlinked `node_modules` | Mobile / build / Metro resolver |
| G-042 | The local Maestro sim gate cannot run at all: no `JAVA_HOME` | Mobile / test harness / Maestro |
| G-041 | Catching IntegrityError by unique-index name never matches on SQLite | Backend / SQLAlchemy / dialects |
| G-040 | begin_nested() on the main engine silently COMMITS on SQLite | Backend / SQLAlchemy / dialects |
| G-039 | EAS build dies at Bundle JavaScript on a module that exists locally | Build / EAS / .easignore |
| G-038 | A ranking method can be a permanent dead end, and nothing reports it | Backend / unlock ladder |
| G-037 | An unlock-proving fixture that seeds `unlocked: true` proves nothing | Backend / test fixtures / monotonic floor |
| G-036 | `league_id` analytics props store `"[scrubbed]"` for Sleeper leagues only | Backend / analytics ingest / PII scrub |
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

## 2026-08-18

### G-050 — A test that asserts inside a swallowed `try` can never fail
**Symptom:** `test_digit_only_ids_skip_the_pick_query` passed green whether or not the guard it
claimed to protect existed.
**Cause:** it patched a query to raise `AssertionError` — but `AssertionError` IS an `Exception`,
and the helper under test wraps its lookup in `except Exception: log.warning(...)`. The assertion
fired, was swallowed, and the helper returned its empty default exactly as the passing case does.
**Lesson:** when the code under test swallows exceptions, **assert on an observable outside the
`try`** — a call counter, a spy, a returned value — never on an exception you inject into the
swallowed region. Generalizes: any "prove this expensive path was skipped" test near defensive
error handling. Verified by running the old assertion under a real sabotage and watching it stay
green. Same class bit the source-assertion tests this sweep: three of six new suites asserted
*shape* (an append exists, a comparison exists) rather than *behavior*, and one of them passed with
the comparison inverted — i.e. with the exact opposite of the requested feature shipped. Prefer
lifting the real function out of source and running it over a fixture (the
`check-picker-pick-filter.js` idiom) over matching source text.

### G-049 — a duplicate pass double-counts Elo — and the damage is in `swipe_decisions`, not `trade_decisions`
**Symptom:** a replayed pass applies `trade_k_pass` twice, skewing the board.
**Cause:** `save_trade_decision` (`backend/database.py`) was a plain INSERT and
`trade_decisions` has no unique constraint. **Corrected 2026-08-18 (second pass):** the
first version of this entry implied a constraint on `trade_decisions` was the fix. It is
not. `_compute_elo` replays **`swipe_decisions`** (via `load_swipe_decisions`), so the
Elo harm comes from the `save_trade_swipes` write; the duplicate `trade_decisions` row is
nearly harmless because every read path already dedupes (`load_awaiting_trades`'s
`seen_keys`, `_past_decision_keys` is a set). **Fixing the wrong table would have changed
nothing measurable.**
**Why a unique constraint is not available:** duplicate `(user, league, trade_id)` rows are
**by design** — `retracted_at` (#318) means a re-like after a retraction writes a fresh row,
the revive path. A constraint also cannot be created against prod (63 pre-existing
duplicates would reject it), and an `IntegrityError` inside the route's persist block would
skip `check_for_match`, silently killing mutual-match detection on a re-like.
**What the prod data showed** (933 rows): duplicates split into two cleanly separated
populations — **40 double-writes at 0.015–0.200 s** (identical payloads, 39 of them passes)
and **23 genuine re-decisions at 147.7 s and up**. A **738× empty band** between them, which
is what makes a time-window guard safe rather than a guess.
**Fix shipped:** a replay guard in `save_trade_decision` (10 s, still-live rows only,
identical payload, same decision) returning `bool`, plus **both** route call sites
(`swipe_trade`, `_apply_reasoned_pass`) gating `save_trade_swipes` on that verdict.
`check_for_match` is deliberately NOT gated — a replayed like must still surface a match.
Neither is `record_trade_signal`: it writes derived in-memory state that `replay_from_db`
rebuilds from `swipe_decisions` each `session_init`, and gating it would tie in-session
board movement to DB reachability (D-073).
**Lesson:** name the table that actually carries the harm. Two tables were written by one
action and the entry blamed the one with the obvious missing constraint. Also: the contract
test defined its own caller and so proved the *contract* while leaving the *call sites*
unpinned — sabotage showed both gates could be deleted with every test green. Route pins
(`inspect.getsource`) now cover them.
**Residual:** the guard is read-then-write in one transaction, not a distributed lock — two
simultaneous requests on separate workers could still both write. All 40 observed prod
duplicates were sequential. Second residual, accepted: a replay still doubles the in-memory
signal until the session is re-initialised (~2 Elo points on the affected pair at
`trade_k_pass = 4.0`); the persisted rows are correct, so it heals on the next
`session_init`.

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
- **Prevention:** the scale of this is the point. A 2026-08-11 sweep of every `track('<name>'` literal in `mobile/src` found **33 of 73 emitted names unregistered**. The P0 batch fixed three (`invite_shared`, `deck_regenerated`, and `celebration_fired` by renaming the client to the registered `celebration_shown`); the **2026-08-13 dropped-emitter backlog batch cleared the rest** (27 registered as-shipped, and the `quickset_completed` client emitter deleted — it is server-authoritative and the namespaces are disjoint by an import-time assertion, so registration was impossible). Addendum: `docs/business/analytics/2026-08-13-dropped-emitter-backlog.md`. Known backlog is now **0** — but only for names emitted as of that sweep; the register-before-emitter rule is what keeps it there.
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


### G-037 — a fixture that seeds `unlocked: true` cannot prove an unlock
- **Symptom:** you add a seed profile to prove a new unlock rule works. The test goes green immediately. It would also go green with the fix reverted.
- **Cause:** `get_rankings_progress` applies a **monotonic floor** (`if not unlocked and fmt in unlocked_formats_list: unlocked = True`) *before* nothing — but crucially the floor is consulted after the per-method ladder and ORs into it, so any pre-seeded `users.unlocked_formats` row makes the answer `True` regardless of what the ladder decided. `seed_ui_test_db.py` calls `db.mark_format_unlocked` for every format in `world.unlocked_formats()`, which is non-empty exactly when the profile says `"unlocked": true`. The fixture therefore short-circuits the branch it exists to exercise.
- **Fix:** seed `"unlocked": false` and let the branch compute it. This is also literally accurate — a user who has just crossed the bar has no *prior* unlock record; the row is written by `mark_format_unlocked` on their first `/api/rankings/progress` after the fix. `backend/tests/fixtures/profiles/anchors-done.json` is the worked example, and `_validate_anchors` now **refuses** the incoherent shape rather than leaving it as a comment.
- **Prevention:** for any fixture whose purpose is "prove X unlocks", assert the floor is unseeded *in the test* (`unlocked_formats == []`), not just in the profile. Same family as G-035: a green structural test is unproven until you have watched it fail.

---

### G-038 — a ranking method can be a permanent dead end, and nothing reports it
- **Symptom:** a cohort of users rank their whole board and Trade Finder never unlocks. No error, no log line, no analytics signal — the progress endpoint cheerfully answers `unlocked: false` forever. The League ring reads 0/4 and the push primer never arms, which looks like two more bugs rather than one.
- **Cause:** `get_rankings_progress`'s unlock ladder is an `if/elif` chain **keyed on `ranking_method` strings**, with a trio-swipe rule in the `else`. `'anchor'` was a valid, first-class method with no arm, so it fell to the `else` — and the anchor lane writes Elo overrides and *never a swipe*, so the fallback rule was structurally unsatisfiable. Adding a method string is a one-line change; adding its unlock rule is a separate one nobody was prompted to make. P0-1 later widened the blast radius by writing methods at the point of use.
- **Fix:** every method gets an explicit arm (P1-7). `'anchor'` and `'manual'` unlock on durable board evidence (`RankingService.board_override_count()`, counting pool-resident `users.tier_overrides`), or the tiers rule.
- **Prevention:** the ladder's `else` is a **fallback for one specific method** (`'trio'`/null), not a default that suits everyone. Adding a value to `VALID` ranking methods without adding an arm makes it a dead end. Note the two traps in fixing it: the interaction counter is **rebuilt from persisted swipes on every session build**, so bumping it in a save handler evaporates on the next cold start; and a rule keyed on a shared write lane (`apply_anchor`) grants credit to surfaces that were deliberately excluded from writing the method at all.
### G-039 — a bare directory name in `.easignore` matches that name at ANY depth
- **Symptom:** an EAS iOS build errors after ~50s at the **Bundle JavaScript** phase with `Unable to resolve module ../screens/SignInScreen` (or any module), while `npx expo export --platform ios` succeeds locally from the same tree. Two builds failed this way (99, 100) on v1.12.1.
- **Cause:** `.easignore` uses **gitignore semantics**. The entry `screens/`, added to exclude the top-level 135-capture screen library, also matched **`mobile/src/screens/`** — every screen in the app — and stripped it from the uploaded archive. The tree was never wrong; only the archive was. Proven with git's own matcher: `screens/` matches both `screens/a.png` and `mobile/src/screens/SignInScreen.tsx`; `/screens/` matches only the first.
- **Fix:** anchor every root-level entry with a leading slash (`/screens/`). Landed as `53bd19f`; build 101 from that commit finished and submitted.
- **Prevention:** **a green local bundle cannot clear an archive-scoped failure** — do not let it talk you out of reading the real log. Two further traps found on the way in: `eas build` **exits 0 even when the remote build ERRORS** (verify with `eas-cli build:list --json` and read `status`), and the build logs are **brotli**-encoded, so the CLI will not render them post-hoc and `curl --compressed` fails — fetch `logFiles[0]` from `eas-cli build:view <id> --json` (signed URL, ~15 min TTL) and decompress with node's `zlib.brotliDecompressSync`.
- **History:** **second instance of this bug class in this same file.** An earlier version globbed `*.png` and stripped the app icon and splash assets, failing the identical phase. The rule is now stated at the top of `.easignore` rather than left implied by a war story. A worktree-vs-clone hypothesis cost a whole build cycle before the log was read — building from a linked git worktree was **ruled out** as a cause.
### G-040 — `begin_nested()` on the main engine silently COMMITS on SQLite
- **Symptom:** a `with engine.begin():` block that uses a SAVEPOINT (`conn.begin_nested()`) and later raises to roll the whole transaction back... leaves the savepointed rows **committed to disk** anyway. No error. Tests that assert "no orphan row after rollback" fail only on SQLite, and only on the main engine.
- **Cause:** the pysqlite savepoint recipe (`isolation_level = None` + explicit `BEGIN` on the `"begin"` event) is attached **only to `ingest_engine`** (`backend/database.py:92-99` — its comment says "SEPARATE listener — do NOT attach"). The main `engine` (`:62`) has no recipe, so pysqlite emits no `BEGIN`, the `SAVEPOINT` becomes the *outermost* transaction, and `RELEASE` commits. Measured 2026-08-13 on SQLAlchemy 2.0.49 / SQLite 3.50.4: default engine leaves the row; an engine carrying the recipe rolls back clean.
- **Fix:** don't use `begin_nested()` on the main engine's SQLite path. Where Postgres needs a SAVEPOINT to survive a caught `IntegrityError` (it aborts the txn; SQLite does **not** — a post-error SELECT succeeds), branch on `engine.dialect.name == "postgresql"` — the device-auth LLD §4.1 step 14 is the worked example.
- **Prevention:** SQLite *not* aborting on constraint errors is the mirror trap: code that "works in dev" without the savepoint then breaks on Postgres with `InFailedSqlTransaction`. Any `IntegrityError` handler that issues further SQL must be tested **on both dialects**, dialect-parameterised, not assumed portable.
### G-041 — catching `IntegrityError` by unique-index name never matches on SQLite
- **Symptom:** an `except IntegrityError` that discriminates with `"ux_my_index" in str(e)` handles the duplicate correctly on Postgres and **re-raises as a 500 on SQLite** — i.e. on dev/test/CI, exactly where the ordinary duplicate-tap case runs.
- **Cause:** the two dialects name **different identifiers for the same event**. Postgres: `duplicate key value violates unique constraint "ux_my_index"` (index name; also structured as `e.orig.diag.constraint_name`, SQLSTATE 23505). SQLite: `UNIQUE constraint failed: table.column` — **the column, never the index name**. Measured 2026-08-13 (PG 18.3 / SQLite 3.50.4).
- **Fix:** dialect-asymmetric matching — PG on SQLSTATE + `diag.constraint_name`; SQLite on the `UNIQUE constraint failed:` prefix + the `table.column` token.
- **Prevention:** the asymmetry is **unique-indexes only**: CHECK constraint names and NOT-NULL column names ARE reported by both dialects, so a startup assertion or handler keyed on a CHECK name is portable. Named CHECK constraints are therefore the more testable choice where either would do.

---

---

## 2026-08-19

### G-053 — the gap-distribution harness is not deterministic; pin `PYTHONHASHSEED` before you compare two trees
- **Symptom:** you run [`docs/plans/package-benchmark-sweetener/measure_gap_distribution.py`](../docs/plans/package-benchmark-sweetener/measure_gap_distribution.py) on a branch, compare against the same file run on `origin/main`, and an arm you did not touch has moved. While wiring the arm-C sweetener the before/after showed `12t_1qb / v2_only / D_challenger` going from 1 sweetened card to 2 — arm D is generated by `gen(L)` and cannot see `trade_gen_v2` at all, so the diff read as a leak from the change under test. It is not: **running the harness TWICE on the identical tree reproduces the same 1 → 2 flip.**
- **Cause:** Python's per-process string-hash randomisation. The harness's league construction and several engine paths iterate `set`/`dict` structures whose order depends on `PYTHONHASHSEED`, and a tie among equally-ranked candidates then resolves differently. The effect is small — it moved one card in one arm in one of eighteen rows — which is exactly what makes it dangerous: it is far too small to look like noise and lands squarely in the size range of a real single-card regression.
- **Fix:** pin the seed on **both** sides of every comparison — `PYTHONHASHSEED=0 python3 docs/plans/package-benchmark-sweetener/measure_gap_distribution.py`. Verified: two consecutive seeded runs on one tree are byte-identical, and with the seed pinned the arm-C wiring shows a diff confined to arm C's own rows, which is the correct answer.
- **Prevention:** the harness's docstring now carries the `PYTHONHASHSEED=0` invocation on both the branch and the `origin/main` side. **This also qualifies the numbers already in the ledger:** the TEST_LEDGER 2026-08-21a table was produced unseeded, so single-card deltas in it (notably the ±1 card swings on arm B / arm D) may be seed noise rather than engine effects. The large moves in that table — the −20 % arm-D deck shrink, and arm C's 0 → 3 and 1 → 2 over-the-line rise — are far outside the observed ±1 jitter and stand. Re-run seeded before quoting any single-card delta from it as evidence.

---

### G-052 — two value→Elo maps exist; using the wrong inverse is silent near a 1st and grows downward
- **Symptom:** a draft pick badges one tier too high on the picks screen / in-league calculator, and the error looks band-shaped rather than arithmetic — a current-year 3rd reads `second`, a current-year 4th reads `third`. Round-1 picks look fine, which is what makes it read as "the cheap end of the ladder is mispriced" rather than "the conversion is wrong".
- **Cause:** the codebase has **two** maps onto the tier-band Elo scale and they are not inverses of each other. `trade_service.elo_to_value` ↔ `value_to_elo` moves between band Elo and **engine value** (what `draft_picks.pool_value`, every `/api/trade/evaluate` value and `pick_pool_value` are in). `data_loader.seed_value_for_elo` ↔ `seed_elo_for_value` moves between band Elo and **DynastyProcess's raw 0–10000 consensus scale**. Feeding an engine value to `seed_elo_for_value` applies DP's affine rescale (× 0.824487, + 223.130) to a number that never lived on the DP scale. **The two agree at exactly one point, Elo 1548.0** — solve `223.130 + 0.824487·v = v` — so the mistake is invisible around a mid-1st and grows the cheaper the asset: +35.2 Elo at a Mid 2nd, +63.4 at a Mid 3rd, +99.3 at a Mid 4th, +109.5 at a Late 4th.
- **Fix:** match the inverse to the scale the number is actually on. Engine value → `trade_service.value_to_elo`. DP value → `data_loader.seed_elo_for_value`. `docs/cross-client-invariants.md` now carries this as a two-row table under the banding rule; the column comment on `database.py`'s `pool_value` already said which scale it was, and reading it would have settled the question in one step.
- **Prevention:** test the **property**, not the literal. `test_league_picks_tier.py::test_current_year_rungs_badge_their_own_round` asserts that a current-year pick of round R badges exactly where `GENERIC_PICK_SEEDS[(R, "Mid")]` sits — which is what `tier_config.json`'s `_calibration` already *defines* to be true, and which no wrong inverse can satisfy for all four rounds. The literal-Elo pins that existed before happily absorbed the wrong numbers because they had been written by reading the buggy output back. **This is the third instance of the class** (#263 → #320 → [D-088](DECISIONS.md)); `seed_elo_for_value` is no longer imported into `server.py` at all, so the wrong tool is not in reach where value-scale numbers are handled.

---

### G-051 — a tier-band edit drifts `web/js/app.js`, the one mirror that never fetches
- **Symptom:** you move a tier floor in `backend/tier_config.json`, confirm mobile and the web tiers page pick it up after a reload, and the **rankings table on the web app keeps showing the old tier labels forever** — no reload, no cache clear, and no redeploy fixes it.
- **Cause:** the tier bands are mirrored across five clients, and they are **not all the same kind of mirror**. `mobile/src/utils/tierBands.ts` and `web/positional-tiers.html` hold *pre-fetch fallbacks* that `GET /api/tier-config` overwrites at boot, so they self-heal. `web/js/app.js`'s `_eloToTierLabel` is a **pure hardcode that never calls the endpoint at all** — the Elo cutoffs are inline `if (elo >= 1400) return '2nd';` literals. It can only be fixed by hand.
- **Fix:** treat `docs/cross-client-invariants.md` → "Tier band Elo cutoffs" → **Locations** as the checklist; it is accurate and it names all five. `git grep -nE "1927|1869|1788|1580|1280|1220|1150"` across `mobile web extension docs` finds the rest. The extension is genuinely clean — it consumes the backend walk and hardcodes no numbers.
- **Prevention:** the mirrors now carry comments saying which kind they are; `web/js/app.js`'s function head says outright that it does not fetch and must be hand-edited. **The deeper trap is the coupling**, worth stating separately: `tier_config.json`'s `_calibration` makes each tier floor a *rung of the pick ladder*, so editing `GENERIC_PICK_SEEDS` in `backend/pick_values.py` is silently also a tier-band edit. A seed change that skips `tier_config.json` (or vice versa) leaves the ladder internally inconsistent with nothing failing loudly — `test_tier_occupancy.py` checks occupancy bounds, not that the two files agree. Both directions were hit while shipping [D-084](DECISIONS.md).

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

### G-036 — a `league_id` analytics prop stores `"[scrubbed]"`, but only for Sleeper leagues
- **Symptom:** an event is registered, its props survive ingest, the row lands — and `props.league_id` reads `"[scrubbed]"`. Per-league analysis returns one giant bucket. Spot-checking against an ESPN league shows a real id and makes the whole thing look fine.
- **Cause:** `backend/analytics_ingest.py` `_PII_VALUE_RES` includes `\b\d(?:[ -]?\d){15,}\b` — a 16+ digit run, aimed at card numbers. **Sleeper league ids are 18 digits**, so they match. ESPN ids are ~6 digits and pass through untouched. The scrub happens *after* the prop allowlist, so every taxonomy-level check says the prop is fine.
- **Scope:** `invite_shared`, `invite_link_opened`, `invite_league_pinned`, `invite_pin_failed`, `outlook_strip_toggled` — every event carrying `league_id` as a string prop.
- **Fix:** not applied. Narrowing the regex weakens a real PII guard, and the honest alternatives (hash the id, or exempt a named prop key) are a decision the operator has not been asked. Pinned as behaviour by `test_p1_t1_league_id_is_redacted_by_the_pii_scrubber` so it cannot be rediscovered as a mystery, and recorded in the tracking plan so nobody plans a per-league metric on top of it.
- **Prevention:** a value-shape PII regex silently redacts any identifier that happens to share the shape. When registering a prop that carries a platform id, post a realistic value through `POST /api/events` and read it back out of `user_events` — asserting the *key* survived is not enough. This is G-031's lesson one layer deeper: name survival, prop survival, and **value** survival are three separate silent failures.


### G-042 — the local Maestro sim gate cannot run at all on this machine: no `JAVA_HOME`
- **Symptom:** every `sim-run.sh --flow …` returns **exit 1 (flow failure)** with `The operation couldn't be completed. Unable to locate a Java Runtime.` plus `/opt/homebrew/bin/maestro: line 251: [: : integer expression expected`. Exit 1 is the code for *a flow assertion failed*, so it reads as "the app is broken" when in fact **no flow ever ran**. Costs a full Release build (~45 min) before you see it.
- **Cause:** maestro is a JVM app. Homebrew `openjdk` **is installed** (26.0.2, `/opt/homebrew/opt/openjdk`) but is **not linked** into `/usr/libexec/java_home`, and `JAVA_HOME` is unset, so `java` resolves to the macOS stub at `/usr/bin/java` that only prints the "install Java" dialog. `which java` succeeds, which makes this look fine on inspection.
- **Fix:** `export JAVA_HOME=/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home` (and put `$JAVA_HOME/bin` first on `PATH`) before invoking `sim-run.sh` / `screen-capture.sh`. Verify with `java -version` printing `openjdk version "26…"`, **not** the install dialog.
- **Prevention:** `sim-run.sh` should preflight `java -version` and exit **2 (infra)** rather than letting maestro's failure surface as **1 (flow failure)** — an infra fault wearing a flow fault's exit code is exactly the class of thing that gets misread as a product regression. Not applied here (out of scope for the change that found it).
- **History:** found 2026-08-15 running the tier-2 gate for the co-owner fix ([TEST_LEDGER](TEST_LEDGER.md)). Fits the last several ledger entries recording the sim gate as not-run or waived — plausibly nobody could run it locally.

### G-043 — `sim-build.sh` fails at the JS bundle phase when `mobile/node_modules` is a symlink
- **Symptom:** after ~30 minutes of Pods compilation, `** BUILD FAILED **` in the `Bundle React Native code and images` phase with `Error: Cannot find module 'metro-runtime/package.json'`, and a require stack pointing at **another checkout's** `node_modules`.
- **Cause:** borrowing a sibling checkout's install (`ln -s …/mobile/node_modules`) to skip an `npm ci`. Node resolves the symlink's **realpath**, so `@expo/cli` walks up from the *other* tree, where `metro-runtime` is only present as a nested dep and is never reachable from that position.
- **Fix:** a real `npm ci` in the worktree. Verify before rebuilding: `node node_modules/expo/node_modules/@expo/cli/build/bin/cli export:embed --entry-file ./index.ts --platform ios --dev false --bundle-output /tmp/t.jsbundle --assets-dest /tmp/a` should bundle in seconds.
- **Prevention:** never symlink `node_modules` into a worktree for a **build**. It is fine for `tsc --noEmit` and the `check-*.js` suites (both passed against the symlink). The failure is specific to Metro's resolver, and it surfaces at the very end of the build — the most expensive possible place.
- **History:** found 2026-08-15 alongside [G-042](#g-042--the-local-maestro-sim-gate-cannot-run-at-all-on-this-machine-no-java_home).

### G-044 — a killed `sim-run.sh` leaves Flask holding :5001 and the next run aborts
- **Symptom:** `INFRA: whoami mismatch` / `AssertionError: STALE FLASK: whoami pid <a> != started pid <b> — another instance holds the port`, exit **2**.
- **Cause:** `sim-run.sh` starts a test-mode Flask on :5001 and stops it on exit. Kill the parent (Ctrl-C, `pkill` on a wrapper script) and the Flask child survives and keeps the port; the next run's whoami handshake correctly refuses to talk to someone else's server.
- **Fix:** `lsof -ti:5001 | xargs kill -9` before re-running.
- **Prevention:** the guard is working as designed — it is a rail, not a bug. Just know that "another instance holds the port" means *your own orphan*, not a second developer.

### G-045 — a whole league-mate silently missing from the deck, not just their cards
- **Symptom:** a boarded opponent produces **zero** trade cards at any per-opponent budget while obviously good trades exist against them — and raising the budget, loosening fairness, or checking the surplus gate all change nothing. Three of four boarded members in the operator's own league were in this state.
- **Cause (two, stacked):** (1) `trade_optimizer`'s candidate-pool prune ranks by the RAW divergence `_vo - _uv`, and `elo_to_value` is **exponential** — so an opponent board pinned near the 1200 floor deflates a stud by thousands of value points and a bench body by tens. Every tradeable stud sorts BELOW the user's junk and the top-`v3_pool_size` pool fills with worthless assets. (2) `trade_service`'s boarded/unboarded branch was `if/else` with **no fall-through**, so the zero result got no consensus fallback either and the member disappeared from the deck entirely.
- **How to recognise it fast:** compare the two boards' **medians**, not their maxima. The broken boards' maxima looked healthy (1800–1839); it was the median (1201 vs 1379) that gave it away. A board whose median sits at the floor is a "started ranking and stopped" board, and any engine step comparing two boards by a raw *value difference* is distorted by it.
- **Prevention:** when an engine step compares two personal boards, ask whether its output is invariant to a board-wide scale offset — an offset carries **zero** information about who either side prefers, so if the answer is no, that step has this bug. Fixed behind `trade.pool_calibration` / `trade.divergence_fallback` (see [D-052](DECISIONS.md)); the paired flag-off tests in `backend/tests/test_compressed_board.py` pin both the defect and the fix.
- **Not the lever it looks like:** `v3_pool_size` is a `model_config` knob and raising it to 30 does rescue these pairs — at **26–102 s per pair** against ~2 s at 12. Enumeration is cubic-ish in pool size on both sides; it is not a shippable mitigation.

### G-046 — a follow-up PR from a branch whose PR was already squash-merged is born CONFLICTING
- **Symptom:** you squash-merge PR A from a branch, commit one more thing to the SAME branch, open PR B — and GitHub says `mergeable: CONFLICTING`, `mergeStateStatus: DIRTY`, with conflicts across files you never touched in the follow-up.
- **Cause:** the squash collapsed your branch's commits into ONE new commit on `main` with no ancestry link back to them. Your branch still carries the originals, so git sees two unrelated histories that both edited the same lines. Nothing is actually wrong with the content — it is the same work twice, described two different ways.
- **Fix — do not try to merge `main` back in.** Cut a fresh branch off `origin/main` and `git cherry-pick` just the follow-up commit. It applies cleanly, because `main` already has everything the follow-up was built on. Then close the conflicted PR as superseded.
- **Prevention:** after a squash-merge, treat the source branch as spent. The next commit starts from `origin/main`, not from it. This repo squash-merges everything, so this applies to every follow-up — and it is the same root cause as the ID-renumber races (D-049→D-050, then D-051→D-052): concurrent work reconciles against `origin/main`, never against your own branch.

### G-047 — "no checks reported" on a PR reads as a pass to a naive poller
- **Symptom:** a wait-for-CI loop shaped `until [ "$(gh pr view N --jq '[.statusCheckRollup[]? | select(.status != "COMPLETED")] | length')" = "0" ]` returns instantly and announces success, having verified nothing. `gh pr checks N` says `no checks reported on the '<branch>' branch`.
- **Cause:** zero pending checks out of **zero total** satisfies the condition. An empty rollup and a fully-green rollup are the same value to that test. GitHub leaves the rollup empty when a PR is `DIRTY`/`CONFLICTING` (no merge commit to run against), and it is also empty in the seconds before workflows register.
- **Fix:** require the rollup to be **non-empty** as a separate clause — `[ "$(… | length)" -ge 1 ] && [ "$(… pending … | length)" = "0" ]` — and assert the conclusions are `SUCCESS`, not merely that nothing is `IN_PROGRESS`.
- **Prevention:** the general shape of this bug is trusting an absence as evidence of a pass. Same family as [G-036](GOTCHAS.md) (a prop key survives while its *value* is silently scrubbed) and the analytics `no_identity` false-pass. When a check reports "nothing wrong", confirm it actually looked.

### G-048 — next living-memory ID computed from a stale checkout collides on main
- **Symptom:** two different decisions both called D-047 — one on `origin/main` (device-auth defaults, 2026-08-13), one minted in a session whose checkout branch's DECISIONS.md topped out at D-046. The collision shipped: merged PR code comments and a `model_config` seed description cited the wrong decision, and had to be renumbered post-merge (D-055/D-056, 2026-08-15).
- **Cause:** "next ID = max existing + 1 — grep first" was run against the checked-out branch's copy of the file. This repo runs many concurrent sessions; the checkout is routinely days stale, and living-memory files advance on `main` between sessions.
- **Fix:** compute IDs against **`origin/main` after a fetch** — `git fetch origin && git show origin/main:living-memory/DECISIONS.md | grep -oE '^## D-[0-9]+' | sort -V | tail -1` — never against the working tree or checkout branch.
- **Prevention:** same discipline for every ID'd file (D-/G-/M-/Q-). If the working tree's copy of an ID'd file differs from `origin/main`'s, the working tree is not evidence of anything.

### G-054 — a blanket decision-ID find-and-replace rewrites headings but not their anchors
- **Symptom:** an `LLD.md` section heading credited D-147 while its own TOC anchor still read `#…-d-144`. The heading text was wrong *and* the anchor was wrong, in two different ways, and the section actually belonged to D-146.
- **Cause:** two stacked edits, neither verified against `DECISIONS.md`. (1) The slot-pricing session drafted its decision as D-144, renumbered the DECISIONS.md entry to D-146 ([G-048](GOTCHAS.md) again) and missed the LLD heading it had already written. (2) PR #168 then ran a blanket `D-144` → `D-147` replace over LLD.md to stamp the negmem section, silently converting the already-wrong D-144 into a differently-wrong D-147 — and, because it authored the new negmem TOC row by copying the neighbouring one, carried the stale `d-144` anchor into a brand-new entry too.
- **Fix:** never blanket-replace an ID across a living-memory doc. Change one heading at a time, and re-derive each section's owner from `DECISIONS.md` by *what the decision says it decided*, not by adjacency or date. Corrected 2026-08-21: both "Retiring a per-user setting" and "Pricing waterfalls" → D-146 (the decision that retired `pick_pricing_mode`); "Append-only, version-stamped measurement tables" stays D-144 (receipts); the negmem heading stays D-147 and only its anchor moved.
- **Blast radius, the part that was NOT in LLD.md:** the same renumber miss left the draft ID `D-144` in every downstream doc the slot-pricing session wrote — `docs/api-reference.md` (the retired route), `docs/config-reference.md` (`trade.slot_pricing`), `docs/data-dictionary.md` (`pick_pricing_mode` dead data) and five places in `docs/cross-client-invariants.md` — each one pointing a reader at Receipts grading instead of pick pricing. It then propagated: PR #169's brand-new D-148 section opened *"D-144 put per-slot pick pricing into the engine"*, inheriting the wrong ID from the neighbour it was written beside. All corrected 2026-08-21. **When you renumber a decision, `git grep` the OLD id across `docs/` and `living-memory/` — renumbering the `DECISIONS.md` entry is the smallest part of the job.** (`docs/plans/**` drafts keep the old number on purpose: they are the historical record of the draft.)
- **Prevention:** **a heading/anchor mismatch is the fingerprint of a blanket replace** — a markdown TOC anchor is a frozen copy of the heading at authoring time, so when they disagree, some later edit touched the text and not the link. Cheap detector, run it after any ID edit: slug every `^## ` heading and assert each `](#…)` target resolves and equals the slug of its own link text. It also catches the copy-a-neighbouring-TOC-row habit that produced the second defect here.

## 2026-08-22

### G-055 — a too-long feedback note vanishes with no error anywhere
- **Symptom:** an operator wrote a long in-app feedback note, tapped Save, and the sheet closed exactly as it does on success. The note never appeared in `/api/feedback/admin`. There was no error toast, no failed-request banner, and no server row to find — because a rejected POST writes nothing.
- **Cause:** three behaviors that are each defensible alone and catastrophic together. (1) `POST /api/feedback` refused any note over **2000 characters** with `400 text_too_long`. (2) `FeedbackSheet` had no `maxLength` and no character counter, so nothing in the UI hinted a cap existed. (3) `onSave` `await`ed `add()` and then cleared the draft and closed *unconditionally* — and `useFeedback.add` fired the POST in a detached `void (async () => …)()` IIFE that always resolved `synced: false`, so the caller could not have checked even if it wanted to. A 400 is **permanent**, so `retrySync()` and the AppState foreground hook then re-attempted the same doomed request forever.
- **Where the data actually was:** on the device. `add()` persists to AsyncStorage *before* the network call, so the note survived with `synced:false` and was readable the whole time at **Settings → Testing → "Test feedback"**, badged `Sync failed`. Nothing was lost — but nothing said so either, which is the entire defect.
- **Fix (2026-08-22):** cap raised 2000 → 8000 ([D-149](DECISIONS.md)); a live counter that reddens past the limit and holds Save; `add()` awaits the POST and resolves the item's true sync state; `onSave` clears the draft only inside the success branch and otherwise says *"saved on this device, but not sent yet"* and names the inbox route.
- **Prevention — the general shape, which is what to remember:** *a write path whose failure is indistinguishable from its success will lose data, and you will not find out from logs.* Three specific tells to hunt for: a `catch` that converts an error into a state field nobody reads; a UI that destroys user input before confirming the input was accepted; and a retry loop with no notion of a permanent failure (a 4xx is not a 5xx — re-sending it is guaranteed waste). Same family as [G-050](GOTCHAS.md) (an assertion inside a swallowed `try` can never fail).
- **Detection cost:** the only reason this was found at all is that the operator remembered writing the note and asked. There is no server-side record of a rejected submission, so the true historical count of notes lost this way is **unknowable** — `obs.api_events` captures the 400s going forward, but only from the day it was checked.

### G-056 — `navigate('TradesHome')` from a pushed Trades-stack screen pushes a second instance; it does not pop back
- **Symptom (2026-08-22, #384 E2E review):** the merged calculator's "Find a Trade" calls `navigation.navigate('TradesHome')`. The prior build session's status doc, its TestFlight checklist, and **three of five independent reviewers** all reasoned "TradesHome is the stack root, so this pops `TradeCalculator`, whose effect cleanup runs `stopCalcTour()`" — and built and judged the tour lifecycle on that assumption. It is false.
- **Cause:** `@react-navigation/routers` 7.5.3 `StackRouter` `NAVIGATE` (`node_modules/@react-navigation/routers/src/StackRouter.tsx:372-390`) only reuses an existing route when it is the *current* route, when `payload.pop` is set, or when the screen declares a `getId`. `TradesHome` has none of these (`mobile/src/navigation/TabNav.tsx:445-449`), so the call **pushes a new `TradesHome` on top** — the stack becomes `TradesHome → TradeCalculator → TradesHome`, the calculator stays mounted (no cleanup), "back" from the deck lands on the calculator, and the new instance starts with its own state (so nothing the previous instance held — deck, job — is what the user sees). The pre-existing #213 "Find a trade →" link and `TeamReviewScreen.tsx:325` have the same shape; `navigation/CLAUDE.md` even documents the deep-link variant as "pushes a second deck instance".
- **Prevention:** a code-walk proof that depends on a navigation side-effect (unmount, cleanup, param merge) must cite the router source for the installed version, not the v6 mental model. To actually return to the root use `navigate('TradesHome', undefined, { pop: true })` / `popTo`, or give the screen a `getId`. Reviewers: when several agents agree on a navigation claim, that is correlated reasoning, not verification — one of them should open `node_modules`.

### G-057 — a Release simulator build crashes at launch after `pod install` because the Hermes config marker lies
- **Symptom (2026-08-22, #384 W8 simulator session):** a Release `xcodebuild` for the simulator succeeds, the app launches, and ~2 s later `launchd_sim` reports `exited due to SIGSEGV`. The `.ips` report's faulting thread is the JS thread: `hermes` (mis-symbolized as `HermesRuntimeImpl::debugJavaScript`) ← `ReactInstance::initializeRuntime` lambda ← `RuntimeScheduler_Modern::runEventLoop`, `KERN_INVALID_ADDRESS at 0x17`. No JS ever runs, so there is no red box, no Sentry event, nothing in `log show` beyond the signal. A **clean** rebuild (`rm -rf <derivedData>/Build`) does not fix it.
- **Cause:** `hermes-engine`'s "[Hermes] Replace Hermes for the right configuration, if needed" script phase (`node_modules/react-native/sdks/hermes-engine/utils/replace_hermes_version.js`) swaps `Pods/hermes-engine/destroot` between the debug and release tarballs in `Pods/hermes-engine-artifacts/`, and remembers what it last installed in **`Pods/.last_build_configuration`**. A later `pod install` (here: forced by "The sandbox is not in sync with the Podfile.lock" after `git checkout -- Podfile.lock`) reinstalls `hermes-engine` from the CocoaPods cache — the **debug** variant, which is what the podspec downloads — but leaves the marker saying `Release`. Every subsequent Release build reads the marker, prints nothing, skips the swap, and links release React against the debug `hermes.framework`. Verify with `md5 -q Pods/hermes-engine/destroot/.../ios-arm64_x86_64-simulator/hermes.framework/hermes` against the two tarballs' slices — the debug one is 13.8 MB, the release one 9.5 MB.
- **Fix:** `rm Pods/.last_build_configuration` and rebuild (incremental is fine — the phase re-extracts the release tarball and the embed step re-copies it). Nothing to commit; `Pods/` is untracked.
- **Prevention:** after **any** `pod install` in a checkout that has already done a Release build, delete the marker before building again. EAS is unaffected (fresh `Pods/` every build). Related to the session-setup notes in [TEST_LEDGER](TEST_LEDGER.md) `2026-08-22i` (`LANG=en_US.UTF-8` for `pod install`, `SENTRY_DISABLE_AUTO_UPLOAD=true`, never `CODE_SIGNING_ALLOWED=NO`).

### G-058 — Loosening a trade-engine knob measures "no effect" three different ways, all of them lies
- **Symptom:** you raise a gate or budget knob to widen the deck, re-run, and the card count is unchanged (or moves by one). The obvious conclusion — "that knob isn't the bottleneck" — is wrong at least as often as it is right. Verified against live prod values on 2026-08-22.
- **Cause 1 — the per-opponent cap is applied three times, and the last one has no knob.** `max_per_opponent` bounds generation, `global_target = max(30, max_per_opponent × 6)` bounds the opponent sweep, and then `server._split_exploration_pool` trims back to **`_EXPLORATION_BASE_PER_OPP = 5`**, a hardcoded module constant. `deck.exploration` is ON, so the route already generates 8/opponent and throws the surplus away. Raising the knob alone changes nothing user-visible.
- **Cause 2 — the gates are conjunctive and heavily redundant.** 97.6% of rejections are made by two or more rules at once; four separate rules punish "one big player for several smaller ones" using different arithmetic on three different value spaces. Loosen one and the next catches the same trade. The measured extreme: `trade_elo_gap_max` first-kills ~half the divergence universe and uniquely kills **zero** — it is free only because `#141` fires first, and becomes the binding wall the moment `#141` moves. **Change them in pairs** (see [`../docs/reviews/2026-08-22-trade-model-restrictiveness.html`](../docs/reviews/2026-08-22-trade-model-restrictiveness.html) R3/R4).
- **Cause 3 — the predicates are bound by value at import.** `trade_optimizer.py` and `trade_gen_v2.py` bind `filler_ok`, `pick_swap_ok`, `fit_premium_1for1` and friends into their own namespace at import time. An A/B that patches the `trade_service` definition rather than the *calling* namespace measures a perfect no-op while the original still runs. `trade_gen_fit.py` deliberately avoids this by calling through the module object (`ts.overpay_ok(...)`) — that is [D-098](DECISIONS.md), not a style preference.
- **Also:** `user_gain_epsilon` is read by **four** call sites across both served arms, so moving it for a consensus experiment silently loosens the divergence arm too.
- **Fix:** before trusting a null result, (a) grep for every read of the knob, (b) check for a hardcoded sibling constant downstream, (c) confirm the patch target matches the *calling* namespace, and (d) check the co-kill data in [`../docs/reviews/2026-08-19-knockout-waterfall.md`](../docs/reviews/2026-08-19-knockout-waterfall.md) for a rule that would catch the same trades.
- **Prevention:** make `_EXPLORATION_BASE_PER_OPP` a `model_config` key; keep quoting *unique* kills, never first-kills, when arguing that a rule matters.

## 2026-08-23

### G-059 — a breaker payload test flakes only on a loaded CI runner: the 250 ms wall-clock budget is a hidden test input
- **Symptom:** CI 2026-08-23 (run 32681703490, commit `8fd23e2`, a docs-only PR): `test_stud_tax_pinned_market` failed asserting two `stamp_breaker` payloads equal — `'skipped': None` vs `{'classes': [...], 'reason': 'budget'}` — then passed on `gh run rerun --failed` of the same sha, passed in isolation, and passed a local full-suite run. Looks exactly like fixture pollution or dict-order nondeterminism; it is neither.
- **Cause:** `stamp_breaker` runs under a *real* wall-clock budget (`breaker_ms_budget` = 250 ms) with a pass-2 checkpoint at `breaker_budget_checkpoint_frac` = 0.6 (`trade_breaker.py:929`): past 150 ms elapsed, every pass-2 class stamps as `_skip(code, "budget")` and the payload's `skipped` field goes non-null. Any test that asserts stamped payload content — especially the stamp-twice-and-compare determinism tests — therefore has wall clock as an invisible input. A busy shared runner (plus the breaker's per-stamp live DB read for asset prefs, whose latency varies with whatever DB state earlier tests left) crosses the checkpoint on one stamp and not the other. Suite order only matters as load; nothing was polluted.
- **Repro (deterministic):** skew `trade_breaker.time.monotonic` by +12 ms per call during the second stamp only — the exact CI assertion diff appears every run.
- **Fix (2026-08-23):** the file's autouse `_env` fixture pins `ts._cfg["breaker_ms_budget"] = 10**9`. Budget rungs stay covered by their own tests, which drive the budget through `_snap_with` knob overrides and fake clocks — the real clock never picks a rung in the suite.
- **Prevention:** any new test file that stamps the breaker and asserts payload content must pin the budget knob the same way. General shape: a production time-budget that changes output shape makes every downstream golden load-flaky; a test touching such a path must control either the clock or the budget, or its green is a function of machine load.

### G-060 — a byte-clean restore can leave a stale `.pyc` red
- **Symptom:** sabotage a module, run the test (red), restore the file from a byte copy, re-run — still red, though `diff` says the file is identical to the green state.
- **Cause:** CPython invalidates bytecode by (mtime, size). A `cp` restore landing in the SAME second as the sabotage write, at identical file size, matches the cached `.pyc`'s stamp — Python keeps executing the sabotaged bytecode. Hit twice during the knockout-refine build (B1's S8, the Fable reviewer's spot-checks).
- **Fix:** `find backend -name __pycache__ -exec rm -rf {} +` after any restore; then re-run.
- **Prevention:** every sabotage recipe in a test docstring should end "clear `__pycache__` after restoring". Both knockout-refine test modules now say so.

### G-061 — the winback tests fail exactly one day a year: the daily tick's Aug-25 branch is a hidden calendar input
- **Symptom:** `test_notif_teardown.py`'s three winback tests fail with zero `winback_dormant` pushes; same tree and interpreter passed the day before. Found live on 2026-08-25, blocking an unrelated PR's local gates.
- **Cause:** `server.py` daily tick: `is_aug25 = (now.month == 8 and now.day == 25)` sends every signed-up user the `season_start` fan-out and `continue`s — deliberately skipping every winback that day. The tests read the REAL clock, so on Aug 25 the branch under test is unreachable. G-059's lesson in calendar form: any real-world input a route reads (wall-clock budget, date) is a test input whether the test declares it or not.
- **Fix:** the winback tests pin the tick's clock (`patch.object(server, "datetime", _clock_at(_TICK_NOW))`, user timestamps derived from the same instant); the Aug-25 branch got its own pinned test (`test_season_start_fanout_on_aug25`) instead of staying dark.
- **Prevention:** a test driving any `/api/cron/*` tick fakes the clock, never inherits the runner's date.
