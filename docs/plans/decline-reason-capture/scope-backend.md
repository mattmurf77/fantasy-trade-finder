# Feature Scope — Decline-reason capture (BACKEND half)

> Spec: [SPEC.md](SPEC.md) (operator-approved 2026-08-17). Approved interaction
> prototype: [`mockups/decline-reason-capture/07-two-step-diagnostic.html`](../../../mockups/decline-reason-capture/07-two-step-diagnostic.html).
> The MOBILE half is a sibling agent's, on `feat/decline-reasons-mobile`. This
> block covers `backend/**`, `config/features.json` and the docs only — no
> file under `mobile/` is touched by this branch.

**Date:** 2026-08-17
**Entry point:** direct ask (operator-approved spec, `docs/plans/decline-reason-capture/SPEC.md`)
**Builder:** backend build agent, branch `feat/decline-reasons-backend` (rebased onto `origin/main` tip `b97744c` — the recovery-ledger commit on top of `92d2358`; post-2026-08-16 feedback wave incl. G6 presentment rules, post gen-v2 knob reconciliation)
**Operator sign-off on waivers:** yes — see §5 (the pre-ship **simulator gate is waived**, operator decision 2026-08-17) and §3 (Maestro/capture rows belong to the mobile half). The Elo change was **approved in-session on 2026-08-17** (see §6).

> **Operator decisions taken mid-build (2026-08-17), in the order they arrived.** Each superseded something and each is reflected in code, tests and docs:
> 1. **SPEC §4 Elo suppression APPROVED** — build as specified; not a merge blocker (§6).
> 2. **`impression_id` fallback APPROVED** — a client that sends none must be *recorded*, never refused; mark the two paths apart on the row (§2b).
> 3. **Ships LIVE for ALL users, not the tester allowlist** — **supersedes SPEC §5**. No allowlist gating anywhere in the feature (§2).
> 4. **Pre-ship simulator gate WAIVED** — Maestro flows ship authored-but-unexecuted; TestFlight is the QA (§5).

---

## 1. Analytics scope

- [x] **(a) New events specced** — SPEC §6, registered in `backend/analytics_taxonomy.py` **before any emitter ships** (the registry is default-deny behind a 200; a name that lands after its `track()` call is silent, unrecoverable data loss).

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | `trade_pass_layer1` | `reason`, `switched_from`, `impression_id`, `trade_id`, `ms_since_render`, `platform` | the layer-1 tile tap — **carries the disposition**; there is no separate pass event, because there is no ✕ | mobile |
  | `trade_pass_layer2` | `reason`, `detail`, `has_free_text`, `switched_from`, `impression_id`, `trade_id`, `ms_since_render`, `platform` | the layer-2 option tap, or the free-text send | mobile |

  Closed enums: `reason` ∈ `value`\|`fit`\|`other`; `detail` ∈ the 8 codes of SPEC §2; `switched_from` ∈ the three reasons or the literal `none`.

  **Both are CLIENT-fired, not server-fired**, and the split is deliberate. The durable truth of a reasoned pass is the `trade_pass_reasons` row plus the `deck_outcomes` `action='pass'` — neither forgeable, neither dependent on the allowlist (the `deck_card_viewed` precedent). These two names are the client-side receipt: they carry `ms_since_render`, which only the emitter knows. The server keeps firing `match_swiped` on the pass exactly as the ✕ did, so no existing funnel moves and no disposition double-counts.

  Both stay **INTENT** (not added to `analytics_queries.NON_INTENT_EVENTS`): both are real user decisions, and every user firing one has already fired `trade_card_viewed` on the same card, so admitting them cannot step-change DAU/WAU.

  **Free text is never a property.** It is stored on `trade_pass_reasons.free_text` and nowhere else (SPEC §3.4); `has_free_text` is a boolean. Pinned by `test_no_free_text_prop_exists_anywhere_in_the_family` and `test_route_never_records_free_text_in_an_event`.

  → follow-through: `docs/data-dictionary.md` (stored), taxonomy registered in `backend/analytics_taxonomy.py` with the SPEC citation in-comment.

