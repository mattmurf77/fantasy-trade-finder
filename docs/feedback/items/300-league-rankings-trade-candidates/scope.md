# Feature Scope — #300 League rankings positional trade candidates

<!--
Copied from docs/templates/feature-scope.md. Every section is answered or
explicitly WAIVED with a reason. Waivers are surfaced to the operator before
build. NOT an express-lane change: this adds a field to a public API contract,
which CLAUDE.md §Conventions "Feature gates" puts on the bright line.
-->

**Date:** 2026-08-12
**Entry point:** feedback #300 — frozen design in
[`operator-answers-2026-08-12.md`](operator-answers-2026-08-12.md)
(supersedes `operator-answers-2026-08-11.md` §6 and `plan.md` on conflict);
mockups in [`mockups/candidates-300-v2/`](../../../../mockups/candidates-300-v2/)
**Builder:** backend build agent (`build-300-backend`, based on `origin/main`
@ `62ff8d6`) + mobile build agent (`build-300-mobile`), running in parallel
against a frozen field contract
**Operator sign-off on waivers:** **NEEDED** — four waivers below (§1 analytics,
§3 Maestro/capture, §4 three doc rows), each flagged inline

---

## 0. Ownership split (this scope block covers the whole feature)

| Surface | Owner | State at time of writing |
|---|---|---|
| `medians` field on `GET /api/league/power-rankings` | backend agent | **built** — this branch |
| `league.pos_candidates` / `league.player_trade_handoff` registration (`config/features.json` + `feature_flags.py` `FLAG_KEYS` + the three release-mirrored test flag fixtures) | backend agent | **built** — this branch |
| `LAUNCHED_FLAG_DEFAULTS` (mobile side of the same two keys) | mobile agent | mobile branch |
| The divider, the 33% Buyer/Seller bands, the stacked-roster drill-in, Variant D player rows, the Offer/Target handoff | mobile agent | mobile branch |
| `docs/api-reference.md` / `docs/cross-client-invariants.md` / `living-memory/*` edits | **orchestrator** | proposed text handed over in the backend agent's status file — deliberately NOT applied here (both build branches would collide on the same lines) |

---

## 1. Analytics scope

- [x] **(c) WAIVED for the BACKEND half — no analytics needed because:** the
  `medians` field is a read-only derivation of data already in the same
  response. It fires no event, stores nothing, and creates no new user-visible
  moment on the server side. `GET /api/league/power-rankings` already emits
  nothing server-side today and #300 does not change that.

