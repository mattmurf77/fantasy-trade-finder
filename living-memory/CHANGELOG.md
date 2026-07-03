# Changelog — Fantasy Trade Finder

> **Purpose:** cross-session memory. Capture what was built, decisions that affect future work, and known gaps.
>
> **Read at:** session start.
> **Write at:** session end.
>
> Companion files: [`HANDOFF.md`](HANDOFF.md) for forward-looking; [`../docs/`](../docs/) for per-feature reference updates.

---

## Table of Contents
- [2026-06-10 (post-ship follow-ups)](#2026-06-10-post-ship-follow-ups)
- [2026-05-21](#2026-05-21)
- [Earlier (pre-changelog)](#earlier-pre-changelog)
- [Outstanding / Known Gaps](#outstanding--known-gaps)

---

## 2026-06-11 (TestFlight ship: v1.2.0)

- **Shipped the full batch:** PR #87 squash-merged → Render deployed (verified: feedback `status` field live, migration ran). EAS build `200a88aa` (v1.2.0) built + submitted to TestFlight (Apple processing). Contents: feedback lifecycle status + inbox chips, FB-45/46/48 fixes, engine telemetry, cold-start invite nudge, FB-47 Phases A+B (dark), League polish batch (28/37/38/42), portfolio season fix, restart-proof swipes.
- **Prod backfill executed: 46/46 feedback statuses + 3 severity reclassifications (37/38/47 → idea).** Whole queue dispositioned; remaining open work = FB-47 Phase C (clients) + operator league-mate recruiting (Q-005).
- ⚠️ CRON_SECRET still pending rotation (used from chat for the backfill).

## 2026-06-10 (feedback bugs 45/46/48)

- **FB-45/46 root cause:** server sessions + trade decks are in-memory and die on every Render deploy, while mobile restores its token from secure-store and never re-inits → all calls 401 (Trios breaks) and every swipe fails "Unknown trade_id". Fixes: mobile `revalidateSession()` (cold launch + foreground resume, 60s throttle, never signs out on failure); 401 guard in client.ts (stale 401 can't clear a freshly-minted token); restart-proof `/api/trades/swipe` — payload echoes card context, server reconstructs unknown cards (`_reconstruct_swipe_card`), full decision flow preserved; `trade_card_to_dict` now serializes `target_user_id`.
- **FB-48 root cause:** Sleeper mints a new league_id per season; `league_members` holds last season's instance of each league (verified locally: Lakeview + FFv3 under two ids each) → carried-over players double-count in Portfolio. Fix: `/api/portfolio?league_ids=` scoping, passed by both mobile (session league list) and web (`_cachedLeagues`).
- **FB-47 queued** (standalone needs-based trade finder) in `NEXT.md`; feedback inbox doc updated through id 48. Suite: 127 passing.
- ⚠️ CRON_SECRET was pasted in chat again — operator should rotate in Render dashboard.

## 2026-06-10 (post-ship follow-ups)

- **External research verified online** for the trade-engine deep dive ([`../docs/reviews/trade-engine-deep-dive.md`](../docs/reviews/trade-engine-deep-dive.md) §3 now has sources). Two corrections: eBay QJE 2020 documents bargaining *behavior*, not an ML acceptance model; DynastyProcess's published decay (k=0.0235) is ~2× steeper than the legacy `ktc_k=0.0126` — depth was over-valued by the old curve.
- **Engine telemetry shipped:** `load_engine_telemetry()` in `backend/database.py` + `GET /api/admin/engine-metrics` (`?days=&league_id=`) — like/pass rates by basis, likes-you, deck position, package shape, league; match conversion. 4 new tests (`test_engine_telemetry.py`); suite at 121 passing. Unblocks fairness_threshold / package_adj_gamma tuning.
- **Cold-start invite flow shipped:** mobile `InviteLeaguematesBanner` on TradesScreen (0-ranked leagues → OS share sheet with `/?league=&ref=` referral URL); web coverage row's 0-ranked label gained an Invite button → existing invite modal (verified in browser preview). Supports Q-005 validation (operator recruiting 1–2 league-mates).
- **Operator decisions recorded:** hold 3-team UI until 2-team proves out; keep DynastyProcess values (FantasyCalc deferred — free/keyless but unlicensed); validation via recruited league-mates.
- **Backlog cleanup:** Q-001 resolved (root DB archived to `data/archive/`); Q-002 resolved (pytest baseline exists); Q-006 closed (mobile shipped); May handoff's notification-name bug confirmed already fixed (`server.py:3962`). `NEXT.md` queue refreshed; stale `.handoff.md` superseded.

## 2026-05-21

- **Adopted the 17-pattern living-memory layer** at [`living-memory/`](.). Pattern imported from the `Master Claude Code Best Practices` workspace. All 18 files created (CHANGELOG + HLD + LLD + THIRD_PARTY + SOURCES + PRACTICES + BRAND + SUBAGENT_PRINCIPLES + CONTEXT + GLOSSARY + DECISIONS + OPEN_QUESTIONS + DEPENDENCIES + TEST_LEDGER + HANDOFF + NEXT + MISTAKES + GOTCHAS) plus FORMAT.md, README.md, and the `living-memory-format-check` skill at [`../.claude/skills/`](../.claude/skills/).
- **Decision logged: D-009 — `docs/` as source of truth.** Living-memory files cross-reference [`../docs/`](../docs/) rather than duplicate. Specific mappings in [`FORMAT.md`](FORMAT.md) §Relationship-with-docs. When the two conflict, `docs/` wins.
- **First-pass decisions captured in `DECISIONS.md`** — 10 foundational decisions (D-001 through D-010), all marked Active. Notable: Sleeper as sole identity provider (D-001), 3-player matchups for 2.6× info gain (D-002), Anthropic optional (D-005), SQLite-first/Postgres-swappable (D-007).
- **Open questions captured** — 9 open items (Q-001 through Q-009) including duplicate-DB cleanup, pytest adoption, tiered-matchup-engine acceptance criteria, fuzzy-matching for DynastyProcess names, real-league trade matching launch, iPhone app completion order, Render deployment tier, browser-extension distribution, mascot decision.

## Earlier (pre-changelog)

This section captures the project's state as it existed before the living-memory layer was adopted. Detailed history lives in `git log`, [`../context.md`](../context.md), and the existing [`../docs/`](../docs/) folder.

- **Backend, ranking engine, trade discovery shipped.** Sleeper-based login, 3-player Elo ranking, mutual-gain trade card generation, in-memory debug logging.
- **Web client shipped** as vanilla HTML/CSS/JS in `web/`. Single-page-app pattern.
- **Mobile client in progress** (Expo / React Native). Login + league select screens done; ranking screen in progress; trade-finder not yet ported.
- **Browser extension shipped** (MV3) in `extension/`.
- **Custom skills built and benchmarked:** `feature-evaluator.skill` (7-dimension code evaluation) and `project-reorganizer.skill` (6-phase reorganization workflow; +40pp vs ad-hoc per [`../project-reorganizer-eval-review.html`](../project-reorganizer-eval-review.html)).
- **Existing reference documentation** in [`../docs/`](../docs/) — architecture, api-reference, data-dictionary, glossary, runbook, coding-guidelines, cross-client-invariants, ADR skeleton.

---

## Outstanding / Known Gaps

- No automated test suite — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) §Q-002.
- Duplicate SQLite DB at root vs `data/` — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) §Q-001.
- Tiered matchup engine planned but not built — see [`NEXT.md`](NEXT.md).
- iPhone app incomplete (ranking screen in progress, trade-finder not ported) — see [`NEXT.md`](NEXT.md).
- Production deployment not exercised — Render config exists but unused.
- Mascot decision pending — see [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) §Q-009.
