#!/usr/bin/env python3
"""negmem_rfps.py — the RFPS metric and the R-X frozen-cohort artifact.

Spec: docs/plans/negative-results-memory/LLD.md §7.4 (computation + artifact
shape), PRD §4.2 (the pre-registered numerator rule), PRD §8.3 (the graduation
ladder this feeds).

RFPS = repeat-family pass share: of the rejections in the window, the fraction
that landed on a partner the map ALREADY held enough evidence against at serve
time. The four computation steps, verbatim from §7.4:

  1. Cohort: every VIEWED pass/not_interested outcome in the window for
     allowlisted leagues (viewed gate, ghost exclusion, clean epoch — the same
     closed-list clauses, through `negmem._admit_events`). RFPS additionally
     needs reason-LESS rejections per the pre-registered numerator rule, so the
     reason requirement is relaxed FOR COHORT MEMBERSHIP ONLY
     (`require_reason=False`); the admission implementation is still the one
     shared code path.
  2. For each outcome, rebuild the map **as-of `served_at`** — the builder is a
     pure function of (user, league, as_of) (C5), which is what guarantees the
     metric and the map agree.
  3. Numerator: a reason-carrying rejection whose own `(partner, family)` cell
     held `n_decayed >= negmem_min_evidence` at `served_at`; a reason-LESS
     rejection iff ANY admitted `(partner, ✱)` cell held ≥ threshold.
  4. Per-arm read via `deck_impressions.model_arm` (`NULL` ⇒ organic).

The artifact is committed at pre-registration as
`docs/plans/negative-results-memory/rfps-baseline-<YYYYMMDD>.json`. Window-close
evaluation then runs over the FROZEN `impression_id` cohort with cell
assignments frozen at close, so H-2's mutable-reason drift is contained to a
reported number (`family_switch_rate`) and can never become a silent baseline
shift. Switch-rate > 5% ⇒ the window extends (PRD §8.3 ladder).

Cost note, stated: step 2 rebuilds the map once per cohort row. That is
deliberately O(n) builds — offline, correctness over speed, and the only way
metric and map provably share one definition.

Usage (from the repo root):
    python3 -m backend.scripts.negmem_rfps --start 2026-08-20 --end 2026-09-17
    python3 -m backend.scripts.negmem_rfps --start … --end … --league 9876
    python3 -m backend.scripts.negmem_rfps --start … --end … --out \
        docs/plans/negative-results-memory/rfps-baseline-20260917.json
    python3 -m backend.scripts.negmem_rfps --start … --end … --prod

`--prod` uses the read-only Postgres connection described in
`backend/scripts/negmem_readout.py`; credentials come from `secrets.local.env`
and are never printed.

Exit codes: 0 ok · 1 failed · 2 missing prod credentials · 3 missing
model_config seed rows · 4 the allowlist is "*" and no --league was given.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from sqlalchemy import text                 # noqa: E402

from backend import database as db          # noqa: E402
from backend import negmem                  # noqa: E402
from backend.scripts.negmem_readout import (  # noqa: E402
    _load_prod_url, _readonly_engine,
)

# The knobs frozen into the artifact (§7.4). `negmem_strength`/`negmem_floor`
# shape the SEAM, not the map, so they do not enter the metric definition.
_FROZEN_KNOB_KEYS = ("negmem_min_evidence", "negmem_halflife_days",
                     "negmem_sat_k", "negmem_like_net")

_ID_MAPPING_NOTE = (
    "NONE on the evidence path (DE-5, v1): features_json.partner_user_id IS "
    "card.target_user_id IS LeagueMember.user_id — already the canonical league "
    "identity, used verbatim as the cell key. The only id-space handling in v1 "
    "is on the M2 side, where trade_matches response keys not present in "
    "league_members are DROPPED and counted (dropped_unmapped_partner_ids)."
)
_ALIAS_SOURCE_NOTE = (
    "identity (v1 ships no producer; the kwarg is reserved for a future "
    "client-supplied or persisted source, which requires its own scope block "
    "per ADR-012)"
)

# Day-prefix bounds only — the DE-4 dialect rule (no date functions, no JSON
# operators) applies to this script exactly as it does to the module.
_PAIRS_SQL = """
SELECT DISTINCT user_id, league_id
FROM deck_impressions
WHERE league_id = :lid
  AND substr(served_at, 1, 10) >= :start_day
  AND substr(served_at, 1, 10) <= :end_day
