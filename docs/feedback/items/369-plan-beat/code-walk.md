# Code-walk proof — #369, the plan beat

**Date:** 2026-08-20 · **Scope block:** [`scope.md`](scope.md)
Base: `origin/main` @ `bc43b6f`. Every line reference is to the post-change file
unless it says `HEAD:`.

Under D-056 this document, plus `mobile/tests/check-team-review.js`, is the
evidence for behaviour a simulator would once have shown.

---

## Table of contents

- [1. The reported symptom has two causes, not one](#1-the-reported-symptom-has-two-causes-not-one)
- [2. Cause A — the positions write has never once succeeded](#2-cause-a--the-positions-write-has-never-once-succeeded)
- [3. Cause B — the receipt design](#3-cause-b--the-receipt-design)
- [4. The third defect found on the way — the scoped partner was inert](#4-the-third-defect-found-on-the-way--the-scoped-partner-was-inert)
- [5. What the beat renders now, trace by trace](#5-what-the-beat-renders-now-trace-by-trace)
- [6. Sabotage table](#6-sabotage-table)
- [7. What is NOT covered by a static check](#7-what-is-not-covered-by-a-static-check)

---

## 1. The reported symptom has two causes, not one

> *"The plan summary page only shows window."*

`docs/feedback/items/364-team-review-fixes/plan-remaining.md` §3 attributes this
to the receipt design alone: *"renders only what the user changed in this
session… skip a beat and it shows nothing for it."* That is true and it is half
the story. The other half is that one of the three things it could recap was
**structurally unreachable**. Both are fixed below.

## 2. Cause A — the positions write has never once succeeded

The write path, as shipped:

1. Depth-beat footer posts a positions-only body —
   `HEAD:mobile/src/screens/TeamReviewScreen.tsx` (the `positions_set` `onPress`):

   ```tsx
   await savePrefs({
     acquire_positions: acquire.length ? acquire : data.depth.acquire_positions,
     trade_away_positions: shed.length ? shed : data.depth.trade_away_positions,
   }, 'positions_set');
   ```

   No `team_outlook`.

2. `saveLeaguePreferences` forwards the object verbatim —
   `mobile/src/api/league.ts:54-59`: `api.post('/api/league/preferences', { league_id: leagueId, ...prefs })`.

3. The route rejects it — `backend/server.py:15788-15790`:

   ```python
   valid = {"championship", "contender", "rebuilder", "jets", "not_sure"}
   if not outlook or outlook not in valid:
       return jsonify({"error": f"team_outlook must be one of {sorted(valid)}"}), 400
   ```

   `outlook = body.get("team_outlook")` (`server.py:15783`) is `None`, so this is
   a **400 on every call**, for every user, since the feature shipped.

4. The client turns a non-2xx into a throw — `mobile/src/api/client.ts:552-553`:
   `const apiErr = new ApiError(res!.status, parsed, msg); … throw apiErr`.

5. So in `savePrefs` the `await` throws, and the **next two lines never run** —
   `HEAD:TeamReviewScreen.tsx`:

   ```tsx
   await saveLeaguePreferences(leagueId, patch as any);
   done.current.add(action);                          // ← never reached
   emit('team_review_action_taken', { beat, action }); // ← never reached
   ```

   The `catch {}` is empty by design ("a failed write surfaces nothing"), so the
   failure is invisible to the user *and* to analytics.

6. The plan beat then asked `done.current.has('positions_set')` — permanently
   false — and rendered no Chasing/Shopping rows. The window rows *did* render,
   because that beat's payload includes `team_outlook` and therefore returns 200.

**That is the exact mechanism behind "only shows window."**

**Fix**, at the single write site rather than at one caller —
`TeamReviewScreen.tsx:163-168`:

```tsx
const fallbackOutlook: OutlookOption =
  outlook ?? data?.window.declared ?? data?.window.inferred ?? 'not_sure';
await saveLeaguePreferences(
  leagueId, { team_outlook: fallbackOutlook, ...patch } as any,
);
```

Ordering is load-bearing: `...patch` spreads **after** the backfill, so a caller
that does supply `team_outlook` (the window beat, and the plan beat's own outlook
chips) still wins. Repairing it in `savePrefs` rather than in the depth footer
keeps the change out of the `Depth` component and its footer, which another
agent owns this session, and fixes every present and future caller at once.

`savePrefs` now also returns whether the write landed
(`TeamReviewScreen.tsx:148-183`) — the window and depth beats ignore the result
and advance as before, the plan beat uses it for the inline failure line that
`lld-delta.md` §4 always specified ("the beat surfaces the failure inline and the
flow continues") but that was never implemented.

**Second-order effect worth stating:** `team_review_action_taken{action:'positions_set'}`
has never been emitted in production. This series starts producing data on the
next client release; do not read its history as a baseline.

## 3. Cause B — the receipt design

The operator did not ask for a better receipt. He asked for
*"the full set of adjustments a user can make with the trade finder"* — a
different page: a standing summary of every lever with the user's current
position on each. `plan-remaining.md` §3 poses it as an either/or (live editor
vs. receipt-plus-link) and guesses the link is "probably right"; the operator's
own words settle it the other way, and the parent's direction confirmed it.

The beat is therefore rebuilt around **saved state**, not session state
(`TeamReviewScreen.tsx:734-963`). Its data sources:

| Lever | Read from | Line |
|---|---|---|
| Window / Chasing / Shopping | `GET /api/league/preferences`, key `['league-prefs', leagueId]`, `refetchOnMount:'always'` | `:756-762` |
| Untouchable / Target / Not interested | `GET /api/league/asset-prefs`, key `['asset-prefs', leagueId]` | `:763-768` |
| Trade fairness | `AsyncStorage[FAIRNESS_PREF_KEY]` via `fairnessOnFromPref` (`api/tradePregen.ts:24,45`) | `:771-780` |
| Pinned specific players | `useFinderTargets` zustand store | `:748-749` |
| Scoped partner | the flow's own partners-beat selection | prop |
| Trade idea / Focus | **not readable** — `TradesScreen` `useState` (`:512`, `:506`). Named, with their home, and no value claimed | `:944-949` |

`refetchOnMount: 'always'` is not incidental. The team-review payload is fetched
once at screen mount with `staleTime: 60_000` (`TeamReviewScreen.tsx:118-123`),
so `data.depth.acquire_positions` is a snapshot taken **before** this session's
own writes. Reading it here would have reproduced the bug in a new shape — the
page would show what was saved when you opened the screen, not what is saved
now. Guard assertion 6 pins both halves.

The query key `['league-prefs', leagueId]` is deliberately the one
`TradeDnaSheet.tsx:250` already uses, so the two surfaces share one cache entry
and one invalidation rather than drifting.

**Editing** reuses the existing path exactly. Every chip tap posts the full
triple (`TeamReviewScreen.tsx:798-812`) — last-write-wins, the same autosave
contract Trade DNA adopted in #236 — through the same `savePrefs`, therefore the
same `POST /api/league/preferences`. No new route, no partial-update semantics,
and a positions edit can never again be missing `team_outlook`.

`PLAN_POSITIONS` (`:89`) is `QB RB WR TE PICK`, wider than the depth beat's
`CORE` (`:78`). `PICK` is a real value in these arrays — `TradeDnaSheet.tsx`'s
`DNA_POSITIONS` offers it and the route accepts it (`server.py:15794-15798`
validates array-ness only). A page that claims to show every lever cannot drop
one; the depth beat correctly stays on `CORE` because it is talking about
startable bodies.

## 4. The third defect found on the way — the scoped partner was inert

`lld-delta.md` §4 specifies partner scoping as
`setHandoff({opponent, autoRun: true})` on the #330 store. The shipped
`Partners` `onScope` (`HEAD:TeamReviewScreen.tsx`) only did:

```tsx
setScoped({ id, name });
done.current.add('partner_scoped');
emit('team_review_action_taken', { beat, action: 'partner_scoped' });
```

`git grep setHandoff` finds exactly one producer — `LeagueSummaryScreen.tsx:1193`
— and one consumer, `TradesScreen.tsx:2382-2393`. Team Review was never wired.
So the plan beat's *"I've already pointed the finder at it"* was false and the
"Scoped to" row was decoration: the user exited to a completely unscoped deck.

Fixed in the plan beat's own footer action (`TeamReviewScreen.tsx:309-315`),
which is the surface that makes the claim:

```tsx
if (scoped) {
  useFinderTargets.getState().setHandoff({
    opponent: { userId: scoped.id, name: scoped.name },
    autoRun: true,
  });
}
```

Then `nav.navigate('TradesHome')` focuses the deck, whose focus-gated effect
consumes the handoff once (`TradesScreen.tsx:2384-2392`), adopts the opponent
into `sheetOpponent`, and lets the existing choke point dispatch the search. This
is byte-identical to what the Offer/Target row already does; nothing new is
invented and nothing fires when the user never scoped anyone.

**Known cosmetic consequence, deliberately not chased:** the auto-run emits
`find_trades_tapped{source:'league_offer'}` (`TradesScreen.tsx:2408`), so a
Team-Review-originated auto-run will be attributed to `league_offer`. Correcting
it means adding a source to the handoff shape and editing `TradesScreen.tsx`,
which this agent does not own. Flagged for the integrator.

## 5. What the beat renders now, trace by trace

Three cards, `TeamReviewScreen.tsx:822-957`:

1. **`team-review.plan.levers`** (`:824`) — "What the finder uses · change any of
   it here". Window chips from `data.window.options` (`:832`), Chasing and
   Shopping chips from `PLAN_POSITIONS`. Selection state comes from `draft`,
   seeded from the saved prefs at `:788-795` and reseeded after every successful
   save via the invalidation at `:811`. While the query is in flight the card
   says "Reading your saved settings…" (`:827`) rather than rendering an empty
   selection that would read as "nothing set".
   Inline failure line at `:902`, shown only when a write actually failed.
2. **`team-review.plan.assets`** (`:911`) — the three player rules, as counts,
   behind `useFlag('trade.preference_lists')` (`:745`) so a dark lever is never
   advertised. Counts route through `countLabel` (`:965`), which returns `—` for
   *not loaded* and `None` for *loaded and zero* — the same "null is not zero"
   rule the standing beat applies to a missing PPG.
3. **`team-review.plan.search`** (`:931`) — trade partner, fairness, trade idea
   (behind `useFlag('trades.intent_modes')`), focus, pinned players; then one
   fine line stating which of these persist and which reset.

Chalkline compliance: no new component is introduced. Cards, chips, `Row` and the
kicker are the screen's existing styles; the two additions (`:1033-1034`) are a
label style and an error colour, both from the token set. No emoji, no gradient,
no blur; `radii.sm` on chips, `radii.md` on cards; ice only on the selected-chip
border and the CTA; `semantic.neg` on the failure line is the specced status
colour, not an accent.

`FeedbackFAB`: still absent (guard assertion 2 — green after the change).

## 6. Sabotage table

Every new or rewritten assertion was broken, the guard confirmed red on the
*expected* assertion, then restored and confirmed green. Harness output, 9/9:

| # | Sabotage | Result |
|---|---|---|
| 5b | render `{o.playoff_pct}` as visible text on the standing card | RED on 5b · restored green |
| 6 | source the plan chips from `data.depth.acquire_positions` (the stale snapshot) | RED on 6 · restored green |
| 6b | drop `refetchOnMount: 'always'` so the beat may show a stale cache entry | RED on 6 · restored green |
| 7 | gate a plan-beat lever on `done.current` again | RED on 7 · restored green |
| 8 | rename the "Trade fairness" lever off the page | RED on 8 · restored green |
| 9 | add a second `asset_preferences` writer to the screen | RED on 9 · restored green |
| 10 | remove the `team_outlook` backfill (i.e. reinstate the shipped bug) | RED on 10 · restored green |
| 11a | stop handing the scoped partner to the #330 store | RED on 11 · restored green |
| 11b | remove the deck-side handoff consumption in `TradesScreen.tsx` | RED on 11 · restored green |

### 6.1 An existing assertion this change would have hollowed out

Assertion **5b** read, before today:

```js
if (/\{[^}]*\bplayoff_pct\b[^}]*\}/.test(s) && !/accessibilityLabel/.test(s))
```

The second clause is a **whole-file** escape hatch. `TeamReviewScreen.tsx` at
`HEAD` contained zero occurrences of `accessibilityLabel` (`git show
HEAD:… | grep -c accessibilityLabel` → `0`), which is the only reason the clause
held. The plan beat's chips add three, so from this commit onward the condition
could never be true and **5b would have kept passing while proving nothing** —
precisely the vacuous-test failure mode the batch before this one hit.

It is now per-occurrence: every line mentioning `playoff_pct` must itself be an
accessibility label. Sabotage 5b is the proof that the rewrite has teeth; the
same sabotage against the old form passes silently.

The other five pre-existing assertions were re-read rather than assumed:
1 (registration) and 3 (mode bar) touch files this change does not open;
2 (no `FeedbackFAB`) still greps the whole screen and is unaffected;
4 (a testID per beat) still finds `team-review.beat.plan`, which was kept
deliberately — renaming it would have been an invisible loss of coverage;
5a and 5c are untouched string checks.

## 7. What is NOT covered by a static check

Left to the TestFlight checklist, because they are network- and
runtime-dependent and their failure mode is a page that looks plausible:

- that `GET /api/league/preferences` returns what the window/depth beats just
  wrote, so the plan beat's rows match reality rather than merely rendering;
- that a positions-only edit now returns 200 rather than 400 (the fix's whole
  point) — provable only against a live server;
- that exiting with a scoped partner lands on a deck actually scoped to them;
- that the failure line appears on a genuinely failed write (airplane mode).
