"""The D-055 first-deck insult rule, as a pure function.

Reference (D-055, `living-memory/DECISIONS.md`): the rule statement in
`docs/plans/onboarding-conversion/deck-eval-report-2026-08-15.md`, "How this
run was scored". Values are consensus values (`elo_to_value` of each asset's
seed Elo) and Δ = receive − give from the deck owner's side. A card is an
insult when the owner is net negative by at least MATERIALITY and either:

  I1, lowball: the owner loses at least LOWBALL_HAIRCUT of the package they
      give (|Δ| / give total);
  I2, junk filler: the return holds an asset worth at most JUNK_MAX while the
      give side holds one worth at least STAR_MIN.

Every threshold is inclusive, as the report states them (≥ 500, ≥ 20%, ≤ 350,
≥ 2,500). No backend imports, so the audit sheet (MOD-M1 task 3) can reuse it.
"""

MATERIALITY = 500        # |Δ| floor: below it the card reads as churn, not an insult
LOWBALL_HAIRCUT = 0.20   # I1: share of the give package's value the owner loses
JUNK_MAX = 350           # I2: an asset at or below the waiver floor
STAR_MIN = 2500          # I2: a top asset


def insult_verdict(give_values, receive_values) -> dict:
    """Score one card from its per-asset consensus values (owner's side).

    Returns the side totals, Δ, the haircut (the share of the give total the
    owner loses: 0 when Δ ≥ 0 or nothing is given), and the I1 / I2 / insult
    verdicts.
    """
    give_values, receive_values = list(give_values), list(receive_values)
    give_total, receive_total = sum(give_values), sum(receive_values)
    delta = receive_total - give_total
    haircut = (-delta / give_total) if delta < 0 and give_total > 0 else 0.0
    material_loss = delta < 0 and -delta >= MATERIALITY
    i1 = material_loss and haircut >= LOWBALL_HAIRCUT
    i2 = (material_loss and any(v <= JUNK_MAX for v in receive_values)
          and any(v >= STAR_MIN for v in give_values))
    return {"give_total": give_total, "receive_total": receive_total, "delta": delta,
            "haircut": haircut, "i1": i1, "i2": i2, "insult": i1 or i2}
