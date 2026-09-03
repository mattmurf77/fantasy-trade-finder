# Feature Scope — FB-418 backend follow-up: a sent offer is a LIKE on the idea routes (D-178)

**Date:** 2026-09-03
**Entry point:** feedback #418 (QA-B finding B-1) → operator ruling → [D-178](../../../../living-memory/DECISIONS.md)
**Builder:** backend session, branch `feat/fb418-backend-like-exclusion`
**Operator sign-off on waivers:** not needed — no waivers. Two deviations from the
written spec are recorded in §6 and need an operator read, not a waiver.

Spec: [`followup-backend-like-exclusion.md`](followup-backend-like-exclusion.md) ·
PRD: [`backend-prd.md`](backend-prd.md) · Mobile half: [`prd.md`](prd.md)

---

## 1. Analytics scope

- [x] **(b) Existing events cover it** — no new event, and none is needed:

  | Existing event | What it answers for D-178 |
  |---|---|
  | `shop_opened` (+ the shop window's idea payload) | The volume question the spec asks for: the `visibleIdeas.length` distribution before vs after. Shrinkage is the predicted cost and this is where it is read. |
  | `calc_trade_queued` | The send itself. Every exclusion this change makes traces back to one of these rows — a like with no `calc_trade_queued` (or deck `like` swipe) before it is a bug, not a feature. |
  | `trade_proposed` (server-side, `POST /api/trades/queue`) | The durable half: the `trade_decisions` row that IS the exclusion. Counting these per user per league gives the size of the exclusion set directly. |
  | `find_trades_tapped {source: "calculator"}` / `calc_find_a_trade_tapped {path: "fair"}` | The fair-packages sweep's own volume, for the same before/after read on that surface. |

  Nothing new is stored, so `docs/data-dictionary.md` is untouched. No taxonomy
  registration and no `analytics_queries.NON_INTENT_EVENTS` classification is
  needed, because no emitter was added.
- [ ] (a) New events specced — n/a.
- [ ] (c) WAIVED — n/a (b applies).

## 2. Schema & flag scope

- **New/changed tables or columns:** none. The change READS `trade_decisions`,
  `trade_matches` and `league_members` through two existing loaders
  (`load_awaiting_trades`, `load_matches_for_exclusion`) and writes nothing.
  `docs/data-dictionary.md` untouched — correct, nothing was added.
- **New/changed feature flags:** none added. The two routes reuse the EXISTING
  `trade.presentment_rules` (true in `config/features.json` since the G6 wave),
  which `docs/config-reference.md` already documents as *"R4's only switch"* —
  reusing it keeps that sentence true instead of silently falsifying it, and it
  is the deploy-free revert (`POST /api/feature-flags/reload`). The blast-radius
  paragraph in `docs/config-reference.md` is updated to name the two new
  surfaces. **Graduation criterion:** none — the flag is already lit and the
  behavior it now also gates is a correctness ruling, not a rollout.
- **New env vars / `model_config` keys:** none. Deliberately no cooldown knob:
  R4 (#336) removed exactly that window from likes, and re-adding one here
  would re-open the bug D-178 closes. **Deploy-free rollback lever:**
  `trade.presentment_rules` → false + `POST /api/feature-flags/reload`; both
  routes are then byte-identical to pre-D-178 (pinned by
  `test_route_flag_off_is_byte_identical` / `test_flag_off_is_byte_identical`).

## 3. Evidence scope

- [x] **Structural guard:** **added by the QA-resolution pass** (it was `n/a`
      at the first build, when the only mobile edit was a comment). That pass
      changes mobile BEHAVIOUR — the queued ✓ now invalidates the
      `shop-ideas` cache rows (QA-B B-5) — so `mobile/tests/check-shop-deck.js`
      gains **k10**: the `invalidateQueries` call sits in the same `res.queued`
      branch k4 gates, carries the `['shop-ideas', …]` key, and passes
      `refetchType: 'none'` (a refetch would rebuild the open pager under the
      user's thumb — the P-1 rule). Proven RED with the call deleted
      (`no invalidateQueries call in the queued branch`). k8's three `#418`
      sites are intact; the suite reports **154 PASS** (153 + k10),
      `npx tsc --noEmit` is clean and `bash scripts/testid-lint.sh` is OK.
      The empty-state copy changes (B-2/B-3/B-6) are string/branch changes with
      no new testID and no new component; they are unreachable without a
      non-zero server count by construction, which is what the backend tests
      pin.
- [x] **Unit tests:** `backend/tests/test_asset_ideas.py` (+6 route tests, +1
      `route_db` fixture, one pre-existing test renamed/re-documented) and
      `backend/tests/test_fair_packages.py` (+6 tests) at the first build;
      **+4 and +2 in the QA-resolution pass** (18 in all). Every new test is
      proven RED — 7 against the unfixed routes, 5 against targeted sabotage of
      the fix (posture/regression bars that CANNOT be red on the baseline), and
      the 6 from the QA pass against four named mutations of the FIXED code
      (Q-B, B-1-off, set-size, flag-gate-removed), each run and each producing
      exactly the expected failures. Two tables in
      [`backend-prd.md`](backend-prd.md) §7.
- [x] **Code-walk proof:** [`backend-prd.md`](backend-prd.md) §6 — file:line
      trace for send → next `asset-ideas` fetch → excluded, and the same for
      `fair-packages`. The QA pass adds the parity arm in §5.4 / R-10 (which of
      the deck's like memories are imported, and which two properties are
      inherited on purpose).
- [x] **Manual TestFlight checklist** — one line, because the runtime claim is
      one round trip:
      1. In a league where the shop window offers ≥2 ideas for a pinned player,
         tap **Send this offer** on the first tile and confirm the toast.
      2. Back out of the shop window entirely, re-enter it on the SAME pin
         (a fresh fetch, not the suppressed session), and confirm the sent idea
         is **absent** — from the tiles AND from the `1 / X` counter — while the
         other ideas are still there.
      3. Retract that offer in **Awaiting them** and re-open the window: the
         idea is **back**. (Proves the retraction half is inherited, not faked.)

      **Added by the QA-resolution pass** — three more, one per fix:
      4. **B-5 (the 60-second hole).** ✓ an idea, tap back **immediately**,
         tap "More offers" again within ~30 s. The sent idea must be **gone**.
         Before this pass it was still on screen (the cache row outlived the
         screen-scoped suppression set); this is the one step that proves the
         invalidation.
      5. **B-1 (declined parity), needs a second test account.** Send an offer,
         have the partner **decline** it in Matches, then reopen the shop on
         the first account (force-quit first, so the session reloads its like
         memory). The idea must still be **absent** — the deck holds it for a
         week and now so does the shop.
      6. **B-2/B-3 (honest copy).** Pick a pin with a thin Same-value pool and
         ✓ every idea in it, then reopen. You must see *"You have offered every
         same-value deal here"* — **not** *"Nobody in this league holds…"* and
         **not** the *"Nothing at {POS} — showing all positions"* widen notice.
         Seeing either of the old two means `excluded_by_group` is not
         reaching the client.
- [ ] WAIVED — n/a.
- `testID`s added/renamed: none (`shop.empty` and `trades.asset-ideas` keep their ids; only the strings inside them branch).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** (twice — first build, then the QA pass) | Both rows in § Trades: `POST /api/trades/asset-ideas` (new D-178 clause; the "a LIKE never excludes here" sentence was deleted because it became false) and `POST /api/trades/fair-packages` (new D-178 clause). Response-semantics change on both, no request-shape change. **QA pass:** the B-1 parity amendment (the `like_days` subset, and why a declined offer needed it), the C-4 additive fields (`excluded_count`, `excluded_by_group`) with an explicit statement of what they do and do not do to flag-off byte identity, the per-request log line, and A-2's softening of the absolute cap claim on both rows. |
| `living-memory/LLD.md` | **n/a** | No convention shifted. The route→generator kwarg, the shared key builder and the non-fatal pref-load posture are all existing conventions being applied, not new ones. The one thing worth remembering — that a like exclusion is now a cross-surface rule — is a DECISION (D-178), already written. |
| `docs/architecture.md` | **n/a** | No module wiring changed. Both routes already call `trade_service`; both already load per-user preference state; `_load_presentment_exclusions` already existed and already read these two tables. Two more call sites on an existing edge is not a data-flow change. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **n/a**, re-checked after the QA pass | No shared constant, enum string or color. The exclusion key is still server-internal and never crosses the wire. The QA pass DOES add two fields the client branches on (`excluded_count` / `excluded_by_group`), but they are plain non-negative integers with no enum, no threshold and no shared constant — the client's only rule is `> 0`, and there is exactly one client (both routes are mobile-only). Nothing for a second client to agree with, so nothing to invariant. |
| `docs/glossary.md` | **n/a** | No new domain term. "Awaiting like", "exclusion set", "presentment" are all already defined; D-178 reuses them. |
| `docs/config-reference.md` | **updated** (extra row — the trigger table mandates it) | `trade.presentment_rules` flag row: R4's reach now covers `asset-ideas` + `fair-packages`. § "The R4 bypass": the two new consult sites are deliberately outside `r4_bypass()`. |
| `docs/runbook.md` | **updated** (QA pass) | § Presentment-rules tripwire, at the kill procedure: a callout that flipping `trade.presentment_rules` also un-fixes #418 — the shop and the anchored sweep resume re-offering sent packages, with no signal, because the tripwire counts R1/R2/R3/R5 only — pointing at the per-rule knobs for a single-rule incident and naming the two new log lines as the only way to see the coupling. QA-B §4's recommendation, adopted verbatim. |
| ADR or `DECISIONS.md` entry | **already exists** | [D-178](../../../../living-memory/DECISIONS.md), written 2026-09-03 with the ruling; its status line moves from "ruled, not built" to built-on-branch. No new ADR — this applies an existing architectural rule to two more surfaces rather than making a new one. |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` → **4605 passed, 1 skipped** after the
  QA-resolution pass (4599/1 at the first build; +6 tests, nothing lost).
  `tsc --noEmit` clean. `check-shop-deck` **154 PASS** (153 + k10).
  `testid-lint` **OK** (no testID added or renamed).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the
  red-proof table, the suite counts and the mobile suites.
- **TestFlight verification:** the 3-step checklist in §3, run by the operator
  after the merge deploys; outcome to be logged in TEST_LEDGER.
- **Express lane declared by the operator?** **No** — the operator asked
  explicitly for *"the full gates plus the API reference update"*. Full gates
  applied. The bright line is relevant and respected: this IS an API
  response-semantics change, so it could never have been a quick fix.

## 6. Deviations from the written spec (operator read, not waivers)

1. **Where the filter lives.** The spec proposed a
   `_drop_liked_ideas(ideas, exclusion_keys)` helper in `server.py`, applied to
   the generators' RETURN values. Built differently: filtering after the
   generator means filtering after `asset_ideas_group_cap` / `fair_packages_cap`,
   which silently shrinks the answer (send 3 offers, get 17 ideas where 20 were
   promised). The exclusion set is threaded INTO both generator impls instead
   and applied at emission. Sharing is preserved and arguably improved: ONE
   loader (`_load_presentment_exclusions`) and ONE key constructor
   (`trade_service.presentment_key`) serve every surface. See
   [`backend-prd.md`](backend-prd.md) §5.1.
2. **The flag.** The spec said "no flag" (meaning: add none). None was added,
   but the existing `trade.presentment_rules` gate was REUSED, mirroring the
   deck's own call site. Reasoning in §2 and in `backend-prd.md` §5.5. The
   consequence the operator should know: killing that flag would also kill the
   shop's like memory. The alternative — leaving the idea routes ungated —
   would have made `docs/config-reference.md`'s "R4's only switch" false.

   **QA-B §4 reviewed this coupling and recommended KEEPING it; adopted.** A
   dedicated flag would mean two switches for one rule (R4) — the drift the G6
   wave designed this flag to prevent, and the first time someone kills R4 on
   the deck and forgets the second switch, two surfaces disagree about the same
   package for the same user, which is a harder bug than the one being
   reverted. **The cost, named plainly and not paid down by a flag:** a panic
   revert of `trade.presentment_rules` also un-fixes #418 — the shop window and
   the anchored sweep resume re-offering every package the user has already
   sent, with no deploy, no code change, and nothing that says so (the
   `presentment-tripwire` WARNING counts R1/R2/R3/R5 only, `server.py:5853`, so
   it goes quiet in a way that looks like the revert worked; there is no
   analytics signal for a re-offered idea). Two cheap mitigations were bought
   instead: **(a)** both idea routes now log the exclusion-set size and the
   drop count per request, so a flag revert shows as an abrupt, permanent
   `set=0` on both lines — the only tripwire this coupling has; **(b)**
   `docs/runbook.md`'s presentment-rules kill procedure carries a callout
   saying the revert un-fixes #418 and pointing at the per-rule knobs
   (`max_overpay_min_value`, `pos_net_cap`, `pick_gap_min_value`,
   `need_gate_min_value`) for a single-rule incident, reserving the flag for a
   genuine group revert. Recorded in D-178's consequences.

3. **Two additive response fields** (QA-B C-4 — this deviates from the first
   build's "no new field" contract, deliberately). `asset-ideas` gains
   `excluded_count` + `excluded_by_group`; `fair-packages` gains
   `excluded_count`. They exist because the routes were dropping ideas
   silently, which left three client empty states explaining an exclusion with
   copy written for an empty market — one of them (the Same-value auto-widen)
   asserting a fabricated cause on the very line §4a wrote to be
   never-fabricated. The bright line applies (this is an API contract change),
   full gates were run, and the flag-off consequence is stated rather than
   glossed: every EXISTING field stays byte-identical with the flag off, and
   the two new ones are present-but-0 in that state. See
   [`backend-prd.md`](backend-prd.md) §4.
