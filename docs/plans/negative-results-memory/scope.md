# Feature Scope — Negative-results memory

**Date:** 2026-08-21
**Entry point:** direct ask (operator product-gap review, item 2; dispatched cross-session 2026-08-21)
**Builder:** planning session `vigilant-spence-8583f5` (branch `claude/vigilant-spence-8583f5`); build unassigned — planning stops at the doc suite
**Operator sign-off on waivers:** PENDING — this scope names three operator decisions (§6) that must be answered before build

Parent docs: [README.md](README.md) · [research-verification.md](research-verification.md) (code-truth memo — every claim below cites it) · PRD/HLD/LLD via dual-agent review (in flight)

---

## 0. What this builds (one paragraph)

A per-league memory of rejected trade proposals — keyed by league-mate, shared-taxonomy
trade shape, and the shipped `trade_pass_reasons` rejection codes, regime-tagged at
rejection time — consulted by the trade engine as a **soft prior at generation time**
(down-weighting candidate families that have repeatedly died), plus the **feeding of
`trade_gen_v2.acceptance_prior`** (ratified empirical-Bayes per-manager math that today
returns 0.5 uniformly because no caller supplies `acceptance_stats` — memo §2f). It is
explicitly NOT a fourth hard filter: D-067's operator line ("one swipe must not silence
a player's whole trade space") is honored by clamped soft multipliers with
byte-identical-disable knobs (memo §Design-constraints 3, 4, 9).

## 1. Analytics scope

- [x] **(b) Existing events cover it** — the memory *consumes* the shipped spine
  (`deck_impressions ⨝ deck_outcomes`, `trade_pass_reasons`, `trade_matches` declines)
  and its *effect* is measured by the same spine plus bake-off arm attribution
  (`model_arm`, `bakeoff_runs.config_json` snapshots the negmem knobs — memo §DC-7).
  No new client events; no taxonomy change.
- [x] **(a-lite) New server-stamped field, not an event:** cards touched by the prior
  carry `features_json.negmem = {mult, keys_hit, ver}` (the `_deck_fatigue_multipliers`
  stamping precedent, memo §2a) → `docs/data-dictionary.md` row. Exact shape is an LLD
  decision; the commitment here is: every influence is stamped, none is silent.

## 2. Schema & flag scope

- **New tables: NONE in v1 (planned).** Memory derives on read — one bulk query per
  (user, league) job building an in-memory map, per the house style ("derive-on-read for
  learned state; stored state is for durable promises," memo §DC-2) and current volumes
  (~845 outcomes; memo §8). A materialized `negmem_*` table is admitted ONLY if the
  job-start read is latency-measured as too slow; that measurement is a named LLD/build
  gate, not an assumption. (`negmem_` prefix is this feature's reserved namespace in the
  three-way reconciliation; `receipts_` is the sibling's.)
- **New flags:** `trade.negmem` (default **false**; OFF ⇒ no reads, no stamps,
  byte-identical generation — the organic-isolation pattern). Graduation criterion:
  bake-off-measured, stated in PRD.
- **New `model_config` knobs (planned, LLD finalizes):** `negmem_strength` (0 = disable,
  byte-identical), `negmem_min_evidence` (shrinkage floor — mandatory at n≈845),
  `negmem_halflife_days`, `negmem_floor` (clamp — a prior can sink a card, never zero
  it). Layer 2 reuses the SEEDED gen_v2 knobs `gen2_accept_prior_strength` /
  `gen2_accept_prior_global` (memo §2f) — no new keys for the stub feed. Every knob gets
  an arm-A disposition sentence (knob-inventory guard) and a `_MODEL_CONFIG_DEFAULTS`
  seed row (the settability trap fixed 2026-08-20 — knobs without rows can't be flipped).
- Rollback: flag off = full revert; `negmem_strength = 0` = deploy-free soft revert.

## 3. Evidence scope

- [ ] **Structural guard:** n/a in v1 — no mobile surface (WAIVER requested: v1 is
  server-side generation only; any later "why am I not seeing X" explainer UI re-enters
  gates on its own).
- [x] **Unit tests (planned):** pytest — map-builder correctness (windowing, D-091
  exclusion, shrinkage, regime tags), clamp semantics (sink-never-rise, no gated-card
  rescue), byte-identical disable (golden), acceptance_stats feed math vs the stub's
  documented E-B formula, identity hygiene (league ids, never account ids — memo §DC-8).
- [x] **Code-walk proof (planned):** the consultation seam per generation path
  (v1/v3, gen_v2, fit) with the bake-off interaction stated (a generation-time prior is
  part of the model under test; knobs snapshotted — memo §DC-7).
- [x] **Manual TestFlight checklist (planned):** operator deck-sanity pass with the flag
  on for their device — decks materially unchanged except named down-weights, stamps
  visible in readout SQL.

## 4. Docs scope

| Doc | Update |
|---|---|
| `docs/config-reference.md` | flag + knobs |
| `docs/data-dictionary.md` | `features_json.negmem` stamp; (table row only if the materialization gate is taken) |
| `docs/api-reference.md` | n/a expected (no route change in v1) — confirm at LLD |
| `docs/architecture.md` + `living-memory/HLD.md` | the memory-consultation seam, if HLD confirms a shared hook |
| `docs/plans/shared/trade-shape-taxonomy.md` | v1.1.0 additive: rejection/objection vocabulary section + PRODUCER column (three-way sign-off) |
| `docs/glossary.md` | "negative-results memory", "regime tag" |
| ADR | soft-prior-not-fourth-filter decision (cites D-067) |

## 5. Ship gate (for the eventual build — recorded now)

- CI green; knob-inventory guard green with disposition sentences; flag-off golden.
- TEST_LEDGER: unit counts + the latency measurement for the derive-on-read gate.
- Express lane: **no** (schema-adjacent, flag surface, engine behavior — bright line).

## 6. Operator decisions this scope surfaces (answer before build)

1. **D-067 family-level ruling.** D-067 deliberately kept dismisses exact-pair and put
   impression-readback out of scope. This feature IS family-level memory — as a clamped
   soft prior, not an exclusion. Does the D-067 principle ("accuracy over volume; one
   swipe must not silence a trade space") permit soft family down-weighting, and at what
   floor? (PRD carries the recommendation; the ruling is the operator's.)
2. **Layer-2 v1 boundary.** Recommendation (memo §DC-10): v1 = feed the existing
   `acceptance_prior` stub from `trade_matches` responses + decline records; full
   per-shape/per-reason tendency modeling = follow-on. Confirm or widen.
3. **Privacy/fairness of modeling league-mates.** Layer 2 models OTHER managers —
   including non-app-users (facts basis: memo §7) — from their observed responses to
   proposals. Surfaced, not decided: does the operator want (a) full layer 2, (b)
   app-users only, (c) aggregate-only (no per-person records shown to anyone, engine
   internal), or (d) defer layer 2 entirely? The PRD presents the options with the
   memo's factual basis; nothing is built until ruled.
