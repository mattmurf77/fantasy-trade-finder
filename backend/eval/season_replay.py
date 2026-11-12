"""Offline replay of the win-now season signal: revision 2 against revision 5 (operator tool).

Spec: docs/plans/win-now-season-signal/validation.md §3 (arms, metrics, bars), §6 (guardrails),
§7 (stage 2); lld.md §8. Operator tooling, unflagged, no server wiring, no network.

    python -m backend.eval.season_replay --synthetic [--seeds 0,1]
    PYTHONHASHSEED=0 python -m backend.eval.season_replay --dir data/prod-requests [--limit N] [--no-flip] [--no-stage2]

Arms (validation §3.2), all run in one process on the same request:

- arm1: revision 2, as served today;
- arm2: revision 5, plan fit from the label table, conflict push-down 0.10 (the plan);
- arm3: revision 5, label table, push-down 0 (isolates the push-down);
- arm4: revision 5, plan fit read from the continuous number (a replay-only switch, the
  prototype's "numbers" rule: clip(RATE x season gain / market - .25, -.25, .40));
- no_evidence: revision 5 with no season evidence (guardrail "No forecast");
- stage2: arm2 plus `season_partner_matching` (validation §7).

Amended 2026-11-11 (operator direction): Rebuilding and Tanking viewers are season-scored in
the shed direction (order only), so the report shows their before/after (points a week in
the first 30, share shedding, share adding, deck size, first-30 overlap, set identity) beside
All-in / Contending; and stage 2 is measured by who the partner is (win-now, selling, other;
saved or read from the roster): a win-now viewer buying a starter from a selling team, a
selling viewer sending a win-now piece to a team it would start for.

Season evidence. Forward recorded requests carry it as `owner_request.season_evidence`
(lld §6: the full object beside `input_evidence`). The existing recordings predate it and are
reported as "no evidence": validation §3.1 offers only an optional early look from Sleeper's
public weekly projections, which needs the network, so this tool never fetches or invents
projections. Without usable evidence a request runs arm1 and no_evidence only (every
revision 5 arm collapses to no_evidence). `--synthetic` replays the committed fixture league
(`backend/tests/fixtures/season-signal/league-12.json`) with its real Sleeper-projection
capture, each of the five outlooks as one request per seed.

Every metric is computed on the SERVED deck: the generator's cards, then significance
(production's capture), the bilateral presentment (with the arm's generator version), then
`deck_quality.filter_deck`. Not replayed: database-backed stages (decline windows,
dispositions, likes-you). Output is aggregate-only: counts, medians, shares; no player id,
user id, league id or name. A request is only ever named by its ordinal in this run.

Exit status: 0 when every evaluated bar passes; 1 when one fails or has too little data.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import inspect
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIRST = 30                       # the first 30 served cards (validation §1)
GAIN = 0.5                       # points a week that "adds a starter" / "costs points"
PUSH_DOWN = 0.10
SCORED = ("championship", "contender")
MIRROR = ("rebuilder", "jets")
PARTNERS = ("win_now", "selling", "other")       # a partner's plan, as the engine resolved it
OUTLOOKS = ("championship", "contender", "not_sure", "rebuilder", "jets")
NAMES = {"championship": "All-in", "contender": "Contending", "not_sure": "Not sure",
         "rebuilder": "Rebuilding", "jets": "Tanking", None: "nothing saved"}
DEFAULT_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX"]
ENFORCE = (2, "significance-v1", "second", True)   # production's significance capture
SAMPLE_REQUESTS, SAMPLE_PAIRS = 40, 5
_EPS = 1e-9


def _ident(card):
    return card.target_user_id, tuple(card.give_player_ids), tuple(card.receive_player_ids)


def _terms(card):
    return _ident(card), card.give_value, card.receive_value, card.fairness_score


def _proof(card):
    return card.owner_evaluation.as_dict()


# ── generation ────────────────────────────────────────────────────────────────

def _numbers_search():
    from .. import trade_gen_bilateral as incumbent, trade_gen_bilateral_season as r5

    class NumbersSearch(r5._GenerationSearch):
        """Arm 4: the plan fit of a projected player from the continuous number, not the table."""

        def _season_lean(self, team, pid):
            lean = super()._season_lean(team, pid)
            if lean is None or self._position(pid) == "PICK":
                return lean
            share = r5.RATE * self.season_gain(team, pid) / max(self.market.get(pid, 0.0), 1.0)
            return incumbent._clip(share - .25, -.25, .40)
    return NumbersSearch


def generate(arm, context, evidence):
    """(cards, CPU seconds) of one arm on one generator context."""
    from .. import trade_gen_bilateral as incumbent
    from .. import trade_gen_bilateral_candidate as r2, trade_gen_bilateral_season as r5
    started = time.process_time()
    if arm == "arm1":
        cards, _ = r2.generate_bilateral_trades(**context)
    else:
        config = dict(context.get("config") or {})
        config[r5.DEMOTION_KEY] = 0.0 if arm == "arm3" else PUSH_DOWN
        config[r5.MATCHING_KEY] = 1.0 if arm == "stage2" else 0.0
        kwargs = dict(context, config=config, season_evidence=None if arm == "no_evidence" else evidence)
        if arm == "arm4":
            cards, _ = incumbent._generate_with_search(_numbers_search()(**kwargs), ranker=r5._rank,
                                                       version=r5.VERSION)
        else:
            cards, _ = r5.generate_bilateral_trades(**kwargs)
    return cards, time.process_time() - started


def version_of(arm):
    from .. import trade_gen_bilateral_candidate as r2, trade_gen_bilateral_season as r5
    return r2.VERSION if arm == "arm1" else r5.VERSION


# ── the served deck ───────────────────────────────────────────────────────────

def _parse_owned_pick(pid, league_id):
    """`server._parse_owned_pick_id`, restated so this tool never imports the server."""
    prefix = f"{league_id}_"
    if not isinstance(pid, str) or not pid.startswith(prefix):
        return None
    parts = pid[len(prefix):].split("_")
    try:
        return (int(parts[0]), int(parts[1])) if len(parts) >= 3 else None
    except (TypeError, ValueError):
        return None


class ServedStandIn:
    """STAND-IN for rules-first's `backend/eval/served_deck_replay.py` (not merged on this branch).
    Remove once that tool's `Request.served` takes the generator version (see `served_deck`).

    Production's downstream for an organic owner deck, minus the database-backed stages:
    significance (discovery, enforced), the bilateral presentment, `deck_quality.filter_deck`."""

    def __init__(self, context, slots, significance=ENFORCE):
        from .. import trade_service as ts
        self.context, self.slots, self.capture = context, slots, significance
        self.viewer = str(context["user_id"])
        self.league_id = context["league"].league_id
        self.rosters = {str(m.user_id): list(m.roster or ()) for m in context["league"].members}
        self.rosters[self.viewer] = list(context["user_roster"])
        seed, players = context["seed_elo"], context["players"]
        self.market = lambda pid: ts.elo_to_value(seed[pid]) if pid in seed else None
        self.position = lambda pid: getattr(players.get(pid), "position", None)

    def significant(self, card):
        from .. import trade_service as ts, trade_significance
        return trade_significance.evaluate_significance(
            card, players=self.context["players"], user_elo=self.context["user_elo"],
            seed_elo=self.context["seed_elo"], user_sources=self.context.get("user_sources"),
            scoring_format=self.context.get("scoring_format", "1qb_ppr"), context="discovery",
            player_min_tier=self.capture[2], allow_first_round_pick=self.capture[3],
            owned_pick_parser=_parse_owned_pick, is_pick_asset=ts.is_pick_asset).eligible

    def served(self, cards, *, generator_version):
        from .. import deck_quality, trade_bilateral_presentment as presentment
        kept = [c for c in cards if self.significant(c)] if self.capture and self.capture[0] == 2 else list(cards)
        kept, _ = presentment.present(kept, generator_version=generator_version)
        kept, _ = deck_quality.filter_deck(kept, viewer_id=self.viewer, market=self.market,
                                           position=self.position, rosters=self.rosters, lineup_slots=self.slots)
        return kept


def served_deck(context, slots):
    """Rules-first's served-deck replay when present and version-aware, else the stand-in."""
    try:
        from . import served_deck_replay as sdr
        if "generator_version" in inspect.signature(sdr.Request.served).parameters:
            return sdr.Request(context, slots)
    except ImportError:
        pass
    return ServedStandIn(context, slots)


