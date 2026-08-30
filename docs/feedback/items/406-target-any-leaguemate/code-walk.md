# FB-406 — Code-walk proof (13 hops, post-change state)

**Date:** 2026-08-30 · **Author:** mobile build agent · **State:** working tree on
`claude/new-user-feedback-5fa613` at base `001ec915` + the FB-406 build (uncommitted —
line numbers cite the built tree the orchestrator is reviewing). Executes the PRD §E-3
outline; every hop is file:line-cited at this state.

Files: `calc` = `mobile/src/components/InLeagueCalculator.tsx` ·
`trades` = `mobile/src/screens/TradesScreen.tsx` ·
`canvas` = `mobile/src/components/TradeBuildCanvas.tsx` ·
`fork` = `mobile/src/utils/canvasSearch.ts`.

## Hop 1 — Sheet Anyone tap

The new leading row (`calc:1537-1564`, testID `calc.team-sheet.any` at `:1544`) sits
inside the team-sheet Modal, above `opponents.map(` (`:1565`). Its onPress
(`calc:1548-1553`) is exactly `haptics.selection()` → `setPartnerAny(true)` (`:1550`) →
`setOpponentId(null)` (`:1551`) → `setTeamPickerOpen(false)` (`:1552`).
`opponentChosenRef` is untouched — its only write sites remain the two user-tap sites
(`calc:1113`, `:1587`), and the adjacent member-row handler is at `calc:1584-1591`.

## Hop 2 — The null id rides the existing partner-change effect

`opponentId → null` fires the `prevOpponentRef` effect (`calc:606-612`): mount-run
guarded (`:608`), then `setReceiveIds([])` (`:610`) and `setPicker(null)` (`:611`).
This matters for the payload: receive assets belonged to the old partner's roster, and
a canvas still holding them would re-scope via the FB-407 `receiveIds.length > 0`
clause. After the clear, both gate terms are false.

## Hop 3 — The default-to-first effect skips

`calc:570-575`: `if (!partnerAny && !opponentId && opponents.length)
setOpponentId(opponents[0].user_id)` (`:574`), deps `[opponents, opponentId,
partnerAny]` (`:575`). With `partnerAny` true the effect is inert, so the unscoped
state is stable — the pre-FB-406 form re-selected the first leaguemate the moment the
id went null.

## Hop 4 — Everything partner-shaped goes absent, honestly labeled

`opponent` resolves null (`calc:614` — `find` on a null id). Then:

- Dropdown value reads **"Anyone"** (`calc:1033`), a11y label carries the matching
  branch "Team: Anyone — offers from every team. Change team" (`calc:1007-1015`).
- Receive column header reads **"any team"** (`calc:1197`); its Add redirects to the
  team sheet instead of an empty picker (`calc:1210-1213`), with the
  `calc.receive-any-hint` line explaining (`calc:1219-1223`).
