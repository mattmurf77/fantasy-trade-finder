# Code-walk proof — G-413 mobile half (#413)

> D-056 evidence for the mobile client of "Send in Sleeper fails on trades with draft picks".
> Every citation is against the post-change tree on branch
> `feat/fb413-sleeper-send-draft-picks-mobile` (base `51794a35`, the backend tip). Targets are
> PRD §9 W-1…W-5; requirements R-13, R-14, R-15, and the mobile half of R-16. Written 2026-09-02.
>
> Static proof only: no simulator, no Maestro. Runtime proof is the operator's TestFlight
> checklist in PRD §10.

## Table of contents

- [W-1 The four mounts pass mixed arrays unchanged](#w-1-the-four-mounts-pass-mixed-arrays-unchanged)
- [W-2 The two new alert branches](#w-2-the-two-new-alert-branches)
- [W-3 Validate warnings render with zero client change](#w-3-validate-warnings-render-with-zero-client-change)
- [W-4 Comment sites agree with the wire contract](#w-4-comment-sites-agree-with-the-wire-contract)
- [W-5 The 422 reaches analytics with no emitter change](#w-5-the-422-reaches-analytics-with-no-emitter-change)
- [Evidence run](#evidence-run)

---

## W-1 The four mounts pass mixed arrays unchanged

No mount was edited. Each forwards the surface's `give_player_ids` / `receive_player_ids` as-is:

| Mount | Lines | Props |
|---|---|---|
| Deck (TradesScreen) | `mobile/src/screens/TradesScreen.tsx:8351-8355` | `givePlayerIds={topCard.give_player_ids}` / `receivePlayerIds={topCard.receive_player_ids}` |
| Match card, stacked | `mobile/src/components/TradeCard.tsx:978-982` | `data.give_player_ids` / `data.receive_player_ids` |
| Match card, send row | `mobile/src/components/TradeCard.tsx:1000-1004` | same |
| Calculator | `mobile/src/components/InLeagueCalculator.tsx:1467-1471` | `giveIds` / `receiveIds` |

(PRD §9 cites the calculator under `screens/`; the file lives at `components/InLeagueCalculator.tsx`. Same lines.)

`SendInSleeperButton.doPropose` forwards them verbatim into the payload —
`mobile/src/components/SendInSleeperButton.tsx:223-229` (`give_player_ids: givePlayerIds`,
`receive_player_ids: receivePlayerIds`) — and `proposeTradeToSleeper` posts the payload untouched
(`mobile/src/api/sendInSleeper.ts:199-203`). No `draft_picks` request key exists in the send
path: `git grep -n draft_picks -- mobile/src/api/sendInSleeper.ts mobile/src/components/SendIn*.tsx`
→ 0 hits (the 8 `draft_picks` mentions elsewhere in `mobile/src` are the DB *table* name in
`league.ts` / `pickAssignment.ts` / `PickAssignmentScreen.tsx` / `MemberEnteredMarker.tsx` and
CLAUDE.md prose — none is a payload field). Guardrail 6 ("the client never encodes") holds by
absence.

The pick ids in those arrays are the two shapes the server splits on:

- Owned league picks are `{league_id}_{season}_{round}_{original_roster_id}` — the deck's own
  comment and prefix test at `TradesScreen.tsx:4442-4447`; the calculator prices them straight
  from `picksQ.data.all_picks[].pick_id` at `InLeagueCalculator.tsx:493-509` (`id: p.pick_id`).
- Generic rungs are `generic_pick_*` — `backend/pick_values.py:213`
  (`GENERIC_PICK_ID_PREFIX = "generic_pick_"`), and `TradesScreen.tsx:4443-4444` names the same
  prefix as the thing that fails the owned-pick test.

## W-2 The two new alert branches

**Path on this build.** `doPropose` catch (`SendInSleeperButton.tsx:246`) → `body = err.body`
(`:247`) → `track('sleeper_send_failed', …)` (`:254-264`, see W-5) → `code = body?.error`
(`:266`) → the if/else-if ladder starting at `sleeper_not_linked` (`:269`):

| Order | Condition | Line |
|---|---|---|
| 1 | `sleeper_not_linked \|\| sleeper_expired` → reconnect (`goConnect` at `:277`) | `:269` |
| 2 | `verification_required` → verify (`goConnect` at `:290`) | `:280` |
| 3 | `sleeper_rejected` | `:293` |
| 4 | `sleeper_unconfigured \|\| feature_disabled` | `:298` |
| 5 | `roster_not_found \|\| opponent_roster_not_found` | `:300` |
| **6** | **`sleeper_pick_unmapped`** (new) | **`:305`** |
| **7** | **`sleeper_pick_not_owned`** (new) | **`:316`** |
| 8 | catch-all `else` → `detail \|\| 'Something went wrong sending to Sleeper. Please try again.'` | `:323-327` |

Both new branches sit after `roster_not_found` and before the catch-all, per LLD §8.1 — so a
422 reaches exactly one `Alert.alert`, never two.

**Count, never render.** Each branch computes
`const n = Array.isArray(body?.picks) ? body.picks.length : 0` (`:311`, `:318`) — the same idiom
as the MFL twin's `mfl_asset_unmapped` branch (`SendInMflButton.tsx:141-146`, `body.unmapped.length`).
The template strings at `:314` and `:321` interpolate only `n`; no element of `picks[]` appears
in any string. With an old server that omits `picks`, `n = 0` and `${n || 'Some'}` degrades to
the server's own "Some draft picks …" sentence.

**No reconnect.** `goConnect` appears exactly six times in the file: `:215` (its definition),
`:277` and `:290` (the two auth branches' buttons), `:330` and `:426` (the `doPropose` /
`onPress` `useCallback` deps arrays), and `:422` (the up-front "Connect Sleeper first" alert in
`onPress`). Neither new branch (`:305-322`) names it. Neither reads `detail`
(`:267`) — the sentence is pinned, not server-supplied.

**Exact strings shipped** (title `Couldn’t send` on both):

- unmapped: `${n || 'Some'} draft pick${n === 1 ? '' : 's'} in this trade couldn’t be matched to a pick in this Sleeper league, so nothing was sent. Generic picks like “Early 1st” can’t be sent — use a specific pick.`
- not-owned: `${n || 'Some'} draft pick${n === 1 ? '' : 's'} in this trade ${n === 1 ? 'has' : 'have'} already changed hands, so nothing was sent. Rebuild the trade and try again.`

Rendered, n = 1: "1 draft pick in this trade has already changed hands, so nothing was sent. …";
n = 2: "2 draft picks in this trade have already changed hands, …"; n = 0: "Some draft picks in
this trade have already changed hands, …" — the server's sentence verbatim.

**Fielded-build path (builds without these branches, i.e. every TestFlight build before this
one).** The same 422 walks the pre-change ladder (`:269-304` unchanged) and lands in the
catch-all at `:323-327`, which renders `detail` when present. The backend sets
`detail == message` on both refusals (`backend/server.py:16263-16273`), so a fielded build shows
the server's sentence — "Some draft picks in this trade couldn’t be matched …" / "… have already
changed hands …" — instead of "Please try again". This is Guardrail 9's consumer.

## W-3 Validate warnings render with zero client change

`confirmSend` (`SendInSleeperButton.tsx:336-367`; no lines changed — the block moved down 18
lines because the branches above it grew) calls `validateTradeSend` with the same mixed arrays
(`:338-343`), then:

- `if (warnings.length > 0)` (`:346`) — any non-empty list, code-agnostic;
- `blocking = warnings.some((w) => w.severity === 'blocking')` (`:347`);
- title `blocking ? 'This trade will likely fail' : 'Heads up before sending'` (`:349`);
- body `warnings.map((w) => \`• ${w.message}\`).join('\n\n')` (`:350`) — the server's `message`
  string, never the `code`;
- buttons Cancel / Send anyway (`:351-354`).

`validateTradeSend` (`sendInSleeper.ts:227-238`) returns `res.warnings` as-is (`:235`), typed
`TradeSendWarning { code: string; severity; message }` (`:214-218`). `code` is an open `string`,
so `asset_unmapped` / `pick_moved` type-check today with no interface change. The server emits
both with `"severity": "blocking"` (`backend/server.py:27860`, `:27866`), so a pick-only failure
titles "This trade will likely fail" and lists the server's pick sentence. R-15 satisfied by
inspection; nothing in `confirmSend` was "improved".

## W-4 Comment sites agree with the wire contract

| Site | Line | Text |
|---|---|---|
| `SendInSleeperButton.tsx` | `:252-253` | `Closed enum: 14 server codes ∪ network \| timeout \| unknown = 17 values, forever.` |
| `sendInSleeper.ts` header | `:5-7` | `(sleeper_not_linked \| sleeper_expired \| sleeper_write_failed \| sleeper_unconfigured \| feature_disabled \| sleeper_pick_unmapped \| sleeper_pick_not_owned)` |
| `sendInSleeper.ts` `TradeSendWarning.code` | `:215` | `league_archived \| player_moved \| roster_limit \| roster_not_found \| asset_unmapped \| pick_moved` |
| `sendInSleeper.ts` `ProposeTradePayload` (LLD §8.2 "may say so") | `:28-29` | `players AND FTF pick ids I send (#413: server encodes picks)` / `… I receive` |

Cross-check against the backend's shipped comment sites (unedited by this half):
`backend/analytics_taxonomy.py:1056-1057` ("… 17 values"), `docs/cross-client-invariants.md:827`
("closed 17-value enum … 14 server codes … ∪ three client-only values", and the validate
vocabulary listing `asset_unmapped · pick_moved`), and
`docs/business/analytics/2026-08-11-p0-7-addendum.md:72-74` ("17 values … 15 → 17 on
2026-09-02"). `git grep -n "15 values" -- mobile/src backend/analytics_taxonomy.py docs/cross-client-invariants.md docs/business/analytics/2026-08-11-p0-7-addendum.md` → 0 hits.

No TypeScript type changed (`npx tsc --noEmit` clean; `git diff` on `sendInSleeper.ts` is
comment-only).

## W-5 The 422 reaches analytics with no emitter change

`track('sleeper_send_failed', …)` at `SendInSleeperButton.tsx:254-264` runs **before** the ladder
and reads:

- `error_code: err.isTimeout ? 'timeout' : (body?.error ?? 'unknown')` (`:256-258`) — so a 422
  whose body is `{"error": "sleeper_pick_unmapped", …}` (`backend/server.py:16267`) or
  `{"error": "sleeper_pick_not_owned", …}` (`:16272`) emits that exact string;
- `status: err.status` (`:259`) → `422`;
- `kind: body?.kind ?? null` (`:260`) → `null` (neither 422 body carries `kind`).

The emitter is untouched; the two new values arrive through the existing `body?.error` read, which
is why the change is a taxonomy change (R-16) and not an instrumentation change. The four
"17 values" sites are listed under W-4.

## Evidence run

Run from the worktree on 2026-09-02, all static (D-056):

| Check | Result |
|---|---|
| `cd mobile && npx tsc --noEmit` | clean |
| `node mobile/tests/check-send-button-platform.js` | all green — 4 new PASS lines (7, 8, 7b, 7c) |
| Full guard set (`for f in tests/check-*.js`) | 89 ran, 0 FAIL |
| `bash mobile/scripts/testid-lint.sh` | OK (no testIDs added or changed) |

Sabotage cycle for the new checks — each applied to `SendInSleeperButton.tsx`, run, and reverted
from a saved copy (file confirmed byte-identical after):

| # | Sabotage (PRD §7.4 / LLD §8.3) | RED on |
|---|---|---|
| S1 | delete the `sleeper_pick_unmapped` branch | 7 (`…unmapped has its own Alert branch`) + 7b |
| S2 | delete the `sleeper_pick_not_owned` branch | 8 (`…not_owned has its own Alert branch`) + 7b |
| S3 | move the not-owned branch below the catch-all `else` (a second `if`) | **7b only** — 7/8 stay green, which is the point: presence is not reachability |
| S4 | fold `sleeper_pick_not_owned` into the `sleeper_not_linked \|\| sleeper_expired` reconnect condition | 8 (branch references `goConnect`) |
| S5 (extra) | keep the dedicated unmapped branch but add a `Connect → goConnect` button | 7 |
| S6 (extra) | swap the catch-all copy for `'Please try again.'` | 7c |