# ── one request ───────────────────────────────────────────────────────────────

class Request:
    """Generator context, lineup slots, season evidence and the aggregate-only facts of one request."""

    def __init__(self, context, slots, evidence, *, evidence_state, pair, partner_saved=()):
        self.context, self.slots, self.evidence = context, slots, evidence
        self.evidence_state, self.pair = evidence_state, pair
        self.saved = context.get("outlook")
        self.partner_saved = set(partner_saved)
        self.pinned = bool(context.get("pinned_give_players") or context.get("pinned_receive_players")
                           or context.get("opponent_user_id"))
        self.downstream = served_deck(context, slots)


class _Probe:
    """Scores a card for the viewer's season lineup (revision 5's own arithmetic)."""

    def __init__(self, request):
        from .. import trade_gen_bilateral_season as r5
        self.search = r5._Search(**dict(request.context, outlook="championship"),
                                 season_evidence=request.evidence)
        self.viewer = self.search.teams[self.search.user_id]
        self.before = self.search._season_total(self.viewer["roster"], self.viewer)[0]

    def delta(self, card):
        roster = (self.viewer["roster"] - set(card.give_player_ids)) | set(card.receive_player_ids)
        return self.search._season_total(roster, self.viewer)[0] - self.before

    def starts(self, uid, pid):
        return self.search.starts_for(self.search.teams[uid], pid)

    def label(self, pid):
        return self.search._label(pid)


def _partner_plan(probe, uid):
    outlook = probe.search.teams[uid]["outlook"]
    return "win_now" if outlook in SCORED else "selling" if outlook in MIRROR else "other"


def _buys_starter(card, probe):
    """The viewer receives a player who would start for the viewer."""
    uid = probe.search.user_id
    return any(probe.search._position(p) != "PICK" and probe.starts(uid, p) for p in card.receive_player_ids)


def _sells_win_now(card, probe):
    """The viewer sends a win-now piece to a team it would start for."""
    return any(probe.label(p) == "win_now" and probe.starts(card.target_user_id, p) for p in card.give_player_ids)


