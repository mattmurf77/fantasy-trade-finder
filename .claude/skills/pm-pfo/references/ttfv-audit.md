# TTFV audit — PFO Half A procedure

> Owner: `onboarding-pm`. Called from [../SKILL.md](../SKILL.md). Evidence follows
> [D-056](../../../../living-memory/DECISIONS.md): a code-walk, counts that
> `analytics-lead` returns, and an operator TestFlight checklist. No simulator, no
> Maestro, no screenshots, no `screens/` captures, and no prod reads by the PM.
> Citations marked "at `678834ab`" are a starting point only; re-derive them at your sha.

## The clock

- **Start:** the first cold app open on a fresh install — `app_opened {launch_type:'cold'}`
  (`mobile/App.tsx:136`), device-scoped and stitched to the user through `identity_links`.
- **Stop:** the first suggestion card renders — the user's first `trade_card_viewed`
  (`mobile/src/screens/TradesScreen.tsx:4279`). Card 0 also carries `ms_since_open` and
  `cold_start` (`:4275-4277`); `ms_since_open` counts from this JS bundle's load
  (`mobile/src/api/events.ts:108`), so it equals the whole clock only when sign-in and the
  first card happen in one cold session.
- **Stages** (each a row in every table below): open → sign-in started → signed in →
  league chosen → league session ready → first-deck request → deck generated → first card
  rendered.
- **The first-deck wait** (request → generated → rendered) is one stage of this clock and
  `trades-pm`'s number. Record it; route a slow one to `trades-pm`; don't tune it.
- **Comparability:** the 2026-07-17 spec's TTFV was `signin_succeeded` → first
  `trades_generated` with `count>0` (server). Report that span too until `head-product`
  retires it, and say why the two differ (the open → sign-in stage, and render vs
  generate).

## (a) Enumerate sign-in outcomes from code, not memory

Re-derive the list every run. Read, at the audit sha:
- `mobile/src/screens/SignInScreen.tsx`, `LeaguePickerScreen.tsx`, `LeagueJoinScreen.tsx`;
- `mobile/src/api/auth.ts`, `api/platformEntry.ts`, `state/useSession.ts`,
  `state/useOnboardingState.ts`, `utils/firstSessionMoment.ts`, `navigation/RootNav.tsx`
  (and `navigation/TabNav.tsx` for the launch tab), `utils/deepLinks.ts`;
- the `/api/auth/*`, `/api/session/*`, `/api/entry/*` and `/api/account*` routes in
  `backend/server.py` (`grep -n '@app.route("/api/(auth|session|entry|account)'`);
- the `onboarding.*`, `landing.*`, `auth.*`, `account.*`, `espn.*`, `mfl.*` flags in
  `config/features.json`, plus whatever routing flags the walk runs into. Note which
  flags are **not** in the app's baked defaults (`mobile/src/state/useFeatureFlags.ts`):
  on a fresh install they read false until `GET /api/feature-flags` returns.

For each entry control on the sign-in screen and each way in from outside (deep link, web),
fill one row. Drop an outcome only with a cite showing it is dead.

| Outcome | Entry control (file:line) | Flags (value at sha) | Handler → endpoint | Lands on | Live? (cite) |
|---|---|---|---|---|---|

Seed at `678834ab` (verify every row; expect drift):
- **Live:** Sleeper username (`SignInScreen.tsx:385-524`, incl. the saved-username
  "Continue as" variant); ESPN via the platform chip (`SignInScreen.tsx:119-126`, entry mint
  `api/platformEntry.ts:131-169`); MFL via the chip, by league ID or "Sign in with MFL";
  Apple, new identity (`account_only`, `SignInScreen.tsx:296-383`) — lands on the picker's "Connect a
  League" state with no deck until a league is linked; Apple, returning (bound to
  Sleeper); invitee — an overlay on the doors above via the legacy `?league=&ref=` link,
  since `growth.invite_join_link` is false (`LeagueJoinScreen` is live but nothing builds
  its link form); web landing — a separate funnel that needs the browser extension for
  Sleeper and requires ranking before trades.
