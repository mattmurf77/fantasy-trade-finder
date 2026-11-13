"""Max PF moves: which of the viewer's players lower max PF most, and what that does to the pick.

Contract: docs/plans/league-projections/max-pf-trade-away/contract.md. Flag
`league.max_pf_moves` (callers check it; nothing here reads a flag).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# The same file `batch.settings()` reads; not imported from batch so this
# module stays free of database and flag imports (the backtest imports it).
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "league_projections.json"

SETTINGS_KEYS = {
    # key: (type, low, high)
    "simulations_per_candidate": (int, 100, 250000),
    "candidates": (int, 1, 20),
    "min_drop_points": ((int, float), 0, 1000),
    "min_pick_change": ((int, float), 0, 32),
    "min_top3_change": ((int, float), 0, 1),
    "time_budget_seconds": ((int, float), 1, 400),
    # v1.1 (D-261): the "top N together" entries, e.g. [2, 3]. Validated
    # apart below (a list, not a number); part of the settings hash, so a
    # change re-runs saved blocks through `retry_missing_moves`.
    "combined_sizes": (list, None, None),
}
COMBINED_SIZES = (2, 3)


def parse_settings(raw):
    """Validated `max_pf_moves` settings. Raises ValueError on a missing,
    unknown or out-of-range key (booleans are never numbers here)."""
    if not isinstance(raw, dict) or set(raw) != set(SETTINGS_KEYS):
        raise ValueError("invalid_max_pf_moves_configuration")
    out = {}
    for key, (kind, low, high) in SETTINGS_KEYS.items():
        value = raw[key]
        if key == "combined_sizes":
            # Distinct sizes from COMBINED_SIZES, ascending; [] turns the step off.
            if (not isinstance(value, list) or any(type(v) is not int or v not in COMBINED_SIZES for v in value)
                    or value != sorted(set(value))):
                raise ValueError("invalid_max_pf_moves_configuration")
            out[key] = list(value)
            continue
        if isinstance(value, bool) or not isinstance(value, kind) or not low <= value <= high:
            raise ValueError("invalid_max_pf_moves_configuration")
        out[key] = value
    return out


def settings():
    """The `max_pf_moves` object of `config/league_projections.json`. Read only
    while the flag is on; `batch.settings()` never looks at it."""
    return parse_settings(json.loads(CONFIG_PATH.read_text()).get("max_pf_moves"))


def settings_hash(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------------------
# The calculation (contract §13). Pure: no I/O, no flags, no clock.
# ---------------------------------------------------------------------------

from decimal import Decimal, ROUND_HALF_UP  # noqa: E402

from .. import pick_projection, pick_slots  # noqa: E402
from . import season_points, simulation  # noqa: E402
from .core import Unavailable, decimal, free_agent_fill, idp_bye_fill, optimize  # noqa: E402
from .scoring import BEST_AVAILABLE  # noqa: E402

VERSION = 1


def short_name(name):
    """"Rhett Sato" -> "R. Sato"; a one-word name is kept as it is."""
    parts = str(name).split()
    return f"{parts[0][0]}. {' '.join(parts[1:])}" if len(parts) > 1 else str(name)


def _whole(value):
    """Exact Decimal -> int, half away from zero."""
    return int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))


class _Context:
    """Per-snapshot lookups shared by every re-solve."""

    def __init__(self, snapshot, cfg, free_agent_pool, names):
        self.slots = snapshot["slots"]
        self.best = (snapshot.get("coverage") or {}).get("scoring_contract") == BEST_AVAILABLE
        self.empty = cfg["empty_slots"]
        self.include_reserve = cfg["ir_maxpf"] == "include"
        self.points = season_points.player_points(snapshot)
        self.positions = season_points.positions(snapshot)
        self.free_agents = {str(k): v for k, v in (free_agent_pool or {}).items()}
        self.names = dict(names or {})
        self.rosters = {int(t["roster_id"]): t["roster"] for t in snapshot["teams"]}
        self.completed, self.out = {}, set()
        for entry in snapshot["player_week_inputs"]:
            if entry.get("free_agent"):
                continue
            if season_points._completed(entry["input"]):
                self.completed.setdefault(int(entry["week"]), set()).add(str(entry["player_id"]))
            elif entry["input"].get("availability") == 0 and not entry["input"].get("bye"):
                # The provider says he will not play: a known zero, not unknown.
                self.out.add((int(entry["week"]), str(entry["player_id"])))
        for week in snapshot["weeks"]:
            for detail in week["teams"].values():
                for lane in ("actual", "maxpf"):
                    for row in detail[lane]["lineup"]:
                        if row["player"] and row["player"].get("name"):
                            self.names.setdefault(str(row["player"]["player_id"]), row["player"]["name"])
        for pool in self.free_agents.values():
            for p in pool:
                self.names.setdefault(str(p["player_id"]), p.get("name") or str(p["player_id"]))

    def name(self, pid):
        return self.names.get(pid) or pid

    def played(self, roster_id, week, detail):
        """A team-week with any completed player is left out (contract §13.2)."""
        if detail.get("actual_score_observed") or detail.get("maxpf_score_observed"):
            return True
        for lane in ("actual", "maxpf"):
            if any(r["player"] and (r["player"].get("locked_actual") or r["player"].get("completed_game"))
                   for r in detail[lane]["lineup"]):
                return True
        roster = self.rosters[roster_id]
        ids = set(roster.get("players", [])) | set(roster.get("taxi", [])) | set(roster.get("reserve", []))
        return bool(ids & self.completed.get(week, set()))

    def lineups(self, roster_id, week, detail, remove=()):
        """(lineup lane, max PF lane) exactly as `provider.capture` builds them
        (`provider.py` lineup and Max PF blocks), with the ids in `remove` taken off the roster."""
        roster = self.rosters[roster_id]
        reserve, taxi = set(roster.get("reserve", [])), set(roster.get("taxi", []))
        ids = sorted((set(roster.get("players", [])) | taxi | reserve) - set(remove))
        week_points = self.points.get(week, {})
        pool, max_pool, bye = [], [], []
        for pid in ids:
            value = week_points.get(pid)
            if pid in reserve and not self.include_reserve:
                continue
            if value == season_points.BYE:
                if pid not in reserve and pid not in taxi:
                    bye.append({"player_id": pid, "positions": self.positions.get(pid, [])})
                continue
            if not isinstance(value, Decimal):
                continue
            player = {"player_id": pid, "name": self.name(pid), "positions": self.positions[pid], "points": str(value)}
            if pid not in reserve and pid not in taxi:
                pool.append(player)
            max_pool.append(player)
        free_agents = self.free_agents.get(str(week), []) if self.best else []
        real = optimize(self.slots, pool, empty_policy=self.empty)
        with_fa = free_agent_fill(self.slots, real, free_agents, empty_policy=self.empty) if self.best else real
        fa_used = any(r["player"] and r["player"].get("free_agent") for r in with_fa["lineup"])
        try:
            placed = [r["player"] for r in with_fa["lineup"] if r["player"]] if fa_used else pool
            actual = idp_bye_fill(self.slots, placed, bye, detail.get("replacement_means") or {}, empty_policy=self.empty)
        except Unavailable as exc:
            if not self.best or exc.reason != "missing_idp_replacement_mean":
                raise
            actual = with_fa
        maximum = optimize(self.slots, max_pool, empty_policy=self.empty, hindsight=True)
        if self.best:
            maximum = free_agent_fill(self.slots, maximum, free_agents, empty_policy=self.empty)
        return actual, maximum


def parity(snapshot, cfg, free_agent_pool):
    """Re-solve every team-week with nobody removed against the stored projected
    score and projected max PF. Returns {"checked", "skipped", "mismatches"};
    an empty `mismatches` is the proof that the re-solve is the forecast's own
    lineup (played team-weeks are skipped, as `compute` skips them)."""
    ctx = _Context(snapshot, cfg, free_agent_pool, None)
    checked = skipped = 0
    mismatches = []
    for week in snapshot["weeks"]:
        w = int(week["week"])
        for rid, detail in sorted(week["teams"].items()):
            if ctx.played(int(rid), w, detail):
                skipped += 1
                continue
            actual, maximum = ctx.lineups(int(rid), w, detail)
            checked += 1
            for lane, mine, stored in (("actual", actual, detail["modeled_actual_projection"]),
                                       ("maxpf", maximum, detail["modeled_maxpf_projection"])):
                if decimal(mine["points"]) != decimal(stored):
                    mismatches.append({"week": w, "roster_id": rid, "lane": lane, "stored": stored, "derived": mine["points"]})
    return {"checked": checked, "skipped": skipped, "mismatches": mismatches}


def _replacement(ctx, pid, free_agent):
    if pid is None:
        return {"player_id": None, "name": None, "short_name": None, "free_agent": False}
    name = ctx.name(pid)
    return {"player_id": pid, "name": name, "short_name": short_name(name), "free_agent": bool(free_agent)}


def resolve(snapshot, cfg, free_agent_pool, roster_id, *, names=None):
    """The exact weekly re-solve for one team (exploration §7.1, contract §13.2).

    Returns {"weeks": [...], "excluded_played": [...], "candidates": {pid: {...}},
    "unknown": [pids left out because a week has no usable projection]}. Each
    candidate carries its per-week lineup-lane and max PF changes (Decimal, ≤ 0
    in normal cases), status and replacements."""
    ctx = _Context(snapshot, cfg, free_agent_pool, names)
    roster_id = int(roster_id)
    weeks = sorted(snapshot["weeks"], key=lambda w: int(w["week"]))
    base, excluded = {}, []
    for week in weeks:
        w = int(week["week"])
        detail = week["teams"][str(roster_id)]
        if ctx.played(roster_id, w, detail):
            excluded.append(w)
            continue
        base[w] = (detail, *ctx.lineups(roster_id, w, detail))
    roster = ctx.rosters[roster_id]
    reserve = set(roster.get("reserve", []))
    ids = sorted((set(roster.get("players", [])) | set(roster.get("taxi", [])) | reserve)
                 - (set() if ctx.include_reserve else reserve))
    candidates, unknown = {}, []
    for pid in ids:
        if any(not isinstance(ctx.points.get(w, {}).get(pid), Decimal) and ctx.points.get(w, {}).get(pid) != season_points.BYE
               and (w, pid) not in ctx.out for w in base):
            unknown.append(pid)
            continue
        per_week, total_a, total_m = [], Decimal(0), Decimal(0)
        for week in weeks:
            w = int(week["week"])
            if w not in base:
                per_week.append({"week": w, "status": "played", "dA": Decimal(0), "dM": Decimal(0), "replaced_by": []})
                continue
            detail, actual, maximum = base[w]
            actual2, maximum2 = ctx.lineups(roster_id, w, detail, remove={pid})
            d_a = decimal(actual["points"]) - decimal(actual2["points"])
            d_m = decimal(maximum["points"]) - decimal(maximum2["points"])
            before = {str(r["player"]["player_id"]) for r in maximum["lineup"] if r["player"]}
            entered = sorted({(str(r["player"]["player_id"]), bool(r["player"].get("free_agent")))
                              for r in maximum2["lineup"] if r["player"] and str(r["player"]["player_id"]) not in before})
            empties = max(0, len(maximum2["gaps"]) - len(maximum["gaps"]))
            replaced = [_replacement(ctx, p, fa) for p, fa in entered] + [_replacement(ctx, None, False)] * empties
            if ctx.points.get(w, {}).get(pid) == season_points.BYE and not d_m:
                status = "bye"
            else:
                status = "changed" if d_m else "no_change"
            per_week.append({"week": w, "status": status, "dA": d_a, "dM": d_m,
                             "replaced_by": replaced if status == "changed" else []})
            total_a += d_a
            total_m += d_m
        candidates[pid] = {"weeks": per_week, "dA": total_a, "dM": total_m}
    return {"weeks": [int(w["week"]) for w in weeks], "excluded_played": excluded, "candidates": candidates,
            "unknown": unknown, "context": ctx, "base": base}


def resolve_together(solved, roster_id, player_ids):
    """The exact weekly re-solve with every id in `player_ids` removed AT ONCE
    (v1.1 combined entries, D-261). Not the sum of the single drops: the
    replacements interact (two removed running backs can both have needed the
    same bench back). `solved` is `resolve`'s answer for the same team.
    Returns {"changes": {week: (dA, dM)}, "dA", "dM"}; played weeks are 0."""
    ctx, roster_id = solved["context"], int(roster_id)
    changes, total_a, total_m = {}, Decimal(0), Decimal(0)
    for w, (detail, actual, maximum) in solved["base"].items():
        actual2, maximum2 = ctx.lineups(roster_id, w, detail, remove=set(player_ids))
        d_a = decimal(actual["points"]) - decimal(actual2["points"])
        d_m = decimal(maximum["points"]) - decimal(maximum2["points"])
        changes[w] = (d_a, d_m)
        total_a += d_a
        total_m += d_m
    return {"changes": changes, "dA": total_a, "dM": total_m}


def _lowered(snapshot, roster_id, changes):
    """A shallow copy of the snapshot whose team-weeks for `roster_id` have the
    projected score and projected max PF lowered by {week: (dA, dM)}."""
    key = str(roster_id)
    weeks = []
    for week in snapshot["weeks"]:
        d_a, d_m = changes.get(int(week["week"]), (Decimal(0), Decimal(0)))
        if not d_a and not d_m:
            weeks.append(week)
            continue
        detail = dict(week["teams"][key])
        detail["modeled_actual_projection"] = str(decimal(detail["modeled_actual_projection"]) - d_a)
        detail["modeled_maxpf_projection"] = str(decimal(detail["modeled_maxpf_projection"]) - d_m)
        weeks.append({**week, "teams": {**week["teams"], key: detail}})
    return {**snapshot, "weeks": weeks}


_EPSILON = 1e-9  # float noise at a threshold edge never decides a row


def passes_threshold(change, cep_now, cep_after, top3_now, top3_after, options):
    """Contract §3.6: a drop of at least `min_drop_points` AND (pick if you miss
    improves by at least `min_pick_change` OR top-3 chance rises by at least
    `min_top3_change`). `change` is the exact max PF change (≤ 0)."""
    if change > -Decimal(str(options["min_drop_points"])):
        return False
    pick = cep_now is not None and cep_after is not None and cep_now - cep_after >= options["min_pick_change"] - _EPSILON
    return bool(pick or top3_after - top3_now >= options["min_top3_change"] - _EPSILON)


def _clamp(value):
    return min(1.0, max(0.0, value))


def _win_equivalents(team):
    record = team.get("expected_record") or [0, 0, 0]
    return record[0] + .5 * record[2]


def _after_teams(result, before, after):
    """Every team's "after": the saved 250,000 figure plus the paired difference."""
    b = {t["roster_id"]: t for t in before["teams"]}
    a = {t["roster_id"]: t for t in after["teams"]}
    out = {}
    for team in result["teams"]:
        rid = team["roster_id"]
        # saved + (after - before): an unchanged roster gives exactly the saved figure.
        playoff = _clamp(team["playoff_probability"] + (a[rid]["playoff_probability"] - b[rid]["playoff_probability"]))
        picks = [max(0.0, s + (x - y)) for s, x, y in zip(team["pick_probabilities"], a[rid]["pick_probabilities"], b[rid]["pick_probabilities"])]
        total = sum(picks)
        if total > 0 and abs(total - (1 - playoff)) > 1e-12:
            picks = [p * (1 - playoff) / total for p in picks]
        cep = (team["conditional_expected_pick"] + (a[rid]["conditional_expected_pick"] - b[rid]["conditional_expected_pick"])
               if None not in (team["conditional_expected_pick"], a[rid]["conditional_expected_pick"], b[rid]["conditional_expected_pick"])
               else None)
        wins = _win_equivalents(team) + (_win_equivalents(a[rid]) - _win_equivalents(b[rid]))
        out[rid] = {"playoff_probability": playoff, "pick_probabilities": picks, "conditional_expected_pick": cep, "wins": wins}
    return out