def deck_metrics(served, probe, *, viewer_saved=None, partner_saved=()):
    """§1 metrics on the first 30 served cards, plus §7's matched share and its split by
    partner (`by_partner[kind][plan|source]`: share of the first 30; kind "cards", "buy"
    (`_buys_starter`) or "sell" (`_sells_win_now`); source "saved" or "inferred")."""
    top = served[:FIRST]
    deltas = [probe.delta(c) for c in top]
    received = [p for c in top for p in c.receive_player_ids if probe.search._position(p) != "PICK"]
    weight = sum(probe.search.market.get(p, 0.0) for p in received)
    uid = probe.search.user_id
    conflicts = 0
    for c in top:
        conflict = _proof(c).get("season_signal", {}).get("conflict")
        conflicts += bool(conflict and conflict["fired"])
    matched = matched_saved = 0
    for c in top:
        if _matched(c, probe, viewer_saved):
            matched += 1
            matched_saved += c.target_user_id in partner_saved
    n = len(top)
    by_partner = {kind: {} for kind in ("cards", "buy", "sell")}
    for c in top:
        plan = _partner_plan(probe, c.target_user_id)
        source = "saved" if c.target_user_id in partner_saved else "inferred"
        for kind, hit in (("cards", True), ("buy", _buys_starter(c, probe)), ("sell", _sells_win_now(c, probe))):
            if hit:
                for key in (plan, f"{plan}|{source}"):
                    by_partner[kind][key] = by_partner[kind].get(key, 0) + 1 / n
    return {"n": n, "served": len(served), "by_partner": by_partner,
            "pts": statistics.mean(deltas) if deltas else 0.0,
            "starter": sum(d >= GAIN - _EPS for d in deltas) / n if n else 0.0,
            "cost": sum(d <= -GAIN + _EPS for d in deltas) / n if n else 0.0,
            "starter_received": (sum(probe.search.market.get(p, 0.0) for p in received if probe.starts(uid, p))
                                 / weight) if weight else None,
            "conflicts_in_view": conflicts / n if n else 0.0,
            "matched": matched / n if n else 0.0, "matched_partner_saved": matched_saved,
            "matched_partner_unsaved": matched - matched_saved,
            "support": statistics.mean(_proof(c)["bilateral"]["weaker_support"] for c in served) if served else 0.0}


def _matched(card, probe, viewer_saved):
    """Validation §7: a win-now piece goes to a team it starts for, rebuild pieces / cornerstones / picks back."""
    future = ("rebuild", "cornerstone")   # picks carry the label "rebuild"
    give, receive = card.give_player_ids, card.receive_player_ids
    if viewer_saved in MIRROR:
        return (any(probe.label(p) == "win_now" and probe.starts(card.target_user_id, p) for p in give)
                and all(probe.label(p) in future for p in receive))
    if viewer_saved in SCORED:
        return (any(probe.label(p) == "win_now" and probe.starts(probe.search.user_id, p) for p in receive)
                and all(probe.label(p) in future for p in give))
    return False


def replay(request, *, flip=True, stage2=True, cache=None, key=None):
    """One request: a dict of aggregates (no ids). `cache` shares decks between requests that
    differ only in the viewer's outlook (the synthetic league's five requests per seed)."""
    from .. import season_value as sv
    cache = {} if cache is None else cache
    key = id(request) if key is None else key

    def run(arm, outlook):
        slot = (key, outlook, arm)
        if slot not in cache:
            cards, cpu = generate(arm, dict(request.context, outlook=outlook), request.evidence)
            cache[slot] = {"cards": cards, "cpu": cpu,
                           "served": request.downstream.served(cards, generator_version=version_of(arm))}
        return cache[slot]

    def same_order(a, b):
        return ([_terms(c) for c in a["cards"]] == [_terms(c) for c in b["cards"]]
                and [_ident(c) for c in a["served"]] == [_ident(c) for c in b["served"]])

    own = request.saved
    row = {"saved": own, "pair": request.pair, "evidence": request.evidence_state,
           "usable": sv.usable(request.evidence), "pinned": request.pinned}
    a1, ne = run("arm1", own), run("no_evidence", own)
    row.update(served_arm1=len(a1["served"]), cpu_arm1=a1["cpu"])
    # Guardrail "No forecast": revision 5 without evidence is arm 1, cards and order.
    row["no_forecast_identical"] = same_order(a1, ne)
    if not row["usable"]:
        row.update(served_arm2=len(ne["served"]), cpu_arm2=ne["cpu"])
        return row
    probe = _Probe(request)
    a2, a3, a4 = run("arm2", own), run("arm3", own), run("arm4", own)
    arms = {"arm1": a1, "arm2": a2, "arm3": a3, "arm4": a4}
    if stage2:
        arms["stage2"] = run("stage2", own)
    row["metrics"] = {arm: deck_metrics(deck["served"], probe, viewer_saved=own,
                                        partner_saved=request.partner_saved) for arm, deck in arms.items()}
    row.update(served_arm2=len(a2["served"]), cpu_arm2=a2["cpu"])
    if own == "not_sure":
        row["not_sure_identical"] = same_order(a1, a2)
    # First-30 overlap of the served decks, rev 2 against rev 5 (identities), every outlook.
    row["first30_overlap"] = (len({_ident(c) for c in a1["served"][:FIRST]} & {_ident(c) for c in a2["served"][:FIRST]})
                              / FIRST)
    if own in MIRROR:
        # Amended 2026-11-11: same cards and terms as rev 2; the shed term reorders them.
        row["mirror_same_terms"] = sorted(map(_terms, a2["cards"])) == sorted(map(_terms, a1["cards"]))
    row["push_down_removes_nothing"] = {_ident(c) for c in a2["cards"]} == {_ident(c) for c in a3["cards"]}
    old = {_ident(c): c for c in a1["cards"]}
    shared = [c for c in a2["cards"] if _ident(c) in old]
    row["floor_unchanged"] = all(_terms(c) == _terms(old[_ident(c)])
                                 and _proof(c)["market"] == _proof(old[_ident(c)])["market"] for c in shared)
    row["below_floor"] = sum(c.fairness_score < request.context.get("fairness_threshold", 0) - _EPS
                             for c in a2["cards"])
    kinds, triggers, fired = {}, {}, 0
    for c in a2["cards"]:
        conflict = _proof(c)["season_signal"].get("conflict") or {}
        if conflict.get("fired"):
            fired += 1
            kinds[conflict["kind"]] = kinds.get(conflict["kind"], 0) + 1
            key = f"{NAMES[conflict['plan']]}:{conflict['trigger']}"
            triggers[key] = triggers.get(key, 0) + 1
    row.update(conflicts=fired, conflict_kinds=kinds, conflict_triggers=triggers)
    signals = [_proof(c)["season_signal"] for c in a2["served"]]
    scored = [s for s in signals if s.get("viewer", {}).get("scored")]
    row["clip"] = (sum(abs(s["components"]["lineup_gain"]) >= 1 - _EPS for s in scored), len(scored))
    if flip:
        row["flip"] = {"r2": {}, "r5": {}}
        for outlook in OUTLOOKS:
            f1, f2 = run("arm1", outlook), run("arm2", outlook)
            row["flip"]["r2"][outlook] = deck_metrics(f1["served"], probe)["pts"]
            row["flip"]["r5"][outlook] = deck_metrics(f2["served"], probe)["pts"]
            if outlook == "not_sure":
                row["flip_not_sure_identical"] = same_order(f1, f2)
    return row