- **Dead:** demo (`landing.try_before_sync` false; `/api/session/demo` 404s,
  `backend/server.py:26792-26793`); Google (`/api/auth/google` 503s without
  `GOOGLE_OAUTH_CLIENT_ID`, `:27701-27704`, and has no client caller); email (no route;
  `auth.email_capture` only stores Apple's email claim); Fleaflicker (`fleaflicker.link`
  false).

## (b) Code-walk each outcome to the first suggestion rendered

One table per live outcome, plus its flag-off path:

| # | Screen | User action (taps / typed fields) | Blocking wait (endpoint; spinner or copy) | Flag gate (flag = value at sha) | Branch condition | file:line |
|---|---|---|---|---|---|---|

**Totals per outcome:** screens, taps, typed fields, blocking waits, flag gates.

Walk it to the card, not to the tab. Things to look for at every step:
- where routing goes after auth (`RootNav.tsx:452-457` initial route; the launch tab in
  `TabNav.tsx` — at `678834ab` a new user lands on Trades only while `firstSwipeDone` is
  false, `:733-739`);
- whether the first deck needs a tap. At `678834ab` it does: with `calc.inline_home` and
  `calc.results_push` on, the Trades landing hosts the calculator canvas and retires the
  landing deck (`TradesScreen.tsx:6127-6133`), the first-run auto-start is suppressed
  (`:2392`), and the user must tap **Find a Trade** (`InLeagueCalculator.tsx:1315`);
- whether ranking is required before the first deck (mobile: no gate at `678834ab`; web:
  yes);
- pre-generated decks: `/api/session/init` kicks off a trade job
  (`server.py:22986-23041`) that a later generate may reuse (`:14790`);
- anything that can interrupt before card 1: prompts, tour beats
  ([tour-beats.md](tour-beats.md)), sheets — and its flag;
- **the flag-off path:** what the same outcome does with `onboarding.v2`,
  `onboarding.landing`, `onboarding.trades_first` and `onboarding.league_autoskip` off,
  and in the fresh-install window before flags load.

## (c) Funnel query spec for `analytics-lead`

You write the spec; `analytics-lead` runs it and returns the numbers. Never run a prod
read yourself.

**Ordered events** (verify every name in `backend/analytics_taxonomy.py` at your sha):

| Stage | Event | Emitter at `678834ab` |
|---|---|---|
| Open | `app_opened {launch_type:'cold'}` | `mobile/App.tsx:136` |
| Sign-in started | `signin_attempted {method}` | `SignInScreen.tsx:305`, `:399`; `platformEntry.ts:137` |
| Signed in / failed | `signin_succeeded {method}` / `signin_failed {method, error_code}` | `SignInScreen.tsx:348`, `:366`, `:495`; `platformEntry.ts:159`, `:162` |
| League chosen | `league_selected {auto, league_count, …}` (fires before session init) | `LeaguePickerScreen.tsx:414-432` |
| League session ready | server `app_open` / `signup`, `league_synced` | `server.py:22619-22646` |
| First-deck request | `calc_find_a_trade_tapped`, then `find_trades_tapped {source}` | `utils/canvasSearch.ts:52-61`; `TradesScreen.tsx:3329-3336` |
| Deck generated | server `trades_generated {count, gen_ms, engine_version, lanes, deck_source?}` | `server.py:9203-9240` |
| First card rendered | `trade_card_viewed` (card 0: `ms_since_open`, `cold_start`) | `TradesScreen.tsx:4279` |

**Cohort:** users whose first-ever `signin_succeeded` (identity-resolved) falls in the
window. Exclude `qa_*`, `test_user_fp_*`, `demo_*` and the tester device allowlist — the
rules in `analytics_queries.device_exclusion` (`backend/analytics_queries.py:473`).
State the window, and use `client_ts` for intervals between client events
(`occurred_at` is server receive time; `backend/database.py:2145`, `:2157`).

