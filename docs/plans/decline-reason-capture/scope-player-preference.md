# Feature Scope — player preference under "Neither" (decline-reason capture)

**Date:** 2026-08-19
**Entry point:** direct operator ask — *"Add it as an option to the 3rd tile. Do the backend DB work to capture it."*
**Builder:** subagent session, branch `feat/decline-reason-player-pref`
**Operator sign-off on waivers:** not needed (no waivers)

Amends [SPEC.md](SPEC.md) §2 — see §2a there for the operator-approved contract.
Prior scope blocks: [scope-backend.md](scope-backend.md), [scope-mobile.md](scope-mobile.md).

---

## 0. The evidence, and the decision it forces

19 pass reasons, one 9-minute burst, 2026-08-17:

| Tile | n | Breakdown |
|---|---|---|
| **Neither** (`other`) | 9 (47%) | all free-text — the tile had no options |
| **Value** | 7 | 4 `value_giving` · 2 `value_getting` · 1 `value_other` |
| **Fit** | 3 | 2 `fit_other` · 1 `fit_new_weakness` |

"Neither" was the largest bucket *and* the only un-coded one. Its free text —
"Don't like Troy" · "No need to move kelce" (`switched_from = fit`) · "Just not
players worth my time" · "I just traded marshawn Lloyd away. It doesn't make
sense to try and trade back for him." — is not price and is not roster
construction. It is **player-level preference**, a third axis with nowhere to
land.

### One code or two — decided: **two**

| Code | Label | Means | Engine fix behind it |
|---|---|---|---|
| `other_player_keep` | "Won't trade one of my players" | won't give up **my** guy (Kelce) | give-side **keep-list** — stop building packages that send that player out |
| `other_player_avoid` | "Don't want one of their players" | don't want **their** guy (Troy, Lloyd) | receive-side **avoid-list** — stop sourcing that player for this user |

Justified from the data, not from taste:

1. **Both poles are attested at n=4.** Kelce is outgoing; Troy and Lloyd are
   incoming. A single code would lose a distinction the data demonstrates at
   the smallest sample the feature has ever had.
2. **The two directions have different fixes.** Package construction and
   candidate sourcing are different code paths. One merged code means reading
   free text to decide which one to fix — which is *exactly* the failure that
   made "Neither" a 47% black box. Merging would reproduce the bug at half
   scale.
3. **The taxonomy already splits on side.** `value_giving` / `value_getting`
   is the same my-side/their-side cut. Two codes is the consistent shape; one
   would be the exception.
4. **Precision is the operator's stated priority** for this feature —
   *"tester only … conversion/completion shouldn't be a primary driver …
   treated as high accuracy and precision exercise."* The only argument for
   one code is fewer taps, which is explicitly not a driver here.

Naming follows the established rule — layer-2 codes are prefixed by their
layer-1 code (`value_giving`, `fit_outlook`, `other_text`), so both are
`other_*`. The shared `other_player_` stem is load-bearing, not cosmetic:
`detail LIKE 'other_player_%'` selects the whole axis while the suffix keeps
the direction.

**`other_text` survives as the residual free-text row** — the two player codes
do not cover everything, and "Other" stays last on this tile as on every other.

## 1. Analytics scope

- [x] **(b) Existing events cover it.** `trade_pass_layer2` already carries
  `detail`; this widens that enum from 8 values to 10. **No new event, no new
  property, no emitter change** — `TradesScreen.handleReasonLayer2Select`
  (`mobile/src/screens/TradesScreen.tsx:4307`) is generic over the option that
  was tapped and was not touched.
- Registry: the enumerating comment on the `trade_pass_layer2` row in
  `backend/analytics_taxonomy.py` (~:1139) lists the 10 values. The row's
  `frozenset` of prop **names** is unchanged, which is why the widening cannot
  cause a silent prop strip.
- `analytics_queries.NON_INTENT_EVENTS`: **no change required.**
  `trade_pass_layer1` / `trade_pass_layer2` are already classified there
  (`analytics_taxonomy.py:448`); classification is per event, not per enum
  value, and no event is being added.
- Question it answers: *of the 47% who said "Neither", how many are player
  preference, and in which direction?* — plus the pre-existing
  layer-1-without-layer-2 rate, which is how we learn whether the new options
  read.

## 2. Schema & flag scope

- **New/changed tables or columns: none.** `trade_pass_reasons.detail` is a
  free-form `String` (`backend/database.py:910`); the vocabulary lives in
  `PASS_REASON_LAYER2` (`:5473`) and `PASS_REASON_PARENT` derives from it
  (`:5482`). **No migration, no backfill.** → `docs/data-dictionary.md`
  updated (enum row + a population caveat).