### 1a. Interpretation call — the `platform` prop

SPEC §6 enumerates `platform` (`ios|android|web`, "set explicitly at the emitter, never inferred"). `backend/analytics_taxonomy.py` states repeatedly that **device** platform is a `user_events` COLUMN derived server-side in `analytics_ingest.py` (the NULL-`platform` incident) and "must not become" a prop.

**Resolved by registering it, with the tension recorded in-comment.** The spec is operator-approved and explicit, and the failure mode of omitting it is worse than the duplication: a prop the client sends but this registry omits is stripped silently behind a 200 — the exact trap the file exists to prevent, and the sibling mobile agent is reading the same spec. The COLUMN stays authoritative for any cross-event platform cut; the prop is the emitter's own claim, and a disagreement between the two is a client bug worth being able to see. This is the one deliberate exception to that rule and the taxonomy comment says so.

## 2. Schema & flag scope

- **New tables:** `trade_pass_reasons` — one UPSERT row per passed card, PK `impression_id`. Columns: `user_id`, `league_id`, `trade_id`, `reason`, `detail`, `free_text`, `switched_from`, `elo_signal_at`, `created_at`, `updated_at`. Index `ix_trade_pass_reasons_user_league`. → [`docs/data-dictionary.md`](../../data-dictionary.md#trade_pass_reasons).
  - **No `_migrate_db` ALTER entry is needed or added:** this is a NEW table, created by `metadata.create_all()` on every boot, exactly as `deck_outcomes` / `deck_suppressions` were. The additive-ALTER list is for columns on existing tables; adding a row there for a new table would be a no-op that fails silently forever.
  - **Justification for a new table over additive columns on `deck_outcomes`** (the call the mission asked to be justified): `deck_outcomes` is append-only *by contract* ("rows are NEVER mutated"), holds several rows per impression (`viewed`/`pass`/`undo`), and has no unique key to upsert on. SPEC §3 requires an upsert keyed on `impression_id` that grows in place across three taps. Bolting mutable columns onto the append-only spine would break its invariant and its readers. The **disposition** still lands in `deck_outcomes` as `action='pass'` — unchanged — so nothing that reads the F1 spine has to learn about this feature.
- **New flags:** `feedback.decline_reasons` — **`true` in `config/features.json`**, registered default false in `backend/feature_flags.py` `FLAG_KEYS`, mirrored into every flag fixture (`release.json`, `onboarding-v2.json`, `profiles-on.json` — the three the parity/key-set tests compare — plus `all-on.json`, which the mobile Maestro flows run against). → [`docs/config-reference.md` § Flags — Decline-reason capture](../../config-reference.md#flags-decline-reason-capture-2026-08-17-ships-on).
  - **Scope: ALL users** (operator, 2026-08-17). This **supersedes SPEC §5**, which proposed tester-allowlist scoping. An earlier revision of this branch built the double gate plus a per-caller mask on `GET /api/feature-flags`; **both were removed** when the scope changed. There is now no allowlist condition anywhere in the feature — not on the route, not on the served flag map, and `config/tester_allowlist.json` is untouched.
  - **Why that matters beyond "less code":** the flag is the *only* condition, so `GET /api/feature-flags` serves every caller the same value and the client surface and the route can never disagree about whether the feature is live. That is what makes this a true one-line revert.
  - **Kill switch (unchanged requirement, and tested):** flip to `false` + `POST /api/feature-flags/reload` — no deploy. OFF ⇒ the route 404s `feature_disabled` before any session work, no `trade_pass_reasons` row is ever written, and `/api/trades/swipe` is byte-identical (nothing in it reads the flag). Pinned by `test_flag_off_404s_and_writes_nothing`, `test_flag_off_leaves_the_swipe_pass_path_byte_identical` and `test_swipe_pass_is_unchanged_even_with_the_flag_on`.
  - **Rollback retains data:** `trade_pass_reasons` rows already written stay (they are the diagnostic's whole output); nothing reads them on any user-facing path.
- **New `model_config` keys:** `pass_reason_elo_suppression`, default **1.0 (ON)**, in `ranking_service._DEFAULT_CFG`. → [`docs/config-reference.md` § Decline-reason Elo suppression](../../config-reference.md#decline-reason-elo-suppression-ranking_service_default_cfg).
  - **Ship-the-knob / deploy-free rollback lever:** setting it to `0` restores today's behavior for every code (every reasoned pass writes Elo at the tile tap). It is read **only** on the reasoned-pass path — `/api/trades/swipe` never consults it — so unreasoned passes are unaffected in either position. Not yet in `_MODEL_CONFIG_DEFAULTS`, so it is a code default until seeded (same status as the `trade_service._DEFAULT_CFG` keys); seeding it is a one-line follow-up if live tuning is wanted.
- **New env vars:** none.

### 2a. Route shape — and why a new route

`POST /api/trades/pass-reason` (new). → [`docs/api-reference.md` § Trades](../../api-reference.md).

The mission asked for the extend-vs-add decision to be recorded. **A new route, and `/api/trades/swipe` is not modified at all.** Two reasons:

1. Only the **first** write of an impression is a disposition; layers 2 and 3 are refinements that must not re-run `record_decision`, the `deck_outcomes` append, the `trade_decisions` write or the swipe event. A `reason` field on `/api/trades/swipe` would either fire all of that three times or need an idempotency mode bolted onto a route that has none.
2. It makes SPEC §5's "flag off ⇒ the current ✓/✕ row renders byte-identically" *structurally* true in the backend rather than a claim about a conditional. Nothing in `swipe_trade` reads the new flag; the shipped path is byte-identical whatever this feature does. Pinned by two tests (`test_flag_off_leaves_the_swipe_pass_path_byte_identical`, `test_swipe_pass_is_unchanged_even_with_the_flag_on`).

**Request contract, reconciled with the mobile half** (`feat/decline-reasons-mobile`, which sends `{impression_id?, trade_id, league_id?, layer, reason, switched_from?, detail?, free_text?}` fire-and-forget). The route takes that payload **verbatim — no change is needed on their side**:

- `free_text` is the primary field name; `text` is accepted as an alias, so neither spelling is silently dropped.
- `layer` is accepted and **deliberately ignored** — the layer is derived from the fields present, which survives a dropped or reordered request in a way a client-asserted layer does not.
- a client-sent `switched_from` is accepted and **deliberately ignored** — it is derived server-side from the stored row, so it cannot disagree with the row it describes, and a client cannot forge a switch that never happened. Pinned by `test_mobile_payload_shape_is_accepted_verbatim` and `test_client_switched_from_is_ignored_in_favour_of_the_stored_row`.

**The cost, recorded honestly:** the pass side effects are written out twice in `server.py` — `swipe_trade`'s pass branch and `_apply_reasoned_pass`. That is deliberate: a shared helper would have had to be threaded through the live like/pass path, and a bug in that refactor would take *likes* down with it. `_apply_reasoned_pass` mirrors the pass branch line for line **as it stands post-G6** — including the D-060 `fit_congruence_mult` weighting on both the in-memory signal and the persisted `k_factor`, and `_save_deck_outcome_safe`'s `acting_user_id` argument. If the swipe pass branch changes, this mirror must change with it; the docstring says so at both sites.

**The contract (SPEC §3), implemented:**

- The **first** write for an impression — whichever layer it carries — performs the pass. Guarded by the upsert reporting `created`, so re-taps and retries cannot pass twice.
- Later writes only sharpen the row. Only supplied fields are written, so no write can lose an earlier one.
- **Order-independent:** a layer-2 write arriving without its layer-1 sibling (dropped request, restart mid-flow) still passes the card and derives its `reason` from the detail's parent.
- `switched_from` is derived **server-side** from the stored row, never taken from the client, so it cannot disagree with the row it describes.
- A tile switch deliberately **keeps** the stored `detail` even though it belonged to the prior reason. Clearing it would violate the never-lose rule; the row reads honestly as `reason=fit, detail=value_giving, switched_from=value`.

### 2b. `impression_id` — never required, always marked

**Operator decision, 2026-08-17: the fallback is APPROVED and is a product decision, not a safety net.** A client that sends no `impression_id` — `deck.signal_v2` off, or a legacy card — must still have its pass and its reason *recorded*. Refusing the write, or hiding the feature whenever the F1 spine is off, was the alternative and was rejected.

On top of that, `impression_id` arrives in a client-supplied body. The 2026-08-14 LLD-review fix made every outcome-writing route validate it (exists, owned by the acting user) precisely because an unvalidated id lets one session write into another user's history — and here it would be the **primary key** of a row this user writes. `_pass_reason_key` applies the same ownership check, with one deliberate difference from `_save_deck_outcome_safe`: an unknown/foreign id is **not** dropped, it degrades to the same per-user surrogate `local:<user_id>:<trade_id>`. The answer is never thrown away and the write is confined to the caller's own key space. `trade_id` is a per-card uuid4 prefix, so the surrogate is stable for the card's life and collides with nothing.

`key_source` (`impression` | `local`) records which path each row took, per the operator's ask that analysis be able to tell them apart. It is stored **explicitly** rather than inferred from the key's `local:` prefix — that kind of implicit encoding rots — and it is **never rewritten** by a later tap, because the key a row was minted under is a fact about the row. Only `impression` rows join the F1 spine and are usable for off-policy evaluation; `local` rows are honest reason counts with no card features behind them. Pinned by four tests (`test_key_source_marks_impression_linked_rows`, `test_key_source_is_not_rewritten_by_later_taps`, `test_missing_impression_id_still_records_both`, `test_signal_v2_off_uses_the_surrogate_even_with_an_id`).

## 3. Test scope

- [ ] **New flow / Extended flow:** n/a on this branch.
- [x] **WAIVED because:** this branch ships **no mobile surface** — `mobile/**` is owned by the sibling agent on `feat/decline-reasons-mobile`, which carries the Maestro delta covering tile → layer 2 → advance plus the Other/free-text path. A Maestro flow authored here would test nothing this branch changes.
- `testID`s added/renamed: **none** (no client files touched) — `mobile/scripts/testid-lint.sh` is unaffected.
- **Capture delta:** none — no visual change ships from this branch.
- **Smoke-suite impact:** none crosses a backend-only, default-OFF, allowlist-gated route. With the flag off (its shipped state) the route 404s before any session work and `/api/trades/swipe` is untouched, so every existing flow is unaffected by construction.
- **Backend pytest:** new file `backend/tests/test_decline_reasons.py` — **58 tests**, covering:
  - **the gate** — flag off 404s and writes nothing; and the operator's all-users scoping is asserted *positively*: an **empty** tester allowlist changes nothing, on the route or in the served flag map (`test_no_allowlist_gating_anywhere`), a plain caller with no device header works, and the shipped flag value is the served flag value,
  - **the kill switch** — the shipped `/api/trades/swipe` pass path is byte-identical with the flag OFF *and* with it ON,
  - **progressive writes** — layer 1 alone leaves a complete row *with the disposition*; layer 1 → layer 2; Other → text; the "Neither" free-text path; a tile switch records `switched_from` without losing the first answer; switching twice names the most recent prior; a re-tap is a no-op; layer-2-first still passes; two impressions are two rows,
  - **the `impression_id` fallback** — missing, unknown, foreign, and `deck.signal_v2`-off, each recorded under the surrogate with `key_source='local'`; `key_source` never rewritten,
  - **the mobile contract** — the sibling branch's exact payload accepted verbatim, the `text` alias, and a client-sent `switched_from` ignored,
  - **validation** — 6 parametrized bad payloads are 400s that write nothing; free text capped; the full SPEC §2 taxonomy accepted and nothing invented,
  - **the Elo matrix, per code, knob ON and OFF** (8 codes × 2) plus layer-1-only under all three reasons, once-only across retries, no re-write after switching away, and the rule tested as a pure function,
  - **analytics** — both names registered client-side and absent from `SERVER_FIRED_EVENTS`, props exactly the spec, no free-text prop anywhere in the family, and the route proven to emit no event containing the user's words.
  - Flag fixtures `release.json` / `onboarding-v2.json` / `profiles-on.json` updated so `test_seed_ui_test_db`'s mirror assertions stay exact; `all-on.json` gets the key ON so the mobile Maestro flows can execute (no parity test covers `all-on.json`, `release-300.json` or `release-espn-send-off.json` — the latter two are deliberately left alone, since a key absent from them reads false, which is what those pinned flows want).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | § Trades — new `POST /api/trades/pass-reason` row (gate, body, contract, Elo, response, errors); `trades/swipe\|generate\|flag\|pass-reason` added to the `@_gate_unverified_write` list |
| `docs/data-dictionary.md` | **updated** | TOC + new `## trade_pass_reasons` section (columns, upsert rationale vs `deck_outcomes`, key validation, Elo rule) |
| `docs/config-reference.md` | **updated** | TOC ×2; new § Flags — Decline-reason capture (all-users scope, kill switch, rollback-retains-data); new § Decline-reason Elo suppression (`pass_reason_elo_suppression`) |
| `docs/glossary.md` | **updated** | **Layer 1 / Layer 2 (decline reason)** and **Decline reason codes** (all 11 strings) |
| `living-memory/LLD.md` | **n/a** | No convention shifted. The route follows the shipped gate idiom (`_test_users_denied`), the storage follows the `save_deck_outcome` helper shape, and the knob follows `ranking_service._DEFAULT_CFG` + `_c()`. The one departure from a sibling table's convention (upsert vs append-only) is argued in the data dictionary, where a reader of that table will actually meet it |
| `docs/architecture.md` | **n/a** | No module added or re-wired. One route, one table, three DB helpers, one pure rule function — all inside existing modules and existing data flow |
| `living-memory/HLD.md` | **n/a** | No architecture shift: no new module, client, or major flow |
| `docs/cross-client-invariants.md` | **n/a** | The reason/detail enums are consumed by exactly one client (mobile) against one server, and they live in `database.PASS_REASON_*` + the taxonomy + the data dictionary. **Promote to cross-client the moment a second client renders these tiles** — web has no trade deck today |
| ADR / `DECISIONS.md` | **`DECISIONS.md` entry warranted at merge** | The SPEC §4 Elo rule is the non-obvious choice (a reasoned pass no longer implies a valuation). It is operator-approved (§6) and knob-reversible, so an ADR is heavier than it needs; a dated `DECISIONS.md` entry citing SPEC §4 + the knob is the right weight. **Not written on this branch** — `living-memory/` is shared state and this is one of two concurrent branches; the merging session writes it once |

## 5. Ship gate declaration

- **Pre-ship simulator gate: WAIVED** — operator decision, 2026-08-17. Maestro flows ship **authored but unexecuted**; TestFlight is the QA for this feature. This is an operator deviation from the matrix in `docs/runbook.md` § Pre-ship simulator gate, taken deliberately and recorded here as the scope block requires. The merging session carries the `living-memory/TEST_LEDGER.md` line (agreed with the coordinator) and no `qa/sim-runs/last-sim-run.json` is written for this feature.
- **What the waiver does and does not cover.** It waives the *simulator run*. It does not waive CI: the full backend suite is green (below), and it does not waive the flag discipline — `feedback.decline_reasons` remains a one-line, no-deploy revert, which is the thing standing in for the sim gate's assurance if the feature misbehaves in the wild.
- **Evidence for this half:** full backend suite **3110 passed, 1 skipped, 0 failures** on merge base `b97744c` (== `origin/main` tip; post-G6 wave, post gen-v2 knob reconciliation). No test was skipped, xfailed or loosened to get there.
- **Residual risk accepted by the waiver, stated plainly.** The backend is exercised end-to-end by 58 route-level tests, so the untested surface is the *client* interaction — the tile row, the notched layer-2 panel, the free-text box — none of which lives on this branch. The backend-side risk that a simulator run would have caught and these tests do not is close to nil; the mobile half's risk is real and is what TestFlight is now carrying.

## 6. The Elo consequence — operator-approved (SPEC §4)

**Status: APPROVED by the operator in-session on 2026-08-17.** Recorded here as a decision, not as an open question or a merge blocker.

Today every pass fires `record_trade_signal(winner=give_ids, loser=receive_ids, decision="pass")` — it asserts *"I value my players more than theirs."* Once the tester says **why**, that assertion holds for exactly one answer:

| Code | Elo write | Why |
|---|---|---|
| `value_giving` | **keep** | the user did say their side is worth more |
| `value_getting` | **suppress** | the user said the opposite; writing the usual signal inverts it |
| `value_other`, all `fit_*`, `other_text`, and layer-1-only `value`/`fit`/`other` | **suppress** | no valuation claim was made |

Implementation notes:

- The rule is a pure function in `ranking_service.pass_reason_writes_elo(code)` — ranking math stays in the ranking module — reading the knob **fresh on every call**, so `pass_reason_elo_suppression` is a live kill switch rather than a boot-time constant.
- The decision is taken from the **most specific code the write knows** (layer-2 detail, else layer-1 reason). Because layer-1-only always suppresses, a kept signal lands at the **layer-2 tap**, not the tile tap.
- `trade_pass_reasons.elo_signal_at` is claimed with `UPDATE … WHERE elo_signal_at IS NULL`, so no sequence of retries, re-taps or reordered writes can double-count one pass into Elo. Pinned by `test_value_giving_writes_elo_exactly_once_across_retries`.
- Knob at 0 ⇒ `pass_reason_writes_elo` is unconditionally true ⇒ the layer-1 tap writes Elo exactly as the ✕ does today, and the once-only claim stops layer 2 re-writing it. Pinned by the knob-off half of the matrix.
- Suppression is about **ranking math only**. The disposition (`deck_outcomes` `pass`, `trade_decisions`, `match_swiped`) is written for every code — the user did pass, whatever their reason. Asserted in every matrix case.

**Known one-way behavior, deliberately deferred rather than fixed:** an Elo signal earned by `value_giving` is **not retracted** if the tester later switches tiles. There is no negative-K correction path on this route — that machinery exists only for match dispositions (`record_disposition_signal` / `trade_k_decline_correction`) — and inventing one for a rare in-flight refinement is more ranking-math risk than the case is worth. It can never write a *second* time. Recorded in the data dictionary and config-reference, and pinned by `test_switching_away_from_value_giving_does_not_re_write_elo`.

## 7. Deliberately not built

- **No allowlist gating, and no `config/tester_allowlist.json` edit.** Built and then REMOVED when the operator rescoped to all users on 2026-08-17 — including the per-caller mask on `GET /api/feature-flags` that a tester-only flag would have needed. Recorded because the absence is deliberate, not an oversight.
- **No `_migrate_db` ALTER row.** New table ⇒ `metadata.create_all()`; see §2.
- **No admin read surface** for `trade_pass_reasons`. SPEC specifies capture, not a dashboard; `load_trade_pass_reason` exists for operator/test reads. A `/api/admin/...` roll-up is a separate ask once there is data to read.
- **No `deck_suppressions` hook.** A reasoned pass writes no F3 decline-suppression window, because today's ✕ pass writes none either (that hook lives on the match-disposition route). Adding one would be a behavior change smuggled in under an instrumentation feature.
- **No cross-client-invariants entry.** One client renders these enums today; §4 records the promotion trigger.