# ── loading ───────────────────────────────────────────────────────────────────

def _pair(user_id, league_id):
    return hashlib.sha256(f"{user_id}|{league_id}".encode()).hexdigest()[:12]   # grouping only, never printed


def request_from_record(record, slots_by_league):
    """A recorded owner request (`data/prod-requests/<file>.json`) as a `Request`."""
    from .. import season_value as sv, trade_service as ts
    from ..ranking_service import Player
    from .scorecard_replay import PERSONAL_SOURCES
    raw = record["owner_request"]
    k = copy.deepcopy(raw["input"])
    players = {pid: Player(id=pid, name=pid, **attrs) for pid, attrs in k.pop("players").items()}
    members = []
    for m in k.pop("members"):
        src = (k.get("opponent_sources") or {}).get(m["id"], {})
        members.append(ts.LeagueMember(m["id"], m["id"], m["roster"], m["elo"],
                                       bool(m["elo"]) and any(s in PERSONAL_SOURCES for s in src.values()),
                                       confidence_sources=src))
    league_id = record.get("league_id") or "x"
    k.update(players=players, league=ts.League(league_id, "offline", "sleeper", members), config=dict(ts._cfg))
    for name in ("past_decision_keys", "exclusion_keys"):
        k[name] = {(frozenset(a), frozenset(b)) for a, b in k.get(name, [])}
    k.pop("roster_owner_map", None)
    pref = (raw["input"].get("manager_preferences") or {}).get(raw["input"]["user_id"]) or {}
    slots = pref.get("starter_slots") or slots_by_league.get(league_id)
    if not slots:
        slots = DEFAULT_SLOTS + (["SUPER_FLEX"] if raw["input"]["scoring_format"] == "sf_tep" else [])
    if "season_evidence" not in raw:
        evidence, state = None, "not recorded"
    else:
        evidence = raw["season_evidence"]
        state = "usable" if sv.usable(evidence) else f"unavailable: {(evidence or {}).get('reason')}"
    partners = {uid for uid, outlook in (raw["input"].get("opponent_outlooks") or {}).items() if outlook}
    return Request(k, slots, evidence, evidence_state=state,
                   pair=_pair(record.get("user_id"), league_id), partner_saved=partners)


def load_dir(directory, limit=None):
    """(requests, failed count) from a recorded-request directory; installs its model_config capture."""
    from .. import trade_service as ts
    index = json.load(open(os.path.join(directory, "index.json")))
    ts._cfg.clear()
    ts._cfg.update(ts._DEFAULT_CFG)
    ts._cfg.update(json.load(open(os.path.join(directory, "model_config.json"))))
    records = [json.load(open(os.path.join(directory, r["file"]))) for r in index[:limit]]
    slots_by_league = {}
    for rec in records:
        inp = rec["owner_request"]["input"]
        pref = (inp.get("manager_preferences") or {}).get(inp["user_id"]) or {}
        if pref.get("starter_slots"):
            slots_by_league.setdefault(rec.get("league_id"), pref["starter_slots"])
    requests, failed = [], 0
    for rec in records:
        try:
            requests.append(request_from_record(rec, slots_by_league))
        except Exception as error:  # noqa: BLE001 - counted, never printed with data
            failed += 1
            print(f"request unreadable: {type(error).__name__}", file=sys.stderr)
    return requests, failed


