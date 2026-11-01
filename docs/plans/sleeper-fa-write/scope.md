# Feature Scope — Free-agent moves in the app at launch (D1): Sleeper first, MFL and ESPN server-only after

> **The operator, 2026-11-01, verbatim:** "For free agents the instructions should not exist. The expectation is the we create the transactions on behalf of the user."
>
> So **D1**, the app itself submitting free-agent add/drop and waiver claims on the user's behalf, moves from post-launch to **launch (2026-11-18)**. Sleeper goes first. MFL and ESPN follow in Update 1, server-only, if their write paths cover free-agent moves (§E).
>
> **This is a launch delta, not a new spec.** The D1 spec is `consent.md` on PR #351 (aliases below). Everything in it stands unless §A says what changes. Read it with `git show origin/plan/sleeper-fa-deeplink:docs/plans/sleeper-fa-deeplink/consent.md`.
>
> - Copied from [`docs/templates/feature-scope.md`](../../templates/feature-scope.md). Every section is answered or waived with a reason. Template sections keep their numbers (§1–§5); the launch material is lettered (§A–§D before them, §E–§I after).
> - Docs only. Nothing here changes code, reads production, calls Sleeper, ESPN or MFL, or flips a flag.

**Sources and labels.** Anything not on `origin/main` carries its branch and sha.

| Alias | What | Where |
|---|---|---|
| **consent.md**, **#351 scope.md**, **prd.md**, **feasibility.md** | The D1 spec: connect → consent → move, the route, refusals, tables, events, AC-19..AC-40 | `origin/plan/sleeper-fa-deeplink` @ `b6455ae6`, `docs/plans/sleeper-fa-deeplink/` (PR #351, draft). **Not on origin/main** |
| **capture.md** | Capture prep: what's known (§1), Q1–Q12 with Q7a/Q7b (§2), what the build needs (§7), risks (§8) | commit `3b77886f`, `docs/plans/sleeper-fa-write/capture.md`, on platforms-eng's branch `plan/sleeper-fa-write`. **Not pushed.** It lands in this folder |
| **R15** | legal-lead's consent rules R15.1–R15.8 | `/Users/teresadickens/ftf-worktrees/org-bringup/docs/plans/org-bringup/leads/legal-lead.md:736-890`. An untracked records file, cited by path only |
| **sizing** | platforms-eng's 10-31 D1 sizing | `/Users/teresadickens/ftf-worktrees/org-bringup/docs/plans/org-bringup/reports/platforms-eng.md:37-39`. Untracked |
| **#379** | The shared external opener and the D2 "Get Sleeper" alert | `build/open-external-helper` @ `b362b4f8` (draft) |
| **#509** | The claim sheet opens the Sleeper app, CTA only | `build/b3-claim-handoff` @ `d14b7308` (open; being trimmed to CTA-only) |
| everything else | | `origin/main` @ `84c4c448` |

**Date:** 2026-11-01
**Entry point:** direct ask from the operator (2026-11-01), routed to `platforms-pm`. Written by a `platforms-pm` spec worker.
**Builder:** `platforms-eng` under `head-eng`: the dark client for the 2026-11-06 binary, then the server after the capture. Not started.
**Operator sign-off on waivers:** two waivers, both the dead D-056 sections (§3 Maestro delta, §5 Simulator-gate tier). They are standing D-056 waivers, not choices. They're surfaced with this PR. The operator decisions this block needs are in §F.

---

## Contents

