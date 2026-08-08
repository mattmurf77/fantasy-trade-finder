# #208 — Ranks follow the position filter (LeagueRankings)

- **Reporter:** tester, app v1.11.0, screen `LeagueRankings`
- **Filed as:** polish. **Routed as:** behavior bug.
- **Ask:** "The ranks listed under the bar charts should update as a user selects/filters positions."
- **Owner file:** `mobile/src/screens/LeagueSummaryScreen.tsx` (serves both the
  `LeagueRankings` tab root and the legacy `LeagueSummary` root-stack route).
  Backend `backend/power_rankings.py` inspected, unchanged.

---

## 1. Repro attempt — the headline symptom does NOT reproduce

**Reported behavior:** filtering to a position reshapes the bars but leaves the
rank numerals on the unfiltered (server) ordering, so a WR-filtered view still
shows overall ranks.

**Result on `teardown-remediation` HEAD: not reproducible.** Every user-visible
rank numeral on this screen is already the *index into the client-side re-sorted
`ranked` array*, and `ranked` takes `posFilter` as a memo dependency. The server's
`PowerRankedTeam.rank` field is present on the payload and **read nowhere** in the
mobile app (`grep -n "\.rank\b" LeagueSummaryScreen.tsx` returns only
`focusOther.rank`, itself a client-side index).

Two derivation chains produce every number on the screen, and both are
`posFilter`-dependent:

