# Feature Scope — FB-409: ✓ queue refuses every trade with `not_league_member`

**Date:** 2026-08-30
**Entry point:** feedback #409 (mattmurf77, v1.16.12, screen `TradesHome`)
**Builder:** build agent, branch `claude/fb-410-412-trade-card-polish` (base `bd83fe94`)
**Operator sign-off on waivers:** **NEEDED** — five sections are waived below (§1c, §2 all three rows,
§3 structural guard / TestFlight, §4 six of seven rows). Every waiver has a written reason; none is
silence. Nothing here is a judgement call about product scope — they are all consequences of the same
fact: this is a **pure backend bug fix that restores a shipped contract**, adding no surface of any kind.

**What actually changed, in one line:** a route that asked "is the caller in this league?" of a list
that is built to exclude the caller now resolves the caller from the session instead. ~10 lines in
`backend/server.py`, plus tests.

---

## 1. Analytics scope

- [ ] **(a) New events specced** — no.
- [x] **(b) Existing events cover it.** `calc_trade_queued` (client, props `{queued, reason}`) and the
      server-side `trade_proposed` (`source: "calculator"`, `backend/server.py:13394-13411`) already
      instrument this exact path. No emitter, name, prop or classification changes.

      What they answer post-fix: `calc_trade_queued` with `queued: true` becomes non-zero for the first
      time since 2026-08-22, and the `reason: "not_league_member"` share should fall to ~0. **Warning
      for whoever reads this metric:** every `calc_trade_queued` row between 2026-08-22 and the deploy
      of this fix carries `{queued: false, reason: "not_league_member"}` and is measuring the bug, not
      a product signal — any "partner not in league" rate computed over that window is meaningless.
      Same for `trade_proposed` from `source: "calculator"`: there are **zero** such rows, because the
      route returned before reaching the emitter.
- [ ] **(c) WAIVED** — n/a, (b) applies.

## 2. Schema & flag scope

- **New/changed tables or columns: NONE.** WAIVED — the fix adds no persistence. It changes which
  branch of an existing predicate is taken; the rows subsequently written (`trade_decisions`,
  `swipe_decisions`) are the ones the shipped code already wrote on its success path, through the
  unchanged `save_trade_decision` / `save_trade_swipes` calls. `docs/data-dictionary.md` untouched.
- **New/changed feature flags: NONE.** WAIVED — deliberately **not** flag-gated. The change is a
  defect repair inside an already-flagged feature (`calc.merged_layout` + `trade.likes_you`, both
  already lit in `config/features.json`); a new flag would only add a second way to keep the ✓ broken.
  The deploy-free rollback lever already exists: turning `calc.merged_layout` off removes the ✓ cell
  entirely, exactly as it does today.
- **New env vars / `model_config` keys: NONE.** WAIVED — no tunable introduced.
  `docs/config-reference.md` untouched.

## 3. Evidence scope

- [ ] **Structural guard: WAIVED — no mobile change.** `mobile/tests/check-*.js` suites pin JSX/AST
      shape; this diff contains zero client files, so there is no structure for one to pin. The four
      suites covering these surfaces (`check-calc-merged-behavior.js`, `check-any-partner.js`,
      `check-canvas-results.js`, `check-shop-deck.js`) are untouched and still pass unchanged.
- [x] **Unit tests — this is the primary evidence, and the part that matters most.**
      `backend/tests/test_calc_trade_queue.py`: **+7 cases and a second fixture.**

      The pre-existing suite passed 26/26 while the feature refused **100%** of real taps for eight
      days, because its fixture put the caller **inside** `league.members` — a session
      `/api/session/init` never builds. That fixture is **kept** (a session that did carry the caller
      must still work) and a **production-shape** fixture is added alongside it:

      | Fixture | Caller in `league.members`? | Caller's roster from | Guards |
      |---|---|---|---|
      | `harness` (existing) | yes | `members` entry | the original 26 cases, unchanged |
      | `prod_harness` (new) | **no** | `sess["user_roster"]` only | the 7 new cases below |

      New cases: `test_prod_shape_queue_succeeds` (**the regression guard**),
      `…_does_not_mutate_league_members` (the hard constraint — the synthesized member must stay local
      to the route), `…_give_side_still_checked_against_my_roster`,
      `…_receive_side_still_checked_against_their_roster`, `…_cannot_queue_a_trade_with_yourself`,
      `…_unknown_opponent_still_refused`, `…_like_reaches_the_opponents_deck`.

      **Sabotage-proven.** Reverting only the synthesized `caller_member` to the bare
      `members_by_id.get(caller_league_id)` turns **5 of the 7** red, every one of them reporting
      `{"queued": false, "reason": "not_league_member", "detail": "caller is not a member of this
      league"}`. Restoring returns 33/33. (The 2 that stay green under sabotage are the two that
      *expect* `not_league_member` — they exist to prove the fix did not over-permit.) Full output in
      `status.md` § Build report.
- [x] **Code-walk proof.** Written and independently verified by the orchestrator before the build, at
      `status.md` §2 — the caller-exclusion chain traced end to end with file:line citations at both
      ends (`backend/server.py:18928-18952` builds it caller-excluded; `:13313-13315` reads it
      expecting the caller; `:13139` returns the refusal;
      `mobile/src/utils/queueCalcTrade.ts:43-44` renders it). §4 additionally clears today's
      #406/#407 ship as a cause. The build confirmed the consumer set independently: `caller_member`
      is read at exactly three places — `:13138` (None check), `:13142` (`.user_id`), `:13151`
      (`.roster`) — which is why the synthesized object is narrow.
