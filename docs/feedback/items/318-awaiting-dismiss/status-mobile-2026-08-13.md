# Status — Matches group build (mobile), 2026-08-13

**Branch:** `wave-matches` · base `origin/main` @ `60fccc7` · plan `plan-2026-08-13.md` (`0cd6e13` + `5d6760d`)
**Covers:** #319 (value disclosure + open-in-calc) · #318 mobile half (awaiting dismiss) · #307 carried Matches contract (frozen, `wave-league` @ `6368e31` §4.3)

**The decision in plain words:** the Matches screen now lets you (a) expand any
row to see the same "Dynasty value swing" bar the finder deck shows, with an
Open-in-calculator button under it, and (b) clear out trades you're still
waiting on the other owner for, with a 5-second Undo and an honest "try again"
if the server call fails. League-home tiles can also deep-link the inbox
pre-filtered to their league. No new feature flag anywhere (see C-7 below).

---

## File:line map

| File | Lines | What |
|---|---|---|
| `mobile/src/api/trades.ts` | 562–592 (`dismissAwaitingTrade` at :578) | #318 wrapper — the single [CONTRACT] site: `POST /api/trades/awaiting/dismiss` `{league_id, my_give ← my_side_player_ids, my_receive ← their_side_player_ids, partner_id ← counterparty_user_id}` |
| `mobile/src/components/MatchValueSection.tsx` | new (203 lines) | #319 body: disclosure (testID `matches.value-details` :90), lazy evaluate `enabled: expanded` :67, ref-guarded `match_opened` :76, dropped-assets caveat :128, `TradeValueBar` verbatim :132, calc CTA `matches.open-in-calc` :147 |
| `mobile/src/components/TradeCard.tsx` | :93 (prop), :141 (destructure), :676 (`{footer ?? null}`) | **footer prop only** — optional, rendered once as the card's final block; nothing else in the file changed (S-2/S-6 pin it) |
| `mobile/src/screens/MatchesScreen.tsx` | :135–136 (#307 param), :742 (#307 chip testIDs), :220 (`dismissAwaitingMutation`), :255 (generalized `pendingDismissRef` union), :271/:282 (flush/undo, both kinds), :344 (`handleDismissAwaiting`), :386 (`handleOpenInCalc`, `switchLeague` at :406), :927 (mutual footer mount), :1038–1046 (awaiting footer: Dismiss `matches.awaiting-dismiss` + section), :1321 (style) | all three workstreams |
| `mobile/tests/check-match-value-section.js` (19) · `check-matches-calc-handoff.js` (12) · `check-awaiting-dismiss.js` (21) · `check-matches-league-param.js` (9) | new | sabotage-pinned suites, S-1…S-10 |
| `mobile/.maestro/capture/matches.yaml` | extended | expand asserts both segments, open-in-calc → `calc.find-a-trade`, evaluate-500 → "Could not value this trade." |
| `mobile/.maestro/flows/matches-awaiting-dismiss.yaml` | new | M-2 rollback-under-500 first, M-1 happy, M-3 empty state; **needs wave-backend's route to run green** |
| `mobile/scripts/testid-lint-allow.txt` | +`matches.league-chip.*` | template-literal chip ids (frozen #307 grammar) |
| `docs/feedback/items/318-awaiting-dismiss/scope.md` | new | gates record; C-7 rationale |

## C-7 — no new flag (rationale, per the orchestrator directive)

D-035 precedent: a flag here is a five-file change (`config/features.json`,
`FLAG_KEYS`, `docs/config-reference.md`, client `useFlag`, flag fixtures) and
`revalidateFlags`' map-replace makes a half-registered flag **worse than
none** — an unknown key reads permanently false, so the affordance could never
ship without a re-ship anyway. The affordance is small, additive, and rollback
is a client revert. Consequence: the Dismiss button renders unconditionally;
against a pre-#318 server the POST fails and the S-9 rollback restores the row
with "Could not dismiss — try again" — honest degradation, never fake success.
The undo toast honours the **existing** `ux.swipe_undo` (ON in prod + release
fixture). Pinned by `check-awaiting-dismiss.js` #13 (no `awaiting_dismiss`
flag key in `mobile/src`).

## Contract bytes confirmation

`dismissAwaitingTrade` sends exactly the frozen wave-backend contract:
`POST /api/trades/awaiting/dismiss` with all four required fields, yours-perspective
arrays matching `load_awaiting_trades`' key (the normalizer's own mapping
inverted: `my_give ← my_side_player_ids` [raw `my_give`], `my_receive ←
their_side_player_ids` [raw `my_receive`]). Success = 2xx `status:"ok"`
regardless of `dismissed_likes` (the client never branches on it). Idempotency
(C-4) is what makes the 5 s delayed-POST undo retry-safe. C-5: no client
event. C-6: nothing asserted about the counterparty. Pinned by
`check-awaiting-dismiss.js` #7–#12.