- **New/changed feature flags: none.** The change rides the existing
  `feedback.decline_reasons` kill switch: off ⇒ the route 404s and the client
  renders the shipped ✓/✕ row byte-identically, exactly as before.
- **New env vars / `model_config` keys: none.** Elo behaviour is unchanged and
  keeps riding `pass_reason_elo_suppression`. Rollback lever for *this* change
  is the same flag; there is no separate knob because there is no separate
  risk surface — an unknown code was a 400 before and after.

### Elo (SPEC §4) — checked, deliberately unchanged

Both new codes **suppress**. `other_player_keep` is the near-miss worth naming:
"won't give up my guy" *looks* adjacent to `value_giving`, but it is
attachment, not a market-value assertion — "not this player at any price" is
the opposite of a claim about price. This required no code change:
`PASS_REASON_ELO_KEEP` (`backend/ranking_service.py:233`) is an **allow-list**
of one, so a new code suppresses structurally rather than by remembering to
add it somewhere. Pinned anyway by `_ELO_MATRIX`, which now runs 10 codes × 2
knob positions.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-decline-reasons.js` — extended,
  new §6. Pins, via the TypeScript AST rather than regex: "Neither" offers
  structured options at all (a revert to free-text-only fails); the `freeOnly`
  tile shortcut is gone; **both** player codes exist as a pair (a collapse to
  one code fails); each commits on tap rather than opening a text box; each
  carries `trades.pass-reason.l2.<code>`; `other_text` is still the free row
  and still last. `npm run test:decline-reasons`.
  - **It also fixed a check that had never executed.** The suite's
    "transcribed codes still match SPEC §2" cross-check was guarded on
    `existsSync(SPEC.md)` — and SPEC.md was **untracked**, present only in one
    checkout's working tree, so the guard had always taken the SKIP branch.
    SPEC.md is committed on this branch and the cross-check now runs.
- [x] **Unit tests:** `backend/tests/test_decline_reasons.py` — 9 new tests
  (`test_player_preference_*`), plus the two existing enumerations extended
  (`test_every_specced_code_is_accepted`, `_ELO_MATRIX`,
  `test_pass_reason_writes_elo_rule_is_pure`). The new tests pin: both codes
  parent to `other` (not to `value`, the tempting mis-parent for `keep`);
  a foreign layer-1 is a `detail_reason_mismatch` 400 that writes nothing;
  a layer-2-first write derives `reason='other'` from the prefix; and the two
  directions plus the residual free text land as three distinguishable stored
  answers.
- [x] **Code-walk proof:** §3a below.
- [x] **Manual TestFlight checklist:** §3b below.
- `testID`s added: `trades.pass-reason.l2.other_player_keep`,
  `trades.pass-reason.l2.other_player_avoid`,
  `trades.pass-reason.l2.other_text` (the "Other" row on this tile, which had
  no option row before). None renamed, none removed.
  `mobile/scripts/testid-lint.sh` → `testid-lint OK`.

### 3a. Code-walk proof — every tap still commits (SPEC §3)

The load-bearing requirement is that a tester who taps and bails leaves a
complete row. Traced for the new options:

1. **Tile tap is unchanged.** `DeclineReasonPanel.tapTile` →
   `onLayer1(next, …)` → `TradesScreen.handleReasonLayer1`
   (`TradesScreen.tsx:4289`) writes the disposition **and** the reason.
   Nothing about the third tile's *layer 1* changed — the tile's `key`,
   `name`, `sub` and `testID` are byte-identical; only its `options` array
   grew (`DeclineReasonPanel.tsx:96-105`).
2. **A player-preference tap commits before anything else can happen.**
   `tapOption` (`:206`) sees `o.free !== true` for both new codes, so it takes
   the fixed-option branch at `:219-220`: `committedRef.current = true` then
   `onLayer2Select(tile.key, o.code)` →
   `TradesScreen.handleReasonLayer2Select` (`:4307`), which fires
   `trade_pass_layer2` and `postDeclineReason({layer: 2, reason, detail})`
   **before** `commitReasonAdvance()`. There is no text box on this path and
   nothing to bail out of.
3. **The "Other" row still banks first.** `other_text` carries `free: true`
   (`DeclineReasonPanel.tsx:104`), so `tapOption` takes the `:207-217` branch:
   `onLayer2Bank(tile.key, 'other_text')` fires **before** `setOpenText`
   reveals the composer. This is *stricter* than what shipped — the old
   free-text-only "Neither" rendered the composer straight from the tile tap
   and banked nothing, so a tester who opened it and bailed left
   `detail = NULL`. Now they leave `other_text`.
4. **The server accepts both without a code change.**
   `PASS_REASON_PARENT` is derived from `PASS_REASON_LAYER2`
   (`backend/database.py:5482-5486`), so the route's validation at
   `backend/server.py:11607` (`detail not in PASS_REASON_PARENT` → 400) and
   `:11609` (parent-vs-reason mismatch → 400) pick the new codes up
   automatically, and `upsert_trade_pass_reason` derives `reason='other'` from
   the prefix for an orphan layer-2 write.
5. **Elo stays suppressed.** `code_now = state["detail"] or state["reason"]`
   (`server.py:11672`) → `pass_reason_writes_elo` (`ranking_service.py:246`)
   → `code in PASS_REASON_ELO_KEEP`, a frozenset of `{"value_giving"}`
   (`:233`). Both new codes are absent ⇒ `False`.
6. **Flag-off is still byte-identical.** Nothing in this change touches
   `TradeCard`'s `disposition.reasons` guard or `/api/trades/swipe`; the
   structural suite's §1 still passes unmodified.

### 3b. Manual TestFlight checklist (operator)

Flag `feedback.decline_reasons` must be **on**. Run on the Trades deck.

1. On a suggested trade, tap **Neither**. → The card is passed (the ✓ goes
   inert), the notched panel opens under the third tile, and it now shows a
   **"WHICH ONE?"** label over **three option rows** — *Won't trade one of my
   players*, *Don't want one of their players*, *Other* — **not** a text box.
   *(Regression if the keyboard opens immediately: the tile reverted to
   free-text-only.)*
2. Tap **"Won't trade one of my players"**. → The deck advances to the next
   trade immediately. No toast, no receipt, no keyboard.
3. On the next card, tap **Neither** → **"Don't want one of their players"**.
   → Advances the same way.
4. On the next card, tap **Neither** → **"Other"**. → The row highlights, a
   text box opens **below that row**, and the *Send & next trade* button is
   visible above the keyboard. Type nothing and **force-quit the app**.
   Reopen. → The card is still passed. *(This is the bail-out case: the row
   should read `reason=other, detail=other_text` — verify in step 7.)*
5. On the next card, tap **Neither** → **Other**, type a few words, tap
   **Send & next trade**. → Keyboard dismisses, deck advances.
6. On the next card, tap **Value**, then tap **Neither**. → The panel re-notches
   to the third tile and shows the three options; the card is not passed twice.
7. **Verify server-side** (`trade_pass_reasons`, newest rows first): steps 2
   and 3 wrote `reason=other` with `detail=other_player_keep` /
   `other_player_avoid` and `free_text` NULL; step 4 wrote `detail=other_text`
   with `free_text` NULL; step 5 wrote `detail=other_text` **with** the text;
   step 6 wrote `reason=other, switched_from=value`. **No row anywhere has a
   non-NULL `elo_signal_at`** — none of these codes may move Elo.
8. Turn the flag **off** and reopen the deck. → The card shows the original
   ✓/✕ row and no tiles.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `POST /api/trades/pass-reason` — "the 8 layer-2 codes" → 10, noting the request/response shape is unchanged |
| `living-memory/LLD.md` | **n/a because** no convention shifted — this adds two values to an existing closed enum through the existing `PASS_REASON_LAYER2` mechanism, which LLD already describes |
| `docs/architecture.md` | **n/a because** no module wiring or data flow changed; no new module, route, table or client |
| `living-memory/HLD.md` | **n/a because** the architecture is untouched |
| `docs/cross-client-invariants.md` | **n/a because** the codes still have no third consumer — backend + mobile only, no web and no extension. (The pre-existing follow-up in `scope-mobile.md` §Docs to add a `§ Decline reasons` block stays open, re-checked and now reading 3 + 10.) |
| `docs/glossary.md` | **updated** | "Decline reason codes" (both new codes + why two) and "Layer 1 / Layer 2" (eight → ten) |
| `docs/data-dictionary.md` | **updated** | `trade_pass_reasons.detail` enum row, plus a player-preference note carrying the `other_text` population caveat |
| `docs/config-reference.md` | **updated** | `pass_reason_elo_suppression` — names the `other_player_keep` near-miss and the allow-list argument |
| `docs/plans/decline-reason-capture/SPEC.md` | **updated** | §2 table + new §2a amendment; §6 enum count; §7 struck of its retired Maestro/sim-gate language per D-056. **Also committed for the first time** — it was untracked |
| ADR or `DECISIONS.md` entry | **updated** | `D-079` — one code vs two, and why two |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` · `tsc --noEmit` · `testid-lint.sh` ·
  `check-decline-reasons.js` — all run locally, results in
  `living-memory/TEST_LEDGER.md`.
- **Evidence recorded:** TEST_LEDGER entry dated 2026-08-19.
- **TestFlight verification:** checklist in §3b, **not yet run** — awaiting the
  operator.
- **Express lane declared by the operator?** No. Full gates: this change
  touches taxonomy/vocabulary and an analytics enum, both bright lines.