def _labels(teams_after, playoff_spots):
    dists = {str(rid): tuple(t["pick_probabilities"] + [t["playoff_probability"] / playoff_spots] * playoff_spots)
             for rid, t in teams_after.items()}
    strength = {str(rid): t["wins"] for rid, t in teams_after.items()}
    return pick_projection.slot_ranks(dists, strength)


def compute(snapshot, result, free_agent_pool, options, *, names=None, trade_deadline=None,
            roster_id=None, cancelled=lambda: False):
    """The saved Max PF moves block for one team (contract §13.1). Pure.

    Inputs:
      snapshot        a forecast capture (`league_projection_runs.snapshot_json`, parsed)
      result          the complete forecast made from it (`result_json`, parsed;
                      the 250,000-run figures every "after" is anchored to)
      free_agent_pool {str(week): [{player_id, name, positions, points}]}, the
                      capture side channel's `free_agents` (or any superset)
      options         validated settings (`parse_settings`)
      names           {player_id: full name} (capture side channel); lineups
                      in the snapshot supply the rest, else the id is shown
      trade_deadline  the league's trade deadline week, or None
      roster_id       the team to evaluate; default the snapshot's viewer
      cancelled       callable polled by every simulation (every 500 runs);
                      when it returns True the simulation raises
                      `core.Unavailable("cancelled")`
    Output: a JSON-ready dict. "computed" is False with "reason":
    "not_eligible" when the team is not in the run. Raises nothing of its own;
    a malformed input raises `core.Unavailable` (callers record it).
    """
    roster_id = int(snapshot.get("viewer_roster_id") if roster_id is None else roster_id)
    cfg = result["config"]
    team = next((t for t in result["teams"] if t["roster_id"] == roster_id), None)
    block = {"version": VERSION, "computed": False, "reason": "not_eligible", "settings": dict(options),
             "settings_hash": settings_hash(options), "viewer_roster_id": roster_id,
             "roster_player_ids": [], "trade_deadline": trade_deadline, "baseline": None,
             "candidates_total": 0, "rows": [], "free_agent_pool": free_agent_pool or {}}
    if team is None or roster_id not in {int(t["roster_id"]) for t in snapshot["teams"]}:
        return block
    roster = next(t["roster"] for t in snapshot["teams"] if int(t["roster_id"]) == roster_id)
    block["roster_player_ids"] = sorted(set(roster.get("players", [])))
    solved = resolve(snapshot, cfg, free_agent_pool, roster_id, names=names)
    ctx = solved["context"]
    weeks = solved["weeks"]
    round_ = cfg.get("draft_round", 1)
    summary = pick_projection.compact(result, run_id="maxpf", created_at="")
    label_slot = summary.slots.get(str(roster_id)) if summary else None
    block["baseline"] = {"weeks_remaining": len(weeks), "first_week": weeks[0] if weeks else None,
                         "last_week": weeks[-1] if weeks else None,
                         "weeks_excluded_played": len(solved["excluded_played"]),
                         "label": pick_slots.slot_suffix(round_, label_slot) if label_slot else None,
                         "label_slot": label_slot, "top3_probability": sum(team["pick_probabilities"][:3])}
    moving = sorted(((pid, c) for pid, c in solved["candidates"].items() if c["dM"] > 0),
                    key=lambda item: (-item[1]["dM"], -item[1]["dA"], item[0]))
    block["candidates_total"] = len(moving)
    chosen = moving[:options["candidates"]]
    rows = []
    if chosen:
        small = {**cfg, "iterations": options["simulations_per_candidate"]}
        before = simulation.simulate(snapshot, small, cancelled=cancelled)
        playoff_spots = int(result["playoff_spots"])
        for rank, (pid, cand) in enumerate(chosen, start=1):
            changes = {wk["week"]: (wk["dA"], wk["dM"]) for wk in cand["weeks"]}
            after = simulation.simulate(_lowered(snapshot, roster_id, changes), small, cancelled=cancelled)
            teams_after = _after_teams(result, before, after)
            mine = teams_after[roster_id]
            slot_after = _labels(teams_after, playoff_spots).get(str(roster_id))
            counts = {}
            for wk in cand["weeks"]:
                for rep in wk["replaced_by"]:
                    key = (rep["player_id"], rep["free_agent"])
                    counts[key] = (counts.get(key, (rep, 0))[0], counts.get(key, (rep, 0))[1] + 1)
            reps = sorted(({**rep, "weeks": n} for rep, n in counts.values()),
                          key=lambda r: (-r["weeks"], r["name"] is None, r["name"] or ""))
            name = ctx.name(pid)
            top3_now, top3_after = sum(team["pick_probabilities"][:3]), sum(mine["pick_probabilities"][:3])
            cep_now, cep_after = team["conditional_expected_pick"], mine["conditional_expected_pick"]
            change = -cand["dM"]
            passes = passes_threshold(change, cep_now, cep_after, top3_now, top3_after, options)
            rows.append({
                "rank": rank, "player_id": pid, "name": name, "short_name": short_name(name),
                "position": (ctx.positions.get(pid) or ["?"])[0],
                "maxpf_change": _whole(change), "maxpf_change_exact": str(change.quantize(Decimal("0.01"))),
                "lineup_change": _whole(-cand["dA"]), "lineup_change_exact": str((-cand["dA"]).quantize(Decimal("0.01"))),
                "weeks_affected": sum(1 for wk in cand["weeks"] if wk["dM"]),
                "replacements": reps[:3], "replacements_more": max(0, len(reps) - 3),
                "weeks": [{"week": wk["week"], "status": wk["status"],
                           "maxpf_change": float((-wk["dM"]).quantize(Decimal("0.1"))) + 0.0,
                           "lineup_change": float((-wk["dA"]).quantize(Decimal("0.1"))) + 0.0,
                           "replaced_by": wk["replaced_by"]} for wk in cand["weeks"]],
                "playoff_probability": {"now": team["playoff_probability"], "after": mine["playoff_probability"]},
                "pick_if_miss": {"now": cep_now, "after": cep_after},
                "top3_probability": {"now": top3_now, "after": top3_after},
                "label": {"now": block["baseline"]["label"],
                          "after": pick_slots.slot_suffix(round_, slot_after) if slot_after else None},
                "label_slot": {"now": label_slot, "after": slot_after},
                "after_pick_probabilities": mine["pick_probabilities"],
                "after_playoff_probability": mine["playoff_probability"],
                "passes_threshold": bool(passes)})
    block.update(computed=True, reason=None, rows=rows)
    # v1.1 combined entries (D-261): rows first, combined second. Sizes come
    # from the listed rows (top N by max PF drop), so every member is a row the
    # app can name; a size larger than the row count is skipped. Any failure
    # here, a cancellation or a hit time budget included, leaves the rows as
    # computed and the block without `combined` (contract §13.5).
    sizes = [n for n in options.get("combined_sizes", ()) if n <= len(rows)]
    if sizes:
        try:
            block["combined"] = [_combined(snapshot, result, solved, team, roster_id, rows[:n], before, small,
                                           options, block["baseline"]["label"], label_slot, round_, cancelled)
                                 for n in sizes]
        except Exception:
            block.pop("combined", None)
    return block