## Sabotage matrix (RED-then-green, run this session)

Protocol: production code committed → apply mutation (`git diff` non-quiet
confirms it landed) → suite must FAIL → `git checkout` → `git diff --quiet`
guard → final green re-run of all four suites. Comment-strip precedes every
absence assertion. Two first-attempt mutations (S-1 `enabled:true`, S-8b
wrong-path) edited a **comment** instead of code (perl first-occurrence);
re-run with code-targeted mutations — mutation-script defects, not suite
defects.

| # | Sabotage (mutation) | Suite | Result |
|---|---|---|---|
| S-1 | `enabled: expanded` → `enabled: true` (code line) | value-section #3 | RED ✓ |
| S-1b | `enabled:` dropped entirely | value-section #3 | RED ✓ |
| S-2a | `footer` made required | value-section #4 | RED ✓ |
| S-2b | footer rendered twice (leaked into disposition area) | value-section #5/#8 | RED ✓ |
| S-2c | footer moved above the send rows (not final block) | value-section #6/#7 | RED ✓ |
| S-3 | dropped-assets caveat branch deleted | value-section #11/#12 | RED ✓ |
| S-4 | bar forked (local "Dynasty value swing" markup) | value-section #14/#15 | RED ✓ |
| S-5 | cross-league branch removed (navigate w/o switch) | calc-handoff #2–#5 | RED ✓ |
| S-6 | TradeCard authors the dismiss (deck leak) | awaiting-dismiss #1/#5 | RED ✓ |
| S-7 | awaiting mount flipped to `variant="match"` | awaiting-dismiss #3 | RED ✓ |
| S-8a | `my_give`/`my_receive` crossed | awaiting-dismiss #10 | RED ✓ |
| S-8b | POST path → `/api/matches/dismiss` (code string) | awaiting-dismiss #8 | RED ✓ |
| S-9 | onError snapshot-restore deleted | awaiting-dismiss #16 | RED ✓ |
| S-10 | `route.params?.at` dropped from effect deps | league-param #5 | RED ✓ |

Final: `GREEN` × 4 suites, `tree clean`. Raw batch output (12/14; the two
corrected cases re-run individually after fixing the mutations):

```
S-1 lazy-fetch (enabled:true): FALSE PASS — sabotage NOT caught   ← mutation hit a comment; corrected run: S-1 RED ok
S-1b lazy-fetch (enabled dropped): RED ok (suite failed under sabotage)
S-2a footer required: RED ok (suite failed under sabotage)
S-2b footer rendered twice: RED ok (suite failed under sabotage)
S-2c footer not final: RED ok (suite failed under sabotage)
S-3 caveat deleted: RED ok (suite failed under sabotage)
S-4 bar forked: RED ok (suite failed under sabotage)
S-5 wrong-league branch dropped: RED ok (suite failed under sabotage)
S-6 deck-leak (TradeCard authors dismiss): RED ok (suite failed under sabotage)
S-7 surface flip: RED ok (suite failed under sabotage)
S-8a crossed my_give/my_receive: RED ok (suite failed under sabotage)
S-8b wrong path: FALSE PASS — sabotage NOT caught   ← mutation hit the comment copy of the path; corrected run: S-8b RED ok
S-9 rollback deleted: RED ok (suite failed under sabotage)
S-10 at dropped from deps: RED ok (suite failed under sabotage)
── green re-run ──
GREEN check-match-value-section.js
GREEN check-matches-calc-handoff.js
GREEN check-awaiting-dismiss.js
GREEN check-matches-league-param.js
tree clean
```

Corrected re-runs (code-targeted mutations, each followed by
`git checkout` + `git diff --quiet`):

```
67:    enabled: true,
S-1 RED ok
clean after S-1
580:    '/api/matches/dismiss',
S-8b RED ok
clean after S-8b
```

**S-8 re-scope (plan deviation, directed):** the plan's S-8 was a
flag-gate sabotage; C-7 resolved to *no flag*, so there is no gate to
sabotage. S-8 is re-scoped to the contract bytes (path + uncrossed field
mapping), keeping ten named sabotages, all RED-then-green. The plan's
Maestro-level sabotages (wrong-path injection vs healthy bar; broken
rollback vs M-2) are run-time and deferred to the wave sim gate — each is
noted inline in the flow files.

## Verification (static, actual output)