- [ ] **(a)/(b) for the MOBILE half — DEFERRED TO THE MOBILE AGENT, and this
  is a live waiver the operator should see.** #300 adds at least three genuinely
  new user moments the backend cannot instrument: the divider being *seen*, a
  team being opened *from a side of the line*, and the Offer/Target handoff into
  the trade finder. Recommendation, not a decision:

  | Event | Properties | Fires when | Client |
  |---|---|---|---|
  | (existing) `league_subset_changed` | `subset`, `from`, `source`, … | position pill changes | mobile |
  | (existing) `league_team_opened` | `via`, `rank`, `basis`, `subset`, … | team drill-in opens — **extend with `side: above\|below\|at`** rather than adding an event | mobile |
  | (new, if wanted) `league_candidate_action` | `action: offer\|target`, `side`, `pos` | Offer/Target tapped | mobile |

  **Binding constraint if any new event is added:** it must go into
  `ALLOWED_CLIENT_EVENTS` **and** `EVENT_PROPS` in `backend/analytics_taxonomy.py`
  (DEFAULT-DENY — unregistered events are counted and dropped server-side, never
  4xx'd, so an unregistered event is silently invisible), **and** the same commit
  must make an explicit `NON_INTENT_EVENTS` decision in
  `backend/analytics_queries.py`. `INTENT_EVENTS` is derived by subtraction, so a
  new name that is not an intent event step-changes DAU/WAU permanently and
  silently. Verdicts if the events above are built: a divider *impression* is
  non-intent; `league_candidate_action` **is** intent (leave it out of
  `NON_INTENT_EVENTS`).

## 2. Schema & flag scope

- **New/changed tables or columns:** none. No migration; `docs/data-dictionary.md`
  not in scope. The medians are computed per request from data already loaded.
- **New/changed feature flags:** two, **both default OFF**, registered on this
  branch in all four required places:

  | Key | Default | What ON does | Graduation criterion |
  |---|---|---|---|
  | `league.pos_candidates` | `false` | the median divider, the 33% Buyer/Seller band labels, and the stacked-roster drill-in on the mobile League rankings list, **only** when exactly one core position is selected | divider verified on the simulator against an 8-team league (the small-league case §4.4 of the frozen design calls out: 6 of 8 teams carry a call) **and** a 12-team league; both `is_you` positions (above and below the line) exercised |
  | `league.player_trade_handoff` | `false` | the drill-in's Offer/Target row actions, which pin `give`/`receive` and route to the trade finder, **replacing existing pins** | pin-replacement verified as non-destructive-by-surprise on the sim; separate key precisely so the divider can graduate without the write-side handoff |

  Registration: `config/features.json` (+ a `_comment_league_pos_candidates`
  block), `backend/feature_flags.py` `FLAG_KEYS` (the load-bearing one —
  `_load_from_json` drops keys absent from `DEFAULT_FLAGS`, so `features.json`
  alone is a silent no-op), and the three release-mirrored test fixtures
  (`backend/tests/fixtures/flags/{release,profiles-on,onboarding-v2}.json` —
  `test_seed_ui_test_db` enforces `release.json` as an exact mirror and the other
  two as release ± a named delta). `all-on.json` is a 41-key subset and is
  deliberately untouched. Mobile-side `LAUNCHED_FLAG_DEFAULTS` is the mobile
  agent's.
- **New env vars / `model_config` keys:** none.
- **Ship-the-knob:** both flags are the deploy-free rollback lever. The
  `medians` field itself is **unflagged** — see §6.

## 3. Test scope

- **Backend pytest:** `backend/tests/test_power_rankings.py` — 8 new tests
  (`-k median`), each proven to FAIL on at least one deliberately sabotaged
  build (9 sabotages run; matrix in the backend agent's report). The trap the
  brief names is covered explicitly: sabotage **S3** keeps `medians` present and
  its `value` correct while labelling the *mean*, and is caught.
- [ ] **Maestro delta — WAIVED FOR THE BACKEND HALF because:** this branch adds
  no user-visible mobile surface; it adds one additive JSON key. **NOT waived for
  the feature** — the divider, the band labels, the stacked drill-in and the
  Offer/Target handoff are all user-visible mobile changes and **require** a
  new/extended flow in `mobile/.maestro/` per CLAUDE.md gate 2. That flow is the
  mobile agent's deliverable; this scope block records it as owed, not as waived.
- **`testID`s added/renamed:** none on this branch (backend). Mobile's are
  subject to `mobile/scripts/testid-lint.sh` in CI.
- **Capture delta:** none from the backend. Mobile owes re-captures of the
  League rankings list (single-position filtered, divider visible) and the team
  drill-in.
- **Smoke-suite impact:** the backend change is additive to a response body no
  smoke flow asserts key-count on; flags are OFF so no mobile smoke flow's
  rendering changes. Expected green with no edit.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **OWED — text written, not applied** | The `GET /api/league/power-rankings` row gains the `medians` field. Exact replacement text is in the backend agent's status/report; it is **orchestrator-owned** because both #300 build branches would otherwise collide on that single very long line. **This row is not closed until the orchestrator applies it.** |
| `living-memory/LLD.md` | n/a | No convention shifted. `medians` follows the existing additive-key precedent (`starters`, `tier`, `picks`) and reuses the existing `_aggregate_pick_label` helper rather than introducing a second value scale. |
| `docs/architecture.md` | n/a | No module added, removed, or re-wired. `_position_medians` is a private helper in `server.py` beside the route it serves; `backend/power_rankings.py` is untouched. |
| `living-memory/HLD.md` | n/a | No architecture shift: no new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **WAIVED, with a reason the operator should weigh** | The 33% band size (`round(team_count * 0.33)`) and the "line, not the label, is the direction rule" ruling are decided *client-side only* — no backend constant encodes them, and only one client (mobile) implements them. By the doc's own trigger ("a value that exists in multiple clients") it does not qualify today. **It will the moment web or the extension renders this divider**, and the value would then have to move server-side or be duplicated. Flagged rather than silently skipped. |
| `docs/glossary.md` | **WAIVED** | "Buyer"/"Seller"/"median divider" are UI copy on one screen, not domain terms that appear in code identifiers or across clients. Revisit if the drill-in vocabulary spreads. |
| `docs/config-reference.md` | **OWED (flags)** | Two new flag keys. Same orchestrator-collision reasoning as `api-reference.md`; the `_comment_league_pos_candidates` block in `config/features.json` carries the full description in the meantime. |
| ADR / `DECISIONS.md` | **WAIVED** | Three decisions were made (median population, subset scope, label de-gating) but none overturns a prior design choice or sets a new convention — they are documented verbatim in the `_position_medians` docstring, which is where a future reader hits them. The one candidate for a `DECISIONS.md` entry is the **subset scope** — see §6, which the operator should read before merge. |

## 5. Ship gate declaration

- **Simulator-gate tier:** **Tier 2** — feature flow + affected smoke subset.
  Rationale against the matrix in `docs/runbook.md`: the user-visible change is
  confined to one screen and its drill-in, and ships behind two default-OFF
  flags, so a full smoke (Tier 1) is not indicated; but it is not
  backend-only-CI (Tier 4) either, because the flags will be flipped ON for the
  operator to evaluate the divider and the flow must be proven in that state.
  The run must be done with `league.pos_candidates` **ON**, on both an 8-team and
  a 12-team league (§2 graduation criterion).
- **Evidence:** `living-memory/TEST_LEDGER.md` entry + `qa/sim-runs/last-sim-run.json`
  written after the run. Enforced by `githooks/pre-push`.
- **Operator deviation from the matrix:** none proposed.
- **Backend-only note:** this branch alone cannot satisfy the gate — it ships no
  mobile surface to run. The gate is satisfied at the merge of both halves.

## 6. Decisions that need operator eyes before merge

1. **`medians` is the ALL subset only.** `teams[].positions[P].value` is the
   whole-roster positional subtotal; Starters/Bench are derived *client-side*
   from `roster` + `starters`, and the frozen field shape
   (`{QB|RB|WR|TE: {value, value_label}}`) has no room for a per-subset median.
   **Consequence the client must honour:** the divider may render only while the
   subset is All. On Starters or Bench there is no server median and none can be
   labelled — the divider must be hidden, never drawn with the All value. This is
   the highest-risk ambiguity in the field and it is resolved by omission, not by
   silence. If the operator wants the divider on Starters/Bench, that is a
   **contract change** (additive sibling keys), not a client fix.
2. **The median population is every team in the payload, the caller included** —
   the frozen design keeps the caller in the list as the anchor, so the line must
   be drawn across that same list.
3. **Even team counts take the mean of the two middle values** (the textbook
   median, and what a naive client-side implementation computes, so server and
   client agree). This also preserves the property §4.1 of the frozen design
   depends on: an odd league leaves exactly one team *on* the line, an even one
   leaves none.
4. **`medians.value_label` is ungated.** It does **not** ride the
   `aggregate_tier_labels` experiment that gates the per-team `value_label`,
   because a divider labelled for the operator and blank for everyone else is
   worse than no divider. No restructuring was needed: `_aggregate_pick_label`
   is a pure function of the value. The experiment's own status
   (frozen design §3, §4.3 "Unresolved") is therefore **no longer a blocker for
   #300** — it remains open for the per-team labels only.
5. **`medians` ships unflagged** while the divider that consumes it ships behind
   `league.pos_candidates`. It is additive (changes no existing key), costs one
   sort per core position per request, and a flag-on/field-absent state would
   only give the client a worse contract to reason about.
