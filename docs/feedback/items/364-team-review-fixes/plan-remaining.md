# Plan — the Team Review reports NOT built in this batch

**Date:** 2026-08-20 · **Status:** specced, unbuilt, awaiting operator direction
Operator selection this session: *"Confirmed defects now, plan the rest."* This file is the "rest".
Nothing here is started. Each section ends with the decision only the operator can make.

---

## 1. #365 — the window is age-only and calls an all-in team a rebuilder

> *"Window needs to do more than just age evaluation. I am all in for ffv3 league but it's
> identifying me as a rebuilder. We should look at signals such as number of 1sts owned vs traded
> away as one such signal."*

**Diagnosis (done — this part is not speculation).** `infer_team_outlook`
(`backend/trade_service.py:2546`) scores exactly three terms:

```
score = w_vet·vet_share − w_youth·youth_share − w_pick·(pick_share − equal_share)
```

with `vet_age = 27`, `youth_age = 26` (`trade_service.py:42-43`). Those two thresholds are
adjacent, so **every aged player is either "vet" or "youth"** — there is no middle band, and the
first two terms are close to a single re-scaled quantity. A team that is all-in *with a young core*
is therefore misread structurally, not marginally: youth share drags the score negative regardless
of intent. The third term is pick **value** share, which does move the right way when you trade
firsts away — but it is capped by `w_pick` and cannot outrun a young roster.

**The operator's signal is available.** Picks carry `original_owner` alongside the current owner
(`backend/server.py:10797`, `:25301`; the normalized shape at `:12425` is
`{round, season, roster_id(orig), owner_id(current), previous_owner_id}`). So both halves are
derivable per member without a new source:

- **firsts held** — current owner is me, round 1;
- **firsts sold** — `original_owner` is me, current owner is not.

The *net* (`sold − held`, or the ratio) is a far more direct intent signal than age: a manager who
has shipped three of his own firsts has declared a window in a way no birthday can.

**Why it is not in this batch — the bright line.** `infer_team_outlook` is not a Team Review
function. It feeds `outlook_alpha`, which the **trade engine** consumes
(`backend/trade_gen_v2.py:986`, `trade_service.py:4250`) and the mock draft reads
(`server.py:14013`). Changing the score changes every deck for every user. That is a scope block,
its own evidence, and its own TestFlight pass — not a follow-up commit.

**What this batch did instead**, so the misread is at least legible today: the window beat now
renders the whole model and states in plain words that it reads age and pick capital only — not
your record, your lineup, or the picks you already traded away. See `code-walk.md` §4.

**Decisions needed before building**
1. Does the new term **enter the score** (re-tuning `infer_contender_cut` / `infer_rebuilder_cut`
   against real leagues) or sit **beside it** as a tie-breaker only when the score lands in
   `not_sure`? The second is far cheaper to prove safe and cannot move existing decks.
2. Weight and cap for the net-firsts term.
3. Backfill: leagues whose pick history predates capture will have `original_owner == owner` for
   everything and read as "traded nothing". Degrade silently, or say so on the card?

---

## 2. #366 — a Handcuff tier, and the "elite" definition

> *"Need one other layer for the startable bodies: Elite, Starter, Replacement. For just RB we also
> should have 'Handcuff' which should simply be the RB2 on every team. And would like to review the
> logic for tagging a player as 'elite'."*

**Two separate asks. The second is the one that matters.**

`_bin_player` (`backend/trade_service.py:1906`) is three **absolute, position-blind** dynasty-value
cuts: `elite ≥ 4000`, `starter ≥ 1500`, `bench ≥ 500`. Consequences worth stating plainly:

- A TE and a RB clear "elite" at the same number, though their value distributions are nothing
  alike — so "elite" means something different at every position while presenting as one word.
- The bins are absolute, so **board-wide inflation silently promotes players** without anyone
  changing a threshold.
- `analyze_roster_strengths` only bins QB/RB/WR/TE (`trade_service.py:1930`), so in your IDP league
  every defensive player is invisible to the depth beat — the same blind spot #364 just made
  explicit on the outlook card.

**Handcuff needs a source FTF does not have.** "The RB2 on every team" is an NFL depth-chart fact,
not a value fact. No current feed carries it. Options: ingest a depth chart (new dependency, new
staleness surface, in-season churn), or approximate as "second-highest-valued RB on the same NFL
team" — cheap, no new source, and wrong in exactly the committee backfields where the label matters
most. **Recommend not approximating**; a Handcuff tag that is wrong on committee backfields is
worse than no tag.

**Recommended split:** re-tier first (position-relative cuts, `Elite / Starter / Replacement` naming
per the report), and treat Handcuff as its own item gated on a depth-chart decision.

**Decisions needed:** position-relative bands or keep absolute · rename `bench` → `Replacement`
across clients (a cross-client string, `docs/cross-client-invariants.md`) · buy/ingest a depth chart
or drop Handcuff.

---

## 3. #369 — the plan beat only shows the window

> *"The plan summary page only shows window.. it's a good page intent but needs more detail. I think
> we just show the full set of adjustments a user can make with the trade finder."*