- [ ] **Manual TestFlight checklist: WAIVED as a *gate*, supplied as a *post-deploy confirmation*.**
      Waived as a gate because no client build ships: Render auto-deploys the backend and every
      already-fielded build (incl. the reporter's v1.16.12 / build 140) is fixed at once, so there is
      no artifact to gate. Recommended confirmation on the **current** build after the Render deploy —
      no app update needed:

      1. Open the app → **Trades** (the landing tab).
      2. On the canvas, pick a **real league partner** (not "Anyone") and build any two-sided package.
      3. Tap the **✓**.
      4. **Expect:** *"Queued for @X — it'll show in their suggestions."*
         **Before the fix this said** *"@X isn't in this league."* — that string reappearing means the
         deploy did not take.
      5. Tap ✓ again on the same package → it should be accepted quietly, with no duplicate (the
         idempotency path), not refused.
- **`testID`s added/renamed: none** (no client files touched). `testid-lint.sh` exposure: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **no — n/a** | **The route contract is unchanged.** `POST /api/trades/queue` keeps its path, method, auth posture, request body, both response shapes (`{queued: true, trade_id, already_queued}` / `{queued: false, reason, detail?}`) and its closed six-value `CALC_QUEUE_REASONS` enum — `test_the_refusal_enum_is_closed` still passes untouched. The route simply **stops falsely returning one of its documented refusals**. Nothing a client or the reference doc asserts becomes false. |
| `living-memory/LLD.md` | no — n/a | No convention shifted. The fix *applies* an existing documented convention (caller-exclusion, `backend/server.py:15168-15172`, `backend/trade_breaker.py:326`, `backend/CLAUDE.md` § Identity) rather than changing it — and the hard constraint was specifically to **not** change it. |
| `docs/architecture.md` | no — n/a | No module added, removed or re-wired; no data-flow change. One local variable and one fallback expression inside one existing route handler. |
| `living-memory/HLD.md` | no — n/a | No new module, client or major flow. |
| `docs/cross-client-invariants.md` | no — n/a | The one cross-client contract in play is the `CalcQueueReason` enum (`mobile/src/api/trades.ts`), and it is byte-identical — no reason added, removed or renamed. |
| `docs/glossary.md` | no — n/a | No new domain term. "Caller-excluded members" is pre-existing vocabulary. |
| ADR / `DECISIONS.md` | no — but **`GOTCHAS.md` yes** | No architectural choice was made — the design was already decided and simply misapplied, so there is nothing to overturn or record as a decision. The durable lesson is a trap, not a decision: **`living-memory/GOTCHAS.md` § G-063** (2026-08-30) records the caller-exclusion convention's **fourth** bite (FB #41 → #291 → #295/#296/#305 → #409) and, critically, that **three of the four were hidden by a fixture that put the caller in `members`**. |

## 5. Ship gate declaration

- **CI green:** to be confirmed on the pushed sha. Locally, on the full merged tree:
  - `pytest backend/tests -q` → **4478 passed / 1 skipped / 0 failed** (345 s). Baseline with the
    change stashed: **4471 passed / 1 skipped / 0 failed** — exactly +7, matching the new cases.
  - `pytest backend/tests/test_calc_trade_queue.py -q` → **33 passed** (was 26).
  - `mobile-typecheck` / `maestro-testid-lint`: **no exposure** — zero client files in the diff.
- **Evidence recorded:** TEST_LEDGER entry to be written by the shipping session (this build agent was
  scoped to `backend/server.py`, `backend/tests/test_calc_trade_queue.py`,
  `living-memory/GOTCHAS.md` and this folder, and did not commit).
- **TestFlight verification:** the §3 confirmation steps, run by the operator **after the Render
  deploy**, on the current build — outcome to be logged in TEST_LEDGER.
- **Express lane declared by the operator?** **No.** Full gates applied. Worth stating explicitly:
  even though this is a ~10-line fix that would read as a "quick fix", it was **not** eligible for
  self-selected express — agents never self-select it, and this change sits adjacent to the
  API-contract bright line (it was checked and found contract-neutral, which is a finding, not an
  assumption).

## 6. Known follow-up, deliberately NOT fixed here

**The client's refusal copy blames the wrong person.** `mobile/src/utils/queueCalcTrade.ts:43-44`
renders `not_league_member` as **"@\<partner> isn't in this league."** — but that single reason string
covers three distinct causes, and **two of them are caller-side**: the caller not resolving (the FB-409
bug), the opponent not resolving, and a self-trade. That mismatch is why the tester's report said a
*user* wasn't in the league when the server was actually complaining about the tester. Out of scope
here on purpose: it is a `mobile/` change, so it needs an EAS build and a TestFlight round trip, which
would delay a backend hotfix that repairs every fielded build immediately. Options for a later item —
neutral copy ("Couldn't queue this trade for @X"), or splitting the enum (which **is** a
cross-client contract change and would then require the `docs/api-reference.md` +
`docs/cross-client-invariants.md` rows above).
