# League format source — a league's own format governs its surfaces (D-268)

> Bug fix spec + scope block. Operator report: a one-QB league's League Summary
> read "Dynasty · SF TEP". Flag `league.format_from_league` (registered default
> false; **proposed shipped value true**, because this is a bug fix). Branch
> `fix/league-format-source`. Status: built, not merged.

## Contents

- [What was wrong](#what-was-wrong)
- [The rule](#the-rule)
- [The seam chosen](#the-seam-chosen)
- [Audit](#audit)
- [Ambiguous: left as they are](#ambiguous-left-as-they-are)
- [Rollout notes](#rollout-notes)
- [Follow-up (not fixed here)](#follow-up-not-fixed-here)
- [Scope block](#scope-block)

## What was wrong

Every league surface read the **session's** active ranking format
(`_active_format(sess)`, and the `sess["service"]` / `sess["trade_svc"]` aliases
`_require_session` selects from it), not the league's stored
`leagues.default_scoring`. The session format diverges from the league's three
ways: `session_init` carried the previous league's format into the next league
(priority body > carry-over > league default); the SF/1QB toggle on Tiers/Trios
sets it (`POST /api/scoring/switch`); the app sends a persisted
`X-Scoring-Format` header on some calls. So a one-QB league could be labelled
and valued on the superflex board: League Summary's caption, team values, the
trade deck (production holds `sf_tep` deck rows for a one-QB league), and so on.

## The rule

- **League surfaces** (anything answering "about this league") use the league's
  stored format: `leagues.default_scoring`, NULL ⇒ `1qb_ppr`, through one
  resolver. "Personal" bases use the caller's board **for the league's format**.
- **Ranking surfaces** (Tiers, Trios, rankings, reorder/save, progress, streak,
  trends, rank-set views) keep the toggle and header exactly as before.
- `session_init`: a carried-over format survives only a re-init of the **same**
  league. Its pre-built deck and owned-pick sync use the league's format.
- A league with **no `leagues` row** has no stored format to obey: it keeps the
  session format (never guess).

## The seam chosen

One resolver, applied once per request at the seam every league route already
passes through, instead of editing ~53 `_active_format(sess)` call sites.

- `database.get_league_scoring_if_known(league_id)` — the stored format, NULL ⇒
  `1qb_ppr`, `None` when there is no row.
- `server._league_format(league_id)` — THE resolver; never raises (a read error
  ⇒ `None` ⇒ the old format).
- `server._league_request_format(sess)` — flag on **and** the matched route
  rule starts with one of `_LEAGUE_FORMAT_PATH_PREFIXES`
  (`/api/league/`, `/api/leagues/`, `/api/trades`, `/api/overhauls`,
  `/api/win-now/`, `/api/projection-runs/`) ⇒ the league's format, where the
  league is the route's `<league_id>`, else `?league_id=`, else the session's.
- `_require_session` uses it as the request's effective format. Because the
  request view (`_RequestSession`) already derives `_active_format(sess)`,
  `sess["service"]`, `sess["trade_svc"]` and everything built from them
  (`_policy_context_from_session`, `_capture_trade_execution`, the installed
  overhaul / win-now / projections modules' `active_format(sess)`), every read
  inside a league request follows with no call-site edits. The view's
  `active_format` key is overridden too (view only), which covers the one raw
  `sess.get("active_format")` reader on a league route (`/api/league/picks`).
  The shared session is never written by a read.

Why a path-prefix list and not an endpoint allowlist: every format-reading route
under these prefixes is league-scoped (audit below), every ranking route lives
outside them, and a new league route added under them is covered by default.
The prefixes are matched against Flask's matched rule, not the raw URL.

Deck and page caches already key on `(user, league, format)`; with the request
format now the league's, a deck built on the other format can never be served
for the league's key (pinned by
`test_trade_generation_in_one_qb_league_uses_one_qb_board`). No stored rows are
deleted; the superflex rows for a one-QB league stay as history and are simply
never read for that league's key.

Mobile: the League Summary caption reads `scoring_format` from
`/api/league/power-rankings`, so the server change alone fixes it. The one app
change is the in-league calculator's **default** format, which read the
app-wide (toggle-held) format; it now defaults to the league's stored format
(`InLeagueCalculator.tsx`, same `['league-format', leagueId]` query RootNav
reads). Its chip override is unchanged.

## Audit

`_active_format(sess)`, `sess["service"]`, `sess["trade_svc"]`,
`_effective_format` and raw `sess.get("active_format")` reads on `origin/main`
(c8807cdd), grouped by the route that reaches them. "Follows" = the read now
resolves through the seam; nothing at that line changed.

### League-scoped — follow the league's format (flag on)

| Route(s) | Reads | Change |
|---|---|---|
| `/api/league/power-rankings`, `/api/league/rank-chip`, `/api/league/team-review` (via `_power_ranking_inputs`, `_outlook_impact_baseline`) | `_active_format`, `sess["service"]` | follows — **the reported bug** |
| `/api/league/outlook`, `/api/league/free-agents`, `/api/league/free-agents/move` | `_active_format`, `sess["service"]` | follows |
| `/api/league/preferences` GET, `/api/league/contrarian` (explicit `?format=` still wins), `/api/league/pick-assignments/order` | `_active_format` | follows |
| `/api/league/picks` | raw `sess.get("active_format")` | follows (view key override) |
| `/api/league/<league_id>/receipts`, `/api/league/season-projections` | via helpers | follows |
| `/api/trades/generate`, `/api/trades/asset-ideas`, `/api/trades/fair-packages`, `/api/trades`, `/api/trades/status`, `/api/trades/liked` | `_active_format`, `services/trade_svcs[fmt]`, `sess["trade_svc"]`, `_trade_current_only_state` | follows |
| `/api/trades/swipe`, `/api/trades/pass-reason` (`_bind_live_trade_pass`, `_apply_reasoned_pass_elo_only`), `/api/trades/flag`, `/api/trades/queue`, `/api/trades/matches/<id>/disposition` | `_active_format`, `sess["service"]`, `sess["trade_svc"]` | follows — trade signals land on the board the card was built on |
| `/api/trades/propose`, `-espn`, `-mfl` (`_record_shop_send_signal`, `_record_trade_proposal` → `_policy_context_from_session`) | `_active_format`, `_effective_format`, `sess["service"]` | follows |
| `/api/overhauls*` (`overhaul_api.generation_inputs`, `eligible_assets`, create) | injected `active_format(sess)`, services/trade_svcs | follows |
| `/api/win-now/*` (`win_now_api.actor`) | injected `active_format(sess)`, `sess["service"]` | follows |
| `/api/leagues/<id>/projection-runs*`, `/api/projection-runs/*` (Max PF `pricer`) | injected `active_format(sess)` | follows |
| `session_init` pre-built deck (`_trade_job_key`, `_trade_current_fingerprints`, `_kickoff_trade_job`) and `_sync_sleeper_owned_picks` | local `active_format` | **edited**: `league_format` |
| `session_init` format priority | `existing_sess["active_format"]` | **edited**: carry-over only for the same league |

Already league-sourced on main, unchanged: the weekly replenish
(`_replenish_deck_for` uses `get_league_scoring`), the prepared-deck cohort
(`prepared_trade_cohort` uses the league's stored format), `/api/extension/rankings`
(resolves `?league_id=` itself), `/api/league/summary` / `format-stats`.

### Ranking-scoped — keep the toggle and header (unchanged)

`/api/trio`, `/api/trio/skip`, `/api/rank3`, `/api/rankings`,
`/api/rankings/progress`, `/api/progress`, `/api/rankings/reorder`,
`/api/rankings/submit`, `/api/rankings/import-match`, `/api/rankings/import-apply`,
`/api/reset`, `/api/account/reset-rankings`, `/api/scoring/switch`,
`/api/tiers/save`, `/api/tiers/status`, `/api/tiers/community-diff`,
`/api/tiers/stability`, `/api/tiers/dismiss`, `/api/tiers/copy-from-format`,
`/api/anchor/save`, `/api/anchor/scale`, `/api/skips`,
`/api/trends/risers-fallers`, `/api/trends/contrarian`, `/api/me/streak`.

### Counts

Routes that read a session format, directly or through a helper, on main:

- **League-scoped: 24 routes in `server.py`** (9 under `/api/league/`, 15 under
  `/api/trades`) **plus three installed route groups** — `/api/overhauls*` (13
  routes, `overhaul_api`), `/api/win-now/*` + `/api/league/season-projections`
  (5, `win_now_api`), `/api/leagues/<id>/projection-runs*` + `/api/projection-runs/*`
  (`league_projections.api`) — and `session_init`'s pre-built deck and
  owned-pick sync.
- **Ranking-scoped: 25 routes** (listed above).
- **Ambiguous: 7** (below), left as they are.
- Neutral: `DELETE /api/account` (purges every format's card store) and
  `/api/extension/rankings` (already resolves the league's stored format).

By call site: 55 `_active_format(` matches in `server.py` on main — the
definition, **20 league-scoped calls** (plus the function passed by reference
into the three installed modules), **24 ranking-scoped**, **10 ambiguous**
(mock draft 4, draft board 2, player profile, consensus-gap, founder waterfall,
the `_run_trade_job` compatibility fallback). None was edited: the 20 resolve
through the seam.

## Ambiguous: left as they are

Conservative choice: these keep today's behaviour. Listed for the operator.

| Route | Why ambiguous |
|---|---|
| `POST /api/trade/evaluate` (in-league calculator, Mode B) | Format comes from the request **body**, set by the calculator's own SF/1QB chip, a deliberate what-if. Server untouched; the app's **default** for that chip is now the league's format (above). Forcing the league format server-side would make the chip a no-op in-league. |
| `GET /api/trends/consensus-gap` (`?league_id=`) | A trends (ranking) view that happens to scope sells/buys to a league roster. |
| `GET /api/players/<id>/profile` | A player view, not a league view; also used outside any league. |
| `GET /api/draft/board` | Rookie/draft board view on the caller's board. |
| `/api/mock-draft`, `/api/mock-draft/pick` | A mock draft stores its own `scoring_format` setting; only the fallback reads the session. |
| `/api/founder/rule-waterfall` | Founder diagnostic; measures a league with an explicit context. |
| `_run_trade_job` compatibility fallback (`execution_context is None`) | Internal/test callers only; every production kickoff passes an explicit format. |

## Rollout notes

- Flag on mid-session: a deck already in a session's other-format card store is
  no longer the one served; a swipe on a card from that older deck can miss the
  league-format store until the next generate. The app's device-held first page
  is keyed by the app's own format and can show a page fetched before the flip
  until its next refresh. Both are one-time and self-heal.
- League with NULL `default_scoring` that is really superflex (brand-new league
  before the session/init daemon's auto-detect writes it): league surfaces read
  one-QB until the detect lands. That is the same value `session_init` already
  used for a first league; the daemon fixes it on the first init.
- `GET /api/league/format-stats` answers `1qb_ppr` for a league with no row
  while the server keeps the session format there; only the calculator default
  reads it, and only rows-less leagues (none in steady state) differ.

## Follow-up (not fixed here)

- **One-QB + TE premium is stored as `sf_tep`.** The format has two buckets, so
  `_detect_scoring_format_from_meta` maps a one-QB league with TE premium to
  `sf_tep`, labelled "Superflex TE-Premium" / "SF TEP" and valued on the
  superflex board. None of the reporting operator's leagues is in that state.
  Fixing it needs a third bucket or a separate TEP axis — a valuation change,
  out of scope here.

## Scope block

Per `docs/templates/feature-scope.md`.

**1. Analytics scope** — waived: no new or changed events. Existing events that
carry `scoring_format` on league routes now carry the league's format (correct
data, same field).

**2. Schema & flag scope** — no schema change. New read helper
`get_league_scoring_if_known`. Flag `league.format_from_league`: `FLAG_KEYS`
default false; `config/features.json` **true** (bug fix; operator to confirm);
mirrored true in `backend/tests/fixtures/flags/{release,onboarding-v2,profiles-on}.json`;
not in `FTF_FLAGS`. Off ⇒ byte-identical to main (tests pin the off path).
Kill switch: set false + `POST /api/feature-flags/reload`.

**3. Evidence scope** — `backend/tests/test_league_format_source.py` (route-level
power rankings, request seam per surface, ranking toggle both ways, trade
generation + stale-deck cache, session/init league switch and same-league
re-init, flag-off paths), each sabotage-checked;
`mobile/tests/check-calc-league-format.js` (sabotage-checked). Manual
TestFlight checklist once the app build ships:
1. In a superflex league, open Tiers and toggle to SF; switch to a one-QB
   league; League Summary caption reads "Dynasty · 1QB PPR".
2. In that one-QB league, toggle Tiers to SF, then open League Summary: still
   1QB PPR; team values unchanged from before the toggle.
3. Find a Trade in the one-QB league after the toggle: QBs are not priced as
   superflex (a QB-for-RB swap that was "fair" on SF is not offered as fair).
4. Open the in-league calculator in the one-QB league with the app on SF: the
   format chip starts on 1QB; tapping SF still switches the calculator.
5. Tiers/Trios toggle still flips the ranking board both ways.

**4. Docs scope**

| Doc | Status |
|---|---|
| `docs/api-reference.md` | updated (format resolution for league routes) |
| `docs/config-reference.md` | updated (flag row) |
| `living-memory/LLD.md` | updated (convention: league surfaces resolve the league format) |
| `docs/architecture.md`, `living-memory/HLD.md` | n/a — no module wiring or architecture change; one resolver at the existing request seam |
| `docs/data-dictionary.md` | n/a — no schema change |
| `living-memory/DECISIONS.md` | D-268 |

**5. Ship gate** — CI (`pytest backend/tests`, `tsc --noEmit`, testid-lint).
`tsc` was not run by the builder (no `node_modules` in the worktree); CI must
run it. `FTF_SKIP_SIM_GATE=1` on push (D-056).
