# Open Questions — Fantasy Trade Finder

> **Purpose:** track questions that need information, decision, or external action before work can proceed. File them here, continue around them, check back when answers arrive.
>
> **Read at:** session start (to confirm none have been answered offline). **Write at:** the instant you'd otherwise stop work to ask.

---

## Table of Contents
- [2026-06-07 — Open Items (perf-optimization)](#2026-06-07--open-items-perf-optimization)
- [2026-05-21 — Open Items](#2026-05-21--open-items)
- [Closed Questions (kept for cross-reference)](#closed-questions-kept-for-cross-reference)
- [Conventions](#conventions)

---

## 2026-06-07 — Open Items (perf-optimization)

> Full detail + defaults: [`../docs/plans/perf-optimization/artifacts/questions-for-user.md`](../docs/plans/perf-optimization/artifacts/questions-for-user.md).
> All six are **non-blocking** — autonomous Wave-2 work proceeds on the documented defaults. Owner: operator. Asked on: 2026-06-07.

### ~~Q-010~~ — Render cold-start mitigation — **RESOLVED 2026-06-08**
- **Resolution:** upgrading to Render Starter dyno ($7/mo, always-on). Complete fix; no code change needed.

### ~~Q-011~~ — Merge audit docs — **RESOLVED 2026-06-08**
- **Resolution:** leave on `audit/perf-optimization` branch. Not merged to main.

### ~~Q-012~~ — Build/ship cadence — **RESOLVED 2026-06-08**
- **Resolution:** EAS build kicked after Wave 2 landed.

### ~~Q-013~~ — INIT-08 backend split — **RESOLVED 2026-06-08 (NOT DOING)**
- **Resolution:** Profiled with real Sleeper data (league `1181674778942836736`). Cold session_init = 519 ms; 95% (494 ms) is Dynasty Process network fetch in `_ensure_universal_pools`, not TradeService construction. Warm server = 25 ms — nothing to split. INIT-08-client (PR #73) is the correct UX fix; backend split not worth doing. See `backend/profile_session_init.py`.

### ~~Q-014~~ — INIT-10 web player payload — **RESOLVED 2026-06-08**
- **Resolution:** Shipped as PR #74. `?view=summary|detail|full` + ETag/Cache-Control added to `/api/players`.

### ~~Q-015~~ — AsyncStorage vs MMKV — **RESOLVED 2026-06-07**
- **Resolution:** AsyncStorage shipped in Wave 2 (PR #71). Upgrade path documented in ADR-001.

---

## 2026-05-21 — Open Items

### ~~Q-001~~ — Cleanup the duplicate SQLite DB — **RESOLVED 2026-06-10**
- **Resolution:** verified `backend/database.py:34` references only `data/trade_finder.db`; root copy (stale since Apr 11) archived to `data/archive/trade_finder.root-legacy-2026-04-11.db`. `.gitignore` already covers `*.db`. Root `CLAUDE.md` convention line updated.

### ~~Q-002~~ — Adopt pytest for backend services — **RESOLVED 2026-06-10 (by the v2 rebuild)**
- **Resolution:** pytest baseline now exists — 121 tests in `backend/tests/` covering trade engine v2/v3 (optimizer, deck ordering, prune equivalence), Elo memoization, DB hygiene, disposition flow, roster profile, narratives, pick values, telemetry. Coverage can deepen, but the "zero automated tests" risk is gone.

### Q-003 — Tiered matchup engine: scope and acceptance criteria
- **Why it matters:** the current matchup generator optimizes globally (tightest Elo cluster across all players). Plan in [`../context.md`](../context.md) is to tier-prioritize: top tier first, then mid, then bench. Open: what's the formal acceptance criterion? "Top-tier rankings converge faster" needs a metric.
- **Action to unblock:** define the metric (e.g. "median Elo std-dev among top 12 players after N swipes drops X%"). Set up A/B harness.
- **Workaround in the meantime:** global matchup engine is fine for general use.
- **Owner:** operator.
- **Asked on:** 2026-05-21.

### Q-004 — DynastyProcess name fuzzy-matching: should this be automated?
- **Why it matters:** `dump_mismatches.py` identifies player name mismatches between DynastyProcess CSV and Sleeper. Manual reconciliation is brittle and gets out-of-date.
- **Action to unblock:** evaluate fuzzy-match libraries (`rapidfuzz`, `Levenshtein`) on the existing mismatch dump. If >90% of mismatches can be auto-resolved, integrate.
- **Workaround in the meantime:** manual reconciliation as mismatches surface.
- **Owner:** operator.
- **Asked on:** 2026-05-21.

### Q-005 — Real-league trade matching: launch criteria — **ACTIVE (operator decision 2026-06-10)**
- **Decision:** operator chose to recruit 1–2 willing league-mates now (pre-season window) to validate the two-sided loop end-to-end on the live v2/v3 engine. Success: a single real mutual match found and surfaced correctly.
- **Supporting work shipped 2026-06-10:** cold-start invite nudge (mobile TradesScreen banner + web coverage-row Invite button → existing invite modal/share sheet) and `/api/admin/engine-metrics` telemetry to watch like/match rates as they join.
- **Owner:** operator (recruiting); engine metrics watched per session.

### ~~Q-006~~ — iPhone app completion order — **RESOLVED (overtaken by events)**
- **Resolution:** full mobile app shipped via EAS/TestFlight (build 14, 2026-06-10) — login, league select, ranking, tiers, trades, matches all live. The question's premise no longer exists.

### Q-007 — Production deployment: Render free tier vs paid?
- **Why it matters:** [`render.yaml`](../render.yaml) exists. Free tier may spin down between requests (cold starts of 30+ seconds). Paid starter (~$7/mo) keeps it warm.
- **Action to unblock:** decide. If launching publicly, paid. If personal-use only, free is fine but document the cold-start UX.
- **Workaround in the meantime:** local dev works fine; production deferred.
- **Owner:** operator.
- **Asked on:** 2026-05-21.

### Q-008 — Browser extension distribution strategy
- **Why it matters:** extension exists in `extension/` but unpublished. Chrome Web Store: $5 one-time + review. Self-hosted as `.crx` is possible but requires sideloading.
- **Action to unblock:** decide: public store (small fee, broader reach, review delay) vs distribute manually (free, friction-y).
- **Workaround in the meantime:** unpacked loading during dev works.
- **Owner:** operator.
- **Asked on:** 2026-05-21.

### Q-009 — Mascot decision (Tommy Tumble vs Ricky Rumble vs other)
- **Why it matters:** branding direction. The mascot concept (running back mid-fumble) is settled; the name isn't. Per [`../context.md`](../context.md): top candidates are "Tommy Tumble" or "Ricky Rumble."
- **Action to unblock:** pick. Maybe poll a few dynasty friends.
- **Workaround in the meantime:** no mascot in current UI.
- **Owner:** operator.
- **Asked on:** 2026-05-21.

---

## Closed Questions (kept for cross-reference)

### Q-010 — Render cold-start mitigation
- **Resolution (2026-06-08):** Upgraded to Render Starter dyno ($7/mo, always-on). No code change needed.

### Q-011 — Merge audit docs to main
- **Resolution (2026-06-08):** Left on `audit/perf-optimization` branch.

### Q-012 — Build/ship cadence
- **Resolution (2026-06-08):** EAS build kicked after Wave 2.

### Q-013 — INIT-08 backend session_init split
- **Resolution (2026-06-08):** Profiled — not worth doing. Warm server is already 25 ms. Cold-server bottleneck is Dynasty Process network fetch (495 ms), not TradeService build. INIT-08-client (PR #73) is the correct fix. See `backend/profile_session_init.py`.

### Q-014 — INIT-10 web player payload
- **Resolution (2026-06-08):** Shipped as PR #74 (`?view=` projection + ETag caching on `/api/players`).

### Q-015 — AsyncStorage vs MMKV
- **Resolution (2026-06-07):** AsyncStorage shipped in Wave 2 (PR #71). Upgrade path in ADR-001.

---

## Conventions

- **Sequential numbering.** Q-001, Q-002, ... — never reuse a number.
- **Each item has:** why it matters, action to unblock, workaround, owner, ask date.
- **Closed items move to the "Closed" section** with a one-line resolution.
- **Don't delete.** Even resolved questions carry information about why decisions were made.