def fixture_world(outlook, seed=0):
    """Generator kwargs for the committed fixture league; the viewer ("me") is its first team.
    Public NFL players with DynastyProcess 1QB values; synthetic owners, picks and boards."""
    import random
    from .. import trade_service as ts
    from ..ranking_service import Player
    from ..tests.test_season_points import load_league, load_pool
    league, pool = load_league(), load_pool()
    rng = random.Random(seed)
    players, values = {}, {}
    for team in league["teams"]:
        for pid in team["players"]:
            row = pool[pid]
            age = row["age"] or (22 if (row.get("years_exp") or 0) == 0 else None)
            players[pid] = Player(pid, row["full_name"], row["position"], row.get("team") or "FA", age,
                                  depth_chart_order=row.get("depth_chart_order"))
            values[pid] = float(row["dp_value_1qb"])
        for pid, value in team["picks"].items():
            players[pid] = Player(pid, pid, "PICK", "PICK", None)
            values[pid] = float(value)
    ids = sorted(values)

    def board(noise):
        return {p: ts.value_to_elo(max(30., values[p] * rng.lognormvariate(0, noise))) for p in ids}

    user_elo = board(.3)
    members, outlooks = [], {}
    for index, team in enumerate(league["teams"][1:]):
        ranked = index < 4
        members.append(ts.LeagueMember(team["owner_id"], team["owner_id"], team["players"] + list(team["picks"]),
                                       board(.25) if ranked else {}, ranked))
        outlooks[team["owner_id"]] = ("contender", "rebuilder", "not_sure", "championship", "jets")[index % 5]
    prefs = {uid: {"starter_slots": list(league["slots"]), "lineup_source": "observed"}
             for uid in ["me", *(m.user_id for m in members)]}
    viewer = league["teams"][0]
    return dict(players=players, league=ts.League("900001", "Fixture", "sleeper", members), user_id="me",
                user_roster=viewer["players"] + list(viewer["picks"]),
                seed_elo={p: ts.value_to_elo(v) for p, v in values.items()}, user_elo=user_elo, outlook=outlook,
                manager_preferences=prefs, opponent_outlooks=outlooks, fairness_threshold=.75)


def fixture_evidence():
    """Season evidence from the real capture over the fixture world (committed projections)."""
    from .. import season_value as sv
    from ..league_projections.core import VERSION
    from ..tests.test_season_points import CAPTURED_AT, LEAGUE_ID, captured_snapshot, load_league
    return sv.build_evidence(captured_snapshot(), as_of=CAPTURED_AT, league_id=LEAGUE_ID,
                             slots=load_league()["slots"], platform="sleeper", run_id="fixture",
                             model_version=VERSION, current=True)


def synthetic_requests(seed, evidence):
    """The five outlooks on one fixture world: five requests that share a deck cache."""
    out = []
    for outlook in OUTLOOKS:
        context = fixture_world(outlook, seed)
        out.append(Request(context, list(context["manager_preferences"]["me"]["starter_slots"]), evidence,
                           evidence_state="usable (fixture)", pair=f"fixture-{seed}",
                           partner_saved=context["opponent_outlooks"]))
    return out


# ── the report and the bars ───────────────────────────────────────────────────

def _median(xs):
    return statistics.median(xs) if xs else None


def _share(flags):
    flags = list(flags)
    return sum(flags) / len(flags) if flags else None


def _f(x, digits=2):
    return "n/a" if x is None else f"{x:.{digits}f}"