| Chain | Lines | Feeds |
|---|---|---|
| bars | `teams` → `computed` (`useMemo` deps `[teams, subset]`) → `ranked` (deps `[computed, subset, posFilter]`, sorted on `activeTotal(tc, subset, posFilter)`) | bar numerals, list-row numerals, focus caption, drill subline, avg line, bar heights |
| other basis (#248) | `otherTeams` → `otherComputed` → `otherByTeam` (deps `[otherComputed, subset, posFilter]`, same `activeTotal` + same `user_id`-asc tiebreak) | ghost tick height, delta chips, dual-rank captions |

Proof harness (scratch, not committed) replicating `computeSubset` + `activeTotal`
+ the `ranked` sort over a synthetic 3-team league:

```
unfiltered: [ '1. A (8000)', '2. C (8000)', '3. B (7000)' ]
WR only   : [ '1. B (5000)', '2. C (2000)', '3. A (500)' ]
QB only   : [ '1. A (5000)', '2. C (2000)', '3. B (500)' ]
```

The ordering AND the numerals move together because they are the same index.

**Why the report is still plausible.** The historical version of this screen
*did* have a pinned rank: before the 2026-07-26 League Analyzer replication
(`a4ed81f`) and the #243 drill-in rework (`b2bd078`), the drill-in overlay
printed `selected.rank` — the raw server field — while the chart around it was
already re-sorted. A tester on a build from that window would see exactly the
reported mismatch. That line is now `selectedIdx + 1`. Since `main` does not
carry this screen at all, the shipped v1.11.0 build the reporter used predates
the current branch's chart work.

An independent second read of the full file (separate agent, no shared context)
reached the same conclusion and enumerated the same two chains.

## 2. Root cause of what IS still wrong

The audit surfaced one genuine violation of #208's actual requirement — *a
filtered comparison decided by an unfiltered quantity* — plus one rank-label
denominator bug. Both are in #248's overlay.

### 2a. `boardsDiffer` gates filter-aware signals on an unfiltered value

`boardsDiffer` compares each team's whole-roster `total_value` across the two
bases. It gates `ticksOn`, which in turn gates the ghost ticks, the delta chips,
the dual-rank focus caption, the drill subline's other-basis half, the legend
tick key and the hint copy — **all of which are computed under the active
filter**.

Consequence: a caller who has only re-ranked RBs on their board, then filters to
**QB**, sees a view where the two bases hold byte-identical QB values — yet every
column still draws a dashed ice tick sitting exactly on its own bar top, and the
focus caption reads "Consensus rank 3/12 · My board rank 3/12". The overlay
asserts a comparison the filtered view does not actually contain. This is the
same class of defect #248's own status note warned about ("a filtered bar next to
an unfiltered tick") — the values were made filter-aware, the *decision to draw
them* was not.

#248's stated rule is that when the two boards are identical the overlay "would
only mark the bars against themselves, so it hides". Under a filter where the two
bases agree, the ticks *are* marking the bars against themselves. Making the gate
filter-aware is a strict generalization of the existing rule, not a new one.

### 2b. Dual-rank captions divide by the wrong basis' team count

`focusOther.rank` comes from `otherByTeam` (ranked over `otherTeams`), but both
captions print it over `ranked.length` (the *bars* payload's team count). The two
parallel queries can legitimately hold different team sets — a membership change
landing between fetches, or one payload served stale via
`placeholderData: (prev) => prev`. The caption can then read "#8 of 12" for a
board that only ranked 11 teams.

## 3. Derived values that must be filter-aware — the contract

| Derived value | Filter-aware today | Action |
|---|---|---|
| Bar-column rank numeral | Yes | none |
| Team-list row rank numeral | Yes | none |
| Focus caption `League rank: N/M` | Yes | none |
| Dual-rank focus caption (both halves) | Yes | fix denominator (2b) |
| Drill panel `#N of M` subline (both halves) | Yes | fix denominator (2b) |
| #248 ghost tick height (`tickPct`) + shared `scaleMax` | Yes | none |
| #248 delta chips (`other.rank − (idx+1)`) | Yes | none |
| League-average line + label | Yes | none |
| **Overlay on/off decision (`ticksOn`)** | **No** | **fix (2a)** |
| Bar heights / stack segment values | Yes | none |

Two values are **deliberately NOT** `posFilter`-dependent, and must stay that way:

- `teamPosRank` — the drill-in group header chip `3/12` answers "rank of this
  team's *RB* value league-wide". Folding a multi-select WR+RB filter into the RB
  chip would make it meaningless. It is correctly `subset`-aware only.
- `playerPosRank` — "RB2" is a player's rank among RBs; selecting WR as well must
  not move it. Correctly `subset`-aware only.

The `#169` odds-section numerals rank by playoff odds from a different endpoint
and are out of scope.

## 4. Fix approach

Surgical, `LeagueSummaryScreen.tsx` only, no backend and no API change.

1. **Split the two questions the overlay currently conflates.**
   - `boardsDiffer` keeps its present meaning — *does the caller have a my-board
     distinct from consensus at all* — and keeps driving the basis-toggle labels
     ("Consensus sorts" / "My board sorts"). The toggle's meaning does not change
     per filter, so this must stay whole-roster.
   - A new `boardsDifferInView` asks *do the two bases differ under the values
     currently on screen*, by comparing each team's `ranked` active total against
     its `otherByTeam` active total. `ticksOn` moves below `otherByTeam` and gains
     this term.
2. **Denominator.** Take the other basis' team count from `otherByTeam.size` and
   use it in both dual-rank captions.

Non-goals (observed, deliberately not changed):

- The unfocused hint line renders `[...posFilter].join(' + ')` in *tap* order and
  prints the raw `PICKS` enum, whereas the #243 focused caption canonicalizes to
  QB→RB→WR→TE and title-cases "Picks" (#195). Cosmetic copy, not a rank — left
  alone rather than drive-by fixed.
- Under `subset === 'all'`, `computeSubset` reads `posValues` from the server's
  `team.positions[p].value` while the drill panel's group total sums
  `team.roster` rows. If those ever disagree the bar and its group header would
  print different totals. Pre-existing, unrelated to the filter.

## 5. Regression risk against #248 / #243 / #237

- **#248 shared max scale** — `scaleMax` still spans both bases whenever the
  overlay is live; the only change is that it collapses to `maxActive` in views
  where the two bases are identical, where the ticks are not drawn anyway.
- **#248 ghost ticks / delta chips** — math untouched. They now hide in exactly
  one additional case: a filtered view in which the other basis is value-identical
  (ticks would have overprinted the bar tops; every delta would have been 0, i.e.
  below the |Δ| ≥ 2 chip threshold already). No view that showed a meaningful tick
  or a chip before shows fewer now.
- **#248 identical-boards fallback** — unchanged and now strictly implied.
- **#248 "sorts" labels** — still on `boardsDiffer`, so the toggle copy does not
  flicker as the user pages through position pills.
- **#243 slim strip / #237 shared filter state** — untouched; no state model,
  testID or visibility rule changes.

## 6. Maestro regression flow

`league-rankings-filter-ranks` — new flow, registry IDs already exist.

1. Launch, sign in, land on the League tab (`LeagueRankings`).
2. Assert `league-summary.bar.<user_id>` columns present and capture the
   unfiltered rank ordering (bar numerals + `league-summary.team.<user_id>` row
   order).
3. Tap `league-summary.posfilter.wr`.
4. **Assert the rank numerals and the team-row order both changed** to the
   WR-value ordering (a WR-heavy team that was mid-pack is now rank 1). This is
   the #208 acceptance check.
5. Tap `league-summary.posfilter.qb` (multi-select WR+QB) → assert the ordering
   changes again and the hint line reads "Ranked by … value only".
6. Tap `league-summary.posfilter.all` → assert the ordering returns to the
   unfiltered one captured in step 2.
7. With a my-board that differs: assert `league-summary.tick.<user_id>` and any
   `league-summary.delta.<user_id>` are present unfiltered, and that after
   filtering to a position the caller has never re-ranked the ticks/chips/legend
   key are **absent** (2a acceptance).
8. Tap a bar → assert `league-summary.focus-caption` prints the same numeral as
   that team's bar numeral under the active filter, and that both halves of the
   dual-rank caption use the same denominator.
9. In the drill panel tap `league-summary.roster-posfilter.te` → assert the chart
   behind it re-ranks (#237 shared state) and the `#N of M` subline follows.
10. `league-summary.roster-close` → assert the unfocused layout restores (#243).

Runtime execution belongs to the batch QA round — this build is
static-verification only.