```
$ npx tsc --noEmit
tsc: clean (no output)
$ bash mobile/scripts/testid-lint.sh
testid-lint OK
$ node mobile/tests/check-single-pin-actions.js      → 17 PASS, "All single-pin-actions checks passed."  (footer did not red it)
$ node mobile/tests/check-analytics-297-302.js       → 35 PASS, "All #297/#298/#299/#302 analytics checks passed."
$ node mobile/tests/check-league-candidates-300.js   → 67 PASS, "All #300 league trade-candidate checks passed."
$ node mobile/tests/check-picks-subset-invariance.js → 72 PASS, "All picks-subset-invariance checks passed."
$ node mobile/tests/check-match-value-section.js     → ALL CHECKS PASSED (19)
$ node mobile/tests/check-matches-calc-handoff.js    → ALL CHECKS PASSED (12)
$ node mobile/tests/check-awaiting-dismiss.js        → ALL CHECKS PASSED (21)
$ node mobile/tests/check-matches-league-param.js    → ALL CHECKS PASSED (9)
```

## Plan defects found (built around, reported)

1. **`setLeague` is not the switcher.** The plan (and §Fix pseudocode) names
   `useSession.setLeague()` for the cross-league calc handoff, citing
   `useSession.ts:195,392-405` — but `setLeague` only persists the pin; it
   never re-runs the backend league handshake. The behavior the plan
   *describes* ("re-runs league session init, visible spinner-time") is
   `switchLeague` (`useSession.ts:419+`, the LeagueSwitcherSheet's machinery,
   which also invalidates the matches/awaiting caches). Built with
   `switchLeague` (+ try/catch → honest toast); `setLeague` would have opened
   the calculator against a session still bound to the OLD league.
2. **Bare `navigate('TradeCalculator')` is unreachable from the Matches tab.**
   The route lives in the *Trades tab's* stack (`TabNav.tsx:427`); the plan's
   call works from TradesScreen but not cross-tab. Built as the nested form
   `navigate('Trades', { screen: 'TradeCalculator', params: { prefill } })` —
   the same pattern the screen's own "Find a trade" CTA already uses. Pinned
   by calc-handoff #11.
3. **Plan's §318 TradeCard affordance vs the footprint directive.** The plan
   put the awaiting Dismiss inside TradeCard's actions row; the build brief
   restricts TradeCard to the footer prop (file otherwise owned by shipped
   work). Built: Dismiss rides the awaiting card's **footer stack**, directly
   under the send button, above the value disclosure — same visual position
   ("joins the send area"), zero TradeCard delta beyond the slot. S-6
   re-pinned accordingly (affordance authored only by MatchesScreen).
4. **S-8 flag sabotage void** — see re-scope above (consequence of C-7, not a
   plan error at write time).

## Proposed shared-doc text (orchestrator applies at wave merge)

- `docs/plans/mobile-testing/lld.md` Appendix A, Matches row →
  `` `matches.segment.<mutual\|awaiting>` `matches.league-chip.<league_id\|all>` `matches.value-details` `matches.open-in-calc` `matches.awaiting-dismiss` `matches.card.<n>` `matches.dismiss.<n>` `matches.empty-text` ``
  (note: `matches.filter.*` was never implemented; the frozen #307 grammar `matches.league-chip.*` supersedes it — recommend replacing the stale token.)
- `mobile/src/components/CLAUDE.md` → new row:
  `| MatchValueSection | Matches-inbox expandable "Trade value" disclosure (#319): lazy POST /api/trade/evaluate on expand only, TradeValueBar verbatim, dropped-assets honesty caveat, open-in-calc CTA. Mounted via TradeCard's footer slot on both segments |`
  and amend the `TradeCard` row: append "…; optional `footer` slot renders as the card's final block (Matches mounts MatchValueSection + the awaiting Dismiss there; deck mounts pass nothing)".
- `mobile/src/screens/CLAUDE.md` → amend `MatchesScreen`:
  `Mutual trade matches inbox; progress module + "Find a trade" CTA on the empty state. Per-row "Trade value" disclosure + open-in-calc on both segments (#319; cross-league rows switchLeague first). Awaiting rows dismissible with 5 s undo, delayed-POST, honest rollback (#318, no flag — C-7). League-scoped deep link: navigate('Matches', {segment, leagueId, at}) rescopes the filter chips (#307 frozen contract)`
- `docs/api-reference.md` / `docs/config-reference.md`: wave-backend's rows (route + its server-fired event); nothing from this half.

## Handoff notes

- The dismiss flow (`matches-awaiting-dismiss.yaml`) and the capture's
  value-error leg can only run green after `wave-backend` merges — sim-gate
  tier 2 at the wave ship, then TEST_LEDGER + `qa/sim-runs/last-sim-run.json`.
- `TradeCard.tsx` delta is deliberately merge-trivial (prop + one JSX line);
  rebase against `wave-trades` before merge if both land, per the plan.
- Commits on `wave-matches`: `5c1fa63` (production), `651cb29` (tests),
  maestro + docs follow.