def _combined(snapshot, result, solved, team, roster_id, members, before, small, options, label_now, slot_now,
              round_, cancelled):
    """One saved combined entry: the top `len(members)` rows removed together,
    exact re-solve, then the same paired 5,000-run re-run as a row."""
    together = resolve_together(solved, roster_id, [r["player_id"] for r in members])
    after = simulation.simulate(_lowered(snapshot, roster_id, together["changes"]), small, cancelled=cancelled)
    teams_after = _after_teams(result, before, after)
    mine = teams_after[roster_id]
    slot_after = _labels(teams_after, int(result["playoff_spots"])).get(str(roster_id))
    top3_now, top3_after = sum(team["pick_probabilities"][:3]), sum(mine["pick_probabilities"][:3])
    cep_now, cep_after = team["conditional_expected_pick"], mine["conditional_expected_pick"]
    change = -together["dM"]
    return {
        "size": len(members), "player_ids": [r["player_id"] for r in members],
        "names": [r["name"] for r in members], "short_names": [r["short_name"] for r in members],
        "maxpf_change": _whole(change), "maxpf_change_exact": str(change.quantize(Decimal("0.01"))),
        "lineup_change": _whole(-together["dA"]), "lineup_change_exact": str((-together["dA"]).quantize(Decimal("0.01"))),
        "playoff_probability": {"now": team["playoff_probability"], "after": mine["playoff_probability"]},
        "pick_if_miss": {"now": cep_now, "after": cep_after},
        "top3_probability": {"now": top3_now, "after": top3_after},
        "label": {"now": label_now, "after": pick_slots.slot_suffix(round_, slot_after) if slot_after else None},
        "label_slot": {"now": slot_now, "after": slot_after},
        "after_pick_probabilities": mine["pick_probabilities"],
        "after_playoff_probability": mine["playoff_probability"],
        "passes_threshold": bool(passes_threshold(change, cep_now, cep_after, top3_now, top3_after, options))}