> **BUILT 2026-08-20** — see [`docs/feedback/items/369-plan-beat/`](../369-plan-beat/)
> ([scope](../369-plan-beat/scope.md), [code-walk](../369-plan-beat/code-walk.md),
> [D-130 / D-131](../../../../living-memory/DECISIONS.md)). **The diagnosis below was
> incomplete**, and the correction matters more than the section did: the receipt design was
> only half the cause. `positions_set` could never be true, because the depth beat posted a
> positions-only body and `POST /api/league/preferences` **400s without `team_outlook`**
> (`backend/server.py:15788-15790`); `apiRequest` throws on non-2xx, so the `await` in
> `savePrefs` threw and `done.current.add('positions_set')` on the next line never ran — the
> catch swallowed it and no analytics fired. The window beat's body *does* carry
> `team_outlook`, so it alone succeeded. **That, not the receipt alone, is why the page showed
> only the window.** A third defect surfaced in the same trace: the partners beat never called
> `setHandoff`, so the scoped partner was recorded and then dropped and the plan beat's "I've
> already pointed the finder at it" was false. The decision below was also resolved the other
> way — see the note at the end of this section.

Correct as reported: `Plan` (`mobile/src/screens/TeamReviewScreen.tsx`) renders only what the user
*changed in this session* — `outlook` if `outlook_set` fired, positions if `positions_set` fired,
and the scoped partner. Skip a beat and it shows nothing for it.

The ask is a different page: not "what you just changed" but **"every lever the trade finder has,
and where you now stand on each"** — outlook, chase/shop positions, avoided positions
(`trade.avoid_positions`, built dark on `feat/jon-360-362`), scoped partner, trade intent mode.
That is a settings summary with edit affordances, and it wants the same source of truth as
`GET /api/league/preferences` rather than session-local state.

**Decision needed:** does the plan beat become a live preferences editor (read the saved prefs, edit
any of them in place), or stay a receipt and gain a "Review all trade settings" link into the
existing preferences surface? The second is much smaller and probably right.

> **Resolved — neither, exactly.** The operator's own words (*"we just show the full set of
> adjustments a user can make with the trade finder"*) rule out the receipt-plus-link, and a
> twelve-lever editor is not buildable without a second `asset_preferences` writer and a
> cross-screen state layer. Shipped as a **hybrid** ([D-131](../../../../living-memory/DECISIONS.md)):
> the three `league_preferences` levers are edited in place through the existing write path;
> the other nine are displayed with their current standing where readable and their home
> named. Also corrected: **`trade.avoid_positions` is not on `origin/main`** — it lives on
> `feat/jon-360-362` and nothing in `backend/` or `mobile/` references it, so the build took no
> dependency on it. The full verified lever inventory is in
> [`369-plan-beat/scope.md`](../369-plan-beat/scope.md) §0.1.

---

## 4. #367's second half — the consensus vs league-specific toggle

> *"Additionally I want a consensus vs league specific toggle on this page."*

**The inversion is fixed; this is the remaining half.** Today the comparison source is chosen *for*
the user by a ladder in `_divergence` (`backend/team_review.py`): league-community when ≥3
leaguemates have ranked (`compute_consensus_gap().has_baseline`), otherwise the universal consensus
seed. The payload already reports which one ran (`divergence.source`), and the screen already prints
it. So the data path for both modes exists — what is missing is letting the user pick.

**Shape:** a `divergence_source=auto|community|consensus` query param on
`GET /api/league/team-review`, defaulting to `auto` (today's ladder, so nothing changes for anyone
who does not touch it), plus a two-chip control on the beat. When `community` is asked for and the
baseline is absent, return the consensus rows **with the reason named** rather than an empty list.

**Not done here** because it adds an API parameter and a control — a contract change, outside
"confirmed defects". Small and well-understood; a good next item.

---

## 5. #371 — make the playoff outlook the primary decision driver

> *"Coming back to the outlook bug, we should primarily use the playoff outlook value as the
> decision maker."*

Reads as: stop inferring the window from roster shape and take it from the **simulated playoff
odds**, which are a genuine model rather than a heuristic.

**Real, and blocked on something specific.** The odds engine is **Sleeper-only** — ESPN, MFL and
Fleaflicker are registered as `NotImplemented` stubs (`backend/outlook/league_state.py`) — while
`infer_team_outlook` works on every platform because it only needs a roster. Making odds the
primary driver either strands non-Sleeper leagues with no window at all, or requires keeping the
heuristic as a fallback, in which case two different definitions of "contender" ship at once and
the trade engine reads whichever the league happened to qualify for.

There is also a **preseason** problem: `completed_weeks == 0` is the engine's weakest window
(preseason skill lower CI bound +2.9 %, [D-094](../../../../living-memory/DECISIONS.md)), and
preseason is exactly when window-setting matters most.

**Interacts with #365 and should be decided with it** — both propose replacing the same score.
Recommend sequencing: do #365's net-firsts term first (cheap, platform-neutral, no new dependency),
then reassess whether odds should override it where they exist.

---

## 6. #370 — repeat trades across sessions (different surface)

> *"Seems to be a bug in presenting trades across sessions. I keep getting the same trades I've
> already liked…"*

**Not a Team Review item** — TradesHome deck presentment. Logged here only so the batch does not
appear to have covered it. Likely neighbours: the dismiss-cooldown work
([D-067](../../../../living-memory/DECISIONS.md)) and NEXT.md's
*"exclude recently-traded"* / `feat/exclude-recently-traded` branch, which is about a related but
distinct exclusion. Wants its own repro against `deck_impressions` before anyone writes code —
specifically whether the liked trade is being re-served to the same *device* or the same *account*,
because those are different bugs.

---

## Suggested order

1. **#367 toggle** (§4) — smallest, and finishes an item already half-shipped.
2. **#370 repro** (§6) — a live user-facing complaint; find out what it actually is before it ages.
3. **#365 net-firsts** (§1) — highest value, needs the two decisions above first.
4. **#366 re-tier** (§2), Handcuff split out and gated on the depth-chart call.
5. **#369** (§3) once the preferences surface question is settled.
6. **#371** (§5) — decide alongside #365, not before it.