- [A. What changes from consent.md](#a-what-changes-from-consentmd)
- [B. Product calls (platforms-pm, 2026-11-01)](#b-product-calls-platforms-pm-2026-11-01)
- [C. States](#c-states)
- [D. Timeline and cut lines](#d-timeline-and-cut-lines)
- [1. Analytics scope](#1-analytics-scope)
- [2. Schema & flag scope](#2-schema--flag-scope)
- [3. Evidence scope](#3-evidence-scope)
- [4. Docs scope (MANDATORY — HLD / LLD / API)](#4-docs-scope-mandatory--hld--lld--api)
- [5. Ship gate declaration](#5-ship-gate-declaration)
- [E. Platform scope](#e-platform-scope)
- [F. Decisions needed](#f-decisions-needed)
- [G. Copy needed](#g-copy-needed)
- [H. Risks](#h-risks)
- [I. What could not be verified](#i-what-could-not-be-verified)

## A. What changes from consent.md

| consent.md (@ `b6455ae6`) | At launch (this block) |
|---|---|
| Header `:3`: **post-launch**; the 11-06 binary ships only the hand-off | **Launch.** The client ships dark in the 11-06 binary. The server follows the capture. The flip is ~11-12..14 for add/drop and ~11-16 for claims (§D) |
| §2 `:71`: `faWriteGate({flagOn, …})`, and the client gates on `sleeper.fa_write` | The client **reads no flag**. A pure `faMoveGate({mode, connect, consentValid, ticked})` takes the server's per-league capability `move` (§B1) |
| §2.1 `:77` and prd.md §4.2 `:199-220`: hand-off mode = clipboard + steps block + Open in Sleeper | **Steps and clipboard dropped** (operator, 11-01). Hand-off = the single CTA "Open in Sleeper to claim", as #509 ships it (`ClaimSheet.tsx:304-310` today) |
| §2.1 `:77`: "Flag off (or the route answers 404)" | `move.mode = 'handoff'`, or 404 `feature_disabled` from the move route |
| §2.2–§2.4 `:90-135`: D10 named CTA, visual spec, "Do it in Sleeper instead" | **Unchanged.** "Do it in Sleeper instead" (`s351.secondary`, approved) now ships at launch |
| §2.3 `:119`: "Recoverable failure (network or 5xx): the reason plus **Try again**" | **Narrowed.** Try again only when nothing was provably sent. Every after-send failure is **outcome unknown** (§B5, state 12) |
| §3 `:156`: `POST /api/league/free-agents/add` | **`POST /api/league/free-agents/move`**. The platform comes from the league row (§B3) |
| §3 `:160`: order of checks | **Kept**, with three steps added: platform resolution, the per-platform kill switch, and the `attempt_id` lookup (§B3) |
| §3 `:164-175`: refusal table with `sleeper_*` codes | **Kept**, with `sleeper_*` → `{platform}_*`. New: `{platform}_outcome_unknown` (502), `move_in_progress` (409), `move_kind_changed` (409). Every body has `detail = message` plus an optional server `title` |
| §3 `:177`: success reports `mode` (`add` \| `claim`) | The field is renamed **`move_kind`**, so `mode` means only the capability. It adds `league_platform` and server-authored `title` / `lines` |
| §3 `:178`: kill switch `sleeper.fa_write` | **`sleeper.send_add_drop`**, named by release-lead (capture.md §7 item 4, `:333-337`). It supersedes `sleeper.fa_write` and is **server-only** |
| §3 `:179`, §9 `:501-506`: D6 | Restated for launch in §5 |
| §4.1 `:221`: consent texts stored in `mobile/src/utils/sleeperConsentCopy.ts`; guards S19 and S22 | **Server-authored.** Texts are keyed by (platform, `copy_version`, locale) in the backend, and the client echoes `copy_version` back. S22's hash pin moves to a backend test. S19 becomes "the client holds no consent text" (§B4) |
| §4.1 `:187-214`: v1 / v2 texts, which version ships with what | **Unchanged.** Legal-final (R15.8 `:858-875`). Referenced, not rewritten |
| §4.2 `:224-238`: mechanics | **Unchanged.** Validity is keyed by (user, platform, `platform_user_id`) |
| §4.3 `:240-285`: the two append-only tables | `platform` is required (closed set). `sleeper_transaction_id` → `platform_transaction_id`. `attempt_id` is unique for the send. `result` gains `unknown`. **Append-only kept** (§2) |
| §4.4 `:306-309`: `GET`/`DELETE /api/sleeper/write-consent` | **`GET`/`DELETE /api/platform-write-consent?platform=sleeper`**. The Settings "Stop roster moves" row shows **only while a grant is active**, server-driven |
| §5 `:311-326`: after the move | **Kept.** One invalidation refreshes the FA list, drop list and FAAB. **K-F5, reduced (trades-pm, 11-01):** the held page is discarded and the server saves the roster before answering, so the next search drops B; cards already on screen keep B until then (§B10) |
| §6 `:328-362`: seven granted `sleeper_fa_*` events | **Renamed `fa_move_*`** with `league_platform`, plus `outcome_unknown`: **granted 2026-11-01 (`analytics-lead`)** with C1–C6 (§1) |
| §7 `:364-391`: AC-19..AC-40, post-launch | **At launch.** AC-20, AC-29, AC-30, AC-33, AC-35 and AC-40 change, and AC-41..AC-48 are added (§3) |

## B. Product calls (platforms-pm, 2026-11-01)

Decided by `platforms-pm` on 2026-11-01. The operator's open decisions are in §F.

**B1. The server decides, and the client is platform-neutral.**
- The 11-06 binary ships the whole flow dark. The client never reads a flag. It reads a per-league capability that the server adds to `GET /api/league/free-agents` (route `server.py:36253`; contract docstring `:36256-36311`):

```
"move": {
  "mode":            "submit" | "handoff" | "unsupported",
  "claims":          bool,
  "league_platform": "sleeper" | "mfl" | "espn" | null,
  "connect":         "ok" | "not_linked" | "expired" | "unverified" | "other_account",
  "consent_until":   "<ISO-8601 UTC>" | null,
  "copy":            { …server-authored pre-tap strings, §G… }
}
free_agents[i].move_kind: "add" | "claim" | null    // null = unknown (capture Q8)
free_agents[i].move_mode: "handoff"                 // optional per-row override: a waiver player while claims are off, or a row under §B6's double-move block
```

- **What each mode shows.**
  - `submit` shows the in-app flow (§C).
  - `handoff` shows "Open in Sleeper to claim" with no steps. It is Sleeper-only, because the only hand-off the binary has is #509's Sleeper opener.
  - `unsupported` keeps today's `NO_ADD_REASON` alert (`ClaimSheet.tsx:67-100`).
- **How the server computes `mode`.** It uses the league's platform (from the league row: `is_linked_platform_league`, `database.py:10593`, as the route does at `server.py:36399-36406`), that platform's kill switch, and whether that platform's captured write shapes are in the code.
- **A 404 `feature_disabled` from the move route also drops the client to hand-off.**
- **`connect: 'other_account'`** (ux-lead F3) means the connected platform account doesn't own a team in this league. It is in the closed set **now**, so the 11-06 binary carries it. **Unknown `connect` values fall back to the plain connect step (3), never to Ready.**
- **Old server or unknown values.** If `move` is absent or `mode` is unknown, the client behaves exactly as today. Hosts route Add by `resolveAddPlatform` (`FreeAgentsScreen.tsx:78-85`, `UsageTrendsScreen.tsx:287-290`), so the 11-06 binary is safe on the current server.
- **Hosts route Add by `move.mode` first.** So MFL and ESPN leagues can open the sheet in Update 1 with no build. In Update 1 the server also fills `roster_capacity`, `waivers` and `drop_candidates` for those leagues (Sleeper-only today, `server.py:36446-36485`).
- **Result:** Sleeper flips with **no build**, and MFL and ESPN light up in Update 1 **server-only**.

**B2. Kill switches.**
- **`sleeper.send_add_drop`**: default `false`. It is never in mobile `LAUNCHED_FLAG_DEFAULTS` (`mobile/src/state/useFeatureFlags.ts:60`), and nothing in `mobile/src` reads it.
- **The flip is the operator's**, under D6 as restated for launch (§5).
- **MFL and ESPN get their own server-side keys in Update 1**: `mfl.send_add_drop` and `espn.send_add_drop`. They pair with the per-platform send flags (`trade.send_in_sleeper`, `trade.send_in_mfl`, `espn.send`: `config/features.json:54-55`, `:117`).
- **The durable prod flip is the `FTF_FLAGS` env var on Render.** Precedence is defaults → `config/features.json` → `FTF_FLAGS` (`backend/feature_flags.py:1274-1281`), so the env value beats the file.

**B3. The route is platform-neutral.**
- **Route:** `POST /api/league/free-agents/move`. It supersedes consent.md's `/add`.
- **The platform comes from the league row server-side, never from the client.** A client-sent platform field is ignored.
- **Request body:** `{league_id, add_player_id, drop_player_id?, move_kind, faab_bid?, consent?: {copy_version, locale}, attempt_id}`.
  - Player ids are FTF's canonical (Sleeper) ids from the FA read. MFL and ESPN crosswalk them server-side, as their trade sends do.
- **Order of checks** (consent.md §3 `:160`, with three steps added):
  1. test-mode fail-closed (599);
  2. **any** `*.send_add_drop` on? If not, 404 `feature_disabled`;
  3. session and `_verified_write_denial` (`server.py:2830`);
  4. body (missing `attempt_id` → 400 `bad_request`);
  5. **league platform from the league row**;
  6. **that platform's kill switch** (404 `feature_disabled`);
  7. **`attempt_id` lookup**, then **the double-move block** (§B6);
  8. credential;
  9. consent: the grant is committed before any platform call (R15.8 `:855`);
  10. pre-write reads, under a preflight budget (§B5);
  11. the claim gate (§B7) and the `move_kind` check;
  12. the write;
  13. the move record.
- **Consent routes are platform-parameterised:** `GET`/`DELETE /api/platform-write-consent?platform=sleeper`. `platform` is validated against `sleeper | mfl | espn`.
- **Codes.** consent.md's refusal table (`:164-175`) is kept, with each platform-specific code generalised: `{platform}_not_linked`, `_expired`, `_unconfigured`, `_rejected`, `_write_failed`, and the new `_outcome_unknown`. The client maps them **by suffix**, so a new platform needs no build. Every error body carries `detail = message`.

**B4. Server-authored copy.**
- **Consent text** and **every result title and message** come from the server.
  - Consent text comes from the consent `GET` and from the 409 `consent_required` body, with its `copy_version` and `locale`.
  - The client echoes `{copy_version, locale}` back, so the grant row records which text was shown.
- **The client bakes in only neutral fallbacks**, and **never consent text**. If no server consent text has arrived, the client goes to hand-off rather than show consent.
- **Why:** legal's launch minimum lands ~11-04, marketing's words come later, and MFL and ESPN need their own wording. None of that should need a binary.
- Copy lives in one backend module, deploys with the server, and is pinned by test (§3).

**B5. Outcome unknown reuses the #513/#527 pattern.**
- **Server.**
  - A post-send timeout, reset, 5xx, or unreadable 2xx is `{platform}_outcome_unknown` (502), classified by `backend/write_outcome.py` (`OUTCOME_UNKNOWN` `:46`, `request_never_sent` `:55`). The response is built the way `_send_write_failed` does it (`server.py:24615-24636`).
  - It is never retried. The move row records `result = 'unknown'`.
- **Sleeper today is not outcome-safe.** `sleeper_write._post_graphql` maps every `URLError` to `kind="network"` and lets post-send socket errors escape (`backend/sleeper_write.py:364-376`). The build routes the new Sleeper ops through `write_outcome.py`, which today serves ESPN and MFL only (`write_outcome.py:3`).
- **Preflight budget.** The move core gets one, like `_SEND_PREFLIGHT_BUDGET_S` (`server.py:24639-24655`), so a write never *starts* after the client may have given up.
- **Client.**
  - The request timeout = the move core's server worst case + 15 s margin, built the way `PLATFORM_SEND_TIMEOUT_MS` is (`mobile/src/api/sendOutcome.ts:48-67`). The worst case is summed per provider call once the capture fixes the calls.
  - Recognition follows `isSendOutcomeUnknown` (`:99-106`), plus the new codes.
  - The state says check the platform before resending (title 8i "Check before resending", `mobile/src/utils/sendOutcomeCopy.ts:9`) and offers **Open in Sleeper**. It **never offers a retry.**
  - **Offline at the tap is "not sent", not "unknown"** (ux-lead A3/F6). The client reads NetInfo (already a dependency) before sending. If it's offline, it shows state 11 and sends nothing. Status 0 after the request has started stays state 12.
    - **[pm]** An offline tap mints **no `attempt_id`** and fires **no `fa_move_write_*` event**, because it isn't an attempt. That keeps analytics C4's read clean: `network` with status 0 means a failure after the request went out.

**B6. Idempotency.**
- `attempt_id` is a client UUID, **one per tap**, and already required by analytics F3 (consent.md `:351`).
- The move's `sent` record is written **before** the platform call, under a unique `attempt_id`.
- **A repeat request with the same `attempt_id`:**
  - returns the recorded result if there is one;
  - if the first is still in flight, answers 409 `move_in_progress`, which the client treats as outcome unknown;
  - **never writes twice.**
- **How, keeping consent.md's append-only rule** (`:242`): two rows per move, `phase ∈ sent | result`, unique on (`attempt_id`, `phase`).
  - `eng-architect` may instead choose a single row with its result set once. If so, `legal-lead` confirms that the R15.3 evidence still holds, before the build.
- **The double-move block: ux-lead F1, adopted [pm] as a requirement.** It's server-only and needs no build. It stops a double move from a new tap after state 12, from an app killed mid-send, and from any claim.
  - **(a) The block.** Say a move for the same (user, league, add player) has a `sent` row with no `result`, or `result = 'unknown'`, within the last **15 minutes**. Then the route answers **409 `move_in_progress`** to a new attempt, and the client shows state 12.
  - **(b) The row override.** The capability sets that row's `move_mode: 'handoff'`, with a server line along the lines of "a recent move wasn't confirmed, check Sleeper".
  - **[pm] Claims.** The same block applies while FTF holds a **pending** claim for that player. It lasts until a later result is recorded, or until the league's next waiver run when that's known, otherwise 24 h.
    - It reuses `move_in_progress`: no new code, so analytics C3's 21-value set is unchanged.
    - The server-authored copy says a claim is already pending.

**B7. Claims at launch: in scope, gated exactly as R15.8 D5 says** (`:851`).
- Claims need **both** the current copy at `sleeper-roster-moves-v2` **and** the claim shape captured (capture.md Q3).
- **Until both hold:**
  - `move.claims = false`;
  - a waiver player gets per-row `move_mode: 'handoff'` when the server can tell pre-tap (capture Q8);
  - otherwise the route answers 422 `waiver_claim_unsupported` → hand-off.
- **Added by `platforms-pm`, from D10(a)/(c):** the request carries the `move_kind` the CTA named. The server **never sends a different kind** than the button showed. A mismatch (the player went on or off waivers) is 409 `move_kind_changed`: nothing is sent, and the sheet re-reads.
- **If waiver status can't be read before the tap** (Q8), `claims` stays `false`.
- **Sequence:** add/drop can flip first (~11-12..14), claims later (~11-16), server-only.

**B8. Consent stays as R15 plans it** (consent.md §4.2–§4.4):
- per account (D11);
- the box is unticked by default;
- a server-enforced rolling 7 × 24 h window;
- append-only tables;
- withdrawal as easy as consent.

The Settings › Leagues "Stop roster moves" row shows only while a grant is active, driven by the consent `GET`. **Legal's launch minimum arrives via `head-bizops` by ~11-04 and folds in.** It is an open input (§F).

**B9. Analytics.** consent.md's events and conditions stand (F1–F5, G-rules), renamed `fa_move_*` with `league_platform`, plus `outcome_unknown`. **Granted 2026-11-01 (`analytics-lead`)** with C1–C6 (§1). Build to `fa_move_*`.

**B10. K-F5, the deck after a move: answered by `trades-pm`, 2026-11-01** (cited at `origin/main` @ `84c4c448`).
- **What ships.** It's in the 11-06 binary, in a **reduced form**: after a completed move, the **next search** no longer offers the dropped player (B). Cards already on screen keep B until that search.
- **Client, in the 11-06 binary.**
  - `platforms-eng` adds `/api/league/free-agents/move` to `discardsDevicePages` (`mobile/src/utils/devicePage.ts:253-256`), with an assertion in `mobile/tests/check-device-first-page.js`, in the claim-sheet PR.
  - `trades-eng` reviews that file, because it is the 200 ms held-page path. `head-eng` confirms who builds it.
  - **The move request must go through the shared API client.** Its `_noteWrite` (`mobile/src/api/client.ts:418-425`, called at `:657` and `:674`) discards the held page on any non-GET request. Guard F13 pins this (§3).
  - The claim sheet fires no extra event or hook. Clearing the held page on a pending or failed move is harmless.
- **Server, built with the route.**
  - **Save the roster before answering.** On `status: complete`, the route saves the user's new roster (B off, A on) **before it answers**, because the phone drops its held page when the request finishes.
  - **Then stamp, off the request thread.** It calls `roster_refresh.stamp` off the request thread (`backend/roster_refresh.py:95-141`; call rules at `backend/roster_snapshot.py:321-333`).
    - The deck serve computes its fingerprint from the stored roster (`backend/server.py:6950-6968`), so a deck built on the old roster stops matching.
    - The stamp also cancels that league's old deck jobs (`server.py:14075-14093`).
  - **Pending, failed and outcome-unknown moves don't touch the roster.** A claim that clears later is picked up by the normal session-start roster refresh.
- **Cards already on screen** keep B until the next search. That is the display half of W-AC-L5 the operator waived (I-1 runs log-only), and it's the same as a drop made in Sleeper itself.
  - A send that includes B is still refused by the live roster read (`server.py:24697`).
  - A Like on that card may still record (AC-6b is post-launch).
  - Removing the card in place comes with strict mode.

## C. States

**For `ux-lead` and `design-lead`.** This is the full set the **11-06 binary must carry**, including claims and the `{platform}_*` suffix mapping, so that claims, MFL and ESPN can light up with no build.
- The user-facing text column gives **intent**, not final words (§G).
- **ux-lead's flow verdicts (2026-11-01) are folded in.** Source: `/Users/teresadickens/ftf-worktrees/org-bringup/docs/plans/org-bringup/reports/ux-lead.md` `:34-176` (untracked). They are recommendations, **pending the operator's approval**:
  - answers A1–A5 (`:43-92`);
  - per-state conditions (`:94-122`);
  - findings F1–F6 (`:124-156`);
  - TestFlight rows FA1–FA6 (`:158-176`, in §3).
- Event names are the granted `fa_move_*` names (§1), shortened here (`connect_shown` = `fa_move_connect_shown`).
  - Every one carries `league_platform` (C1).
  - `error_code` is the platform-free suffix (C2).
  - The hand-off event keeps its full name, `sleeper_handoff_resolved`.

| # | State | Trigger (server code or capability) | What the user sees (intent) | Actions | Event | Sheet after |
|---|---|---|---|---|---|---|
| 1 | **Hand-off** | `move.mode='handoff'`: Sleeper with `sleeper.send_add_drop` off; per-row `move_mode='handoff'` (including §B6's double-move block); 404 `feature_disabled` from the move route; or **the consent text can't be fetched** (ux-lead F4) | Today's sheet (bid, drop) and one CTA, "Open in Sleeper to claim" (`fa-claim.open-sleeper`). **No steps, no clipboard.**<br>Footer: you'll finish this in Sleeper (server line, replacing `ClaimSheet.tsx:312`). The neutral client fallback is **never** "Sleeper doesn't allow apps to submit claims" (`ClaimSheet.tsx:320` on #509), which is false once `submit` is on anywhere.<br>On F4, a line says moves from Fleeced aren't available right now. On the double-move block, the server line says a recent move wasn't confirmed, or that a claim is already pending | Open in Sleeper to claim (#509's opener; #379's D2 alert if Sleeper isn't installed); Cancel | `sleeper_handoff_resolved {target: add}` on the open (#528) | Stays until the open. No refresh |
| 2 | **Unsupported** | `move.mode='unsupported'` (ESPN or MFL until Update 1, Fleaflicker, local/demo), or `move` absent on a non-Sleeper league | Unchanged: the Add is dimmed and the tap shows `NO_ADD_REASON`, byte for byte (`ClaimSheet.tsx:67-100`) | OK | none | No sheet |
| 3 | **Connect** | Pre-tap `move.connect='not_linked'` or `'other_account'`, or any unknown `connect` value; or 409 `{platform}_not_linked` | A connect step in the sheet, saying why: "Connect your Sleeper sign-in to make moves from here" (`s351.connect`, approved).<br>For `other_account` (ux-lead F3), a line says that account isn't in {League}, so connect the one that owns your team | **Connect** opens the platform's connect screen. The sheet is hidden, not destroyed.<br>After a real connect, it comes back **at the next step needed**: Consent (5) if missing, else Ready (6). Bid and drop are intact, and it **never auto-sends** (consent.md `:84-88`).<br>A cancelled or failed sign-in returns to 3 with bid and drop intact (ux-lead F2).<br>**Do it in Sleeper instead** | `connect_shown {reason: not_linked \| other_account}` (`other_account` requested 11-01, §1) | Stays (hidden while connecting) |
| 4 | **Verify** | `move.connect='expired'` / `'unverified'`, or 409 `{platform}_expired`, or 403 `verification_required` | The same step, with **Verify** | As 3 | `connect_shown {reason: expired \| unverified}` | Stays |
| 5 | **Consent needed** (first / lapsed / version / withdrawn) | At the tap, `move.consent_until` is null or past → consent `GET` (text + `copy_version`). Safety net: 409 `consent_required` (carries the same) | The consent step: the server's text for (platform, `copy_version`, locale). v1 is legal-final now (consent.md §4.1); v2 once claims are on. "This move: {CTA label} in {League}." sits above an **unticked** box. Make the move is disabled until it's ticked.<br>**ux-lead A5:**<ul><li>the "This move" line uses the same string and source as state 6's CTA;</li><li>Make the move sits directly under the box, and both are on screen together on an SE;</li><li>ticking never sends;</li><li>the disabled button has a VoiceOver hint.</li></ul>**F5:** a 409 `consent_required` carrying a new `copy_version` re-shows the new text **unticked**, with a "terms changed" line. The tick never carries over | **Make the move** (a fresh tap; sends `consent: {copy_version, locale}`); **Not now** (back to the sheet with bid and drop intact); **Do it in Sleeper instead** | `consent_shown {reason}`; on Make the move, `write_attempted {consent_ticked: true}`; server `consent_recorded` | Stays |
| 6 | **Ready** | `mode='submit'`, connected, consent valid | **The named CTA is the per-move confirmation (D10)**: "Add A, drop B" / "Add A" / "Claim A for $N, drop B", matching the row's `move_kind`. The league is on or beside it. The finality line is always under it. A claim also shows the waiver line and bid. Inside a window: "Adds authorized until {date}" + **Turn off**.<br>**ux-lead:**<ul><li>roster full (`open_slots === 0`) with no drop picked → the CTA is **disabled**, with "Drop a player to make room" (#509's line). 10a is only the safety net;</li><li>a long CTA wraps to two lines and never truncates a name;</li><li>the bid follows note (d);</li><li>#509's pinned-CTA conditions carry over.</li></ul> | CTA; Do it in Sleeper instead; Cancel. **Turn off** closes the sheet and opens Settings › Leagues | none until the tap | Open |
| 7 | **Submitting** | CTA tapped (and online, §B5) | CTA loading, and disabled from tap to result (D10(f)).<br>**Not dismissible** (ux-lead A1): the backdrop, Cancel and the Modal close request do nothing while sending. Cancel shows disabled, not hidden.<br>At ~8 s a "still sending" line appears, and the CTA stays busy (`accessibilityState` busy). The client timeout leads to 12 | none | `write_attempted` | Open |
| 8 | **Added** | 200, `status: complete` | Says exactly what the platform reports: A added, B dropped, in {League}. A partial result is stated as reported (R15.1 `:767-771`, K-F6). Focus moves to the result title, which is announced | **Done** | server `write_succeeded {move_kind: add, result: accepted \| partial}` | Done closes. Refresh (note b). The held trade page is discarded automatically and the server has already saved the new roster (§B10), so the next search drops B. Cards already on screen keep B until then: the display half of W-AC-L5 the operator waived, the same as a drop made in Sleeper. A send including B is refused by the live roster read (`server.py:24697`); a Like may still record (AC-6b post-launch). In-place removal comes with strict mode |
| 9 | **Waiver pending** | 200, `status: pending` | "Claim submitted" for A, bid $N, dropping B **if it clears**, run on the league's waiver schedule (say when, if the server knows). **Never "added".** No cancel line until capture Q7b is verified (R15.8 `:874`) | **Done** | server `write_succeeded {move_kind: claim, result: accepted}` | Done closes. Refresh; the row reads "claim pending" for the session (consent.md §5). The server blocks a second claim on that player (§B6) |
| 10a | **Rejected: roster full** | 422 `roster_full_drop_required` | Pick a player to drop. The drop list is highlighted, scrolled into view, and gets focus. No result screen. A safety net only: state 6 disables the CTA first | Pick a drop, tap again (a new move, not a retry) | `write_failed {error_code, status}` (10a–10g) | Stays |
| 10b | **Rejected: drop gone** | 422 `asset_not_owned` | B (named) is no longer on your roster. The stale selection is cleared | Pick again | as 10a | Stays. Drop list refreshed |
| 10c | **Rejected: player taken** | 422 `player_unavailable` | A was just picked up | **Done** (no retry) | as 10a | Closes. Refresh |
| 10d | **Rejected: over budget** | 422 `waiver_bid_over_budget` (+ `remaining`) | The inline bid error, showing the server's remaining. The user's bid is kept, and the CTA stays disabled until it's fixed | Lower the bid | as 10a | Stays. FAAB from the body |
| 10e | **Rejected: changed** | 409 `move_kind_changed` | A went on (or off) waivers. A line says why the CTA's label changed and that nothing was sent, and focus moves to it | Review the corrected CTA | as 10a | Stays. Re-reads the FA list |
| 10f | **Rejected by the platform** | 502 `{platform}_write_failed` (the platform refused; `detail` is its sentence) | The reason in plain words. Nothing changed (R15.1 rejection line) | **No retry.** Open in Sleeper (secondary); Done | as 10a | Closes on Done |
| 10g | **Unavailable** | 503 `{platform}_unconfigured` | Moves aren't available right now | Open in Sleeper; Done. No retry | as 10a | Closes on Done |
| 11 | **Not sent** | 502 `{platform}_write_failed` with `kind: network` from a definite connect-phase failure (`request_never_sent`), or a pre-write read failure (`kind: roster_read`); or **offline at the tap** (NetInfo; nothing is sent, §B5) | Couldn't reach Sleeper, so nothing was sent | **Try again**, the only retry anywhere (ux-lead A3).<ul><li>It's a fresh tap with a new `attempt_id`.</li><li>Consent isn't asked again, because it was committed before the platform call.</li><li>**Do it in Sleeper instead** sits beside it.</li></ul> | `write_failed {error_code: write_failed, kind: network \| roster_read}` (C6). **[pm]** None when offline at the tap: no attempt, so no `attempt_id` | Stays |
| 12 | **Outcome unknown** | Exactly C4's "couldn't confirm" read: 502 `{platform}_outcome_unknown` (`outcome_unknown`); 409 `move_in_progress`; 500 `internal_error`; the client's timer fired (`timeout`); status 0 (`network`); a 5xx with no usable code (`unknown`, status ≥ 500) | **"Check before resending"** (8i). We couldn't confirm whether the move reached Sleeper; check your roster (or your claims) in Sleeper before trying again. Never "failed", never "try again" | **Open in Sleeper**; Done. **No retry.** The CTA doesn't come back for this player, **including after the sheet closes**: the row is held in hand-off by §B6's block for ~15 min (ux-lead A2/F1) | `write_failed {error_code, status}` with the code in brackets in the trigger cell (C4) | Closes on Done. Refresh (a landed add leaves the list) |
| 13 | **Connection rejected** | 409 `{platform}_rejected`: the platform refused the stored token. The server deletes the credential and appends a withdrawal (`credential_rejected`, consent.md `:300`) | Sleeper turned down Fleeced's connection, so nothing changed. Connect again to make moves | **Connect again (primary**, ux-lead CHANGE) → 3, then 5, with the sheet intact; Do it in Sleeper instead; Done | `write_failed {error_code: rejected}`; server `consent_withdrawn {via: credential_rejected}` | Stays until Done. Capability refetched |
| 14 | **Claims not enabled** | Per-row `move_mode='handoff'` for a waiver player, or 422 `waiver_claim_unsupported` (D5 not met) | This player is on waivers, and claims from Fleeced aren't on yet, so claim in Sleeper. The sheet switches to hand-off (1) with bid and drop kept. A line says why the button changed and that nothing was sent; focus moves to it. On the 422 path the bid field appears empty and unfocused under that line (ux-lead A4) | Open in Sleeper to claim | `write_failed {error_code: waiver_claim_unsupported}` (422 path only); then `sleeper_handoff_resolved {target: add}` on the open (#528) | Stays, in hand-off mode |
| 15 | **Settings: Stop roster moves** | Consent `GET` → `valid: true` | Settings › Leagues: "Roster moves: on until {date}" + **Stop roster moves** (consent.md §4.4; status lines approved, R15.8 `:856`). The row shows only while a grant is active | One tap, no dialog. Then R15.2.6's notice, verbatim. Focus moves to the notice, then the row goes | server `consent_withdrawn {via: settings}` | n/a |

**Notes:**
- **(a) Copy source.** Every title and message comes from the server (§B4). The client's fallbacks are neutral and never include consent text.
- **(b) What refreshes.** One invalidation of `['free-agents', leagueId, *]` (`FreeAgentsScreen.tsx:65`) refreshes all of these together, since they ride on the same read (`server.py:36496-36508`):
  - the FA list;
  - `drop_candidates`;
  - `waivers.faab.remaining`;
  - the `move` capability.

  Usage Trends' FA query is invalidated too. The trade deck is K-F5, reduced form (§B10): the next search drops B.
- **(c) Codes map by suffix.** `_not_linked`, `_expired`, `_rejected`, `_unconfigured`, `_write_failed` and `_outcome_unknown` map by suffix, so MFL and ESPN need no build.
- **(d) The FAAB field: answered by ux-lead A4.**
  - `submit` + add: **hidden**. An add spends no FAAB, and the CTA carries no bid.
  - `submit` + claim: **shown**, and in the CTA.
  - Hand-off (the mode, the per-row override, or state 14): **shown on FAAB leagues**, as today (`ClaimSheet.tsx:189-229`).
- **(e) Everywhere** (ux-lead). VoiceOver focus moves to each new step's title, and results are announced. Each step replaces the sheet's content rather than stacking.

## D. Timeline and cut lines

Sizing is platforms-eng's (sizing `:37-39`).

| When | What | Owner |
|---|---|---|
| 11-01 | D1 pulled to launch; this block | operator; `platforms-pm` |
| **11-02 midday** | This spec and §C to `platforms-eng`; `ux-lead` and `design-lead` review §C | `platforms-pm` → `head-product` |
| **by 11-02** | The capture session (capture.md §4). It is operator-driven: every Sleeper write is the operator's own click, and **each live write needs the operator's approval when it runs** | operator + `platforms-eng` |
| ~11-04 | Legal's launch minimum arrives via `head-bizops` and folds into §G and §5 | `legal-lead` |
| **11-06** | The client goes into the binary, **dark**. It renders from `move` and reads no flag | `platforms-eng` → release-lead |
| capture + ~3–4 days | Server: route, adapter ops, tables, capability, consent routes, tests | `platforms-eng` |
| **~11-12..14** | Flip `sleeper.send_add_drop` for add/drop (the operator's call, under D6 for launch), then the §3 TestFlight checklist straight after | operator |
| **~11-16** | Claims on, if D5 holds (v2 + the claim shape). Server-only | operator |
| 11-18 | Launch | — |
| Update 1 | MFL and ESPN, server-only (§E) | `platforms-eng` |

**Cut lines:**
- **The capture slips past ~11-04.** Sleeper D1 can't flip before launch. The binary still ships dark, and the claim button keeps "Open in Sleeper to claim" (#509). The flip lands later, **server-only, with no build**.
- **The client misses the 11-06 binary.** D1 waits for the next binary, and 11-06 ships #509's CTA-only hand-off.
- **The claim shape isn't captured, or v2 isn't current.** Add/drop flips alone. Claims stay 422 `waiver_claim_unsupported` → hand-off, and light up later, server-only.
- **Legal's launch minimum isn't in by the flip date.** No flip (§5).

---

## 1. Analytics scope

- [x] **(a) New events specced.** **Granted 2026-11-01 by `analytics-lead`**, with conditions C1–C6. consent.md §6's seven events (`:336-344`), granted 2026-10-20 with F1–F5 (`:348-358`) and the G-rules, are **renamed `fa_move_*`**. They also gain a closed prop **`league_platform` ∈ `sleeper` \| `mfl` \| `espn`** (P2), and `outcome_unknown` joins `error_code` (P1).
  - **Never a prop named `platform`.** `user_events.platform` is the device-platform column (`backend/analytics_taxonomy.py:1168-1174`; the NULL-`platform` incident).
  - **Nothing to migrate.** No `sleeper_fa_*` or `fa_move_*` name is registered, emitted or read on `origin/main` @ `84c4c448`. So there is no alias and no series break.

  | Event | Side | Class | Props (granted) |
  |---|---|---|---|
  | `fa_move_connect_shown` | client | NON_INTENT (exposure) | `surface`, `reason` ∈ `not_linked` \| `expired` \| `unverified`, `league_platform` |
  | `fa_move_consent_shown` | client | NON_INTENT (exposure) | `surface`, `reason` ∈ `first` \| `lapsed` \| `version` \| `withdrawn`, `league_platform` |
  | `fa_move_consent_recorded` | server | NON_INTENT | `surface`, `copy_version`, `league_platform` |
  | `fa_move_consent_withdrawn` | server | NON_INTENT | `via` ∈ `settings` \| `disconnect` \| `credential_expired` \| `credential_rejected`, `league_platform` |
  | `fa_move_write_attempted` | client | INTENT | `surface`, `has_drop`, `has_bid`, `consent_ticked`, `attempt_id`, `league_platform` |
  | `fa_move_write_succeeded` | server | INTENT | `move_kind` ∈ `add` \| `claim` (C5), `has_drop`, `has_bid`, `result` ∈ `accepted` \| `partial`, `attempt_id`, `league_platform` |
  | `fa_move_write_failed` | client | INTENT | `surface`, `error_code` (C3), `status` (int), `attempt_id`, `league_platform`, `kind` (C6, only when present) |

  **Conditions C1–C6 (`analytics-lead`, 2026-11-01), in substance:**
  - **C1. `league_platform` is always present, never null.**
    - Client events fire only when `move.mode = 'submit'`, where the capability's `league_platform` is set. A null capability emits nothing (a client test, F15).
    - Server events use the resolved platform.
    - The two consent events use the consent's `?platform=` value. For a grant recorded by the move route, that is the same resolved platform.
  - **C2. `error_code` is platform-free.** It records the suffix (`not_linked`, `expired`, `unconfigured`, `rejected`, `write_failed`, `outcome_unknown`). The platform lives in `league_platform`.
  - **C3. A closed set of 21 values,** enumerated in the addendum and pinned by test against the route's codes:
    - `feature_disabled`, `bad_request`, `verification_required`, `not_linked`, `expired`, `unconfigured`, `consent_required`;
    - `roster_full_drop_required`, `asset_not_owned`, `player_unavailable`, `waiver_bid_over_budget`, `waiver_claim_unsupported`, `move_kind_changed`;
    - `rejected`, `write_failed`, `outcome_unknown`, `move_in_progress`, `internal_error`;
    - `network`, `timeout`, `unknown`.
  - **C4. Record the cause as it happened.** `error_code` is the response's code when it has one. Otherwise it is `timeout` (the client's timer fired), `network` (status 0) or `unknown` (no usable code).
    - **"Couldn't confirm"** (§C state 12) is the defined read: `error_code` ∈ {`outcome_unknown`, `move_in_progress`, `internal_error`, `timeout`, `network`}, or `unknown` with status ≥ 500.
    - State 12's trigger list matches it exactly, and a client test maps each trigger to its (`error_code`, `status`) (F15).
  - **C5.** `write_succeeded`'s `mode` prop becomes **`move_kind`** (`add` \| `claim`), matching the response rename (§A).
  - **C6, taken by `platforms-pm`:** `write_failed` carries `kind`, the server's kind (`network` \| `roster_read`), **only when the body has one**, and is absent otherwise. That keeps state 11 (not sent, the only retry) apart from 10f (the platform refused).

  **Unchanged:**
  - F1–F5;
  - the classes: four NON_INTENT, three INTENT;
  - none is a WAT event.

  **Registration.** The events are registered in `ALLOWED_CLIENT_EVENTS`, `CLIENT_EVENT_PROPS` and `NON_INTENT_EVENTS` **in the emitters' commit**. That commit comes after a dated addendum stating the seams: no history before ship, and MFL/ESPN rows start with Update 1. The test file is `backend/tests/test_analytics_taxonomy_fa_move.py` (§3).

  **Hand-off event.** `sleeper_handoff_resolved` (granted G1–G7, #351 scope.md `:48-64`) **is emitted, by #528** (`feat/sleeper-handoff-resolved` @ `c77a3f72`, draft).
  - The merge order is #379 → #528 → #509. #509 passes `hasDrop` @ `2eb1bf83` (`build/b3-hasdrop`, `ClaimSheet.tsx:164`).
  - So hand-off states 1 and 14 are already instrumented (`target=add`).
  - It keeps its `sleeper_` name, because only Sleeper has a hand-off.

  **Requested 11-01 (`platforms-pm`), not yet granted:** add `other_account` to `fa_move_connect_shown.reason`, for ux-lead F3's `connect: 'other_account'` (§B1).
- [ ] **(b) Existing events cover it.** Not chosen.
- [ ] **(c) WAIVED.** Not chosen.

## 2. Schema & flag scope

- **New tables (two, append-only):** `platform_write_consents` and `platform_write_moves`, as in consent.md §4.3 (`:244-276`), with these deltas:
  - `platform` is **required** in both, from the closed set `sleeper | mfl | espn` (consent.md `:252` let `eng-architect` drop it).
  - `platform_user_id` is the platform account the moves are made as.
  - `sleeper_transaction_id` → **`platform_transaction_id`**.
  - `result` gains **`unknown`**.
  - Moves are recorded under `attempt_id` with `phase ∈ sent | result`, unique on (`attempt_id`, `phase`) (§B6). The `sent` row is written before the platform call.
  - Coverage is unchanged: both join `delete_user_data` / `export_user_data` through `accounts._ADDITIONAL_PRIVATE_TABLES` (`backend/accounts.py:685`) in the same change, and are deleted with the account (R15.8 D12 `:852`, [PRO]).
  - **A bright line: the operator's yes is needed** (§F1).
- **New flag: `sleeper.send_add_drop`.** It supersedes `sleeper.fa_write`.
  - Default `false`. It goes in `config/features.json`, `FLAG_KEYS` (`backend/feature_flags.py:47`), the flag fixtures and `docs/config-reference.md`. It is **never** in mobile `LAUNCHED_FLAG_DEFAULTS`, and **no client reads it**.
  - It gates the move route and the consent routes (404 when off), and makes the capability answer `handoff`.
  - **Graduation:** D6 for launch (§5), then the TestFlight checklist passes. It stays as a permanent kill switch.
  - **Rollback lever:** `FTF_FLAGS` on Render sets it `false`, with no deploy and no build.
  - Update 1 adds `mfl.send_add_drop` and `espn.send_add_drop`, the same way.
- **API surface:**
  - `POST /api/league/free-agents/move` (new);
  - `GET /api/league/free-agents`, contract change: additive `move` and per-row `move_kind` / `move_mode`;
  - `GET` / `DELETE /api/platform-write-consent?platform=` (new; supersede `/api/sleeper/write-consent`);
  - `DELETE /api/sleeper/link` and every credential deletion append a withdrawal (consent.md `:298-301`).
- **New env vars / `model_config` keys:** none.
  - The 7-day window, the consent copy versions, and the move core's preflight budget are code constants.
  - The server-authored copy lives in a backend module and deploys with the server.
- **Native config:** none.

## 3. Evidence scope

- **Maestro delta: WAIVED.** D-056 (2026-08-15) retired Maestro and the simulator entirely. The D-056 evidence below replaces it.
- [x] **Structural guard: new `mobile/tests/check-fa-move.js`** + `npm run test:fa-move`.
  - It's a new file because `check-sleeper-handoff.js` isn't on origin/main yet (it arrives with #509).
  - Its executed sections use the plain-node, stubbed-`react-native` idiom of `check-offer-prefill-330-unit.js`.
  - Each pin names its sabotage:

  | Id | Pins | Sabotage |
  |---|---|---|
  | F1 | **No client flag read.** `send_add_drop` and `fa_write` appear nowhere in `mobile/src` | Read `flags['sleeper.send_add_drop']` in `ClaimSheet` |
  | F2 | `faMoveGate` truth table, executed: absent or unknown `move` → legacy; `unsupported` → `NO_ADD_REASON`; `handoff` → the CTA; connect and verify beat consent; unticked never submits | Return `submit` for unticked + lapsed |
  | F3 | **No retry in outcome unknown.** That renderer has no Try again and no re-enabled CTA. `isMoveOutcomeUnknown` covers `*_outcome_unknown`, `move_in_progress`, timeout, status 0, `internal_error`, and a code-less 5xx | Add a Try again button to state 12 |
  | F4 | CTA text comes from the capability or state (server `copy` or the row's `move_kind`), with one neutral fallback constant; no hard-coded Sleeper wording in the `submit` branch | Hard-code "Add {name}" in the submit branch |
  | F5 | Refusals map by code **suffix**; `feature_disabled` and `waiver_claim_unsupported` → hand-off | Map only `sleeper_write_failed` |
  | F6 | The move timeout = a server-worst-case constant + margin (the `check-send-timeout.js` pattern) | Use the 15 s default |
  | F7 | The move API has exactly one call site, behind the gate's `submit` / `submit_with_consent` | Call it straight from `onPress` |
  | F8 | The box starts `false`; Make the move's `disabled` includes `!ticked`; the CTA is disabled while sending | Initialise the box `true` |
  | F9 | `attempt_id` is minted once per tap and sent in the body | Mint it per render |
  | F10 | **No steps block and no clipboard write** in `ClaimSheet` in any mode (operator, 11-01) | Re-add `fa-claim.steps` |
  | F11 | Consent text is rendered only from the server payload. No consent literal exists in `mobile/src`. The echoed `copy_version` is the one received | Bake v1 into the client |
  | F12 | A terminal result invalidates the `['free-agents', leagueId]` prefix | Drop the invalidation |
  | F14 | **Analytics C2/C6.** `error_code` is the platform-free suffix from C3's closed set. `kind` is set only when the body carries `network` or `roster_read` | Send `sleeper_write_failed` as the code |
  | F15 | **Analytics C1/C4, executed.** A null capability (or any mode but `submit`) emits no `fa_move_*` event. Each state-12 trigger maps to its (`error_code`, `status`): `outcome_unknown`, `move_in_progress`, `internal_error`, `timeout`, `network`/0, `unknown`/≥500 | Emit with `league_platform: null`; map a timeout to `unknown` |
  | F13 | **K-F5 (§B10).** The move request goes through the shared API client, whose `_noteWrite` (`mobile/src/api/client.ts:418-425`) discards the held page on any non-GET. No direct `fetch` exists in the move path. The claim sheet fires no extra event or hook for it | Send the move with a bare `fetch` |

  | F16 | **State 7 is not dismissible** (ux-lead A1). While sending, the backdrop, Cancel and the Modal `onRequestClose` are no-ops. Cancel renders disabled, not hidden. The CTA carries `accessibilityState` busy. The ~8 s "still sending" line is wired | Let `onRequestClose` close the sheet mid-send |
  | F17 | **Offline at the tap is state 11, and nothing is sent** (ux-lead A3/F6, [pm]). NetInfo is read before the move call. Offline → state 11 with **no request, no `attempt_id` minted, and no `fa_move_write_*` event**. Executed against a stubbed NetInfo | Send anyway and map status 0 to state 12 |

  - **Plus the held-page path:** an assertion in `mobile/tests/check-device-first-page.js` that `discardsDevicePages('/api/league/free-agents/move')` is true. It goes in the claim-sheet PR, reviewed by `trades-eng` (§B10). Sabotage: drop the path from `discardsDevicePages`.

- [x] **Unit tests** (backend; platforms mocked through each adapter's `_opener`; never a live write):
  - `backend/tests/test_fa_move_route.py`:
    - order of checks, behavioural and source-order (sabotage: move the write above consent);
    - a client-sent platform is ignored;
    - refusals parametrized per §C code, asserting `detail == message` and the opener call count;
    - grant committed before the write;
    - **idempotency**: a same-`attempt_id` repeat makes one opener call and returns the same body; an in-flight duplicate gets 409 `move_in_progress`;
    - **outcome unknown**: a post-send timeout, reset or 5xx → 502 `sleeper_outcome_unknown`, one opener call, `result='unknown'`;
    - a connect-phase failure → `kind: network`, "not sent";
    - `move_kind_changed`;
    - a claim refused until v2 **and** the shape is captured;
    - the preflight budget;
    - **K-F5 (§B10):**
      - on `status: complete`, the new roster (B off, A on) is saved **before** the response is returned;
      - `roster_refresh.stamp` runs **off the request thread** (sabotage: call it inline);
      - **no roster write** on a pending, failed or outcome-unknown move.
    - **The double-move block (§B6, ux-lead F1):**
      - a new `attempt_id` for the same (user, league, add player) gets 409 `move_in_progress`, with **no opener call**, in two cases: while a `sent` row has no `result`, and while `result = 'unknown'` is under 15 min old;
      - it is allowed again at 15 min, or once a later result is recorded;
      - a **pending claim** blocks a new claim on that player until a later result, the next waiver run when known, or 24 h;
      - the capability sets that row's `move_mode: 'handoff'` with the server line, in both cases.
  - `backend/tests/test_fa_move_capability.py`: `mode`, `claims`, `connect` and `consent_until` per platform and flag state:
    - Sleeper off → `handoff`; on → `submit`;
    - MFL, ESPN, Fleaflicker and local → `unsupported`;
    - `claims` is false until D5;
    - `FTF_FLAGS` beats the file.
  - `backend/tests/test_platform_write_consent.py`: consent.md §8.1's consent tests (`:412-419`) under the new route names:
    - the window at 7 d − 1 min (valid) and 7 d (invalid);
    - append-only withdrawals;
    - bound to the platform account;
    - a version bump invalidates;
    - the server copy is pinned by hash per (platform, version, locale) (the old S22).
  - **Extended:**
    - `test_sleeper_write.py`: golden bodies from the capture, and the new ops classified through `write_outcome.py`;
    - the flag-parity tests: `sleeper.send_add_drop` defaults false;
    - `test_account_deletion_coverage.py`: automatic, through the tuple;
    - **`backend/tests/test_analytics_taxonomy_fa_move.py`** (new): the seven `fa_move_*` names with exact props, including `league_platform` and `move_kind`; the class split (four NON_INTENT, three INTENT); C3's 21-value `error_code` set, pinned against the route's codes; C6's `kind`.
- [x] **Code-walk proof.** The builder fills this skeleton with file:line citations, in `docs/plans/sleeper-fa-write/code-walk.md`:
  1. Host Add → `move.mode` → sheet, or `NO_ADD_REASON`.
  2. `faMoveGate` → connect, verify, consent or submit.
  3. Consent `GET` → step → `POST …/move` with `consent`.
  4. Server, the §B3 order: test mode → any kill switch → session → body → league platform → kill switch → `attempt_id` → credential → consent (grant committed) → pre-write reads + budget → D5 / `move_kind` → adapter write (`write_outcome` classification) → move rows → on `complete`, save the roster → event → response → `roster_refresh.stamp` off the request thread (§B10).
  5. Client result by `status` / code → the shared client's `_noteWrite` discards the held page → Done → FA invalidation.
  6. Withdrawals: Settings, disconnect, expiry, rejection.
  7. Capability computation per platform.
- [x] **Manual TestFlight checklist** (dummy league; the only runtime evidence mobile gets). **Every real move below is a production platform write.** Each one:
  - needs **the operator's approval when it runs**;
  - uses **the dummy Sleeper league only** (capture.md §4 step 1);
  - is **reversed straight afterwards**: release the added player, re-add the throwaway drop, cancel the claim if Q7b allows (otherwise let it run in the dummy league).

  The flag goes back off (`FTF_FLAGS`) if any step fails.

  | # | Setup | Steps | Expected |
  |---|---|---|---|
  | T1 | Flag **off** | Free Agents → Add on a Sleeper row; then Add on an ESPN or MFL row | Sleeper: "Open in Sleeper to claim", **no steps**, opens Sleeper. ESPN/MFL: `NO_ADD_REASON` unchanged |
  | T2 | Flag on; Sleeper **not connected** | Add → CTA → Connect → sign in | The connect step; back on **the same sheet with bid and drop intact**; nothing sent |
  | T3 | Connected, no consent, an open slot | Add (no drop) → CTA | The consent step with **v1** text and "This move: Add A in {League}."; the box unticked and Make the move disabled. Tick → tap → "added" naming A and the league. Done → A is gone from the list; Sleeper shows A on the roster. Reverse |
  | T4 | Roster full; inside the window | Pick a throwaway drop → CTA | The CTA reads "Add A, drop B" with the league; no consent step; "Adds authorized until {date}". The result names both halves; Done → B is gone from the drop list. Reverse |
  | T5 | Roster full | No drop → tap | No write; the drop list is highlighted; Sleeper unchanged |
  | T6 | Sheet open on A | As commissioner on Sleeper web, add A to another dummy roster → tap in the app | "A was just picked up"; no write; Done → the list is refreshed |
  | T7 | Claims on (v2 current) | A FAAB claim with a $7 bid and a drop | Consent **re-asks with v2** (version bump). The CTA reads "Claim A for $7, drop B", with the waiver line and bid under it. The result says **claim submitted, never added**. Cancel in Sleeper if possible. *With claims off:* hand-off mode, bid and drop kept |
  | T8 | FAAB league | Bid > remaining → tap | The inline error and a disabled CTA (`ClaimSheet.tsx:129`, `:308`). If the server's remaining is lower than the app's, a 422 shows the server's figure; no write |
  | T9 | Connected, consent valid | Tap, then **airplane mode immediately** | **"Check before resending"**; **no Try again**; Open in Sleeper offered. Airplane off → Sleeper shows whether it landed; the list after Done agrees. Reverse if it landed |
  | T10 | Day 8 after T3's grant | Tap | The consent step (lapsed); no write until ticked. (The boundary itself is pinned by the backend test) |
  | T11 | Grant active | Settings › Leagues → **Stop roster moves** | "Roster moves: on until {date}"; R15.2.6's notice verbatim; the row disappears; the next move asks consent again |
  | T12 | Sheet open, flag on | The operator sets the flag **off** in `FTF_FLAGS` → tap | 404 → hand-off mode; nothing sent. Pull to refresh → "Open in Sleeper to claim" |
  | T13 | Connected, grant active | Disconnect Sleeper → reconnect → move | Consent re-asked (withdrawal via `disconnect`) |
  | T14 | After T4's completed add/drop, before reversing | Start a **new** trade search | **No card includes B** |
  | T15 | A trade card that was already on screen showing B before T4 | Send that card | **Send is refused** with the readable message (the live roster read); nothing is sent |

  **ux-lead's rows** (`/Users/teresadickens/ftf-worktrees/org-bringup/docs/plans/org-bringup/reports/ux-lead.md` `:158-176`):

  | # | Setup | Steps | Expected |
  |---|---|---|---|
  | FA1 | **Airplane Mode on** | Tap the CTA | **Not sent (11)** with Try again; nothing sent. Back online, Try again sends with **no consent step** |
  | FA2 | Network Link Conditioner, 3G | Tap; **kill the app** mid-send; reopen and open that player's sheet | The "check Sleeper" line and **no Add or Claim CTA for ~15 min** (§B6). Exactly **one** move in Sleeper. Reverse |
  | FA3 | FAAB league, `submit` mode, a free agent | Open the sheet | **No bid field**; the CTA reads "Add A" or "Add A, drop B" |
  | FA4 | Roster full | Open the sheet | The CTA is **disabled until a drop is picked** |
  | FA5 | Not connected | Connect → cancel the sign-in; then Connect for real | Cancel: back on the connect step with bid and drop intact. Real connect: back **on the consent step** |
  | FA6 | Connected, consent valid | Tap; during Submitting, tap the backdrop and Cancel | Nothing closes. The still-sending line shows at ~8 s |

  **For launch, T14 and T15 supersede consent.md's step 29** (`:475`). There is no in-place card-removal step: cards already on screen keep B until the next search (§B10). `trades-pm` is asking `head-product` to update PRD step L4b to match.

- [ ] **WAIVED.** Not waived.
- **`testID`s** (all static strings, so they pass `testid-lint.sh`):
  - **Added:** `fa-claim.connect`, `fa-claim.consent`, `fa-claim.consent.box`, `fa-claim.make-move`, `fa-claim.do-in-sleeper`, `fa-claim.result`, `settings.roster-moves.status`, `settings.roster-moves.stop` (consent.md #351 scope.md `:226-236`).
  - **Kept:** `fa-claim.open-sleeper`.
  - **Dropped:** `fa-claim.steps`, which never ships.
- **Acceptance criteria.** AC-19..AC-40 move to launch, with these changes:
  - **AC-20:** flag off → `handoff` + 404.
  - **AC-29 / AC-30:** the gate takes `move`.
  - **AC-33:** copy versions are server-side.
  - **AC-35:** replaced by AC-48.
  - **AC-37:** reduced form (§B10). The next search no longer offers B, and cards already on screen keep it until then. Verified by F13, the `check-device-first-page.js` assertion, the K-F5 route tests, and T14–T15.
  - **AC-40:** the seven `fa_move_*` events, per §1 and C1–C6.

  **New:**

  | AC | Criterion | Verified by |
  |---|---|---|
  | AC-41 | The client reads no flag | F1 |
  | AC-42 | The capability is correct per platform and flag; `claims` only under D5; an absent `move` is legacy | `test_fa_move_capability.py`; F2 |
  | AC-43 | The platform comes from the league row; a client value is ignored | route test |
  | AC-44 | One `attempt_id` writes at most once | route test |
  | AC-45 | An after-send failure → `{platform}_outcome_unknown`, no retry anywhere | route test; F3; T9 |
  | AC-46 | Consent and result copy are server-authored; `copy_version` is echoed and recorded | consent test; F11 |
  | AC-47 | A claim is never sent from an add-labelled CTA (`move_kind_changed`) | route test |
  | AC-48 | No steps or clipboard on the claim sheet | F10 |

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated (by the build)** | `POST /api/league/free-agents/move` (body, order of checks, the §C codes, success). The `GET /api/league/free-agents` row (`:1083`) gains `move` and per-row `move_kind` / `move_mode`. `GET` / `DELETE /api/platform-write-consent`. `DELETE /api/sleeper/link` appends a withdrawal |
| `docs/data-dictionary.md` | **updated (by the build)** | `platform_write_consents` and `platform_write_moves` (§2), user-keyed and deleted with the account |
| `docs/config-reference.md` | **updated (by the build)** | `sleeper.send_add_drop`: default false, what it gates, D6 for launch, the `FTF_FLAGS` flip, never in `LAUNCHED_FLAG_DEFAULTS`, server-only. `sleeper.fa_write` is recorded as never shipped |
| `docs/integrations/sleeper.md` | **updated (by the build)** | §1.2 GraphQL ops (and its endpoint count), §3.3 the captured shapes (redacted per capture.md §5), §4 the new error modes including outcome unknown |
| `docs/integrations/mfl.md`, `espn.md` | n/a now | Update 1, when their free-agent writes are verified (§E) |
| `living-memory/LLD.md` | **updated (by the build)** | Two conventions: (1) on-behalf platform writes need a server-enforced, versioned, time-boxed consent record checked before the write call; (2) **a server-decided capability drives client behaviour for platform writes, and the client never reads the kill switch** |
| `docs/architecture.md` | **updated (by the build)** | Module rows: the `sleeper_write.py` ops, and `write_outcome.py` now serving Sleeper. Route wiring: `…/move` → league platform → per-platform adapter, then on a completed move the roster save and an off-thread `roster_refresh.stamp` (§B10). The FA read's capability |
| `living-memory/HLD.md` | **updated (by the build)** | The platform-neutral write seam counts: one route dispatching to per-platform adapters, plus a server-decided client mode that lets new platforms light up server-only. `eng-architect` may downgrade it to n/a if it judges this a convention, not a shift |
| `docs/cross-client-invariants.md` | **updated (by the build)** | The consent `copy_version` strings (`sleeper-roster-moves-v1` / `-v2`) and the `move.mode` / `move_kind` enums |
| `docs/glossary.md` | **updated (by the build)** | **Write consent**; **move capability** (`move.mode`) |
| `DECISIONS.md` | **updated (by the build)** | A new D-entry (next id = max + 1 at build time): FAAB claims and free-agent adds are submitted for flagged-on leagues. It **supersedes D-019's "FAAB claims have no API at all"** (`living-memory/DECISIONS.md:427`) and #179's posture for those leagues. Also records §B1–§B7. An ADR for the consent model if `eng-architect` prefers one |
| `docs/runbook.md` | **updated (by the build)** | Kill the move: `FTF_FLAGS` sets `sleeper.send_add_drop` false; users then see hand-off |
| `mobile/src/components/CLAUDE.md` `:16` | **updated (by the build)** | The `ClaimSheet` row says "Sleeper has no roster-move API". It changes to capability-driven submit / hand-off |
| `web/privacy.html`, `web/terms.html` §5 | **updated (wording by `legal-lead`)** | R15.4 / R15.5 (`:816-830`), as legal's launch minimum scopes them. Live before the flip |
| `docs/design/components.md` | **updated by `design-lead`** | The checkbox and step rows consent.md §2.3 says design owes |

## 5. Ship gate declaration

- **Simulator-gate tier: WAIVED.** D-056 retired the tier matrix. `FTF_SKIP_SIM_GATE=1` is the standing posture, with the evidence in §3 named in its place.
- **CI green** on the pushed sha: `backend-tests`, `mobile-typecheck` (which runs every `check-*.js`, including `check-fa-move.js`), and `maestro-testid-lint`.
- **The 11-06 binary gate (client, dark).** F1–F17 and the `check-device-first-page.js` assertion pass, and the code-walk is written. It needs no flag or server change to ship.
- **D6, restated for launch.** The flip needs **all** of these:
  1. **Legal's launch minimum folded in.** LEG-L12 as `legal-lead` scopes it for launch (`legal-lead.md:421`), arriving via `head-bizops` ~11-04: the consent copy (v1; v2 before claims), the R15.3 tables, and the privacy and terms text, live.
  2. **The capture recorded** in `capture.md`, redacted (AC-19).
  3. **The server merged**, with CI green and the evidence logged.
  4. **The 11-06 binary** is the build testers have.
  5. **`platforms-pm`'s write-feature-gate pass** on the risk register (consent.md `:500`).

  #351's P31 device tests gate #509's hand-off merge, not this flip. **The flip itself is the operator's.** The TestFlight checklist runs straight after it, and the flag goes back off on any failure.
- **Claims** need, in addition, D5: the current copy at v2 **and** the claim shape captured.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the F1–F17 sabotages (applied and reverted), the backend tests, the code-walk, the T1–T15 and FA1–FA6 outcomes, and `FTF_SKIP_SIM_GATE=1`.
- **Express lane declared by the operator?** No. Schema, API and flag surfaces are all touched, so full gates apply.

## E. Platform scope

| Platform | Write path today (`origin/main`) | Free-agent moves | When |
|---|---|---|---|
| **Sleeper** | `sleeper_write.py`: `propose_trade` / `reject_trade` only (`:405`, `:414`) over `_post_graphql` (`:338`) | Add, add+drop and claim ops come from the capture (capture.md §2). Shapes are **not yet captured**; capture.md §3's community hints are UNVERIFIED | **Launch.** Dark client 11-06; flip ~11-12..14 (add/drop) and ~11-16 (claims) |
| **MFL** | `mfl_write.py` covers **trades only**: `propose_trade` (`:364`) and `respond_trade` (`:379`) over `_issue_import` (`:302`), with `TYPE=tradeProposal` (`:212`) / `tradeResponse` | MFL's public import API documents free-agent and waiver import types on the same transport (e.g. `fcfsWaiver`, `waiverRequest`, `blindBidWaiverRequest`). **UNVERIFIED: not exercised in code** | **Update 1, server-only:** `mfl.send_add_drop`, its own consent copy from `legal-lead`, the FA read filling its claim context, and verification against a test league |
| **ESPN** | `espn_write.py` covers **trades only**: `TRADE_PROPOSAL` built at `:285`, POSTed by `_post_transaction` (`:351`) to `transactions_url` (`:340`); `cancel_trade` (`:467`) | Free-agent and waiver transaction types would need a capture like Sleeper's. **UNVERIFIED** | **Update 1, server-only**, as MFL, after its capture |
| **Fleaflicker** | none (dark, `fleaflicker.link` false) | none | `unsupported`; `NO_ADD_REASON` unchanged |
| **local / demo** | none | none | `unsupported`; unchanged |

**What makes Update 1 server-only.** The 11-06 client has to know:
- `league_platform`;
- the suffix codes;
- server copy;
- **a connect-step mapping to each platform's existing connect screen.**

`platforms-eng` confirms the last one by 11-02. Until a platform's connect screen is reachable from the sheet, the server never answers `submit` to an unlinked or expired user on that platform.

**R15 is Sleeper-specific** (`:736`). MFL and ESPN need their own consent wording and copy versions from `legal-lead` before Update 1.

## F. Decisions needed

**For the operator, via `head-product`:**
1. **Schema and flag: a bright line.** Two new tables (`platform_write_consents`, `platform_write_moves`) and the kill switch `sleeper.send_add_drop`. **Needs the operator's yes** before the server build. The client binary doesn't need it.
2. **`head-bizops`'s 11-01 yes/no on the app submitting free-agent moves:** pending. Record only the decision.
3. **The capture session by 11-02** (platforms-eng's ask, platforms-eng.md `:14-17`). This needs two answers:
   - **(a) method:** copy each request from Chrome DevTools by hand (head-eng's recommendation), or platforms-eng injects a redacting read script;
   - **(b) league:** is the July dummy Sleeper league still usable (in season, drafted, FAAB waivers)?

   Each live write is the operator's own click, approved when it runs.
4. **Claims at launch, or add/drop only.** `platforms-pm` recommends: in scope, gated by D5, flipped after add/drop (~11-16). Add/drop alone is the fallback, and claims then follow server-only.

**Not now:** the flip itself is the operator's, at ~11-12..14, under §5.

**Inputs owed** (routed, not decided here):
- **`legal-lead`**, via `head-bizops`: the launch minimum (~11-04). Also, if `eng-architect` picks a write-once move row, confirmation that it still meets R15.3 (§B6).
- **`analytics-lead` — granted 2026-11-01:** P1 and P2, with C1–C6 (§1).
- **`ux-lead` — done 2026-11-01:** flow verdicts folded into §B and §C, and FA1–FA6 into §3 (`/Users/teresadickens/ftf-worktrees/org-bringup/docs/plans/org-bringup/reports/ux-lead.md` `:34-176`). They are recommendations, pending the operator's approval.
- **`design-lead`:** §C's visual review. Still open.
- **`analytics-lead`:** `other_account` on `fa_move_connect_shown.reason`. Requested 11-01 (§1).
- **marketing**, via `head-product`: §G.
- **`trades-pm` — answered 2026-11-01:** K-F5 is in the 11-06 binary in a reduced form. After a completed move, the next search no longer offers the dropped player; cards already on screen keep it until that search. The build requirements are §B10. `head-eng` confirms who builds the `devicePage.ts` change (`trades-eng` reviews it).
- **`platforms-eng`:**
  - the connect mapping (§E);
  - the move core's worst case (§B5);
  - whether waiver status can be read before the tap (capture Q8).

## G. Copy needed

**Words go to marketing via `head-product`. All are server-authored** (§B4) unless marked as a client fallback. The legal-final consent copy is **referenced, not rewritten**.

| Id | State | String | Intent | Status |
|---|---|---|---|---|
| G1 | 1 | Hand-off footer | You'll finish this move in Sleeper. Makes no claim about what Sleeper allows (today's `ClaimSheet.tsx:312` becomes untrue once D1 is on) | needed |
| G2 | 3 | Connect line | Why connecting is needed to move from here | **approved** (`s351.connect`) |
| G3 | 4 | Verify line | Your connection needs a re-check before moves | needed |
| G4 | 5 | Consent text v1 / v2 | — | **legal-final**, consent.md §4.1 (`:187-204`) / R15.8 `:858-875`. Not rewritten |
| G5 | 5 | "This move: {CTA label} in {League}." | — | **legal-final** (R15.8 D10(d)) |
| G6 | 6 | CTA templates: add / add+drop / claim / claim+drop | Name the exact move (D10(a)); the league on or beside it | needed (draft: "Add A, drop B", "Claim A for $N, drop B") |
| G7 | 6 | Finality line | — | **legal-final**: "Final on Sleeper. Fleeced can't undo it." (R15.8 D10(b)) |
| G8 | 6 | Waiver line + bid | — | **legal-final**, R15.1 `:766` |
| G9 | 6 | Window line + Turn off | Your OK runs until {date}; switch it off here. With v2: "moves", not "adds" | needed (draft: consent.md `:115`) |
| G10 | 8 | Added result | Exactly what the platform reports; partials stated exactly | needed (draft: R15.1 `:768`) |
| G11 | 9 | Claim-pending result | Claim submitted, with the bid and the drop-if-it-clears; it runs on the waiver schedule; never "added". No cancel line until Q7b | needed |
| G12 | 10a–10e | One line per refusal | Plain reason, and what to do next | needed |
| G13 | 10f | Platform refused | Nothing changed; you can still do it in Sleeper | needed (draft: R15.1 `:769`) |
| G14 | 10g | Unavailable | Moves can't be made right now | needed |
| G15 | 11 | Not sent | Couldn't reach Sleeper, nothing was sent, try again | needed (precedent: `server.py:24598-24599`) |
| G16 | 12 | Outcome unknown, title + body | We can't confirm it; check Sleeper before trying again; never "failed" or "try again" | title **reuses 8i** "Check before resending"; body needed (precedent `server.py:24600-24602`) |
| G17 | 13 | Connection rejected | Sleeper turned down the connection; nothing changed; connect again | needed |
| G18 | 14 | Claims not enabled | This player is on waivers; claim in Sleeper for now | needed |
| G19 | 15 | Settings status lines + withdrawal notice | — | **approved** (R15.8 `:856`; R15.2.6 `:783`, verbatim) |
| G20 | all | "Do it in Sleeper instead" | — | **approved** (`s351.secondary`) |
| G21 | all | **Client fallbacks** (baked into the binary) | Neutral, platform-free wording for: result, refusal, outcome unknown and not sent. **Never consent text** | needed before 11-06 |

## H. Risks

From capture.md §8 (`:349-363`), in short, plus two that are new at launch:
- **ToS / E2** (Sleeper Terms §11): carried as capture.md §8 records it. Not relitigated here.
- **Account bans.** Sleeper may revoke sessions or block third parties (§11.2). A server-side write with browser headers (R15.7(d), [PRO]) risks the **user's** account.
- **No undo.** An add with a drop executes at once, which makes this FTF's highest-blast-radius write. The named CTA, the server drop and bid checks, and `move_kind_changed` are not optional.
- **App Store.** Guidelines 5.2.2 and 4.x: a new write class on the exposure Send in Sleeper already carries.
- **Token custody.** The same full-account JWT gets a more consequential use. No token goes in any record.
- **Timing.** Claims process later ("claim submitted", never "added"). Adds may be blocked in the processing window or after kickoff. Outcomes may need reconciling.
- **Schema drift.** The API is undocumented, so every captured shape holds only as of its capture date.
- **New: the launch schedule.** The capture, legal's minimum and the server all have to land between 11-02 and ~11-14. The cut lines (§D) keep launch safe: the binary is dark either way.
- **New: outcome unknown.** A user who resends after a timeout could double-move. §B5 and §B6 (no retry, idempotent `attempt_id`, preflight budget) are the mitigation. The residual is the user acting in Sleeper themselves.

## I. What could not be verified

- **Sleeper's add, add/drop, claim, edit and cancel shapes:** not captured yet. The capture is pending the operator (capture.md, `3b77886f`). The community hints (capture.md §3) are **UNVERIFIED**.
- **Whether Sleeper returns a transaction id** for an add or a pending claim (Q7a), and **whether a pending claim can be cancelled** (Q7b).
- **Whether waiver status can be read cheaply before the tap** (Q8). If not, claims can't satisfy D10(c) and stay off.
- **MFL free-agent and waiver import types:** UNVERIFIED, not exercised in code.
- **ESPN free-agent and waiver transaction types:** UNVERIFIED. They need a capture.
- **The move core's server worst case,** and so the client timeout. It's known only after the capture fixes the calls.
- **Whether the 11-06 client can open MFL's and ESPN's connect screens from the sheet** (§E).
- **Legal's launch minimum:** content and date (~11-04).
- **The #509 trim:** this block assumes #509 lands as CTA-only. As of `d14b7308` it keeps "Open in Sleeper to claim" and the current footer. The hand-off event is emitted by #528, not #509 (§1). Merge order is #379 → #528 → #509, and #509's `hasDrop` is at `2eb1bf83`.
