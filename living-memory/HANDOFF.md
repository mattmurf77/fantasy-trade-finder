# Handoff — Fantasy Trade Finder

> **Purpose:** forward-looking session handoff. Where am I right now, what's half-done, what's next, what's blocking. Like a doctor's shift handoff sheet — different from CHANGELOG (which is backward-looking).
>
> **Read at:** session start. **Write at:** session end (or before stopping for the day).
>
> Companion files: [`CHANGELOG.md`](CHANGELOG.md), [`NEXT.md`](NEXT.md).

---

## Table of Contents
- [2026-07-04 — Current State (calculator live mode; branch ready to merge)](#2026-07-04--current-state-calculator-live-mode-branch-ready-to-merge)
- [Handoff Template (for future sessions)](#handoff-template-for-future-sessions)

---

## 2026-07-04 — Current State (calculator live mode; branch ready to merge)

### Where I am right now
- **Manual Trade Calculator is feature-complete on `trade-engine-v2`**: live
  "Real values" mode (public `POST /api/trade/evaluate` + `GET /api/trade/values`,
  server-authoritative — reuses `_fairness_v3`/universal pool) + "Demo league"
  mode (mock dual-board league with picks/arbitrage badges). Entry: Calculator
  pill on Trades. 8 endpoint tests; backend suite 252 green; mobile tsc clean.
- **Tiers refetch clobber fixed** (the 06-16 follow-up #1): `isFetching` dropped
  from the full-screen `loading` gate + dirty-guard on the auto-bucket effect.
- **Send in Sleeper slices 1–3 committed, flag OFF** (`trade.send_in_sleeper`).
  Slice 4 (calculator surface) deliberately deferred — needs in-league calc mode.
- **In-flight review done (2026-07-04):** everything intended is committed;
  working tree clean after this session's commits.

### What's half-done
- Nothing uncommitted. Open-by-design gaps: Sleeper slice 4 (above); staged
  backlog-#27 web calculator overlaps `/api/trade/*` — consolidate contracts
  when it lands; backend has no CORS (fine for native + same-origin web).

### What I was about to do next
1. **Deploy decision (operator):** merge `trade-engine-v2` → `main` (Render
   auto-deploys; branch carries the WHOLE July body of work incl. flag-OFF
   Send in Sleeper) + EAS build → TestFlight. Before the build: run
   `eas build:version:set` (marketing version still 1.0.0-era; NEXT.md #3) and
   note `react-native-webview` was added — the next build MUST be a full EAS
   build (native module), not an OTA update.
2. **Rotate `CRON_SECRET` in Render** (operator; launch-blocking; pasted in
   chat historically).
3. Set `SLEEPER_TOKEN_KEY` in Render before ever flipping `trade.send_in_sleeper`.

### What's blocking me
- Deploy shape + timing is the operator's call (whole-branch merge vs cherry-pick).

### Active environment state
- Branch `trade-engine-v2`, ~27 commits ahead of `main`; no open PRs expected
  (verify `gh pr list`). Backend: `python3 -m pytest backend/tests/ -q` → 252
  passing. Mobile: `cd mobile && npx tsc --noEmit` → clean. Web preview quirk:
  browser-origin API calls fail (no CORS) — verify live mode on-device, or via
  the stubbed-fetch technique in the 07-04 session transcript.
- TestFlight/EAS knowledge (ascAppId, no-space clone for local sim builds,
  Metro-from-clone recipe) unchanged from the 06-16 entry — key bits: EAS
  build+submit one-shot `cd mobile && npx eas-cli build --platform ios
  --profile production --auto-submit --non-interactive` (ascAppId 6771488431,
  team N5Y4N2Q49A, logged in as mattmurf77); spaces in repo path break local
  `expo run:ios` — use the no-space clone at `../ftf-test-clone`; feedback
  readback `GET /api/feedback/admin` with `X-Cron-Secret` from secrets.local.env.

---

## Handoff Template (for future sessions)

```markdown
## YYYY-MM-DD — Current State

### Where I am right now
- <one or two-bullet snapshot of project state>

### What's half-done
- <each in-flight item, with where the next person picks up>

### What I was about to do next
1. <ordered list, top is highest priority>

### What's blocking me
- <open questions / external waits / decisions pending>

### Active environment state
- <git status, data freshness, env vars, anything that affects "can I just run things">
```

Overwrite each day; do not let this file accumulate. (The history lives in [`CHANGELOG.md`](CHANGELOG.md).)
