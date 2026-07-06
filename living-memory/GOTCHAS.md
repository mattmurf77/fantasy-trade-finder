# Gotchas — Fantasy Trade Finder

> **Purpose:** known traps in *this* codebase. Symptoms, root causes, workarounds. Different from [`MISTAKES.md`](MISTAKES.md): mistakes are *approaches that failed*; gotchas are *bugs and quirks that bite*.
>
> **Read at:** before debugging anything that smells weird. **Write at:** the moment you waste >30 minutes on a non-obvious quirk.
>
> Companion files: [`../docs/runbook.md`](../docs/runbook.md) for operational runbook (longer-form).

---

## Table of Contents
- [2026-05-21](#2026-05-21)
- [2026-07-04](#2026-07-04) — G-011 PlayerCard gesture-swallow, G-012 iOS version source
- [Gotcha Template](#gotcha-template)

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