**Outputs:**
- step counts per stage, as counts and a cohort table — not bare rates at beta scale;
- median and p75 time between consecutive stages, and TTFV, split by sign-in outcome
  (`signin_succeeded.method`), `platform` and `app_version`;
- **empty-deck rate**, with its exact definition from real events. At `678834ab` no
  single event says "this user's first deck was empty"; ask for both and their overlap:
  (1) server — the user's first completed `trades_generated` for the league, excluding
  `deck_source` (replenish) rows, with `count = 0`; (2) client — a `find_trades_tapped`
  with no `trade_card_viewed` in the same `session_id`. Label the result approximate.
  The bar is <5% ([D-055](../../../../living-memory/DECISIONS.md));
- the return cites the query text, the source (database, read-only engine) and the time
  it ran.

**GAPs** — any stage with no event becomes a registration request to `analytics-lead`
(a grant, then registration plus `NON_INTENT_EVENTS` classification in the emitter's
commit). Known at `678834ab` — re-check each:
- no client event marks "league session ready" or its failure (the picker's 90 s attempt,
  `mobile/src/state/leagueSession.ts:5`);
- `signup` may never fire for new mobile users: every sign-in route creates the user row
  before `/api/session/init` checks `user_exists` (`server.py:22592-22594`). Don't define
  the cohort on `signup` until `analytics-lead` confirms;
- `demo_entered` has no emitter, though `device_exclusion` relies on it;
- `trades_generated` can't tell a pre-generated job from a tapped one, and carries no
  first-deck marker; `deck_exhausted_viewed` never fires on a zero-card deck;
- the web funnel has no `league_selected` or `trade_card_viewed`;
- `report_pfo` (`analytics_queries.py:957`) hard-codes TTFV as dark — don't read its
  cells as data.

## (d) Operator TestFlight timing checklist

The only runtime evidence mobile gets. Write it for the operator; `release-lead` logs the
outcome.

**Inputs:** build number; first-run device state (fresh install — app deleted, signed
out, no prior account on that device, no saved Sleeper username); one test account or
league per live platform; the flag values the run assumes, pinned (and how to confirm
them: `GET /api/feature-flags`).

**Per outcome**, numbered steps:
```
Outcome: <name>   Build: <n>   Flags pinned: <list>
1. Cold-launch the app.                 ⏱ START
2. <screen>: <exact action>. Expect: <exact result>.        ⏱ split: signed in
3. <screen>: <exact action>. Expect: <exact result>.        ⏱ split: league chosen
…  (one step per code-walk row; splits at the same stage boundaries as (b))
n. First trade card is on screen.       ⏱ STOP
Record: wall-clock per stage · total · empty deck yes/no · anything that interrupted
```
Run each outcome at least twice (warm and cold server) and note which. Stopwatch splits
must match the code-walk's stage boundaries, so the timing and the walk line up row by
row.

**TEST_LEDGER outcome line** (logged by `release-lead` in
`living-memory/TEST_LEDGER.md`):
`PFO Half A timing, build <n>: <outcome> <total>s (<stage splits>), empty deck <y/n>; …
— operator-timed, <date>`.

## (e) Grade and write

1. Grade each stage per outcome **works / friction / broken**, each with its evidence.
2. Label every number: *measured* (operator-timed, or an `analytics-lead` query — cite
   it), *code-derived*, *benchmarked* (cite; e.g.
   `docs/research/onboarding/round-2/r2-1b-first-session-mechanics.md` for the 60–90 s
   first-value budget, with its caveats), or *assumed*.
3. Diff against the last Half A audit: outcomes added or dropped, steps added or removed,
   stage times moved.
4. Rank friction by damage to first-run success (how many new users it touches × how
   likely it ends the session).
5. Give the smallest fix for each, then route it ([../SKILL.md](../SKILL.md) § Handoffs):
   a fix needs a scope block; an event gap goes to `analytics-lead`; a first-deck wait or
   an empty or insulting first card goes to `trades-pm`.