def evaluate_bars(rows, *, synthetic=False):
    """[(section, check, status, detail)]; status PASS, FAIL, INSUFFICIENT or n/a."""
    bars = []

    def bar(section, check, ok, detail, enough=True):
        bars.append((section, check, "INSUFFICIENT" if not enough else "PASS" if ok else "FAIL", detail))

    gate = [r for r in rows if r["usable"]]
    scored = [r for r in gate if r["saved"] in SCORED]
    if synthetic:
        bars.append(("§3.4", "sample: >=40 requests, >=5 pairs, exact season maps", "n/a",
                     "synthetic fixture: directional only, not the gate set"))
    else:
        pairs = len({r["pair"] for r in scored})
        bar("§3.4", "sample: >=40 requests, >=5 pairs, exact season maps",
            len(scored) >= SAMPLE_REQUESTS and pairs >= SAMPLE_PAIRS,
            f"{len(scored)} All-in/Contending requests with usable evidence, {pairs} pairs",
            enough=len(scored) >= SAMPLE_REQUESTS and pairs >= SAMPLE_PAIRS)

    def diffs(group, metric, a="arm2", b="arm1"):
        return [r["metrics"][a][metric] - r["metrics"][b][metric] for r in gate if r["saved"] == group]

    allin_pts, allin_start = diffs("championship", "pts"), diffs("championship", "starter")
    allin_cost = diffs("championship", "cost")
    bar("§3.4", "All-in lineup points: median +1.0/week over rev 2, higher on >=80%",
        bool(allin_pts) and _median(allin_pts) >= 1.0 - _EPS and _share(d > 0 for d in allin_pts) >= .8,
        f"median {_f(_median(allin_pts))}, higher on {_f(_share(d > 0 for d in allin_pts))} (n={len(allin_pts)})",
        enough=bool(allin_pts))
    bar("§3.4", "All-in adds a starter: up >=15 points",
        bool(allin_start) and statistics.mean(allin_start) >= .15 - _EPS,
        f"mean change {_f(statistics.mean(allin_start) if allin_start else None)}", enough=bool(allin_start))
    bar("§3.4", "All-in costs points: no higher than rev 2 on >=90%",
        bool(allin_cost) and _share(d <= _EPS for d in allin_cost) >= .9,
        f"no higher on {_f(_share(d <= _EPS for d in allin_cost))}", enough=bool(allin_cost))
    cont_pts, cont_start = diffs("contender", "pts"), diffs("contender", "starter")
    cont_cost = diffs("contender", "cost")
    enough = bool(cont_pts) and bool(allin_pts)
    ok = enough and (_median(cont_pts) > 0 and _median(cont_pts) >= .5 * _median(allin_pts) - _EPS
                     and statistics.mean(cont_start) > 0
                     and statistics.mean(cont_start) >= .5 * statistics.mean(allin_start) - _EPS
                     and _share(d <= _EPS for d in cont_cost) >= .9)
    bar("§3.4", "Contending: same direction, at least half the All-in size", ok,
        f"median points {_f(_median(cont_pts))}, mean starter change "
        f"{_f(statistics.mean(cont_start) if cont_start else None)}, costs no higher on "
        f"{_f(_share(d <= _EPS for d in cont_cost))} (n={len(cont_pts)})", enough=enough)
    flips = [r["flip"] for r in gate if "flip" in r]

    def ordered(f):
        return f["championship"] >= f["contender"] - _EPS and f["contender"] > f["not_sure"] + _EPS
    r5_rate, r2_rate = _share(ordered(f["r5"]) for f in flips), _share(ordered(f["r2"]) for f in flips)
    bar("§3.4", "Outlook flip under rev 5: All-in >= Contending > Not sure on >=80%",
        bool(flips) and r5_rate >= .8, f"rev 5 {_f(r5_rate)}; rev 2 {_f(r2_rate)} (reported) (n={len(flips)})",
        enough=bool(flips))
    table = [r["metrics"]["arm2"]["pts"] - r["metrics"]["arm4"]["pts"] for r in scored]
    bar("§3.4", "Label table within 0.3/week of the numbers, or ahead (arm 2 vs 4)",
        bool(table) and _median(table) >= -.3 - _EPS,
        f"median arm2 - arm4 {_f(_median(table))}" + ("" if not table or _median(table) >= -.3 - _EPS else
                                                       "; on a miss the plan fit reads the number"),
        enough=bool(table))
    # Rebuilding / Tanking, amended 2026-11-11: the first 30 shed lineup points, Tanking more.
    tank_pts, rebuild_pts = diffs("jets", "pts"), diffs("rebuilder", "pts")
    mirror_pts = tank_pts + rebuild_pts
    bar("§3.4", "Rebuilding/Tanking lineup points, first 30: lower than rev 2 (mean)",
        bool(mirror_pts) and statistics.mean(mirror_pts) < -_EPS,
        f"Tanking mean {_f(statistics.mean(tank_pts) if tank_pts else None)} (n={len(tank_pts)}), "
        f"Rebuilding mean {_f(statistics.mean(rebuild_pts) if rebuild_pts else None)} (n={len(rebuild_pts)})",
        enough=bool(mirror_pts))
    bar("§3.4", "Tanking falls more than Rebuilding (mean change)",
        bool(tank_pts) and bool(rebuild_pts) and statistics.mean(tank_pts) <= statistics.mean(rebuild_pts) + _EPS,
        f"Tanking {_f(statistics.mean(tank_pts) if tank_pts else None)}, "
        f"Rebuilding {_f(statistics.mean(rebuild_pts) if rebuild_pts else None)}",
        enough=bool(tank_pts) and bool(rebuild_pts))
    clipped, total = sum(r["clip"][0] for r in gate), sum(r["clip"][1] for r in gate)
    bar("§3.4", "Need term clipping: share of scored cards at +-1 not above half",
        total and clipped / total <= .5, f"{clipped} of {total} served scored cards", enough=bool(total))
    # §6 guardrails
    ratios = [r["served_arm2"] / r["served_arm1"] for r in rows if r["served_arm1"]]
    broken = [i for i, r in enumerate(rows, 1) if r["served_arm1"] >= FIRST and r["served_arm2"] < FIRST]
    bar("§6", "Deck size: rev 5 >= 95% of rev 2 at the median; never under 30 where rev 2 >= 30",
        bool(ratios) and _median(ratios) >= .95 - _EPS and not broken,
        f"median ratio {_f(_median(ratios), 3)}" + (f"; under 30: requests {broken}" if broken else ""),
        enough=bool(ratios))
    bar("§6", "Fairness floor unchanged on shared cards; none below the floor",
        all(r["floor_unchanged"] and not r["below_floor"] for r in gate),
        f"{sum(not r['floor_unchanged'] for r in gate)} requests differ, "
        f"{sum(r['below_floor'] for r in gate)} cards below", enough=bool(gate))
    not_sure = [r["not_sure_identical"] for r in gate if "not_sure_identical" in r] \
        + [r["flip_not_sure_identical"] for r in gate if "flip_not_sure_identical" in r]
    bar("§6", "Not sure: identical cards and order", all(not_sure),
        f"{sum(not_sure)} of {len(not_sure)} decks identical", enough=bool(not_sure))
    mirror = [r for r in gate if "mirror_same_terms" in r]
    bar("§6", "Rebuilding/Tanking: same cards and terms as rev 2 (the order differs by design)",
        all(r["mirror_same_terms"] for r in mirror),
        f"{sum(r['mirror_same_terms'] for r in mirror)} of {len(mirror)}", enough=bool(mirror))
    bar("§6", "No forecast: rev 5 without evidence identical to rev 2",
        all(r["no_forecast_identical"] for r in rows),
        f"{sum(r['no_forecast_identical'] for r in rows)} of {len(rows)} requests", enough=bool(rows))
    cpu = [r["cpu_arm2"] / r["cpu_arm1"] for r in gate if r["cpu_arm1"] > 0]
    bar("§6", "Speed: rev 5 full-solve CPU within 10% of rev 2 (median)",
        bool(cpu) and _median(cpu) <= 1.10 + _EPS, f"median ratio {_f(_median(cpu), 3)}", enough=bool(cpu))
    bar("§6", "Push-down removes nothing (inventory at 0.10 == at 0)",
        all(r["push_down_removes_nothing"] for r in gate),
        f"{sum(r['push_down_removes_nothing'] for r in gate)} of {len(gate)}", enough=bool(gate))
    pinned = [r for r in gate if r["pinned"]]
    if pinned:
        bar("§6", "Pinned and partner-scoped searches: no conflict", all(not r["conflicts"] for r in pinned),
            f"{sum(r['conflicts'] for r in pinned)} conflicts on {len(pinned)} requests")
    else:
        bars.append(("§6", "Pinned and partner-scoped searches: no conflict", "n/a", "no pinned request"))
    # §7 stage 2
    # §7 as corrected 2026-11-11: measured by who the partner is. Two win-now teams share a
    # priority, so their share MAY fall (reported, no bar).
    staged = [r for r in gate if "stage2" in r.get("metrics", {})]

    def moved(rs, kind, key):
        return [r["metrics"]["stage2"]["by_partner"][kind].get(key, 0.0)
                - r["metrics"]["arm2"]["by_partner"][kind].get(key, 0.0) for r in rs]

    def split(rs, kind, plans):
        return ", ".join(f"{plan}|{source} {_f(statistics.mean(moved(rs, kind, f'{plan}|{source}')), 3)}"
                         for plan in plans for source in ("saved", "inferred")) if rs else "n/a"

    win_now = [r for r in staged if r["saved"] in SCORED]
    up = moved(win_now, "buy", "selling")
    bar("§7", "Stage 2, win-now viewers: share buying a starter from a Rebuilding/Tanking partner up",
        bool(up) and statistics.mean(up) > 0,
        f"mean change {_f(statistics.mean(up) if up else None, 3)} (n={len(up)}); {split(win_now, 'buy', ('selling',))}",
        enough=bool(up))
    same = moved(win_now, "cards", "win_now")
    bars.append(("§7", "Stage 2, win-now viewers: share of cards with win-now partners (reported, no bar)", "n/a",
                 f"mean change {_f(statistics.mean(same) if same else None, 3)} (n={len(same)}); "
                 f"{split(win_now, 'cards', ('win_now',))}"))
    selling = [r for r in staged if r["saved"] in MIRROR]
    total = [a + b + c for a, b, c in zip(moved(selling, "sell", "win_now"), moved(selling, "sell", "selling"),
                                          moved(selling, "sell", "other"))]
    bar("§7", "Stage 2, Rebuilding/Tanking viewers: share selling a win-now piece to a team it starts for up",
        bool(total) and statistics.mean(total) > 0,
        f"mean change {_f(statistics.mean(total) if total else None, 3)} (n={len(total)}); by partner: "
        f"{split(selling, 'sell', PARTNERS)}", enough=bool(total))
    ns = [r for r in staged if r["saved"] == "not_sure"]
    within = [abs(r["metrics"]["stage2"][m] - r["metrics"]["arm2"][m]) <= .02 * abs(r["metrics"]["arm2"][m]) + _EPS
              for r in ns for m in ("support", "served")]
    bar("§7", "Stage 2: Not sure mean support and deck size within 2% of stage 1", bool(within) and all(within),
        f"{sum(within)} of {len(within)} within", enough=bool(within))
    return bars