- `evalQ` cannot fire: `enabled: !!opponentId && …` (`calc:640`).
- The ONE gated derivation `const ev = opponentId ? evalQ.data : undefined`
  (`calc:657`) closes the `placeholderData` retention leak (`:642` keeps the previous
  key's data while disabled): the verdict block (`calc:1428`), eveners/trade-options
  rows (`calc:1378`), the lineup-impact branch (inside `LeagueVerdict`, reachable only
  through `:1428`), the picker's Suggested rows (`calc:667`, gated on `ev?.gap`), and
  `balancePlan`/`balanceQ` (`:691`, `:740`) all hang off `ev` or `!!opponentId`.
- Receive pool is empty by construction (`calc:622-627`, `opponentId ? … : []`).
- The ✓ cell stays disabled through the **textually untouched** expression
  `!onLikeTrade || !bothSides || !opponent || queueing` (`calc:1331`) — `opponent`
  is null, no `partnerAny` term added.

**Hop 4b — note ⇔ payload equivalence, term by term.** The scope-truth note
(`calc:1360-1365`, inside the merged branch directly under the action row) renders on
`partnerAny || (!partnerChosen && receiveIds.length === 0)` (`:1361`). The payload
gate (`calc:1288`) ships a partner iff `opponent && (opponentChosenRef.current ||
receiveIds.length > 0)`. Term map: `partnerAny` ⇒ `opponent` null (hops 1-3) ⇒ payload
null, note shown. Else `!partnerChosen && receiveIds.length === 0`: `partnerChosen`
mirrors the ref — identical initializers (`calc:364`/`:370`, both
`!!initialOpponentId && !seededPrefill`) and paired adjacent writes (`:1113`/`:1114`,
`:1587`/`:1588`) — so note-shown ⇔ ref false AND receive empty ⇔ gate false ⇔ payload
null. Note-hidden ⇒ `partnerChosen || receiveIds.length > 0` ⇒ (with `opponent`
non-null) gate true ⇒ scoped. The one-sided N-4 edge (departed-member prefill:
`partnerChosen` true, `opponent` never resolves, payload null, note hidden) fails in
the safe direction only — a league-wide search runs unannounced; the note never claims
league-wide while the wire is scoped.

## Hop 5 — Find a Trade builds a null-opponent payload

`calc:1276-1291`: `onFindATrade({ give, receive, opponent: … })` with the gate at
`:1288-1290` — `opponent` is null ⇒ `opponent: null`, regardless of the ref (the
`opponent &&` head short-circuits).

## Hop 6 — The shared fork reports an unscoped run

`forkCanvasSearch` (`fork:41-69`): `has_partner: !!opts.opponent` ⇒ **false**
(`fork:58`); path `fair` iff the give side is non-empty (`fork:51`); `anchor` rides
only on `fair` (`fork:67`). No new analytics — the existing
`calc_find_a_trade_tapped` row covers the unscoped run.

## Hop 7 — The inline host adopts the null scope

`handleInlineFindATrade` (`trades:3046-3073`) → `setSheetOpponent(fork.opponent)` =
`setSheetOpponent(null)` (`trades:3055`) → `scopedOpponent` derives to `undefined`
(`trades:832-836`).

## Hop 8 — Both request paths omit the partner

Fair: `runFairPackages` (`trades:3336`) spreads
`...(scopedOpponent ? { opponent_user_id: scopedOpponent } : {})` (`trades:3353`) —
key omitted. Model: `generateMutation` (`trades:1815`) sends
`opponent_user_id: scopedOpponent || undefined` (`trades:1850`) — `undefined` is
dropped from the JSON body.

## Hop 9 — Server: omitted partner ⇒ every-leaguemate sweep (zero backend diff)

`backend/server.py:12398-12399` (fair-packages docstring: "omitted ⇒ every league-mate
with a roster"), parse at `:12460` (`or None`). `backend/trade_service.py:5797-5799`
builds the all-members opponents list; the `opponent_user_id` narrowing at
`:5800-5801` is skipped when None; each emitted idea carries its own
`counterparty_user_id`/`counterparty_username` (`:5816-5817`) → mixed-partner deck via
`ideaToCard`, zero card changes. Covered by `backend/tests/test_fair_packages.py:15`/`:203`.

## Hop 10 — Round trip (the scoped counter-case)

Member-row tap (`calc:1584-1591`): `setPartnerAny(false)` (`:1586`),
`opponentChosenRef.current = true` (`:1587`), `setPartnerChosen(true)` (`:1588`),
`setOpponentId(o.user_id)` (`:1589`), sheet closes (`:1590`). Next Find a Trade:
gate true at `:1288` ⇒ scoped sweep; receive pool is their roster (`:622-627`);
evaluate live (`:640`); ✓ eligible (`:1331`); note hidden (`:1361`,
`partnerChosen` true). Byte-identical to pre-FB-406 scoped behavior — all existing
code paths. The Anyone row is always present in the sheet, so the reverse stays
available forever.

## Hop 11 — Post-search browse session (NB-1 / critic B-1)

Results land ⇒ the seeding effect (`trades:5812-5824`) writes
`setCanvasPrefill({ opponentId: rawTopCard.opponent_user_id, seeded: true, give,
receive })` (`:5815-5819`, marker at `:5817` — the ONLY `seeded: true` site) and bumps
`prefillSeq` (`:5821`). `TradeBuildCanvas` adopts on the seq (`canvas:150-156`), bumps
`canvasKey`, and the calculator remounts seeded and `partnerLocked`
(`trades:5588` `browseLive`, `:7457` `partnerLocked={browseLive}`), with
`seededPrefill={!!prefill?.seeded}` (`canvas:184`). R-10: both initializers
(`calc:364`/`:370`) read `!!initialOpponentId && !seededPrefill` ⇒ ref and
`partnerChosen` mount **false**. In-session Find a Trade over the intact idea still
scopes via the `receiveIds.length > 0` clause (`calc:1288`) — server-emitted ideas
always carry receive assets (`trade_service.py:5849-5857`, receive sets of 1-3). An
*edited* give-only reseed (`trades:5813`, snapshot replay) searches league-wide with
the note rendering — the accepted honest corner. The note is hidden while an intact
idea's sides are on the canvas (receive term false).

## Hop 12 — Clear-after-browse (the QA-B-1 counter-case R-10 fixes)

Canvas action-row Clear empties the sides without a remount (`calc:843-848` —
`setGiveIds([])`/`setReceiveIds([])`). Next Find a Trade: ref **false** (seeded
mount), receive empty ⇒ gate false (`:1288`) ⇒ payload `opponent: null` ⇒ league-wide
restart — matching #402's own restart intent (`trades:5654-5657`: an emptied canvas's
Find a Trade "honestly reads as the restart"). The note renders (`:1361` —
`partnerChosen` false, sides empty). Pre-fix, the ref mounted true and this ran a
silent single-team sweep of the seeded counterparty. Session-end paths: the
pass-exhaustion blank restore (`trades:5659`) and `endBrowseSession`'s blank/anchor
restore (`:5676`) carry no `opponentId` and no `seeded`; `initialOpponentId` falls
back to `scopedOpponent` (`canvas:158`) — null after an Anyone search — so nothing
pins back.

## Hop 13 — NB-1 zero-results trace

No `rawTopCard` ⇒ the seeding effect returns early (`trades:5813`) ⇒ no session seed.
The calculator key (`canvas:174` — `` `${canvasKey}-${effectiveOpponentId ?? 'none'}` ``)
changes only if `effectiveOpponentId` changed: a fresh-session Anyone search leaves it
unchanged and the "Anyone" display survives; after a previously *scoped* search the
key steps (`…-<id>` → `…-none`) and the calculator remounts to honest
default-unchosen — note visible (`:1361`), payload still null. In every path the wire
truth and the note agree; only the "Anyone" *label* is pre-search-only (accepted,
PRD NB-1).
