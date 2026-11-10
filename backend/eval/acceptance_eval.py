"""Offline acceptance evaluation of the bilateral support score (R5 pre-work).

Does the hand-weighted owner-v2-bilateral support score (0.45 preference
fulfilment + 0.35 market acceptability + 0.20 team plan per side, ordered by
the weaker side; backend/trade_gen_bilateral.py) predict what managers did
with the cards they were served, and would a fitted logistic head over the
same frozen per-side components do better on held-out users? Operator tooling
in the style of its eval/ neighbours: unflagged, no server wiring, read-only.

    python -m backend.eval.acceptance_eval --production [--secrets PATH]
        [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--arm ARM ...]
        [--keep-allowlist] [--out report.json] [--markdown report.md]
        [--extract /outside/the/repo/rows.jsonl]
    python -m backend.eval.acceptance_eval --db path/to.sqlite ...

Extraction is label-first: the impression ids that carry any response
(deck_outcomes, trade_decisions.impression_id) are read from the small label
tables, and only those impressions are read from deck_impressions, by primary
key, in pages, with the proof fields pulled server-side by JSON path
(Postgres `#>>`, SQLite `json_extract`): never a wide JSON column across the
table. A labelled id with no row is looked up in deck_evidence_packs
(ADR-025; "<run_id>:<card_index>", evidence_pack.unpack_run): a packed card
carries only the compact block, so it counts toward volume but has no support
proof. Served-but-unlabelled volume comes from short COUNT windows.

Labels (per served card, viewer = the manager it was served to):
  viewer_like     like (deck_outcomes or trade_decisions) = 1, pass or
                  not_interested = 0; undone or like+pass conflicts dropped.
  viewer_strong   among responded cards: propose, send, calculator opened,
                  a confirmed proposal, a match or an exact executed trade = 1.
  counterparty    the partner liked the mirror (their own labelled impression
                  of the same trade_concept_id, or a trade_decisions row on it),
                  accepted the match, or the trade executed exactly = 1; the
                  partner passed the mirror or declined the match = 0;
                  otherwise no label.

Exclusions: the demo league, qa_/demo_/test_ stage users, the tester
allowlist (experiments.load_tester_allowlist; --keep-allowlist keeps it),
Calibration refresh decks (deck_source grading_refresh), partner-redacted
cards (the deletion scrub; never reconstructed), partial-run rows and ghosts.

The report is aggregate only: no user, league, impression or player ids, no
board values, no individual trades; any cell under MIN_CELL observations is
suppressed. Group keys used for cross-validation are salted hashes and appear
only in the optional --extract file, which must be outside the repository.

Pure stdlib + SQLAlchemy. The logistic fitter is a small IRLS (Newton) with
L2 on standardised features; no numpy/scipy/sklearn.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import bindparam, create_engine, event, inspect, text

from backend.analytics_stats import norm_ppf, power_n_per_arm
from backend.eval import evidence_pack
from backend.eval.calibration import ece, reliability_table
from backend.eval.contract import REDACTED_PARTNER_PREFIX
from backend.eval.data import CALIBRATION_REFRESH_SOURCE, PARTIAL_RUN_TIER

TOOL_VERSION = "acceptance-eval-1"
REPO = Path(__file__).resolve().parents[2]
BILATERAL_ARM = "owner_v2_bilateral"
DEMO_LEAGUE = "league_demo"
STAGE_PREFIXES = ("qa_", "demo_", "test_")
MIN_CELL = 5            # any reported cell below this is suppressed
MIN_GROUPS = 5          # fewer users than this: grouped CV cannot generalise
EPV = 10                # events per variable for an estimable head
PAGE = 200              # ids per spine query
PAUSE_S = 0.2           # between production queries
COUNT_WINDOW_DAYS = 3   # served-volume COUNT window (index range on served_at)
BOOTSTRAP = 500
SEED = 20261110
L2 = 1.0                # on standardised features, summed log-loss scale
_SALT = "acceptance-eval-v1|"

# valuation_json paths of the bilateral proof (trade_gen_bilateral._owner and
# _decision). Per side: viewer and counterparty.
TOP_PATHS = {
    "weaker_support": ("bilateral", "weaker_support"),
    "total_support": ("bilateral", "total_support"),
    "gen_version": ("generator_version",),
    "shape": ("construction", "shape"),
}
SIDE_PATHS = {
    "support": ("support", "score"),
    "pref_c": ("support", "components", "preference_fulfillment"),
    "market_c": ("support", "components", "market_acceptability"),
    "plan_c": ("support", "components", "team_plan"),
    "net_pref": ("intent", "net_preference"),
    "market_gain": ("market_gain_fraction",),
    "plan_gain": ("team_plan_gain",),
    "need": ("need_utility",),
    "personal_gain": ("personal_gain_fraction",),
    "state": ("preference_evidence", "state"),
    "outlook": ("outlook",),
}
FEATURE_PATHS = {"partner": ("partner_user_id",)}
_SIDES = (("v", "viewer"), ("c", "counterparty"))
PROOF_FIELDS = (list(TOP_PATHS) + [f"{s}_{k}" for s, _ in _SIDES for k in SIDE_PATHS]
                + list(FEATURE_PATHS))

# The fitted heads' inputs (all frozen in the proof, plus served position).
VIEWER_FEATURES = ("v_net_pref", "v_market_gain", "v_plan_gain", "v_need",
                   "v_state_known", "v_state_partial", "c_state_unknown",
                   "multi_asset", "v_rebuilding", "c_rebuilding", "log_position")
COUNTERPARTY_FEATURES = ("c_net_pref", "c_market_gain", "c_plan_gain", "c_need",
                         "c_state_known", "c_state_partial", "multi_asset", "c_rebuilding")
# Scores compared as orderings (Q1, Q4). Higher = predicted more acceptable.
BASELINE_SCORES = ("weaker_support", "product_support", "total_support",
                   "viewer_support", "counterparty_support",
                   "v_pref_c", "v_market_c", "v_plan_c", "c_pref_c", "c_market_c", "c_plan_c",
                   "market_balance", "viewer_market_gain", "counterparty_market_gain")


# ---------------------------------------------------------------------------
# Small numerics (pure stdlib)
# ---------------------------------------------------------------------------

def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (small dense systems)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        if abs(m[col][col]) < 1e-300:
            raise ValueError("singular system")
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            if f:
                for c in range(col, n + 1):
                    m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))) / m[r][r]
    return x


def fit_logistic(x: list[list[float]], y: list[float], *, l2: float = L2,
                 max_iter: int = 100, tol: float = 1e-10) -> list[float]:
    """L2-penalised logistic regression by IRLS (Newton). Minimises
    Σ logloss + (l2/2)·||w||² (intercept unpenalised). Returns
    [intercept, w1..wp]. Callers standardise x first."""
    p = len(x[0]) if x else 0
    w = [0.0] * (p + 1)
    for _ in range(max_iter):
        g = [0.0] * (p + 1)
        h = [[0.0] * (p + 1) for _ in range(p + 1)]
        for xi, yi in zip(x, y):
            row = [1.0] + list(xi)
            mu = _sigmoid(sum(a * b for a, b in zip(w, row)))
            r, s = mu - yi, max(mu * (1.0 - mu), 1e-12)
            for a in range(p + 1):
                g[a] += r * row[a]
                ha = h[a]
                for b in range(a, p + 1):
                    ha[b] += s * row[a] * row[b]
        for a in range(p + 1):
            for b in range(a):
                h[a][b] = h[b][a]
        for a in range(1, p + 1):
            g[a] += l2 * w[a]
            h[a][a] += l2
        step = _solve(h, g)
        w = [wi - si for wi, si in zip(w, step)]
        if max(abs(s) for s in step) < tol:
            break
    return w


def _standardise(x: list[list[float]]) -> tuple[list[float], list[float]]:
    p = len(x[0])
    mean = [sum(r[j] for r in x) / len(x) for j in range(p)]
    sd = []
    for j in range(p):
        v = sum((r[j] - mean[j]) ** 2 for r in x) / len(x)
        sd.append(math.sqrt(v) if v > 1e-18 else 1.0)
    return mean, sd


def _apply(x, mean, sd):
    return [[(v - m) / s for v, m, s in zip(r, mean, sd)] for r in x]


def predict(w: list[float], x: list[list[float]]) -> list[float]:
    return [_sigmoid(w[0] + sum(a * b for a, b in zip(w[1:], r))) for r in x]


def auc(scores: list[float], ys: list[float]) -> float | None:
    """Mann-Whitney AUC by mid-ranks (ties count half)."""
    n = len(scores)
    pos = sum(1 for y in ys if y)
    neg = n - pos
    if not pos or not neg:
        return None
    order = sorted(range(n), key=lambda i: scores[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    rpos = sum(r for r, y in zip(ranks, ys) if y)
    return (rpos - pos * (pos + 1) / 2) / (pos * neg)


def log_loss(ps: list[float], ys: list[float]) -> float | None:
    if not ps:
        return None
    eps = 1e-12
    return -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps))
                for p, y in zip(ps, ys)) / len(ps)


def hanley_mcneil_se(a: float, n_pos: int, n_neg: int) -> float:
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    return math.sqrt((a * (1 - a) + (n_pos - 1) * (q1 - a * a)
                      + (n_neg - 1) * (q2 - a * a)) / (n_pos * n_neg))


def n_for_auc(a0: float, a1: float, pos_share: float, *, alpha=.05, power=.8) -> int | None:
    """Smallest total labelled n at which AUC a1 is distinguishable from a0
    (two independent Hanley-McNeil SEs; conservative for a paired design)."""
    if not 0 < pos_share < 1:
        return None
    z = norm_ppf(1 - alpha / 2) + norm_ppf(power)
    for n in range(20, 2_000_001, 10):
        npos, nneg = max(int(n * pos_share), 2), max(int(n * (1 - pos_share)), 2)
        se = math.sqrt(hanley_mcneil_se(a0, npos, nneg) ** 2 + hanley_mcneil_se(a1, npos, nneg) ** 2)
        if abs(a1 - a0) >= z * se:
            return n
    return None


# ---------------------------------------------------------------------------
# Grouped cross-validation
# ---------------------------------------------------------------------------

def group_key(raw: str) -> str:
    """Opaque, salted group key (never reversible to the id in the report)."""
    return hashlib.sha256((_SALT + str(raw)).encode()).hexdigest()[:16]


def grouped_folds(groups: list[str], k: int = 5) -> list[tuple[list[int], list[int]]]:
    """Folds whose test sets partition the rows and never share a group with
    their train set. Leave-one-group-out when there are at most k groups."""
    uniq = sorted(set(groups), key=lambda g: hashlib.sha256(g.encode()).hexdigest())
    fold_of = {g: (i if len(uniq) <= k else i % k) for i, g in enumerate(uniq)}
    n_folds = min(len(uniq), k)
    folds = []
    for f in range(n_folds):
        test = [i for i, g in enumerate(groups) if fold_of[g] == f]
        train = [i for i, g in enumerate(groups) if fold_of[g] != f]
        if test and train:
            folds.append((train, test))
    return folds


def _cluster_bootstrap(rows_by_group: dict, stat, *, b: int = BOOTSTRAP, seed: int = SEED):
    """Percentile 95% interval of stat(rows) over group-resampled datasets."""
    keys = sorted(rows_by_group)
    if len(keys) < 2:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(b):
        sample = [r for _k in range(len(keys)) for r in rows_by_group[keys[rng.randrange(len(keys))]]]
        v = stat(sample)
        if v is not None:
            vals.append(v)
    if len(vals) < b // 2:
        return None
    vals.sort()
    return [round(vals[int(.025 * len(vals))], 4), round(vals[int(.975 * len(vals)) - 1], 4)]


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------

def cell(n: int, **values) -> dict:
    """One reported cell: values are dropped and n shown as '<MIN_CELL' when
    fewer than MIN_CELL observations back it."""
    if n < MIN_CELL:
        return {"n": f"<{MIN_CELL}", **{k: None for k in values}}
    return {"n": n, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in values.items()}}


def small(n: int):
    """A bare count, suppressed below MIN_CELL. Distinct user/league counts
    are the exception: they are reported exactly, because every verdict
    rests on them and a count of people identifies none of them."""
    return f"<{MIN_CELL}" if n < MIN_CELL else n


def _rate_cell(ys: list[float]) -> dict:
    return cell(len(ys), rate=(sum(ys) / len(ys)) if ys else None)


def _reliability(pairs) -> dict:
    rows = reliability_table(pairs)
    e = ece(rows)
    return {"ece": None if e is None else round(e, 4),
            "bins": [{"range": [r.lo, r.hi], **cell(r.n, mean_predicted=r.mean_predicted,
                                                     observed=r.observed_rate)}
                     for r in rows if r.n]}


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _jexpr(dialect: str, src: str, path: tuple) -> str:
    if dialect == "postgresql":
        return "(%s #>> '{%s}')" % (src, ",".join(path))
    return "json_extract(%s, '$.%s')" % (src, ".".join(path))


def _spine_sql(dialect: str) -> str:
    if dialect == "postgresql":
        v, f = "j.v", "j.f"
        lateral = ("CROSS JOIN LATERAL (SELECT CASE WHEN i.model_arm = :proof_arm "
                   "THEN i.valuation_json::jsonb END AS v, CASE WHEN i.model_arm = :proof_arm "
                   "THEN i.features_json::jsonb END AS f) j ")
        guard = lambda e: e                                      # noqa: E731
    else:
        v, f, lateral = "i.valuation_json", "i.features_json", ""
        guard = lambda e: f"CASE WHEN i.model_arm = :proof_arm THEN {e} END"   # noqa: E731
    cols = [f"{guard(_jexpr(dialect, v, p))} AS {k}" for k, p in TOP_PATHS.items()]
    cols += [f"{guard(_jexpr(dialect, v, (side,) + p))} AS {s}_{k}"
             for s, side in _SIDES for k, p in SIDE_PATHS.items()]
    cols += [f"{guard(_jexpr(dialect, f, p))} AS {k}" for k, p in FEATURE_PATHS.items()]
    return ("SELECT i.impression_id, i.user_id, i.league_id, i.deck_job_id, i.card_index, "
            "i.served_at, i.is_ghost, i.model_arm, i.policy_version, i.evidence_tier, "
            "i.trade_concept_id, i.propensity, "
            "CASE WHEN i.features_json LIKE :refresh THEN 1 ELSE 0 END AS refresh_hint, "
            "CASE WHEN i.features_json LIKE :redacted THEN 1 ELSE 0 END AS redacted_hint, "
            + ", ".join(cols) + " FROM deck_impressions i " + lateral
            + "WHERE i.impression_id IN :ids")


def _num(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    if v in ("true", "false"):
        return 1.0 if v == "true" else 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


class _Reader:
    """Sequential, paced reads on one connection."""

    def __init__(self, conn, pace: float):
        self.conn, self.pace, self.queries, self.rows = conn, pace, 0, 0
        self.dialect = conn.dialect.name
        self._tables = set(inspect(conn).get_table_names())

    def has(self, table: str) -> bool:
        return table in self._tables

    def q(self, sql: str, params: dict | None = None, expanding=()):
        stmt = text(sql)
        if expanding:
            stmt = stmt.bindparams(*(bindparam(k, expanding=True) for k in expanding))
        out = self.conn.execute(stmt, params or {}).mappings().fetchall()
        self.queries += 1
        self.rows += len(out)
        if self.pace:
            time.sleep(self.pace)
        return out


def _excluded_user(uid: str | None, allowlist: set) -> str | None:
    if uid is None:
        return None
    if str(uid).startswith(STAGE_PREFIXES):
        return "stage_user"
    if uid in allowlist:
        return "tester_allowlist"
    return None


def extract(conn, *, since: str | None, until: str | None, allowlist: set,
            pace: float = 0.0) -> dict:
    """Read the labelled spine, labels and served volume. Returns
    {"rows": [...], "volume": {...}, "exclusions": Counter, "ids": set,
     "queries": n, "rows_read": n}. Row-level; never reported as is."""
    rd = _Reader(conn, pace)
    seen_ids: set[str] = set()
    until_clause = " AND acted_at < :until" if until else ""
    outcomes = defaultdict(list)
    for r in rd.q("SELECT impression_id, action, calc_opened, detail_expanded FROM deck_outcomes"
                  " WHERE 1=1" + until_clause, {"until": until}):
        outcomes[r["impression_id"]].append(r)
    decisions = defaultdict(list)
    concept_decisions = defaultdict(list)
    if rd.has("trade_decisions"):
        for r in rd.q("SELECT impression_id, user_id, league_id, trade_concept_id, decision "
                      "FROM trade_decisions WHERE (impression_id IS NOT NULL OR trade_concept_id "
                      "IS NOT NULL)" + (" AND created_at < :until" if until else ""),
                      {"until": until}):
            if r["impression_id"]:
                decisions[r["impression_id"]].append(r["decision"])
            if r["trade_concept_id"]:
                concept_decisions[(r["user_id"], r["league_id"], r["trade_concept_id"])].append(
                    r["decision"])
    proposals = set()
    if rd.has("trade_proposals"):
        proposals = {r["impression_id"] for r in rd.q(
            "SELECT impression_id FROM trade_proposals WHERE impression_id IS NOT NULL")}
    matches = defaultdict(list)     # impression -> [(own decision, other decision, status)]
    if rd.has("trade_matches"):
        for r in rd.q("SELECT user_a_impression_id, user_b_impression_id, status, user_a_decision,"
                      " user_b_decision FROM trade_matches WHERE user_a_impression_id IS NOT NULL"
                      " OR user_b_impression_id IS NOT NULL"):
            if r["user_a_impression_id"]:
                matches[r["user_a_impression_id"]].append((r["user_b_decision"], r["status"]))
            if r["user_b_impression_id"]:
                matches[r["user_b_impression_id"]].append((r["user_a_decision"], r["status"]))
    links = {}
    if rd.has("suggestion_trade_links"):
        for r in rd.q("SELECT matched_impression_id, match_type FROM suggestion_trade_links "
                      "WHERE matched_impression_id IS NOT NULL"):
            links[r["matched_impression_id"]] = r["match_type"]
    reasons = {}
    if rd.has("trade_pass_reasons"):
        for r in rd.q("SELECT impression_id, reason, detail FROM trade_pass_reasons "
                      "WHERE key_source = 'impression'"):
            reasons[r["impression_id"]] = (r["reason"], r["detail"])

    labelled = sorted(set(outcomes) | set(decisions))
    dialect = rd.dialect
    sql = _spine_sql(dialect)
    spine = {}
    for i in range(0, len(labelled), PAGE):
        for r in rd.q(sql, {"ids": labelled[i:i + PAGE], "proof_arm": BILATERAL_ARM,
                            "refresh": f"%{CALIBRATION_REFRESH_SOURCE}%",
                            "redacted": f"%{REDACTED_PARTNER_PREFIX}%"}, expanding=("ids",)):
            spine[r["impression_id"]] = dict(r)
    # Labelled ids with no row: packed cards ("<run_id>:<card_index>").
    missing = [i for i in labelled if i not in spine]
    packed_runs = sorted({i.rsplit(":", 1)[0] for i in missing if ":" in i})
    pack_integrity = 0
    if packed_runs and rd.has("deck_evidence_packs"):
        for i in range(0, len(packed_runs), PAGE):
            for p in rd.q("SELECT run_id, user_id, league_id, served_at, pack_version, header_json,"
                          " cards_blob, checksum, card_count FROM deck_evidence_packs"
                          " WHERE run_id IN :runs", {"runs": packed_runs[i:i + PAGE]},
                          expanding=("runs",)):
                try:
                    _run, cards = evidence_pack.unpack_run(evidence_pack.PackedRun(
                        pack_version=p["pack_version"], header_json=p["header_json"],
                        cards_blob=bytes(p["cards_blob"]), checksum=p["checksum"],
                        card_count=p["card_count"]))
                except evidence_pack.PackIntegrityError:
                    pack_integrity += 1
                    continue
                for u in cards:
                    iid = f"{p['run_id']}:{u['card_index']}"
                    if iid in outcomes or iid in decisions:
                        partner = u.get("partner_user_id")
                        spine[iid] = {
                            "impression_id": iid, "user_id": u.get("user_id", p["user_id"]),
                            "league_id": u.get("league_id", p["league_id"]),
                            "deck_job_id": p["run_id"], "card_index": u["card_index"],
                            "served_at": u.get("served_at", p["served_at"]), "is_ghost": 0,
                            "model_arm": u.get("model_arm"), "policy_version": u.get("policy_version"),
                            "evidence_tier": None, "trade_concept_id": None,
                            "propensity": u.get("propensity"), "refresh_hint": 0,
                            "redacted_hint": int(isinstance(partner, str)
                                                 and partner.startswith(REDACTED_PARTNER_PREFIX)),
                            "partner": partner, "packed": True}

    excl = Counter()
    if pack_integrity:
        excl["pack_integrity"] += pack_integrity
    excl["label_without_impression"] = sum(1 for i in labelled if i not in spine)
    rows = []
    for iid in labelled:
        s = spine.get(iid)
        if s is None:
            continue
        seen_ids.update(x for x in (iid, s["user_id"], s["league_id"], s["deck_job_id"],
                                    s.get("partner"), s.get("trade_concept_id")) if x)
        if since and s["served_at"] < since or until and s["served_at"] >= until:
            excl["outside_window"] += 1
            continue
        why = ("demo_league" if s["league_id"] == DEMO_LEAGUE else
               _excluded_user(s["user_id"], allowlist) or
               ("ghost" if s["is_ghost"] == 1 else None) or
               ("partial_run" if s["evidence_tier"] == PARTIAL_RUN_TIER else None) or
               ("calibration_refresh" if s["refresh_hint"] else None) or
               ("partner_redacted" if s["redacted_hint"] or str(s.get("partner") or "").startswith(
                   REDACTED_PARTNER_PREFIX) else None))
        if why:
            excl[why] += 1
            continue
        rows.append(_label_row(s, outcomes.get(iid, ()), decisions.get(iid, ()),
                               iid in proposals, matches.get(iid, ()), links.get(iid),
                               reasons.get(iid)))
    _counterparty_labels(rows, spine, outcomes, decisions, concept_decisions)
    volume = _served_volume(rd, since=since, until=until, allowlist=allowlist,
                            first=min((r["served_at"] for r in rows), default=None))
    return {"rows": rows, "volume": volume, "exclusions": excl, "ids": seen_ids,
            "queries": rd.queries, "rows_read": rd.rows}


def _label_row(s, outs, decs, proposed, match_list, link, reason) -> dict:
    acts = Counter(o["action"] for o in outs)
    liked = acts["like"] > 0 or "like" in decs
    passed = acts["pass"] > 0 or acts["not_interested"] > 0 or "pass" in decs
    undone = acts["undo"] > 0
    strong = (acts["propose"] > 0 or "send" in decs or proposed or bool(match_list)
              or link in ("exact", "retro_exact")
              or any(o["calc_opened"] for o in outs))
    responded = liked or passed or strong
    row = {k: s.get(k) for k in ("impression_id", "user_id", "league_id", "served_at", "model_arm",
                                 "policy_version", "trade_concept_id", "partner", "card_index")}
    row.update(packed=bool(s.get("packed")), propensity=_num(s.get("propensity")),
               position=int(s["card_index"]), viewed=acts["viewed"] > 0 or responded,
               responded=responded, undone=undone, conflict=liked and passed,
               y_like=None if undone or (liked and passed) or not (liked or passed)
               else (1.0 if liked else 0.0),
               y_strong=(1.0 if strong else 0.0) if responded and not undone else None,
               pass_reason=reason if passed else None,
               match_other=[m[0] for m in match_list], match_status=[m[1] for m in match_list],
               executed=link)
    for k in PROOF_FIELDS:
        if k in ("gen_version", "shape", "partner") or k.endswith(("_state", "_outlook")):
            row[k] = s.get(k)
        else:
            row[k] = _num(s.get(k))
    row["has_proof"] = row.get("weaker_support") is not None
    return row


def _counterparty_labels(rows, spine, outcomes, decisions, concept_decisions):
    """The partner's response to the same concept: their own labelled
    impression of it (a mirror; read from the labelled spine, so no scan of
    a partner's whole inventory), their trade_decisions on it, the match, the
    executed trade. A mirror the partner was served but never answered is
    not looked up: it carries no label."""
    mirrors = defaultdict(list)
    for s in spine.values():
        if s.get("trade_concept_id"):
            mirrors[(s["user_id"], s["league_id"], s["trade_concept_id"])].append(s["impression_id"])
    for r in rows:
        pos = neg = False
        key = (r["partner"], r["league_id"], r["trade_concept_id"])
        mirror_ids = mirrors.get(key, []) if r["partner"] and r["trade_concept_id"] else []
        acts = Counter(o["action"] for m in mirror_ids for o in outcomes.get(m, ()))
        decs = [d for m in mirror_ids for d in decisions.get(m, ())] + concept_decisions.get(key, [])
        r["mirror_responded"] = bool(acts) or bool(decs)
        pos |= acts["like"] > 0 or "like" in decs or "send" in decs
        neg |= acts["pass"] > 0 or acts["not_interested"] > 0 or "pass" in decs
        pos |= "accept" in r["match_other"] or "accepted" in r["match_status"]
        neg |= "decline" in r["match_other"]
        pos |= r["executed"] in ("exact", "retro_exact")
        r["y_counterparty"] = 1.0 if pos else (0.0 if neg else None)
        r["counterparty_conflict"] = pos and neg


def _served_volume(rd, *, since, until, allowlist, first) -> dict:
    """Non-ghost impression rows written, by arm and month, from short
    COUNT windows (COUNT_WINDOW_DAYS wide, an index range on served_at),
    plus packed cards by arm."""
    start = since or (first[:10] if first else None)
    if start is None:
        return {"by_arm_month": {}, "packed_cards_by_arm": {}}
    end = until or (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    where = ("served_at >= :a AND served_at < :b AND (is_ghost IS NULL OR is_ghost = 0) "
             "AND league_id <> :demo AND user_id NOT LIKE 'qa\\_%' ESCAPE '\\' "
             "AND user_id NOT LIKE 'demo\\_%' ESCAPE '\\' AND user_id NOT LIKE 'test\\_%' ESCAPE '\\'")
    expanding = ()
    params = {"demo": DEMO_LEAGUE}
    if allowlist:
        where += " AND user_id NOT IN :allow"
        params["allow"] = sorted(allowlist)
        expanding = ("allow",)
    out = Counter()
    a = date.fromisoformat(start[:10])
    stop = date.fromisoformat(end[:10])
    while a < stop:
        b = min(a + timedelta(days=COUNT_WINDOW_DAYS), stop)
        for r in rd.q(f"SELECT model_arm, COUNT(*) AS n FROM deck_impressions WHERE {where} "
                      "GROUP BY model_arm", {**params, "a": a.isoformat(), "b": b.isoformat()},
                      expanding=expanding):
            out[(r["model_arm"] or "none", a.isoformat()[:7])] += int(r["n"])
        a = b
    packed = Counter()
    if rd.has("deck_evidence_packs"):
        for p in rd.q("SELECT user_id, league_id, pack_version, header_json, cards_blob, checksum,"
                      " card_count FROM deck_evidence_packs WHERE served_at >= :a AND served_at < :b",
                      {"a": start, "b": end}):
            if p["league_id"] == DEMO_LEAGUE or _excluded_user(p["user_id"], allowlist):
                continue
            try:
                _run, cards = evidence_pack.unpack_run(evidence_pack.PackedRun(
                    p["pack_version"], p["header_json"], bytes(p["cards_blob"]), p["checksum"],
                    p["card_count"]))
            except evidence_pack.PackIntegrityError:
                continue
            for u in cards:
                packed[u.get("model_arm") or "none"] += 1
    return {"by_arm_month": {f"{k[0]}|{k[1]}": v for k, v in sorted(out.items())},
            "packed_cards_by_arm": dict(sorted(packed.items()))}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _derived(r: dict) -> dict:
    """Per-row baseline scores and model features (None when unavailable)."""
    d = {}
    if r.get("has_proof"):
        v, c = r.get("v_support"), r.get("c_support")
        d.update(weaker_support=r["weaker_support"], total_support=r.get("total_support"),
                 product_support=v * c if v is not None and c is not None else None,
                 viewer_support=v, counterparty_support=c,
                 market_balance=(-abs(r["v_market_gain"]) if r.get("v_market_gain") is not None
                                 else None),
                 viewer_market_gain=r.get("v_market_gain"),
                 counterparty_market_gain=r.get("c_market_gain"))
        for k in ("v_pref_c", "v_market_c", "v_plan_c", "c_pref_c", "c_market_c", "c_plan_c",
                  "v_net_pref", "v_market_gain", "v_plan_gain", "v_need",
                  "c_net_pref", "c_market_gain", "c_plan_gain", "c_need"):
            d[k] = r.get(k)
        for s in ("v", "c"):
            state = r.get(f"{s}_state")
            d[f"{s}_state_known"] = None if state is None else float(state == "known")
            d[f"{s}_state_partial"] = None if state is None else float(state == "partial")
            d[f"{s}_state_unknown"] = None if state is None else float(state == "unknown")
            o = r.get(f"{s}_outlook")
            d[f"{s}_rebuilding"] = None if o is None else float(o in ("rebuilder", "jets"))
        shape = r.get("shape")
        d["multi_asset"] = None if shape is None else float(shape != "1x1")
    d["log_position"] = math.log1p(r["position"])
    return d


def _labelled(rows, label, need):
    out = []
    for r in rows:
        y = r.get(label)
        if y is None:
            continue
        d = _derived(r)
        if all(d.get(k) is not None for k in need):
            out.append((r, d, y))
    return out


def verdict(n_pos: int, n_neg: int, n_groups: int, n_features: int) -> str:
    """insufficient_data: too few groups or events to say anything;
    mostly_prior: estimable in principle but under EPV events per feature, so
    a fit would be dominated by its regulariser; estimable otherwise."""
    minority = min(n_pos, n_neg)
    if n_groups < MIN_GROUPS or minority < 2 * MIN_CELL:
        return "insufficient_data"
    if minority < EPV * n_features or n_groups < 2 * MIN_GROUPS:
        return "mostly_prior"
    return "estimable"


def _score_diagnostics(data, group_of) -> dict:
    """Each baseline score as an ordering: in-sample AUC with a
    group-bootstrap interval (no fitting), and under grouped CV a Platt map
    to a probability: held-out log-loss/ECE against the held-out base rate."""
    out = {}
    ys = [y for _r, _d, y in data]
    groups = [group_of(r) for r, _d, _y in data]
    folds = grouped_folds(groups)
    for name in BASELINE_SCORES:
        idx = [i for i, (_r, d, _y) in enumerate(data) if d.get(name) is not None]
        sc = [data[i][1][name] for i in idx]
        yy = [ys[i] for i in idx]
        pos = int(sum(yy))
        if pos < MIN_CELL or len(yy) - pos < MIN_CELL:
            out[name] = {**cell(len(yy)), "auc": None, "note": f"a class has <{MIN_CELL} rows"}
            continue
        by_group = defaultdict(list)
        for i in idx:
            by_group[groups[i]].append((data[i][1][name], ys[i]))
        ci = _cluster_bootstrap(by_group, lambda s: auc([a for a, _ in s], [b for _, b in s]))
        held = _platt_cv(data, idx, name, ys, groups, folds)
        out[name] = {**cell(len(yy), auc=auc(sc, yy)), "within_group_auc": _r(within_auc(by_group)),
                     "auc_ci95_group_bootstrap": ci, **held}
    return out


def within_auc(by_group: dict) -> float | None:
    """Stratified AUC: only positive/negative pairs from the same group,
    pair-weighted, so differences in base rate and score level between users
    cannot masquerade as ranking skill."""
    num = den = 0.0
    for pairs in by_group.values():
        ys = [y for _s, y in pairs]
        pos = sum(ys)
        a = auc([s for s, _y in pairs], ys)
        if a is not None:
            w = pos * (len(ys) - pos)
            num += a * w
            den += w
    return num / den if den else None


def _platt_cv(data, idx, name, ys, groups, folds):
    ps, pb, yh = [], [], []
    keep = set(idx)
    for train, test in folds:
        tr = [i for i in train if i in keep]
        te = [i for i in test if i in keep]
        if not tr or not te or len({ys[i] for i in tr}) < 2:
            continue
        x = [[data[i][1][name]] for i in tr]
        mean, sd = _standardise(x)
        w = fit_logistic(_apply(x, mean, sd), [ys[i] for i in tr], l2=1e-3)
        ps += predict(w, _apply([[data[i][1][name]] for i in te], mean, sd))
        base = sum(ys[i] for i in tr) / len(tr)
        pb += [base] * len(te)
        yh += [ys[i] for i in te]
    if len(yh) < MIN_CELL:
        return {"heldout": None}
    return {"heldout": {"n": len(yh), "log_loss": round(log_loss(ps, yh), 4),
                        "base_rate_log_loss": round(log_loss(pb, yh), 4),
                        "platt": _reliability(list(zip(ps, yh)))}}


def _cv_fit(data, features, group_of, baseline="weaker_support") -> dict:
    """Grouped-CV comparison of a fitted L2 logistic head against the Platt-
    mapped baseline score, on the same folds and the same rows."""
    ys = [y for _r, _d, y in data]
    groups = [group_of(r) for r, _d, _y in data]
    folds = grouped_folds(groups)
    x_all = [[d[k] for k in features] for _r, d, _y in data]
    pf, pb, yh, gh, per_fold, signs = [], [], [], [], [], []
    for train, test in folds:
        ytr = [ys[i] for i in train]
        if len(set(ytr)) < 2:
            continue
        mean, sd = _standardise([x_all[i] for i in train])
        w = fit_logistic(_apply([x_all[i] for i in train], mean, sd), ytr)
        signs.append([math.copysign(1, c) if abs(c) > 1e-9 else 0 for c in w[1:]])
        f_pred = predict(w, _apply([x_all[i] for i in test], mean, sd))
        bx = [[data[i][1][baseline]] for i in train]
        bm, bs = _standardise(bx)
        bw = fit_logistic(_apply(bx, bm, bs), ytr, l2=1e-3)
        b_pred = predict(bw, _apply([[data[i][1][baseline]] for i in test], bm, bs))
        yt = [ys[i] for i in test]
        per_fold.append({"n": len(yt), "fitted_auc": auc(f_pred, yt), "baseline_auc": auc(b_pred, yt)})
        pf += f_pred
        pb += b_pred
        yh += yt
        gh += [groups[i] for i in test]
    if not yh:
        return {"folds": 0}
    by_group = defaultdict(list)
    for g, a, b, y in zip(gh, pf, pb, yh):
        by_group[g].append((a, b, y))

    def delta(s):
        fa = auc([a for a, _b, _y in s], [y for _a, _b, y in s])
        fb = auc([b for _a, b, _y in s], [y for _a, _b, y in s])
        return None if fa is None or fb is None else fa - fb

    mean, sd = _standardise(x_all)
    w_full = fit_logistic(_apply(x_all, mean, sd), ys)
    coefs = {}
    for j, k in enumerate(features):
        sign = math.copysign(1, w_full[j + 1]) if abs(w_full[j + 1]) > 1e-9 else 0
        agree = sum(1 for s in signs if s[j] == sign) / len(signs) if signs else None
        coefs[k] = {"coef_std": round(w_full[j + 1], 4), "sign": int(sign),
                    "fold_sign_agreement": None if agree is None else round(agree, 3)}
    fold_aucs = [f["fitted_auc"] for f in per_fold if f["fitted_auc"] is not None]
    base_aucs = [f["baseline_auc"] for f in per_fold if f["baseline_auc"] is not None]
    return {
        "folds": len(per_fold), "heldout_n": len(yh),
        "fitted": {"auc": _r(auc(pf, yh)), "log_loss": _r(log_loss(pf, yh)),
                   "calibration": _reliability(list(zip(pf, yh)))},
        "baseline": {"score": baseline, "auc": _r(auc(pb, yh)), "log_loss": _r(log_loss(pb, yh)),
                     "calibration": _reliability(list(zip(pb, yh)))},
        "fold_auc": {"fitted": _spread(fold_aucs), "baseline": _spread(base_aucs)},
        "auc_delta_ci95_group_bootstrap": _cluster_bootstrap(by_group, delta),
        "coefficients_full_fit": coefs,
    }


def _r(v):
    return None if v is None else round(v, 4)


def _spread(vals):
    if not vals:
        return None
    return {"mean": round(sum(vals) / len(vals), 4), "min": round(min(vals), 4),
            "max": round(max(vals), 4), "folds": len(vals)}


def _head(rows, label, features, *, monotone=None) -> dict:
    data = _labelled(rows, label, features + ("weaker_support",))
    ys = [y for _r, _d, y in data]
    n_pos = int(sum(ys))
    users = {r["user_id"] for r, _d, _y in data}
    leagues = {r["league_id"] for r, _d, _y in data}
    v = verdict(n_pos, len(ys) - n_pos, len(users), len(features))
    out = {"label": label, "features": list(features), "n": small(len(ys)),
           "positives": small(n_pos), "negatives": small(len(ys) - n_pos),
           "distinct_users": len(users),
           "distinct_leagues": len(leagues), "verdict": v}
    if len(ys) < 2 * MIN_CELL or min(n_pos, len(ys) - n_pos) < MIN_CELL or len(users) < 2:
        out["note"] = "too few labelled rows or groups to fit; nothing reported"
        return out
    out["baseline_scores"] = _score_diagnostics(data, lambda r: group_key(r["user_id"]))
    out["cv_by_user"] = _cv_fit(data, features, lambda r: group_key(r["user_id"]))
    if len(leagues) >= 2:
        out["cv_by_league"] = _cv_fit(data, features, lambda r: group_key(r["league_id"]))
    if monotone:
        coefs = out["cv_by_user"].get("coefficients_full_fit", {})
        c = coefs.get(monotone)
        out["monotonicity"] = {"feature": monotone, "expected": "non-negative",
                               "holds_full_fit": None if c is None else c["sign"] >= 0,
                               "fold_sign_agreement": None if c is None else c["fold_sign_agreement"]}
    return out


def _volume(rows, served) -> dict:
    by_arm = defaultdict(list)
    by_month = defaultdict(list)
    for r in rows:
        key = f"{r['model_arm'] or 'none'}|{r['policy_version'] or 'none'}"
        if r["model_arm"] == BILATERAL_ARM and r.get("gen_version"):
            key = f"{BILATERAL_ARM}|{r['gen_version']}"
        by_arm[key].append(r)
        by_month[r["served_at"][:7]].append(r)

    def summary(rs):
        likes = [r["y_like"] for r in rs if r["y_like"] is not None]
        return {**cell(len(rs), viewed=sum(r["viewed"] for r in rs),
                       responded=sum(r["responded"] for r in rs), with_proof=sum(r["has_proof"]
                                                                                 for r in rs),
                       packed=sum(r["packed"] for r in rs)),
                "viewer_like": cell(len(likes), positives=small(int(sum(likes))),
                                    rate=sum(likes) / len(likes) if likes else None),
                "viewer_strong": _count([r["y_strong"] for r in rs]),
                "counterparty": _count([r.get("y_counterparty") for r in rs]),
                "distinct_users": len({r["user_id"] for r in rs}),
                "distinct_leagues": len({r["league_id"] for r in rs})}

    served_by_arm = Counter()
    for k, n in served["by_arm_month"].items():
        served_by_arm[k.split("|")[0]] += n
    responded_by_arm = Counter(r["model_arm"] or "none" for r in rows if r["responded"])
    viewed_by_arm = Counter(r["model_arm"] or "none" for r in rows if r["viewed"])
    # Rows written are not cards delivered: an owner job writes rows for its
    # inventory, so the no-response share of rows overstates non-response.
    # The response share of VIEWED cards is the honest companion figure.
    never = {}
    for arm, n in sorted(served_by_arm.items()):
        seen = viewed_by_arm[arm]
        never[arm] = {**cell(n, viewed=seen, responded=responded_by_arm[arm],
                             no_response_share_of_rows=1 - responded_by_arm[arm] / n if n else None,
                             response_share_of_viewed=responded_by_arm[arm] / seen if seen else None)}
    user_counts = Counter(r["user_id"] for r in rows if r["y_like"] is not None)
    total = sum(user_counts.values())
    return {
        "labelled_total": summary(rows),
        "by_arm_version": {k: summary(v) for k, v in sorted(by_arm.items())},
        "by_month": {k: summary(v) for k, v in sorted(by_month.items())},
        "served_rows_by_arm_month": {k: cell(n)["n"] for k, n in served["by_arm_month"].items()},
        "served_vs_responded_by_arm": never,
        "packed_cards_by_arm": {k: cell(n)["n"] for k, n in served["packed_cards_by_arm"].items()},
        "largest_user_share_of_like_labels": round(max(user_counts.values()) / total, 3)
        if total else None,
    }


def _count(ys):
    ys = [y for y in ys if y is not None]
    return cell(len(ys), positives=small(int(sum(ys))))


def _power(rows, until=None) -> dict:
    likes = [r["y_like"] for r in rows if r["y_like"] is not None and r["has_proof"]]
    if not likes:
        return {"note": "no viewer_like labels with proofs"}
    p = sum(likes) / len(likes)
    base = auc_now = None
    data = _labelled(rows, "y_like", ("weaker_support",))
    if data:
        auc_now = auc([d["weaker_support"] for _r, d, _y in data], [y for *_x, y in data])
    base = auc_now if auc_now is not None else .5
    # Label rate from the first labelled card to the end of the window (the
    # report's `until`, else today): idle weeks after a burst count.
    days = [r["served_at"][:10] for r in rows if r["y_like"] is not None and r["has_proof"]]
    end = until[:10] if until else datetime.now(timezone.utc).date().isoformat()
    span = max((date.fromisoformat(end) - date.fromisoformat(min(days))).days, 7) / 7
    rate = len(likes) / span
    need = {
        "like_rate_lift_5pp_per_arm": power_n_per_arm(p, .05) if 0 < p < 1 else None,
        "like_rate_lift_10pp_per_arm": power_n_per_arm(p, .10) if 0 < p < 1 else None,
        "auc_0.60_vs_0.50_total_labels": n_for_auc(.5, .6, p),
        "auc_plus_0.05_over_baseline_total_labels": n_for_auc(base, min(base + .05, .99), p),
        "auc_plus_0.10_over_baseline_total_labels": n_for_auc(base, min(base + .10, .99), p),
    }
    return {"viewer_like_labels_with_proof": len(likes), "like_rate": round(p, 4),
            "baseline_weaker_support_auc": _r(auc_now),
            "labels_per_week_since_first_label": round(rate, 1),
            "required": need,
            "weeks_at_current_rate": {k: (round(v / rate, 1) if v and rate else None)
                                      for k, v in need.items() if "total" in k},
            "method": "two-proportion n per arm (analytics_stats.power_n_per_arm, alpha .05, "
                      "power .8); AUC via two independent Hanley-McNeil SEs at the current "
                      "positive share (conservative for a paired comparison). Clustering by "
                      "user inflates every figure by the design effect 1+(m-1)ICC."}


def _questions(rows) -> dict:
    proofs = [r for r in rows if r["has_proof"]]
    out = {}
    # Unknown vs known counterparty boards.
    by_state = defaultdict(lambda: {"viewer_like": [], "counterparty": []})
    for r in proofs:
        st = r.get("c_state") or "missing"
        if r["y_like"] is not None:
            by_state[st]["viewer_like"].append(r["y_like"])
        if r.get("y_counterparty") is not None:
            by_state[st]["counterparty"].append(r["y_counterparty"])
    out["counterparty_board_state"] = {
        st: {"viewer_like": _rate_cell(v["viewer_like"]), "counterparty": _rate_cell(v["counterparty"])}
        for st, v in sorted(by_state.items())}
    # Endowment proxies: pass reasons by the viewer's market position.
    reasons = defaultdict(Counter)
    for r in proofs:
        if r["pass_reason"] and r.get("v_market_gain") is not None:
            side = "viewer_gains_at_market" if r["v_market_gain"] >= 0 else "viewer_pays_at_market"
            reasons[side][r["pass_reason"][1] or r["pass_reason"][0] or "none"] += 1
    out["viewer_pass_reasons_by_market_position"] = {
        side: {"total": cell(sum(c.values()))["n"],
               "reasons": {k: cell(n)["n"] for k, n in sorted(c.items())}}
        for side, c in sorted(reasons.items())}
    cp = [r for r in proofs if r.get("y_counterparty") is not None]
    out["counterparty_endowment"] = (
        {"note": "insufficient data", "counterparty_labels": cell(len(cp))["n"]}
        if len(cp) < 4 * MIN_CELL else
        {"by_counterparty_market_gain": {
            "gains": _rate_cell([r["y_counterparty"] for r in cp if (r.get("c_market_gain") or 0) >= 0]),
            "pays": _rate_cell([r["y_counterparty"] for r in cp if (r.get("c_market_gain") or 0) < 0])}})
    # Position (rank bias).
    buckets = defaultdict(list)
    for r in proofs:
        if r["y_like"] is not None:
            p = r["position"]
            buckets["0-4" if p < 5 else "5-9" if p < 10 else "10-29" if p < 30 else "30+"].append(
                r["y_like"])
    out["viewer_like_by_position"] = {k: _rate_cell(buckets[k])
                                      for k in ("0-4", "5-9", "10-29", "30+") if k in buckets}
    out["mirror_responded_share"] = cell(len(proofs), rate=(sum(r.get("mirror_responded", False)
                                                             for r in proofs) / len(proofs))
                                      if proofs else None)
    return out


def _data_quality(rows) -> dict:
    arms_without = Counter(r["model_arm"] or "none" for r in rows if not r["has_proof"])
    bil = [r for r in rows if r["model_arm"] == BILATERAL_ARM]
    missing = Counter()
    for r in bil:
        for k in ("v_pref_c", "v_market_c", "v_plan_c", "c_pref_c", "c_market_c", "c_plan_c",
                  "v_need", "c_need", "v_state", "c_state", "shape", "partner"):
            if r.get(k) is None:
                missing[k] += 1
    props = [r["propensity"] for r in bil if r["propensity"] is not None]
    return {"labelled_rows_without_bilateral_proof_by_arm": {k: cell(n)["n"]
                                                               for k, n in sorted(arms_without.items())},
            "bilateral_rows_missing_field": {k: cell(n)["n"] for k, n in sorted(missing.items())},
            "bilateral_generator_versions": {k: cell(n)["n"] for k, n in sorted(
                Counter(r.get("gen_version") or "none" for r in bil).items())},
            "bilateral_propensity": {"min": min(props), "max": max(props)} if props else None,
            "packed_labelled_cards": sum(r["packed"] for r in rows)}


def analyse(rows: list[dict], *, served=None, arms=None, until=None) -> dict:
    """Aggregate report over extracted rows (pure; no I/O)."""
    served = served or {"by_arm_month": {}, "packed_cards_by_arm": {}}
    scoped = [r for r in rows if not arms or r["model_arm"] in arms]
    return {
        "volume": _volume(rows, served),
        "viewer_head": _head(scoped, "y_like", VIEWER_FEATURES, monotone="v_market_gain"),
        "viewer_strong_head": _head(scoped, "y_strong", VIEWER_FEATURES, monotone="v_market_gain"),
        "counterparty_head": _head(scoped, "y_counterparty", COUNTERPARTY_FEATURES,
                                   monotone="c_market_gain"),
        "power": _power(scoped, until),
        "questions": _questions(scoped),
        "data_quality": _data_quality(scoped),
    }


def assert_aggregate(report: dict, ids: set) -> None:
    """Refuse a report that carries any raw identifier seen in extraction."""
    blob = json.dumps(report, sort_keys=True, default=str)
    leaked = [i for i in ids if isinstance(i, str) and len(i) >= 4 and i in blob]
    if leaked:
        raise ValueError(f"report carries {len(leaked)} raw identifier(s); refusing to emit it")


def run(engine, *, since=None, until=None, arms=(BILATERAL_ARM,), allowlist=frozenset(),
        pace: float = 0.0) -> tuple[dict, list[dict]]:
    """Extract + analyse. Returns (sanitised report, row-level extract)."""
    with engine.connect() as conn:
        got = extract(conn, since=since, until=until, allowlist=set(allowlist), pace=pace)
    report = {
        "tool": TOOL_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"since": since, "until": until},
        "arms_analysed": list(arms or []),
        "thresholds": {"min_cell": MIN_CELL, "min_groups": MIN_GROUPS, "events_per_variable": EPV,
                       "l2_standardised": L2, "bootstrap": BOOTSTRAP},
        "exclusions": {k: v for k, v in sorted(got["exclusions"].items())},
        "allowlist_excluded": bool(allowlist),
        "reads": {"queries": got["queries"], "rows": got["rows_read"]},
        **analyse(got["rows"], served=got["volume"], arms=set(arms or ()), until=until),
    }
    assert_aggregate(report, got["ids"] | {r["user_id"] for r in got["rows"]})
    return report, got["rows"]


# ---------------------------------------------------------------------------
# Rendering and CLI
# ---------------------------------------------------------------------------

def render_markdown(rep: dict) -> str:
    lines = [f"# Acceptance eval ({rep['tool']}, {rep['generated_at']})", "",
             f"Window {rep['window']}, arms {rep['arms_analysed']}, "
             f"allowlist excluded: {rep['allowlist_excluded']}.", "",
             "## Exclusions", ""]
    lines += [f"- {k}: {v}" for k, v in rep["exclusions"].items()]
    lines += ["", "## Heads", "",
              "| head | n | pos | users | leagues | verdict | fitted AUC (user CV) | "
              "baseline AUC | delta CI95 |", "|---|---|---|---|---|---|---|---|---|"]
    for name in ("viewer_head", "viewer_strong_head", "counterparty_head"):
        h = rep[name]
        cv = h.get("cv_by_user") or {}
        lines.append(f"| {name} | {h['n']} | {h['positives']} | {h['distinct_users']} | "
                     f"{h['distinct_leagues']} | {h['verdict']} | "
                     f"{(cv.get('fitted') or {}).get('auc')} | {(cv.get('baseline') or {}).get('auc')}"
                     f" | {cv.get('auc_delta_ci95_group_bootstrap')} |")
    vb = rep["viewer_head"].get("baseline_scores") or {}
    if vb:
        lines += ["", "## Viewer like: baseline scores", "",
                  "| score | n | AUC | within-user AUC | CI95 (user bootstrap) | held-out log-loss "
                  "| base-rate log-loss | ECE |", "|---|---|---|---|---|---|---|---|"]
        for k, v in vb.items():
            h = v.get("heldout") or {}
            lines.append(f"| {k} | {v['n']} | {_r(v.get('auc'))} | {v.get('within_group_auc')} "
                         f"| {v.get('auc_ci95_group_bootstrap')}"
                         f" | {h.get('log_loss')} | {h.get('base_rate_log_loss')} | "
                         f"{(h.get('platt') or {}).get('ece')} |")
    lines += ["", "## Power", "", "```", json.dumps(rep["power"], indent=1), "```"]
    return "\n".join(lines) + "\n"


def _production_engine(secrets: str | None):
    from backend.eval.flip_read import _reads_only
    from backend.tools import prod_analytics
    if secrets and not os.environ.get("DATABASE_URL_PROD"):
        for line in Path(secrets).read_text().splitlines():
            if line.strip().startswith("DATABASE_URL_PROD="):
                os.environ["DATABASE_URL_PROD"] = line.split("=", 1)[1].strip().strip("\"'")
    eng = prod_analytics._connect_readonly(prod_analytics._load_prod_url(), 15000)
    event.listen(eng, "before_cursor_execute", _reads_only)
    with eng.connect() as conn:
        if conn.execute(text("SHOW transaction_read_only")).scalar() != "on":
            raise SystemExit("refusing: the production session is not read-only")
    return eng


def _outside_repo(path: str) -> Path:
    p = Path(path).resolve()
    if p == REPO or REPO in p.parents:
        raise SystemExit("--extract must be outside the repository (row-level data)")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--production", action="store_true",
                     help="read production through prod_analytics' read-only engine")
    src.add_argument("--db", help="SQLite path (tests, local copies)")
    ap.add_argument("--secrets", help="secrets.local.env holding DATABASE_URL_PROD")
    ap.add_argument("--since"), ap.add_argument("--until")
    ap.add_argument("--arm", action="append", help=f"arms to fit (default {BILATERAL_ARM})")
    ap.add_argument("--keep-allowlist", action="store_true",
                    help="keep tester-allowlist users (excluded by default)")
    ap.add_argument("--out", help="write the JSON report here (default stdout)")
    ap.add_argument("--markdown", help="also write a markdown rendering")
    ap.add_argument("--extract", help="row-level JSONL with hashed keys; outside the repo only")
    args = ap.parse_args(argv)
    extract_path = _outside_repo(args.extract) if args.extract else None
    if args.production:
        eng, pace = _production_engine(args.secrets), PAUSE_S
    else:
        eng = create_engine(f"sqlite:///file:{args.db}?mode=ro&uri=true",
                            connect_args={"uri": True})
        pace = 0.0
    from backend.experiments import load_tester_allowlist
    allow = frozenset() if args.keep_allowlist else frozenset(load_tester_allowlist())
    try:
        report, rows = run(eng, since=args.since, until=args.until,
                           arms=tuple(args.arm or (BILATERAL_ARM,)), allowlist=allow, pace=pace)
    except Exception as e:      # the message may carry connection detail
        if args.production:
            # The type and the SQL verb/table only: never the message, which
            # may carry connection detail.
            stmt = " ".join(str(getattr(e, "statement", "") or "").split()[:6])
            print(f"acceptance_eval: {type(e).__name__} {stmt}", file=sys.stderr)
            return 2
        raise
    finally:
        eng.dispose()
    blob = json.dumps(report, indent=1, sort_keys=True, default=str)
    if args.out:
        Path(args.out).write_text(blob + "\n")
    else:
        print(blob)
    if args.markdown:
        Path(args.markdown).write_text(render_markdown(report))
    if extract_path:
        with extract_path.open("w") as fh:
            for r in rows:
                out = {k: v for k, v in r.items() if k not in (
                    "impression_id", "user_id", "league_id", "partner", "trade_concept_id")}
                out.update(user_key=group_key(r["user_id"]), league_key=group_key(r["league_id"]))
                fh.write(json.dumps(out, default=str) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
