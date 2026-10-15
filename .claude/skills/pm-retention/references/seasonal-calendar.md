# Seasonal re-engagement calendar — pm-retention

> A planning reference for the dynasty year: when users come back, why, which touches fit,
> and who owns them. It is not a schedule. Nothing here fires by itself. Any new seasonal
> touch is product code that ships through a PRD. Dates are approximate. Anything not cited
> to a repo source is marked **(assumption)**.

## Contents

- [What the code already knows about the calendar](#what-the-code-already-knows-about-the-calendar)
- [The calendar](#the-calendar)
- [Offseason rules](#offseason-rules)
- [Annual review (first week of July)](#annual-review-first-week-of-july)

---

## What the code already knows about the calendar

The repo-wide seasonality statement is in `docs/business/context.md:48-50`: interest ramps
July–August, peaks September–December, spikes at the rookie draft (late April–May) and NFL
trade deadlines, and troughs February–March.

The backend has almost no season awareness. Regenerate before relying on this list:

- `_in_rookie_draft_window()`: April 1 to September 15 UTC (`backend/server.py:19005-19022`).
  It is used **only** by the draft-status cache, and its comment says there is "no
  season-phase notion anywhere else in the backend" (`:18999-19001`).
- `season_start` fires on **August 25** each year, hard-coded (`server.py:24697`). It is in
  the re-engagement bucket, so it reaches only users who opted in.
- The weekly cadences are:
  - `weekly_digest` on Tuesday 09:00 local and `pending_review` on Wednesday 09:00 local
    (`server.py:24641`, `:24652`);
  - `deck_replenished` from Wednesday on, "post-waivers" (`replenish_weekday`,
    `server.py:23663-23670`);
  - the roster-snapshot sweep, weekly (`backend/roster_history.py`, ADR-011).
- The rookie class shows up in Sleeper's player dump around late April. The daily tick
  logs its arrival (`server.py:24843-24849`).
- Per-league dates are partly readable. Sleeper league settings carry `trade_deadline` (a
  week number) and `playoff_week_start`, defaulting to 15 when absent. Today only the
  win-now service reads them (`backend/win_now_service.py:152`, `:193`). ESPN and MFL
  equivalents are **unverified**.

Home has no seasonal states. It shows the same tiles all year (D-202, `components.md:123-125`).
Every "Home hub state" entry below is therefore a **candidate**, not current behavior.

## The calendar

Each moment below gives its dates, why users come back, what fits, the Home hub candidate,
when the work must be on TestFlight, which tick would fire it, and who owns it. Tick names
are the three in `render.yaml:41-71`. "New" means no tick has that logic today.

**Rookie draft window**
- **When:** late April to May (`context.md:49`). The backend window is wider, April 1 to
  September 15 (`server.py:19005`).
- **Why they come back:** the rookie class arrives, rookie ranks reset, and draft-pick
  trades happen.
- **Fits:** a rookie-class-loaded touch (new); `deck_replenished` keeps its weekly
  cadence.
- **Home hub candidate:** foreground rookie ranks and the Draft Room.
- **Ready on TestFlight by:** about April 10 (assumption: one release cycle).
- **Fires from:** daily-tick (the class-load monitor already lives there).
- **Owner:** `engagement-pm` for the touch; the Draft Room's owning lead for the landing.

**June lull (assumption)**
- **When:** June.
- **Why they come back:** rookie drafts are finishing and attention is low.
- **Fits:** no new pushes. Rely on the inbox and the existing weekly kinds.
- **Home hub candidate:** none.
- **Ready by:** —
- **Fires from:** —
- **Owner:** `engagement-pm`.

**July–August ramp**
- **When:** July to August (`context.md:48`).
- **Why they come back:** startup drafts, training camp, and re-ranking for the new season.
- **Fits:** `season_start` (August 25), `finish_ranking` for new signups, and new-league
  sync touches.
- **Home hub candidate:** foreground "Rank players" and "Find a trade".
- **Ready by:** about July 1, after the annual review below.
- **Fires from:** daily-tick.
- **Owner:** `engagement-pm`; `onboarding-pm` owns the first-run surfaces.

**In-season weekly rhythm**
- **When:** September to December (`context.md:49`).
- **Why they come back:** waivers (often Tuesday or Wednesday, depending on the platform),
  lineups (Sunday), injuries and value swings (assumption: platform and league specific).
- **Fits:**
  - `weekly_digest` (Tuesday), `pending_review` (Wednesday), `deck_replenished`
    (Wednesday on);
  - match kinds as they happen;
  - the value-movers digest (#33, a candidate cited in the year-in-review plan §8).
- **Home hub candidate:** keep the live position tiles; consider a "this week" tile.
- **Ready by:** August 25.
- **Fires from:** hourly-tick (digest, review) and daily-tick (deck).
- **Owner:** `engagement-pm`.

**NFL trade deadline and league trade deadlines**
- **When:** NFL: early November (assumption; check the NFL calendar each year). Leagues:
  their own week (Sleeper `trade_deadline`).
- **Why they come back:** last call to buy or sell before rosters freeze.
- **Fits:** a deadline-countdown touch (new). It is per-league, so it needs per-platform
  deadline data first.
- **Home hub candidate:** a deadline banner or tile on leagues near their deadline.
- **Ready by:** about October 15.
- **Fires from:** daily-tick (new).
- **Owner:** `engagement-pm`. Data feasibility is `engagement-eng`'s, via `head-eng`.

**Fantasy playoffs and championship**
- **When:** December. Playoffs usually start around NFL Week 15 (Sleeper's default
  `playoff_week_start`); the championship is often Week 17 (assumption).
- **Why they come back:** contenders chase lineups; eliminated teams turn to next year.
- **Fits:** for eliminated teams, an offseason-trade or rebuild touch (new). Contenders
  get no trade nudges, because most leagues lock trades.
- **Home hub candidate:** Contender versus Rebuilding framing (the follow-up F3 chip in
  `docs/plans/home-engagement/scope.md` §0).
- **Ready by:** about December 1.
- **Fires from:** daily-tick (new).
- **Owner:** `engagement-pm`; `trades-pm` for the trade landing.

**Year-in-review recap window**
- **When:** late December to early January (plan §7 `:318`, §8 Phase 4).
- **Why they come back:** the season artifact. Users share it, argue about it, and it
  opens the offseason trading window.
- **Fits:** a recap-ready touch plus an inbox row (new).
- **Home hub candidate:** a recap tile for the window, then gone.
- **Ready by:** recap compute and UI in November–December (plan §8).
- **Fires from:** daily-tick or request path (new).
- **Owner:** `engagement-pm` (the touch and its timing) and `growth-pm` (share and invite
  mechanics); `models-lead` if Receipts grades feed it.

**February–March trough**
- **When:** February to March (`context.md:50`).
- **Why they come back:** offseason trading, and the recap as "a bridge into the
  rookie-draft ramp" (plan §7, `:323`).
- **Fits:** value-led touches only, such as consensus movers or a quiet inbox. **No guilt
  streaks** (see below).
- **Home hub candidate:** offseason trade tiles.
- **Ready by:** about January 15.
- **Fires from:** existing ticks only.
- **Owner:** `engagement-pm`.

**Year in review: the state at `678834ab`.**
- **Capture is live.** It is behind `market.roster_history: true`
  (`config/features.json:63`), and the module is `backend/roster_history.py` (ADR-011,
  `docs/adr/adr-011-league-state-history-is-append-only.md`). The plan's deadline was
  capture before Week 1 (`docs/business/product/2026-08-13-dynasty-year-in-review-plan.md`
  §1, §8 Phase 0).
- **The recap is not built.** No recap screen exists under `mobile/src/screens/`. The plan
  phases it as fetchers October–November, compute and UI November–December, ship late
  December (§8).
- **`backend/wrapped_collector.py` is frozen legacy analytics, not the recap pipeline.**
  `docs/architecture.md:603` says `wrapped_events` receives zero writes. Never spec the
  recap against it.
- **The plan README's status line is stale for capture.**
  `docs/plans/dynasty-year-in-review/README.md:3` still says "Not built", but capture is
  live. Trust the flag and the module.

## Offseason rules

- **No guilt mechanics.** No streaks, "you've been away" counts or loss-framed copy in
  February–March. A dynasty manager who ignores the app in March is behaving normally, not
  churning.
- **Every offseason touch carries real new value:** the rookie class landed, a value moved,
  the recap is ready. `winback_dormant` already requires unread matches under
  `notif.honest_winbacks` (`server.py:24732-24747`). Hold new kinds to the same bar.
- **Respect the re-engagement default.** Offseason touches are re-engagement by nature, so
  under `notif.reengagement_default_off` they reach only opted-in users. The inbox and Home
  reach everyone who opens the app. Plan the inbox first and push second.
- **Spend the cap budget where attention is.** One great push in the rookie window beats
  four in February.

## Annual review (first week of July)

Do this once a year, before the ramp, and write it up as a memo in
`docs/business/product/`:

1. **Re-date every moment for the coming season.** Get the NFL schedule, the trade
   deadline, the playoff weeks and the rookie-draft dates. Replace the assumptions above
   with dated facts and cite them.
2. **Regenerate the notification inventory** (`notifications.md` §1). Confirm
   `season_start` is still August 25 and still the right date.
3. **Run the health check** (`notifications.md` §3) for all three ticks. A dead tick
   voids every moment that depends on it.
4. **Ask `analytics-lead`, via `head-product`, for last season's per-moment numbers:**
   sends, opt-in reach and the return proxy. Label any answer that comes back dark.
5. **Pick at most 2–3 new seasonal touches** for the year, each with a PRD and a "ready on
   TestFlight by" date taken from the calendar above.
6. **Propose an update to this file** through `head-product` if a moment, owner or tick
   changed.
