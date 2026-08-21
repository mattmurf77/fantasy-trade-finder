# ADR-015 — Negative-results memory is a clamped soft prior, not a fourth filter

**Date:** 2026-08-22
**Status:** Accepted
**Author:** worktree session `claude/vigilant-spence-8583f5`
(scope block: [`../plans/negative-results-memory/scope.md`](../plans/negative-results-memory/scope.md);
doc suite [PLAN](../plans/negative-results-memory/PLAN.md) ·
[PRD](../plans/negative-results-memory/PRD.md) ·
[HLD](../plans/negative-results-memory/HLD.md) ·
[LLD](../plans/negative-results-memory/LLD.md);
operator rulings 2026-08-22, recorded in scope.md §6-RULINGS)

## Context

The system throws away its own most direct signal. A user swipes pass on a card and
picks a reason — `value_giving`, `fit_outlook`, and the rest of the layer-2 taxonomy —
and that reason is written to `trade_pass_reasons`, read by an Elo suppression rule, and
otherwise never consulted again. Generation runs the next day as if the rejection had
never happened, and the engine re-derives the same *kind* of offer from the same manager.

Three mechanisms already suppress repetition, and **none of them can express this**:

| Mechanism | Keys on | Why it can't cover the gap |
|---|---|---|
| **D-067 pass cooldown** | the **exact pair**, hard, 14-day window | Deliberately exact-pair. It has never seen the *cousin* offer — a different package, same manager, same objection. |
| **F3 fatigue** | **exposure** of a card that was **served** | Structurally cannot touch a candidate family that was never served in that composition: no impression exists to fatigue. |
| **F5 taste vectors** | attribute preferences, **reason-blind**, user-scoped | Never reads `trade_pass_reasons`, so it cannot tell "passed for value" from "passed for fit"; and it smears across leagues, so an aversion to a manager in one league follows the user into another. |

There is a real gap, and it is narrow. Honesty about *how* narrow is what justifies the
feature: the defensible delta over F5 is (1) consuming the filed reason and (2) being
league-scoped. "Sinks but never rises" alone would not have been enough.

The obvious way to close it is also the wrong one. Turning "this manager keeps saying no
to value-heavy offers" into an exclusion would reach exactly the outcome D-067 rejected
in its Alternatives section: *"one swipe would silence a player's whole trade space."*
That was ruled against a mechanism much narrower than family-level memory.

## Decision

Negative-results memory ships as a **clamped soft prior consulted at generation time**,
never as a filter. Concretely, and each clause is load-bearing:

1. **Multiplier, floored.** The map yields a multiplier per `(league-mate × reason
   family)`, combined per partner by **MIN** (two families of complaint about one manager
   are one manager problem, not a compounding one) and clamped at `negmem_floor` = 0.6.
   A card can sink; it can never vanish, and it can never be *rescued* either — the
   multiplier is applied **after** every gate, so it reorders acceptable trades and
   changes membership nowhere.
2. **Coarse key, ruled explicitly.** "Cousin" means *same partner + same reason family*
   (`value` | `fit`) — **not** package similarity. The operator was walked through this
   definition in plain terms and aligned on it. It is the whole reason the memory
   generalizes past D-067's exact pair, and the whole reason it must stay soft.
3. **Evidence floor and decay.** Cells below `negmem_min_evidence` = 3 are exactly
   identity, evidence decays on a 45-day half-life, and an admitted **like** nets against
   the partner's cells chronologically with a clamp at zero. One pass is noise; the
   memory forgives.
4. **Every influence is stamped.** `deck_impressions.features_json.negmem` carries the
   multiplier and the families that produced it on **every** row of a flag-on job —
   `{m: 1.0}` when nothing fired, not an absent key. A soft prior nobody can audit is
   indistinguishable from a bug.
5. **Two byte-identical disables.** `trade.negmem` off ⇒ no map, no kwarg, no seam, no
   stamp. `negmem_strength = 0` ⇒ `effective_mult` returns exactly 1.0 before any other
   knob is read — deploy-free, and the stamps stay so the readout still proves the flip
   landed.
6. **No new tables, nothing persisted.** The memory derives on read from the shipped
   spine. Deleting the source rows deletes the memory; there is no second copy to
   reconcile and no deletion path to build.

### The operator rulings this encodes (2026-08-22)

- **D1 — family-level soft prior: YES.** "Aligned." Soft family down-weighting ships as
  specced (floor 0.6, min-evidence 3, 45-day half-life, like-netting). This ADR is the
  durable record that D-067's principle **permits** soft family damping while continuing
  to forbid hard family exclusion.
