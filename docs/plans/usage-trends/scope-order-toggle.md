# Feature Scope — Usage Trends: order toggle and readable jumps

**Date:** 2026-10-10
**Entry point:** direct ask. Two days into the live feature, the operator found that "Biggest jumps last week" isn't sorted from largest to smallest. Their direction: "The users should be able to toggle between biggest jumps and weekly share."
**Builder:** lead session (the one that shipped [#321](https://github.com/mattmurf77/fantasy-trade-finder/pull/321))
**Operator sign-off on waivers:** not needed (no waivers)

Parent scope: [scope.md](scope.md). This change amends its **Sorting** row and §3 step 6b, and adds to [D-203](../../../living-memory/DECISIONS.md) as D-205.

---

## 0. What changes, and the decisions it rests on

**The finding.** "Biggest jumps" *is* sorted biggest-first, but by the size of the jump. The jump is this week's team share minus the player's average over his earlier weeks. The card only said where he landed ("Jumped to 90%"), so the list looked unsorted. For example, Jauan Jennings landed at 95% but ranks 10th, because he was already at 64% before. The section also mixed in "Back in the lineup" and "New role" players, which were ordered by this week's share and placed after every jump. Returning players also had no volume minimum, so a 0% return showed up as news.

| Decision | Ruling | Who |
|---|---|---|
| Order toggle | Version A gets **Biggest jumps \| Weekly share** (operator). It's a pill at the top of the Simple list, and Raw stats doesn't get it, because its columns already sort. **Weekly share** orders by the **newest selected week**, using the number currently showing (% of team, or the count under Filters → Count; the label then reads "Weekly count"). Highest is first, and a missed game or bye that week sorts last. Each card then states that week's number ("62% of Eagles plays in Week 4"), so the order is visible. | operator; lead (newest-week reading, count label) |
| Default | **Biggest jumps** (operator). Like the Simple \| Raw stats pill, the choice is remembered until the app restarts. | operator |
| Jump copy | A jump card says where it started as well as where it landed: **"Jumped from 22% to 90% of Eagles plays"**. "From" is the player's average over his earlier weeks, the same baseline the server measured the jump against, so the gap on the card is the sort key. In the Count unit it reads "Jumped from 15 to 55 targets". A return that is also a jump reads "Back and up from 37% to 58% of Patriots plays". I offered "Up 68 pts to 90%", but rejected it: in a fantasy app, "pts" reads as fantasy points. | operator (state the jump); lead (wording) |
| Sections | Biggest jumps now has three sections: **Biggest jumps last week** (only jumps, biggest jump first), then **Back or new last week** (returns and first games that aren't jumps, ordered by this week's share), then **Everyone else**. The server already ranks these groups in this order, so the client only splits the list and never re-sorts it. | operator |
| Return floor | A return now needs the same weekly volume a jump does: **20 snaps, 6 carries or 4 targets** in the comeback game. Below that, it isn't news. This is a server change, and it takes effect on iOS 1.21.0 without an app update. | operator |

## 1. Analytics scope

- **`usage_trends_view_changed`** gains prop **`order`** ∈ `jumps | week`. It fires when the toggle changes, and it's carried on every other view change. Classification is unchanged: NON_INTENT.
- **`usage_trends_action`** gains prop **`order`**, so an Add/Trade/Re-rank can be attributed to the order the user was reading. Classification is unchanged: INTENT.
- **No new event names.** Both props are registered in `backend/analytics_taxonomy.py` `CLIENT_EVENT_PROPS` in the same commit as the emitter. The tracking-plan addendum is [2026-10-10-usage-trends-events.md](../../business/analytics/2026-10-10-usage-trends-events.md).
- Question it answers: do users read usage by change or by level, and which order produces the Adds/Trades?

## 2. Schema & flag scope

- **Schema:** none.
- **API contract:** `GET /api/usage-trends` has the same shape. One semantic change: a `return` signal now requires the volume floor. Below the floor, the player gets the next signal that applies (an earlier spike, rising/falling, or none). `docs/api-reference.md` is updated.
- **Flags:** none new. It rides `usage_trends.enabled`, which is ON. The rollback for the whole screen is unchanged. The return floor has no separate switch; reverting it is a one-line revert plus a deploy.
- **Mobile version:** 1.21.2 (1.21.1 went to #322).

## 3. Evidence scope

- **Backend:** `test_return_needs_the_weekly_volume_floor`. It failed when I removed the floor and passed with it. The rest of `test_usage_trends.py` and `test_usage_trends_refresh.py` stay green (47).
- **Structural guard** `mobile/tests/check-usage-trends.js` gains these checks:
  - 1j–1l / 1m2: jump copy states where the jump started and where it landed;
  - 1p: no jargon in the card copy, now including "pts";
  - 1t2–1t3: `newsSplit`;
  - 1y2: `sortByLatestWeek`;
  - 1y3: `weekHeadline`;
  - 2e4: Weekly share is the only Version A sort, and it goes through the helper; Biggest jumps keeps the server order;
  - 2e5: the toggle is Simple only, defaults to jumps, is remembered, is reported, and is handed to the card;
  - 2e6: the card reads the week sentence only in Weekly share.

  Eight named sabotages each went red:
  1. jump copy reverted;
  2. back-without-jump counted as a jump;
  3. weekly order ascending;
  4. week card shows the average;
  5. jargon in copy;
  6. weekly branch unsorted;
  7. card ignores order;
  8. toggle not remembered.
- **Real data:** I recomputed live Week 4 Snaps with the new rule. It gives 35 jumps, then Back or new = Nico Collins 69%, Chig Okonkwo 58%, Mitch Tinsley 53%, Elijah Sarratt 36%. The 0–31% returns that had no real role (Jack Endries 0%, Barion Brown 4%, Treyton Welch 10%, …) are gone.
- **Code-walk:** [code-walk.md](code-walk.md) §8.
- **TestFlight checklist (1.21.2)**, to run in addition to scope §3:
  1. Simple view opens on **Biggest jumps**, with the pill at the top of the list.
  2. Under "Biggest jumps last week", each card reads "Jumped from X% to Y% of … plays". The gap (Y − X) shrinks as you scroll down. Darius Cooper (22% → 90%) is above Braelon Allen (41% → 94%).
  3. Below that, "Back or new last week" lists "Back in the lineup: …" and "New role: …" cards, highest % first. No card there shows a near-zero %.
  4. Tap **Weekly share**. The list becomes one section, "Week 4 share of team plays". Every card reads "N% of <team> plays in Week 4", and the numbers fall from top to bottom. Players who didn't play in Week 4 ("Didn't play in Week 4" / "Bye in Week 4") are at the bottom.
  5. **Filters → Count**. The pill reads **Weekly count**, cards read "N snaps in Week 4", and the order follows the counts. Switch to Carries and Targets: the order follows that stat.
  6. **Filters → Weeks → pick 1–3**. Weekly share orders by Week 3 and the cards say "in Week 3".
  7. Leave the screen on Weekly share and reopen it. It's still Weekly share. After an app restart it opens on Biggest jumps.
  8. **Raw stats** has no order pill. Its column sorts are unchanged.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `GET /api/usage-trends`: the return floor; the client re-sort note (Simple's Weekly share) |
| `living-memory/LLD.md` | updated | Usage Trends entry: Version A's one sort goes through `sortByLatestWeek` → `sortStatsRows` |
| `docs/architecture.md` | n/a | no module wiring or data-flow change |
| `living-memory/HLD.md` | n/a | no architectural shift |
| `docs/cross-client-invariants.md` | n/a | mobile only; no shared constant changed |
| `docs/glossary.md` | updated | return (volume floor); Biggest jumps / Weekly share orders |
| ADR or `DECISIONS.md` entry | updated | D-205 |
| `docs/plans/usage-trends/scope.md` | updated | Sorting row + §3 6b point here |
| `docs/business/analytics/2026-10-10-usage-trends-events.md` | updated | `order` prop |
| `mobile/src/screens/CLAUDE.md`, `mobile/src/components/CLAUDE.md`, `mobile/tests/README.md` | updated | screen / card / guard rows |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (which runs the `check-*.js` suites) + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry.
- **TestFlight verification:** the 8 steps in §3, on 1.21.2.
- Express lane declared by the operator? **No**, so full gates apply.