"""

_ARM_SQL = """
SELECT impression_id, model_arm
FROM deck_impressions
WHERE user_id = :uid AND league_id = :lid
  AND substr(served_at, 1, 10) >= :start_day
  AND substr(served_at, 1, 10) <= :end_day
"""

_SWITCH_SQL = """
SELECT impression_id, reason, switched_from
FROM trade_pass_reasons
WHERE user_id = :uid AND league_id = :lid
"""


def _rows(sql: str, params: dict) -> list[dict]:
    with db.engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def _knobs() -> dict:
    cfg = db.get_config()
    out = {}
    for key in _FROZEN_KNOB_KEYS + ("gen2_accept_prior_strength",):
        if key not in cfg:
            print("negmem seed rows missing — run init_db", file=sys.stderr)
            raise SystemExit(3)
        out[key] = float(cfg[key])
    return out


def _leagues(explicit: list[str]) -> list[str]:
    if explicit:
        return explicit
    allow = negmem.load_negmem_league_allowlist()
    if "*" in allow:
        print('the allowlist is "*" — pass --league explicitly so the cohort is '
              "reproducible", file=sys.stderr)
        raise SystemExit(4)
    return sorted(allow)


def _cohort_for_pair(user_id: str, league_id: str, knobs: dict,
                     start_day: str, end_day: str) -> list[dict]:
    """Steps 1-3 for one (user, league). Returns cohort rows (§7.4 shape)."""
    halflife = knobs["negmem_halflife_days"]
    min_evidence = knobs["negmem_min_evidence"]

    arms = {r["impression_id"]: r["model_arm"]
            for r in _rows(_ARM_SQL, {"uid": user_id, "lid": league_id,
                                      "start_day": start_day,
                                      "end_day": end_day})}
    switched = {r["impression_id"]: (r["reason"], r["switched_from"])
                for r in _rows(_SWITCH_SQL, {"uid": user_id, "lid": league_id})}

    # Step 1 — the cohort, through the ONE admission implementation with the
    # reason clause relaxed for MEMBERSHIP only.
    end_dt = datetime.fromisoformat(end_day + "T23:59:59.999999+00:00")
    horizon_day = negmem._horizon_floor_day(end_dt, halflife)
    spine = negmem._fetch_spine(user_id, league_id, horizon_day)
    retracted = negmem._retracted_keys(
        negmem._fetch_retracted(user_id, league_id, horizon_day))
    cohort_events, _netting, _errs = negmem._admit_events(
        spine, as_of_dt=end_dt, retracted_keys=retracted, require_reason=False)

    out: list[dict] = []
    for event in cohort_events:
        served_at = event.get("served_at")
        if not served_at or not (start_day <= str(served_at)[:10] <= end_day):
            continue

        # Step 2 — rebuild the map as-of served_at. Allowlist BYPASSED for the
        # same reason the readout bypasses it: the metric describes the data,
        # not the rollout.
        nm_map, _extras = negmem._build(
            user_id, league_id,
            halflife_days=halflife, min_evidence=min_evidence,
            sat_k=knobs["negmem_sat_k"], like_net=knobs["negmem_like_net"],
            floor_b=1.0,                      # curve floor is irrelevant to the
                                              # threshold question; kept inert
            accept_prior_strength=0.0,        # M2 not part of RFPS — guard shut
            as_of=str(served_at), owner_alias=negmem._EMPTY_ALIAS)

        partner = event["partner"]
        cells_at_serve = {
            family: nm_map.cells[(partner, family)].n_decayed
            if (partner, family) in nm_map.cells else 0.0
            for family in negmem.NEGMEM_ADMITTED_FAMILIES
        }

        # Step 3 — the pre-registered numerator rule.
        if event.get("reason_carrying"):
            numerator = cells_at_serve.get(event["family"], 0.0) >= min_evidence
        else:
            numerator = any(v >= min_evidence for v in cells_at_serve.values())

        reason_now, switched_from = switched.get(event["impression_id"],
                                                 (None, None))
        out.append({
            "impression_id": event["impression_id"],
            "served_at": served_at,
            "outcome_id": event["row_id"],
            "user_id": user_id,
            "league_id": league_id,
            "model_arm": arms.get(event["impression_id"]),
            "partner_league_id": partner,
            "reason_family": event.get("family"),
            "reason_carrying": bool(event.get("reason_carrying")),
            "switched_from": switched_from,
            "reason_at_freeze": reason_now,
            "cells_at_serve": {k: round(v, 4) for k, v in cells_at_serve.items()},
            "numerator": bool(numerator),
        })
    return out


def _family_switch_rate(cohort: list[dict]) -> float:
    """Share of reason rows whose `switched_from` hop CHANGED their layer-1
    family. At freeze this is informational; at window close it is the H-2
    drift number, and > 5% extends the window (PRD §8.3)."""
    reasoned = [c for c in cohort if c["reason_carrying"]]
    if not reasoned:
        return 0.0
    switched = sum(1 for c in reasoned
                   if c["switched_from"] and c["switched_from"] != c["reason_family"])
    return round(switched / len(reasoned), 4)


def build_artifact(leagues, start_day: str, end_day: str) -> dict:
    knobs = _knobs()
    cohort: list[dict] = []
    for league_id in leagues:
        pairs = _rows(_PAIRS_SQL, {"lid": league_id, "start_day": start_day,
                                   "end_day": end_day})
        for pair in pairs:
            cohort.extend(_cohort_for_pair(
                pair["user_id"], league_id, knobs, start_day, end_day))

    cohort.sort(key=lambda c: (str(c["served_at"]), c["outcome_id"]))
    n = len(cohort)
    numerator = sum(1 for c in cohort if c["numerator"])

    per_arm: dict[str, dict] = {}
    for row in cohort:
        arm = row["model_arm"] or "organic"
        bucket = per_arm.setdefault(arm, {"n": 0, "numerator": 0})
        bucket["n"] += 1
        bucket["numerator"] += 1 if row["numerator"] else 0
    for bucket in per_arm.values():
        bucket["rfps"] = (round(bucket["numerator"] / bucket["n"], 4)
                          if bucket["n"] else None)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pre_registered": True,
        "window": {"start": start_day, "end": end_day},
        "leagues": list(leagues),
        "knobs_frozen": {k: knobs[k] for k in _FROZEN_KNOB_KEYS},
        "id_mapping": _ID_MAPPING_NOTE,
        "owner_alias": {},
        "owner_alias_source": _ALIAS_SOURCE_NOTE,
        "dropped_unmapped_partner_ids": 0,   # M2 is not part of RFPS; its guard
                                             # is shut for every rebuild above,
                                             # so no count is taken (§5.4)
        "admission_ver": negmem.NEGMEM_VER,
        "cohort": cohort,
        "baseline_rfps": round(numerator / n, 4) if n else None,
        "n": n,
        "per_arm": per_arm,
        "family_switch_rate": _family_switch_rate(cohort),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", required=True, help="window start day, YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="window end day, YYYY-MM-DD")
    ap.add_argument("--league", action="append", default=[],
                    help="league id (repeatable; default: the negmem allowlist)")
    ap.add_argument("--out", default=None,
                    help="write the artifact here instead of stdout")
    ap.add_argument("--prod", action="store_true",
                    help="run against production Postgres, read-only")
    args = ap.parse_args(argv)

    if args.prod:
        db.engine = _readonly_engine(_load_prod_url())

    try:
        artifact = build_artifact(_leagues(args.league), args.start, args.end)
    except SystemExit:
        raise
    except Exception as err:
        print(f"negmem rfps failed: {err}", file=sys.stderr)
        return 1

    payload = json.dumps(artifact, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(payload + "\n")
        print(f"wrote {args.out}: n={artifact['n']} "
              f"baseline_rfps={artifact['baseline_rfps']} "
              f"family_switch_rate={artifact['family_switch_rate']}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