- **D2 — layer-2 boundary: SEED ONLY.** v1 feeds aggregate per-manager acceptance counts
  into the `trade_gen_v2.acceptance_prior` stub that has shipped unfed since it was
  written. Per-trade-type tendency modeling stays deferred behind a data-volume gate.
- **D3 — privacy posture: (a) FULL layer 2**, ruled knowingly **against** the
  recommendation of (c) aggregate-only, with the options and consequences laid out in
  layman's terms including the modeling of non-app-user league-mates. Two consequences
  are recorded here because they will outlive the conversation:
  - **v1 is byte-identical under (a) and (c).** It ships derive-on-read with zero tables
    regardless — that is now an *engineering* choice, no longer a privacy ceiling.
  - **(a) unlocks, later:** a P2 expansion MAY persist per-person tendency profiles
    (including non-app-users) and MAY surface per-person insights. Both were foreclosed
    under (c).
  - **(a) obliges, later:** the moment any per-person profile is **persisted**,
    `delete_user_data` gains a partner-keyed surface it does not have today. That change
    carries its own scope block with the deletion path as a named requirement, and the
    PRD §5.1 "no per-person dossier" user story must be re-scoped **in that PRD**, not
    silently.

## Alternatives considered

- **A fourth hard filter (family-level exclusion).** Rejected — this is the D-067 line
  verbatim, at a scope broader than the one D-067 already rejected.
- **Widening D-067's cooldown from exact-pair to family.** Rejected for the same reason,
  and it would additionally convert a mechanism the operator understands into one with
  very different blast radius under the same knob name.
- **Extending F5 taste to read pass reasons.** Rejected: taste is user-scoped and can
  *boost* up to 1.4×; bolting reason-awareness onto it would entangle a sink-only signal
  with a rise-capable one and make neither auditable. The overlap is acknowledged as
  thin-but-real, and if reason-consumption (R2) were ever stripped from this feature the
  correct action is to cut it to M2-only, not to keep a reason-blind M1.
- **A materialized `negmem_*` table.** Rejected for v1 at current volumes (~845
  outcomes). Admitted only if the job-start read is *measured* too slow — a named gate,
  not an assumption.
- **A per-arm overlay as the M2 kill switch.** Rejected as unsound, and recorded because
  it looks like it works: the feed guard fires on the job-level **global** read taken
  before the bake-off fan-out, so an arm overlay leaves the feed populated. The only
  sanctioned M2 kill is a global `gen2_accept_prior_strength = 0`.

## Consequences

- **The memory is invisible until two switches agree.** `trade.negmem` is only half the
  ON-condition; the league must also appear in `config/negmem_leagues.json` (or
  `FTF_NEGMEM_LEAGUES`), which ships empty. A non-allowlisted league is *deliberately
  indistinguishable* from flag-off — which is what makes per-league rollout possible
  under a global flag system, and what makes "zero rows" in the stamp-rate query mean
  "empty allowlist", never "builds are failing".
- **Neighbouring mechanisms are untouched** (NG9). F3, D-067's cooldown, F5, R4 and
  Thompson keep their exact semantics; negmem composes with them and modifies none. The
  cost of that discipline is that the layers *can* compound, which is why GR4 exists:
  p5 of `negmem_m × final_score/base_score` must stay ≥ 0.15, and the known downward
  pollution (the diversity penalty riding the same ratio) is checked before concluding
  real compounding.
- **Decks thin slightly further** for heavy swipers, on top of D-067's cooldown and G6's
  presentment kills — consistent with the operator principle "accuracy, not volume".
  Unlike those, this one thins by *reordering*, so the deck's membership is unchanged.
- **The bake-off measures it as part of the model.** A generation-time prior is inside
  the model under test; arm A pins `negmem_strength = 0.0` in `MODEL_A_PROFILE` so the
  baseline remains the pre-negmem engine, and `bakeoff_runs.config_json` snapshots every
  knob. Every flag or knob move lands at a **round boundary** ([ADR-014](adr-014-bakeoff-serving-rounds.md)) — mid-round
  censors the window.
- **Graduation is pre-registered, not argued after the fact.** The RFPS rule in
  [PRD](../plans/negative-results-memory/PRD.md) §8.3 is evaluated once at window close
  against a frozen cohort artifact, with an explicit extend-the-window branch so an
  underpowered result cannot be talked into a promotion.
- **Six `negmem_*` knobs** each carry an arm-A disposition sentence (the knob-inventory
  guard fails by name otherwise) and a `_MODEL_CONFIG_DEFAULTS` seed row. The module
  itself holds **no** default literals — a missing seed row raises rather than silently
  pricing the memory differently from the config table.
