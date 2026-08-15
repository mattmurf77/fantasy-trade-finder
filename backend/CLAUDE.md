# backend/ — Notes for Claude

Flask + SQLAlchemy Core. Module map:

- **server.py** — ALL ~174 HTTP routes (20k lines). Grep the route path (`app.route("/api/...`); don't read the whole file.
- **database.py** — schema + migrations (10k lines).
- **Engine** — ranking_service.py (Elo), value_model.py, trade_service.py, trade_optimizer.py, smart_matchup_generator.py.
- **Gating** — feature_flags.py (reads `config/features.json`), experiments.py, entitlements.py, accounts.py.
- **Analytics** — analytics_ingest.py / analytics_queries.py / analytics_stats.py / analytics_taxonomy.py. Spec events in taxonomy.py BEFORE firing them anywhere.
- **League integrations** — sleeper_write.py, espn_service.py, mfl_service.py, fleaflicker_service.py.
- **sleeper_roster.py** — the ONE roster→user predicate (`owner_id` **or** `co_owners`). Anything asking "is this roster the caller's?" goes through it; mirrored in `mobile/src/api/sleeper.ts` + `web/js/app.js`. Its companion is `server._league_user_id(sess)` — the caller's LEAGUE identity (their roster's `owner_id`) as opposed to `sess["user_id"]`, their ACCOUNT identity. League-scoped comparisons use the former, account-scoped state the latter; they're the same string for a sole owner. See ADR-012.

**CRITICAL:** `test_support.py` and `test_users.py` are PRODUCTION modules imported by server.py (the `FTF_TEST_MODE` mobile-UI-testing harness + the `qa_*` stage-user spawner) — never move or archive them. Real tests live in `tests/`.

Docs triggers: route change → `docs/api-reference.md`; schema change → `docs/data-dictionary.md`; env var/flag → `docs/config-reference.md`; module wiring → `docs/architecture.md` + `living-memory/HLD.md`. See root `CLAUDE.md` §Conventions "Feature gates" before adding user-visible behavior.