def summarize(rows, *, failed=0, synthetic=False):
    """(report text, bars). Aggregates only."""
    lines = [f"requests replayed: {len(rows)}" + (f"; unreadable or failed: {failed}" if failed else "")]
    states = {}
    for r in rows:
        states[r["evidence"]] = states.get(r["evidence"], 0) + 1
    lines.append("season evidence: " + ", ".join(f"{k} {v}" for k, v in sorted(states.items())))
    saved = {}
    for r in rows:
        saved[NAMES.get(r["saved"], str(r["saved"]))] = saved.get(NAMES.get(r["saved"], str(r["saved"])), 0) + 1
    lines.append("saved outlook: " + ", ".join(f"{k} {v}" for k, v in sorted(saved.items())))
    lines.append(f"manager-league pairs: {len({r['pair'] for r in rows})}")
    gate = [r for r in rows if r["usable"]]
    if gate:
        lines.append("")
        lines.append("served deck, first 30 (median over requests): pts/week | adds starter | costs | "
                     "starter share received | conflicts in view | served size")
        for group in OUTLOOKS:
            rs = [r for r in gate if r["saved"] == group]
            if not rs:
                continue
            for arm in ("arm1", "arm2", "arm3", "arm4", "stage2"):
                ms = [r["metrics"][arm] for r in rs if arm in r["metrics"]]
                if not ms:
                    continue
                received = [m["starter_received"] for m in ms if m["starter_received"] is not None]
                lines.append(f"  {NAMES[group]:<11} {arm:<7} {_f(_median([m['pts'] for m in ms])):>6} | "
                             f"{_f(_median([m['starter'] for m in ms])):>5} | {_f(_median([m['cost'] for m in ms])):>5} | "
                             f"{_f(_median(received)):>5} | {_f(_median([m['conflicts_in_view'] for m in ms])):>5} | "
                             f"{_median([m['served'] for m in ms])} (n={len(ms)})")
        lines.append("")
        lines.append("rev 2 -> rev 5 (arm 2), first 30 served (mean over requests): pts/week | shedding (<= -0.5) | "
                     "adding (>= +0.5) | served size | first-30 overlap | same set as rev 2")
        for group in OUTLOOKS:
            rs = [r for r in gate if r["saved"] == group]
            if not rs:
                continue
            def mean(arm, metric):
                return statistics.mean(r["metrics"][arm][metric] for r in rs)
            same = (f"{sum(r['mirror_same_terms'] for r in rs)} of {len(rs)}" if group in MIRROR else "n/a")
            lines.append(f"  {NAMES[group]:<11} {_f(mean('arm1', 'pts')):>6} -> {_f(mean('arm2', 'pts')):>6} | "
                         f"{_f(mean('arm1', 'cost'))} -> {_f(mean('arm2', 'cost'))} | "
                         f"{_f(mean('arm1', 'starter'))} -> {_f(mean('arm2', 'starter'))} | "
                         f"{_f(mean('arm1', 'served'), 0)} -> {_f(mean('arm2', 'served'), 0)} | "
                         f"{_f(statistics.mean(r['first30_overlap'] for r in rs))} | {same} (n={len(rs)})")
        kinds, triggers = {}, {}
        for r in gate:
            for kind, n in r["conflict_kinds"].items():
                kinds[kind] = kinds.get(kind, 0) + n
            for key, n in r.get("conflict_triggers", {}).items():
                triggers[key] = triggers.get(key, 0) + n
        lines.append("conflicts (arm 2 inventory) by kind: " + (", ".join(f"{k} {v}" for k, v in sorted(kinds.items()))
                                                             or "none"))
        lines.append("conflicts (arm 2 inventory) by plan and trigger: "
                     + (", ".join(f"{k} {v}" for k, v in sorted(triggers.items())) or "none"))
        staged = [r["metrics"]["stage2"] for r in gate if "stage2" in r["metrics"]]
        if staged:
            lines.append(f"stage 2 matched cards in the first 30: partner outlook saved "
                         f"{sum(m['matched_partner_saved'] for m in staged)}, not saved "
                         f"{sum(m['matched_partner_unsaved'] for m in staged)}")
    cpu1 = [r["cpu_arm1"] for r in rows]
    cpu2 = [r["cpu_arm2"] for r in rows]
    lines.append(f"search CPU s: rev 2 median {_f(_median(cpu1))}, rev 5 median {_f(_median(cpu2))}; "
                 "page path vs gated full solve: n/a until the join (WI-8)")
    bars = evaluate_bars(rows, synthetic=synthetic)
    lines.append("")
    lines.append("bars:")
    for section, check, status, detail in bars:
        lines.append(f"  [{status}] {section} {check} - {detail}")
    return "\n".join(lines), bars