# ---------------------------------------------------------------------------
# The read (contract §3-§4). Pure: every live value is passed in.
# ---------------------------------------------------------------------------

_ROW_KEYS = ("rank", "player_id", "name", "short_name", "position", "maxpf_change", "maxpf_change_exact",
             "lineup_change", "lineup_change_exact", "weeks_affected", "replacements", "replacements_more", "weeks",
             "playoff_probability", "pick_if_miss", "top3_probability", "label", "label_slot", "passes_threshold")
_COMBINED_KEYS = ("size", "player_ids", "names", "short_names", "maxpf_change", "maxpf_change_exact", "lineup_change",
                  "lineup_change_exact", "playoff_probability", "pick_if_miss", "top3_probability", "label", "label_slot",
                  "passes_threshold")
NOT_MAXPF = {"reverse_standings", "lottery_or_other"}


def _dist(picks, playoff, spots):
    return list(picks) + [playoff / spots] * spots


def compose(view_state, saved, *, failure_reason=None, draft_order=None, saved_outlook=None,
            untouchables=(), cuts=None, price=None):
    """The `max_pf_moves` block served on the forecast read (contract §3, §4.1).

    view_state     the read's forecast state (`batch.view` after the model check)
    saved          the saved run's parsed `result_json` with its raw block, or None
    failure_reason the last attempt's reason (as `recommendation.unusable_reason` takes it)
    draft_order    {"rule", "set_at"} from the league row
    saved_outlook  the user's saved outlook id, or None
    untouchables   the user's Keep player ids for this league
    cuts           `recommendation.thresholds(...)` for the playoff band
    price          callable(slot distribution) -> engine value or None (read-time pricing)
    """
    from . import recommendation
    price = price or (lambda dist: None)
    block = {"version": VERSION, "state": "unavailable", "reason": None, "viewer_roster_id": None, "captured_at": None,
             "draft_season": None, "draft_round": None,
             "draft_order": draft_order or {"rule": None, "set_at": None}, "saved_outlook": saved_outlook,
             "pick_owner": None, "baseline": None, "roster_player_ids": [], "candidates_total": 0, "rows": [],
             "combined": []}
    reason = recommendation.unusable_reason(view_state, saved, failure_reason=failure_reason)
    if reason:
        return {**block, "reason": reason}
    viewer = saved.get("viewer_roster_id")
    team = next((t for t in saved.get("teams", []) if t["roster_id"] == viewer), None)
    if team is None:
        return {**block, "reason": "team_not_found"}
    names = {t["roster_id"]: t["name"] for t in saved["teams"]}
    block.update(viewer_roster_id=viewer, captured_at=saved.get("captured_at"),
                 draft_season=saved["config"].get("draft_season"), draft_round=saved["config"].get("draft_round", 1),
                 pick_owner={"owns_own_pick": team["pick_owner_roster_id"] == viewer,
                             "owner_roster_id": team["pick_owner_roster_id"],
                             "owner_name": names.get(team["pick_owner_roster_id"], f"Team {team['pick_owner_roster_id']}")})
    raw = saved.get("max_pf_moves")
    if not isinstance(raw, dict) or not raw.get("computed") or raw.get("version") != VERSION:
        return {**block, "reason": "not_computed"}
    block.update(roster_player_ids=list(raw.get("roster_player_ids") or []), candidates_total=raw.get("candidates_total", 0))
    base = raw["baseline"]
    if not base["weeks_remaining"]:
        return {**block, "state": "season_over"}
    deadline = raw.get("trade_deadline")
    if deadline and saved.get("completed_weeks", 0) >= deadline:
        return {**block, "state": "after_trade_deadline"}
    if block["draft_order"].get("rule") in NOT_MAXPF:
        return {**block, "state": "draft_order_not_maxpf"}
    spots = int(saved["playoff_spots"])
    now_value = price(_dist(team["pick_probabilities"], team["playoff_probability"], spots))
    block["baseline"] = {
        "weeks_remaining": base["weeks_remaining"], "first_week": base["first_week"], "last_week": base["last_week"],
        "weeks_excluded_played": base["weeks_excluded_played"],
        "playoff_probability": team["playoff_probability"],
        "playoff_band": recommendation.classify(team["playoff_probability"], cuts) if cuts else None,
        "pick_if_miss": team["conditional_expected_pick"], "top3_probability": base["top3_probability"],
        "label": base["label"], "label_slot": base["label_slot"],
        "pick_value": now_value, "pick_value_status": "priced" if now_value is not None else "not_priced"}
    if team["conditional_expected_pick"] is None:
        return {**block, "state": "no_miss"}
    keep = set(map(str, untouchables or ()))
    rows = []
    for saved_row in raw.get("rows", []):
        row = {k: saved_row[k] for k in _ROW_KEYS}
        value = None
        if now_value is not None:
            after = price(_dist(saved_row["after_pick_probabilities"], saved_row["after_playoff_probability"], spots))
            if after is not None:
                value = {"now": now_value, "after": after, "change": round(after - now_value, 1)}
        row.update(pick_value=value, keep=row["player_id"] in keep)
        rows.append(row)
    # v1.1 (D-261), additive: the "top N together" entries, priced and Keep-
    # tagged the way rows are. They never decide `state` (v1's rule, which
    # build 191 relies on, is unchanged) and carry no hand-off.
    combined = []
    for saved_entry in raw.get("combined") or []:
        entry = {k: saved_entry[k] for k in _COMBINED_KEYS}
        value = None
        if now_value is not None:
            after = price(_dist(saved_entry["after_pick_probabilities"], saved_entry["after_playoff_probability"], spots))
            if after is not None:
                value = {"now": now_value, "after": after, "change": round(after - now_value, 1)}
        entry.update(pick_value=value, keep=any(pid in keep for pid in entry["player_ids"]))
        combined.append(entry)
    state = "ready" if any(r["passes_threshold"] for r in rows) else "no_moves"
    return {**block, "state": state, "rows": rows, "combined": combined}
