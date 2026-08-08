# #208 — Ranks follow the position filter — status

**Status:** BUILT (2026-08-08) — worktree branch `worktree-agent-ac81596c5b45c68c9`
off `teardown-remediation`. Not merged, not pushed.
**Verification:** static only (`tsc --noEmit` + grep proofs). Runtime/Maestro is
the batch QA round's — see `prd.md` §6 for the flow it should run.
**Code:** `mobile/src/screens/LeagueSummaryScreen.tsx` only. Backend untouched.

## Headline finding: the reported symptom does not reproduce

"The ranks listed under the bar charts should update as a user selects/filters
positions" — they already do, on this branch. Every user-visible rank numeral is
an index into the client-side `ranked` array, which takes `posFilter` as a memo
dependency; the server's `PowerRankedTeam.rank` is read **nowhere** in the mobile
app. Confirmed three ways:

1. Line-by-line trace of both derivation chains (bars and #248 other-basis) —
   `prd.md` §1.
2. An independent second read of the full 1776-line file by a separate agent with
   no shared context, which reached the same conclusion and enumerated the same
   chains.
3. A scratch node harness replicating `computeSubset` + `activeTotal` + the
   `ranked` sort:
   ```
   unfiltered: [ '1. A (8000)', '2. C (8000)', '3. B (7000)' ]
   WR only   : [ '1. B (5000)', '2. C (2000)', '3. A (500)' ]
   QB only   : [ '1. A (5000)', '2. C (2000)', '3. B (500)' ]
   ```

The report is not bogus — it is stale. The pre-#243 drill-in overlay printed the
raw server `selected.rank` while the chart around it was already re-sorted, which
is exactly the reported mismatch. That was fixed by `a4ed81f` (2026-07-26 chart
rework) and `b2bd078` (#243). `main` does not carry this screen at all, so the
shipped v1.11.0 build the reporter used predates the current branch's chart work.

**Nothing was changed to "fix" the headline symptom** — inventing a diff for
already-correct code would have been the worse outcome.

## What #208 actually surfaced, and what shipped

Auditing the item's real requirement — *every derived value must be computed
under the active filter* — turned up one genuine violation and one label bug,
both in #248's overlay.

### 1. `ticksOn` made its DRAW decision on an unfiltered quantity

#248 made the overlay's **values** filter-aware but left its **on/off gate** on
`boardsDiffer`, a whole-roster `total_value` comparison. So a caller who has
re-ranked only RBs and then filters to **QB** — a view where the two bases hold
byte-identical values — still saw a dashed ice tick sitting exactly on every bar
top and a focus caption reading "Consensus rank 3/12 · My board rank 3/12". The
chart asserted a comparison the filtered view does not contain. Same class of
defect #248's own status note warned about ("a filtered bar next to an unfiltered
tick"), one level up.

**Shipped:** the two questions are now separate.

- `boardsDiffer` keeps its unfiltered meaning — *does the caller have a my-board
  distinct from consensus at all* — and keeps driving the basis-toggle labels
  ("Consensus sorts" / "My board sorts"), which must not flicker as the user
  pages through position pills.
- New `boardsDifferInView` compares each team's `ranked` active total against its
  `otherByTeam` active total, i.e. the values on screen. `ticksOn` moved below
  `otherByTeam` and now gates on it.

This is a strict generalization of #248's own rule ("identical boards ⇒ the
overlay would only mark the bars against themselves, so it hides") from the whole
roster to the current view. The unfiltered view behaves exactly as before.

### 2. Dual-rank captions divided by the wrong basis' team count

`focusOther.rank` is ranked over `otherTeams`, but both captions printed it over
`ranked.length` (the *bars* payload's count). The two parallel queries can hold
different team sets — a membership change landing between fetches, or one payload
served stale via `placeholderData` — producing "#8 of 12" for an 11-team board.
**Shipped:** new `otherCount = otherByTeam.size`, used in the focus caption and
the drill subline.

### Deliberately NOT changed

- `teamPosRank` (drill-in group header `3/12`) and `playerPosRank` ("RB2") are
  correctly `posFilter`-**independent**. "Rank of this team's RB value league-wide"
  and "rank among RBs" must not fold a simultaneous WR selection in. Both stay
  `subset`-aware only. Recorded in `prd.md` §3 so a future pass doesn't "fix" them.
- The unfocused hint line renders `[...posFilter].join(' + ')` in tap order and
  prints the raw `PICKS` enum, while the #243 focused caption canonicalizes to
  QB→RB→WR→TE and title-cases "Picks" (#195). Cosmetic copy, not a rank — noted,
  not drive-by fixed.
- Under `subset === 'all'`, `computeSubset` reads `posValues` from the server's
  `team.positions[p].value` while the drill panel's group total sums `team.roster`
  rows; a disagreement would print different totals in bar vs group header.
  Pre-existing, unrelated to the filter.

## Files touched

| File | Change |
|---|---|
| `mobile/src/screens/LeagueSummaryScreen.tsx` | `boardsDifferInView` + `ticksOn` moved below `otherByTeam`; `otherCount` denominator in both dual-rank captions; header-comment #208 block |
| `docs/cross-client-invariants.md` | new clause under the dashed-ice tick entry — same-view rule for the other-board marker |
| `mobile/src/screens/CLAUDE.md` | `LeagueSummaryScreen` row: #208 outcome |
| `docs/feedback/items/208-ranks-follow-position-filter/{prd,status}.md` | new |

No backend diff ⇒ `pytest` not run (baseline untouched). No API-contract change ⇒
`docs/api-reference.md` unchanged. No new testIDs, no new flags.

## Invariant updated

`docs/cross-client-invariants.md`, under "Dashed-ice tick = other-board marker
(#248)": the marker and any rank delta derived from it must be computed under
exactly the filters the bars are drawn under, and must **not render in a view
where the two bases hold identical values** — "identical in this view", not
"identical overall". Any rank printed for the other basis is denominated by that
basis' own entity count. Governs any future client that draws a two-basis chart.

## Verification

- `mobile/ tsc --noEmit` → **exit 0, clean** (worktree has no `node_modules`;
  symlinked the main checkout's for the run, symlink removed afterwards).
- Grep proofs:
  - `grep -n "\.rank\b"` → only `focusOther.rank` / `other.rank`, both indices
    from `otherByTeam`. **No read of the server `team.rank`.**
  - `grep -n "rank={idx + 1}\|selectedIdx + 1\|rank: i + 1"` → every numeral is a
    `ranked` / `otherByTeam` index.
  - `grep -n "posFilter\]"` → `posFilter` is a dep of both value memos
    (`ranked` line 390, `otherByTeam` line 438).
  - `grep -n "boardsDifferInView\|const ticksOn"` → gate rewired.
  - `grep -n "otherCount"` → used in all three other-basis rank labels.
- Node harness (scratch, not committed) proving `ranked` reorders and renumbers
  under WR-only and QB-only filters — output in §"Headline finding" above.

## QA checklist (batch QA round)

Regression watch — #248/#243/#237 must not move:

1. **#208 core** — filter to WR: bar numerals, bar order and the team-row list
   below all re-rank to the WR ordering; "All" restores the original ordering.
2. **#248 ticks/chips, boards differ in view** — unfiltered, a caller with a
   real my-board still sees `league-summary.tick.<user_id>` on every column and
   `league-summary.delta.<user_id>` where |Δ| ≥ 2. **No fewer ticks or chips than
   before this change in any view where they were meaningful.**
3. **#208 fix** — filter to a position the caller has never re-ranked: ticks,
   delta chips, the legend "…rank" key and the both-boards hint all disappear;
   the chart renders as a clean single-basis chart. Return to "All" ⇒ they come
   back.
4. **#248 shared scale** — no tick ever clips off the chart top under any
   subset × position combination; the avg line sits on the same scale.
5. **#248 identical boards** (caller who has never ranked) — overlay fully
   absent, exact pre-#248 chart, "Consensus"/"My board" labels without "sorts".
6. **#248 toggle labels** — "Consensus sorts"/"My board sorts" stay stable while
   toggling position pills (they must NOT flicker to the short labels under a
   filter — that would mean `boardsDiffer` got wired to the filtered check).
7. **Denominator** — focus a team with the overlay live: both halves of
   `league-summary.focus-caption` and the drill subline read `N of <count>` with
   the same count in a healthy league.
8. **#237** — changing a filter in the drill panel re-ranks the chart behind it;
   both control sets stay in lockstep.
9. **#243** — focused state still collapses to the slim strip with
   `league-summary.filter-caption`; `league-summary.roster-close` restores the
   unfocused layout exactly.
10. **Starters/Bench** — ticks still hide for those subsets when the other
    payload lacks `starters_available`.