def passed(bars):
    return all(status in ("PASS", "n/a") for _, _, status, _ in bars)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _offline():
    os.environ.setdefault("DATABASE_URL", "sqlite://")   # never the app database
    import socket

    def _no_network(*_args, **_kwargs):
        raise RuntimeError("season_replay is offline")
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = _no_network


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dir", help="recorded requests (index.json, model_config.json)")
    source.add_argument("--synthetic", action="store_true", help="the committed fixture league, five outlooks")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seeds", default="0", help="synthetic board seeds, comma-separated")
    parser.add_argument("--no-flip", action="store_true", help="skip the five-outlook flip")
    parser.add_argument("--no-stage2", action="store_true", help="skip the partner-matching arm")
    args = parser.parse_args(argv)
    _offline()
    from .. import database, feature_flags, trade_service as ts
    database.metadata.create_all(database.engine)
    rows, failed = [], 0
    if args.synthetic:
        feature_flags._flags_cache = dict(feature_flags.DEFAULT_FLAGS)
        ts._cfg.clear()
        ts._cfg.update(ts._DEFAULT_CFG)
        evidence = fixture_evidence()
        for seed in (int(s) for s in args.seeds.split(",") if s.strip()):
            cache = {}
            for index, request in enumerate(synthetic_requests(seed, evidence)[:args.limit]):
                # The five requests of a seed share one world: its flip is run once, not five times.
                rows.append(replay(request, flip=not args.no_flip and index == 0, stage2=not args.no_stage2,
                                   cache=cache, key=seed))
    else:
        feature_flags._flags_cache = feature_flags._load_from_json(REPO / "config" / "features.json")
        requests, failed = load_dir(args.dir, args.limit)
        for request in requests:
            try:
                rows.append(replay(request, flip=not args.no_flip, stage2=not args.no_stage2))
            except Exception as error:  # noqa: BLE001 - counted, never printed with data
                failed += 1
                print(f"request failed: {type(error).__name__}", file=sys.stderr)
    text, bars = summarize(rows, failed=failed, synthetic=args.synthetic)
    print(text)
    return 0 if rows and passed(bars) and not failed else 1


if __name__ == "__main__":
    sys.exit(main())
