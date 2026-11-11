# Feature Scope — WS3: ask why, once every few passes (R9)

**Date:** 2026-11-10
**Entry point:** direct operator ask — offer-learnings plan §3 WS3 (plan.md lives on the
coordinator's branch, not on `main`)
**Builder:** WS3 builder agent, branch `feat/pass-reason-cadence`
**Operator sign-off on waivers:** not needed (no waivers)

---

## 0. What exists today, and what this changes

**Today (read from the code on `origin/main` 6017d64b).**

- The reason capture is `feedback.decline_reasons`. It is **off** in `config/features.json`
  since 2026-10-02: the operator found a reason after every decline tedious. With it off the
  deck card shows the plain ✕, a pass is one tap through `POST /api/trades/swipe` (full
  `trade_k_pass` Elo, swipe-undo window), and `POST /api/trades/pass-reason` 404s
  `feature_disabled`.
- With it on, the ✕ is replaced on **every** card by three tiles (Value · Fit · Neither).
  A tile tap is the pass; the deck waits on layer 2 (`deferDeckAdvance`) until an option is
  picked. Rows land in `trade_pass_reasons`, one per card.
- Elo (`ranking_service.pass_reason_writes_elo`, knob `pass_reason_elo_suppression` = 1):
  a reasoned pass writes the pass Elo signal only for `value_giving`. Every other code is
  suppressed (`PASS_REASON_ELO_KEEP` is an allow-list).

**With `trade.pass_reason_cadence` on.**

- The deck card shows the plain ✕ (today's one-tap pass, undo window, full Elo) on every card
  **except** when the cadence asks.
- The cadence asks once the user has passed **N cards in a row** (`pass_reason_ask_after`,
  starting value 3). On that card the ✕ is replaced by one row of reason chips plus
  **Just pass**. A chip is the pass and the reason in one tap; the deck advances at once
  (no layer 2, no waiting). **Just pass** is one tap, records no reason, and is today's plain
  pass. The swipe gesture still passes the card with no reason. ✓ is unchanged.
- Once the prompt has been answered or dismissed (any pass on the asked card), it stays quiet
  for the next **M passes** (`pass_reason_quiet_for`, starting value 5). A like resets the
  run of consecutive passes; it does not shorten the quiet period.
- N and M are `model_config` knobs served on `GET /api/feature-flags` as
  `pass_reason_cadence: {ask_after, quiet_for}` (only while the flag is on), so they change
  with `scripts/set_knob.py` and no app release.
- The cadence is independent of `feedback.decline_reasons`: the route accepts writes when
  either flag is on. If both are on, the cadence governs the deck card; the dormant canvas
  browse pager keeps the full tile panel.

## 1. Analytics scope

- [x] **(a) New events specced:**

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `pass_reason_prompt_shown` | `trade_id`, `consecutive_passes` | the chip row mounts on a deck card (once per card) | mobile |
  | `pass_reason_prompt_dismissed` | `trade_id` | **Just pass** tapped | mobile |

  Both NON_INTENT (an exposure and a dismissal — the `trade_pass_overlay_opened` /
  `_dismissed` class). The existing overlay pair was considered and not reused: it measures
  the calculator overlay specifically (its `banked` boolean is that surface's question), and
  pooling a second surface into a prop-less `opened` event would make both unreadable.

  A chip answer reuses the existing INTENT pair: `trade_pass_layer1` **and**
  `trade_pass_layer2` (with `detail`, `has_free_text: false`), so the
  "layer 1 without layer 2" metric is not polluted by one-tap answers. The `detail` enum of
  both widens by the two new codes (no new prop). Answered-vs-tiles is told apart by joining
  `pass_reason_prompt_shown` on `trade_id`.

  → `backend/analytics_taxonomy.py` (names + props) and
  `analytics_queries.NON_INTENT_EVENTS`, same commit as the emitter.

## 2. Schema & flag scope

- New/changed tables or columns: **none.** `trade_pass_reasons.detail` gains two values
  (TEXT column, no migration): `other_picks_keep`, `other_waiting` → `docs/data-dictionary.md`.
- New/changed feature flags: `trade.pass_reason_cadence`, default **false** →
  `config/features.json`, `feature_flags.FLAG_KEYS`, flag fixtures (`release.json`,
  `onboarding-v2.json`, `profiles-on.json`; `all-on.json` deliberately omits uncalibrated
  flags, so it is left alone), `docs/config-reference.md`.
  Graduation: the operator turns it on for TestFlight after the checklist in §3; it can go on
  without `feedback.decline_reasons`.
- New `model_config` keys: `pass_reason_ask_after` (3), `pass_reason_quiet_for` (5), seeded
  insert-if-absent. Rollback lever: the flag (one-line, `POST /api/feature-flags/reload`);
  `pass_reason_ask_after` can also be raised to make the prompt rarer without a release.

### Reason chips (operator's phrases → codes)

| Chip (operator's phrase) | Code | New? | Elo effect (suppression on) |
|---|---|---|---|
| Not moving that player | `other_player_keep` | existing | none (unchanged) |
| Keeping my picks | `other_picks_keep` | **new** | none — attachment, the `other_player_keep` argument |
| Wrong direction for my team | `fit_outlook` | existing | none (unchanged) |
| Don't rate what I'd get | `other_player_avoid` | existing | none (unchanged) |
| Waiting on something | `other_waiting` | **new** | none — timing, no claim about price |
| Value too low | `value_giving` | existing | writes pass Elo (unchanged) |

New codes are accepted by the route **only while the cadence flag is on** (400
`invalid_detail` otherwise), so flag-off is byte-identical server-side too. They are not added
to `PASS_REASON_ELO_KEEP`, so they suppress by construction.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-pass-reason-cadence.js`
      (`npm run test:pass-reason-cadence`) — executes the real cadence module: asks at N,
      quiet for M, a like resets, flag off never asks and leaves the reasons object untouched,
      server config clamps; pins the chip→code table against `api/declineReasons.ts`; pins
      the screen wiring (one `record` in `advance`, the deck card's reasons pass through the
      cadence helper, reasoned passes skip the undo hold).
- [x] **Unit tests:** `backend/tests/test_pass_reason_cadence.py` (flag-off payload and route
      identical; N/M served and clamped; new codes gated; Elo of new and existing codes);
      `test_decline_reasons.py` taxonomy pin widened by the two codes.
- [x] **Code-walk proof:** in the builder's report (chip tap → `handleReasonLayer1` with
      detail → one POST → `advance('pass')` without defer or undo hold → `record('pass')`).
- [x] **Manual TestFlight checklist** (flag on, `feedback.decline_reasons` off, N=3, M=5):
  1. Open a deck. Pass 3 cards with ✕. Each pass is one tap, the deck advances at once, and
     the Undo toast appears as today.
  2. Card 4 shows a "WHY PASS?" row of six chips and **Just pass** in place of the ✕; ✓ is
     still there.
  3. Tap **Keeping my picks**. The deck advances immediately; no second panel, no Undo toast.
  4. Pass the next 5 cards with ✕: no chips on any of them.
  5. Card after those 5 shows the chips again (the run of passes is ≥ 3). Tap **Just pass**:
     the deck advances, the Undo toast appears, nothing else asks.
  6. Pass 2, like 1, pass 3: the chips appear only on the card after the third pass after the
     like.
  7. On a chip card, swipe left instead: the card passes with no reason and the next 5 passes
     are quiet.
  8. `scripts/set_knob.py pass_reason_ask_after 6`, then relaunch the app (or background
     it 30+ minutes): after a fresh deck, the chips appear only after 6 passes in a row.
     Set it back to 3.
  9. Flag off + reload: every card shows the plain ✕; nothing ever asks (today's behaviour).
  10. Admin check: `trade_pass_reasons` has a row for the step-3 card with
      `reason=other`, `detail=other_picks_keep`; none for the Just-pass card.
- testIDs added: `trades.pass-reason-chips`, `trades.pass-reason-chip.<code>` (template),
  `trades.pass-reason-skip`. `testid-lint.sh` passes unchanged (no retained flow references them).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `GET /api/feature-flags` (`pass_reason_cadence`), `POST /api/trades/pass-reason` (gate, two codes) |
| `living-memory/LLD.md` | n/a because | no convention shifts: the route, table and progressive-write rules are unchanged |
| `docs/architecture.md` | n/a because | no module wiring or data flow change |
| `living-memory/HLD.md` | n/a because | no architectural shift |
| `docs/cross-client-invariants.md` | updated | decline-reason codes (two added) |
| `docs/glossary.md` | n/a because | "pass reason" / "decline reason" already defined; cadence is described in config-reference |
| `DECISIONS.md` | updated | `D-NEXT` — cadence as a prompt-on-the-card, not a post-pass sheet; new codes gated to the flag |

## 5. Ship gate declaration

- **CI green:** backend-tests + mobile-typecheck + testid-lint, on the integrated tree
  (the coordinator ships).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry.
- **TestFlight verification:** checklist §3, by the operator, before the flag goes on.
- Express lane declared by the operator? no.
