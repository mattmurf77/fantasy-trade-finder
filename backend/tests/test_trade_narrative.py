"""Snapshot-style tests for the templated trade narrative.

Covers `build_narrative` (positional honesty, sentence cap, fairness fallback)
and — from the counterparty-breaker plan — `hesitation_line`:

* LLD §1.6 / §7.2 — template table, `HESITATION_TMPL_VERSION` snapshot, the
  null-evidence rule (present-but-null ⇒ None, never "None-year-old"),
  unknown/dark codes, D-053 name-from-evidence-id resolution.
* PRD §5.4 — the binding tone rules in their mechanical form: fixed lead-in,
  hedged modality, no unhedged mental-state verbs, no surveillance framing,
  one sentence, ≤120 chars at worst-case interpolation.
* LLD §3.3 / §7.1 `test_opponent_frame_breaker_coherence` — the same-scalar XOR
  precondition between `_opponent_frame` and the breaker's `fit_outlook`.
"""
import itertools
import re
import sys
from dataclasses import dataclass, field

import backend.trade_narrative as tn
from backend.trade_narrative import (
    HESITATION_DARK_CODES,
    HESITATION_LEAD_IN,
    HESITATION_TEMPLATE_FIELDS,
    HESITATION_TEMPLATES,
    HESITATION_TMPL_VERSION,
    build_narrative,
    hesitation_line,
)


@dataclass
class _P:
    id: str
    name: str
    position: str
    pick_value: float | None = None
    search_rank: int = 100


@dataclass
class _Card:
    give_player_ids: list[str]
    receive_player_ids: list[str]
    fairness_score: float = 0.9
    mismatch_score: float = 50.0
    composite_score: float = 100.0


def test_overlap_mentions_position_and_player():
    players = {"r1": _P("r1", "Bijan Robinson", "RB")}
    card = _Card(give_player_ids=["w1"], receive_player_ids=["r1"])
    ctx = {
        "user_needs":       ["RB"],
        "opponent_surplus": ["RB"],
        "league_settings":  {"dynasty": False},
    }
    out = build_narrative(card, ctx, players)
    assert "RB" in out
    assert "Bijan Robinson" in out
    assert out.count(".") <= 2  # ≤ 2 sentences


def test_picks_get_dynasty_callout_when_dynasty():
    players = {
        "r1": _P("r1", "Saquon", "RB"),
        "p1": _P("p1", "2026 1st", "PICK", pick_value=67.5),
    }
    card = _Card(give_player_ids=["w1"], receive_player_ids=["r1", "p1"])
    ctx = {"user_needs": [], "opponent_surplus": [], "league_settings": {"dynasty": True}}
    out = build_narrative(card, ctx, players)
    assert "dynasty pick" in out.lower()


def test_no_context_falls_back_to_fairness():
    players = {"r1": _P("r1", "Player A", "RB")}
    card = _Card(give_player_ids=["w1"], receive_player_ids=["r1"], fairness_score=0.6)
    out = build_narrative(card, None, players)
    assert "uneven" in out.lower() or "tilt" in out.lower() or "Player A" in out


def test_picks_highest_value_received_player_not_first():
    # depth piece listed first, headliner second — narrative must name headliner
    players = {
        "depth":     _P("depth",     "Bench Guy",     "WR", search_rank=400),
        "headliner": _P("headliner", "CeeDee Lamb",   "WR", search_rank=3),
    }
    card = _Card(give_player_ids=["g"], receive_player_ids=["depth", "headliner"])
    ctx = {"user_needs": ["WR"], "opponent_surplus": ["WR"], "league_settings": {}}
    out = build_narrative(card, ctx, players)
    assert "CeeDee Lamb" in out
    assert "Bench Guy" not in out


# ───────────── positional honesty (2026-08-15 correctness fix) ─────────────
# `user_needs` comes from the roster analysis and the received players come
# from the card. A sentence may only pair a position with a player who
# actually plays it.

def test_te_only_return_never_claims_the_qb_need():
    players = {"r1": _P("r1", "Brock Bowers", "TE", search_rank=8)}
    card = _Card(give_player_ids=["g"], receive_player_ids=["r1"])
    ctx = {
        "user_needs":       ["QB", "RB"],
        "opponent_surplus": ["TE"],
        "league_settings":  {},
    }
    out = build_narrative(card, ctx, players)
    assert "QB" not in out
    assert "Brock Bowers" in out
    assert "thin" not in out and "shore up" not in out   # neutral fallback


def test_names_the_position_the_received_player_actually_plays():
    # top need is QB; the only need-filling player received is the RB
    players = {
        "rb": _P("rb", "Bijan Robinson", "RB", search_rank=2),
        "te": _P("te", "Bench TE",       "TE", search_rank=300),
    }
    card = _Card(give_player_ids=["g"], receive_player_ids=["rb", "te"])
    ctx = {
        "user_needs":       ["QB", "RB"],
        "opponent_surplus": ["RB"],
        "league_settings":  {},
    }
    out = build_narrative(card, ctx, players)
    assert "shore up RB by acquiring Bijan Robinson" in out
    assert "QB" not in out


def test_overlap_position_matches_the_named_player():
    # overlap[0] is QB but only the WR comes back
    players = {"wr": _P("wr", "Puka Nacua", "WR", search_rank=5)}
    card = _Card(give_player_ids=["g"], receive_player_ids=["wr"])
    ctx = {
        "user_needs":       ["QB", "WR"],
        "opponent_surplus": ["QB", "WR"],
        "league_settings":  {},
    }
    out = build_narrative(card, ctx, players)
    assert "shore up WR by acquiring Puka Nacua" in out
    assert "QB" not in out


def test_picks_alone_do_not_fill_a_positional_need():
    players = {"p1": _P("p1", "2026 1st", "PICK", pick_value=67.5)}
    card = _Card(give_player_ids=["g"], receive_player_ids=["p1"])
    ctx = {"user_needs": ["QB"], "opponent_surplus": ["QB"],
           "league_settings": {"dynasty": True}}
    out = build_narrative(card, ctx, players)
    assert "QB" not in out
    assert "2026 1st" in out


def test_fit_premium_uses_the_premium_position():
    players = {"r1": _P("r1", "Trey McBride", "TE", search_rank=15)}
    card = _Card(give_player_ids=["g"], receive_player_ids=["r1"])
    card.fit_premium = {"value_paid": 120.0, "position": "TE"}
    ctx = {"user_needs": ["QB", "TE"], "opponent_surplus": ["TE"],
           "league_settings": {}}
    out = build_narrative(card, ctx, players)
    assert "Fills your TE hole with Trey McBride" in out
    assert "QB" not in out


def test_fit_premium_without_a_position_does_not_borrow_the_top_need():
    players = {"r1": _P("r1", "Trey McBride", "TE", search_rank=15)}
    card = _Card(give_player_ids=["g"], receive_player_ids=["r1"])
    card.fit_premium = {"value_paid": 120.0, "position": None}
    ctx = {"user_needs": ["QB"], "opponent_surplus": ["QB"],
           "league_settings": {}}
    out = build_narrative(card, ctx, players)
    assert "QB" not in out
    assert "Trey McBride" in out


def test_no_position_is_claimed_that_is_not_actually_received():
    """Invariant over every needs × received-positions combination: a
    position token in the narrative must belong to a received player."""
    import itertools

    POSITIONS = ["QB", "RB", "WR", "TE"]
    for recv in itertools.chain(
        itertools.combinations(POSITIONS, 1),
        itertools.combinations(POSITIONS, 2),
    ):
        players = {p: _P(p, f"{p} Guy", p, search_rank=10) for p in recv}
        card = _Card(give_player_ids=["g"], receive_player_ids=list(recv))
        for r in range(1, len(POSITIONS) + 1):
            for needs in itertools.permutations(POSITIONS, r):
                for surplus in ([], list(needs), POSITIONS):
                    ctx = {"user_needs": list(needs),
                           "opponent_surplus": surplus,
                           "league_settings": {}}
                    out = build_narrative(card, ctx, players)
                    claimed = [p for p in POSITIONS
                               if f" {p} " in f" {out} "
                               or f"{p} hole" in out
                               or f"{p} group" in out]
                    assert all(p in recv for p in claimed), (
                        f"recv={recv} needs={needs} surplus={surplus} → {out}")


def test_two_sentence_cap():
    players = {
        "r1": _P("r1", "RB1", "RB"),
        "p1": _P("p1", "Pick", "PICK", pick_value=50),
    }
    card = _Card(give_player_ids=["g"], receive_player_ids=["r1", "p1"])
    ctx = {"user_needs": ["RB"], "opponent_surplus": ["RB"], "league_settings": {"dynasty": True}}
    out = build_narrative(card, ctx, players)
    assert out.count(".") == 2


# ══════════════ counterparty breaker — hesitation_line (LLD §1.6) ══════════════

#: One well-formed objection per template key. Evidence keys are exactly the
#: LLD §2.4 enums for the code; only the keys a template renders matter here,
#: the rest ride along to prove the renderer ignores them.
_OBJECTIONS = {
    "fit_outlook.rebuild": {
        "code": "fit_outlook", "severity": 0.8,
        "evidence": {"outlook": "rebuilder", "lean": 0.19, "asset": "vet",
                     "age": 31, "pos": "RB"},
    },
    "fit_outlook.win_now": {
        "code": "fit_outlook", "severity": 0.7,
        "evidence": {"outlook": "contender", "lean": -0.25, "asset": None,
                     "age": None, "pos": None},
    },
    "fit_new_weakness": {
        "code": "fit_new_weakness", "severity": 1.0,
        "evidence": {"pos": "TE", "before": 1, "after": 0, "need": 1,
                     "asset": "te", "tier_basis": "positional"},
    },
    "fit_duplicate": {
        "code": "fit_duplicate", "severity": 0.9,
        "evidence": {"pos": "WR", "bench_n": 4, "value_share": 0.6,
                     "asset": "wr", "tier_basis": "positional"},
    },
    "value_giving": {
        "code": "value_giving", "severity": 0.8,
        "evidence": {"basis": "consensus", "margin": -180.0,
                     "n_give": 2, "n_recv": 1},
    },
    "roster_crunch.one": {
        "code": "roster_crunch", "severity": 0.5,
        "evidence": {"extra": 1, "slot_cost": 6.0, "pileup": []},
    },
    "roster_crunch": {
        "code": "roster_crunch", "severity": 0.5,
        "evidence": {"extra": 2, "slot_cost": 12.0, "pileup": ["WR"]},
    },
}

#: Evidence ids resolve against this pool. "decoy" is in the pool but in NO
#: evidence dict — a sentence that ever names it is inventing a claim.
_HES_PLAYERS = {
    "vet":   _P("vet",   "Aaron Jones",     "RB"),
    "te":    _P("te",    "Trey McBride",    "TE"),
    "wr":    _P("wr",    "Jordan Addison",  "WR"),
    "decoy": _P("decoy", "Ja'Marr Chase",   "WR"),
}

#: Worst-case interpolation for the PRD §5.4 rule-7 length budget: the longest
#: name on the DynastyProcess consensus board ("Marquez Valdes-Scantling", 24
#: chars), a 2-digit age, a 2-char position enum (every `_POS_TIER_CUTS`
#: position is 2 chars), and a 2-digit body count.
_WORST = {"name": "Marquez Valdes-Scantling", "age": "99", "pos": "QB",
          "extra": "99"}
_LENGTH_BUDGET = 120


def _objection(key, **evidence_overrides):
    """A deep-enough copy of a canonical objection with evidence overridden."""
    base = _OBJECTIONS[key]
    ev = dict(base["evidence"])
    ev.update(evidence_overrides)
    return {"code": base["code"], "severity": base["severity"], "evidence": ev}


def test_hesitation_templates_snapshot():
    """Every template string and the version are pinned verbatim. A reword
    without a `HESITATION_TMPL_VERSION` bump fails here — the narration A/B
    readout keys on (ver, tmpl_ver) and would otherwise pool two copies."""
    assert HESITATION_TMPL_VERSION == "brt-1"
    assert HESITATION_TEMPLATES == {
        "fit_outlook.rebuild":
            "Their likely hesitation: their roster leans rebuild, and this "
            "sends them {name}, a {age}-year-old {pos}.",
        "fit_outlook.win_now":
            "Their likely hesitation: they look win-now, and this asks them "
            "to take back future capital.",
        "fit_new_weakness":
            "Their likely hesitation: giving up {name} may leave them thin "
            "at {pos}.",
        "fit_duplicate":
            "Their likely hesitation: they're already deep at {pos}, so "
            "{name} may not move their lineup.",
        "value_giving":
            "Their likely hesitation: by consensus value they'd likely see "
            "this as giving up more than they get.",
        "roster_crunch.one":
            "Their likely hesitation: taking back 1 more player than they "
            "send is a roster squeeze.",
        "roster_crunch":
            "Their likely hesitation: taking back {extra} more players than "
            "they send is a roster squeeze.",
    }
    # The field table and the template table describe the same six templates.
    assert set(HESITATION_TEMPLATE_FIELDS) == set(HESITATION_TEMPLATES)
    for key, tmpl in HESITATION_TEMPLATES.items():
        slots = set(re.findall(r"\{(\w+)\}", tmpl))
        assert slots == set(HESITATION_TEMPLATE_FIELDS[key]), key
    # `other_player_keep` is permanently dark (D-6): no template, ever.
    assert HESITATION_DARK_CODES == frozenset({"other_player_keep"})
    assert not (HESITATION_DARK_CODES & set(HESITATION_TEMPLATES))


def test_hesitation_length_budget():
    """PRD §5.4 rule 7 — every template at maximal interpolation fits two
    lines of `type.bodySm`, pinned as ≤120 chars."""
    for key, tmpl in HESITATION_TEMPLATES.items():
        rendered = tmpl.format(**{f: _WORST[f]
                                  for f in HESITATION_TEMPLATE_FIELDS[key]})
        assert len(rendered) <= _LENGTH_BUDGET, (
            f"{key}: {len(rendered)} chars > {_LENGTH_BUDGET}\n{rendered}")


def test_hesitation_line_renders_each_class():
    """Each narratable class renders its PRD §5.4 worked example verbatim."""
    got = {k: hesitation_line(_OBJECTIONS[k], _HES_PLAYERS) for k in _OBJECTIONS}
    assert got == {
        "fit_outlook.rebuild":
            "Their likely hesitation: their roster leans rebuild, and this "
            "sends them Aaron Jones, a 31-year-old RB.",
        "fit_outlook.win_now":
            "Their likely hesitation: they look win-now, and this asks them "
            "to take back future capital.",
        "fit_new_weakness":
            "Their likely hesitation: giving up Trey McBride may leave them "
            "thin at TE.",
        "fit_duplicate":
            "Their likely hesitation: they're already deep at WR, so Jordan "
            "Addison may not move their lineup.",
        "value_giving":
            "Their likely hesitation: by consensus value they'd likely see "
            "this as giving up more than they get.",
        "roster_crunch.one":
            "Their likely hesitation: taking back 1 more player than they "
            "send is a roster squeeze.",
        "roster_crunch":
            "Their likely hesitation: taking back 2 more players than they "
            "send is a roster squeeze.",
    }
    # The singular branch is evidence-selected, never assumed: only `extra == 1`
    # reaches it, and a missing/null/garbage count still refuses to render.
    assert "1 more player " in hesitation_line(_objection("roster_crunch", extra=1), {})
    assert "2 more players" in hesitation_line(_objection("roster_crunch", extra=2), {})
    for bad in (None, "1", True, 0, -1, 3):
        out = hesitation_line(_objection("roster_crunch", extra=bad), {})
        assert out is None or "1 more player " not in out, bad
    assert hesitation_line(
        {"code": "roster_crunch", "evidence": {"slot_cost": 6.0}}, {}) is None


def test_hesitation_line_honesty():
    """R-12 / D-053, mechanically. Per class: the sentence says nothing the
    objection's own evidence doesn't contain; every rendered key that is
    missing — or PRESENT-BUT-NULL — yields None rather than a guess or a
    literal "None"; unknown and dark codes never render."""
    for key, fields in HESITATION_TEMPLATE_FIELDS.items():
        obj = _OBJECTIONS[key]
        out = hesitation_line(obj, _HES_PLAYERS)
        assert out is not None, key

        # (a) Content ⊆ evidence. The only name that may appear is the one the
        #     evidence's own `asset` id resolves to; no other pool member, and
        #     no evidence value the template does not render.
        for pid, player in _HES_PLAYERS.items():
            expected = "name" in fields and obj["evidence"].get("asset") == pid
            assert (player.name in out) is expected, (key, pid)
        if "pos" in fields:
            assert obj["evidence"]["pos"] in out
        if "age" in fields:
            assert str(obj["evidence"]["age"]) in out
        if "extra" in fields:
            assert str(obj["evidence"]["extra"]) in out

        # (b) Missing key ⇒ None. (c) Present-but-null ⇒ None, and never the
        #     string "None" — the "None-year-old" interpolation case.
        for field in fields:
            ev_key = "asset" if field == "name" else field
            stripped = dict(obj["evidence"])
            stripped.pop(ev_key)
            assert hesitation_line(
                {**obj, "evidence": stripped}, _HES_PLAYERS) is None, (key, field)

            nulled = hesitation_line(_objection(key, **{ev_key: None}),
                                     _HES_PLAYERS)
            assert nulled is None, (key, field)

        # (d) An id the player pool cannot resolve is not a licence to guess.
        if "name" in fields:
            assert hesitation_line(_objection(key, asset="ghost"),
                                   _HES_PLAYERS) is None
            assert hesitation_line(obj, {}) is None

    # The explicit "None-year-old" regression: a null age must not stringify.
    null_age = hesitation_line(_objection("fit_outlook.rebuild", age=None),
                               _HES_PLAYERS)
    assert null_age is None

    # The singular `roster_crunch` branch hardcodes "1", so its honesty rests
    # on the discriminator: no evidence count ⇒ no sentence at all, and no
    # other count is ever spoken as one.
    for bad in (None, "one", [], float("nan")):
        assert hesitation_line(_objection("roster_crunch", extra=bad), {}) is None
    assert hesitation_line(_objection("roster_crunch", extra=1), {}).count("1") == 1

    # Unknown, dark, and malformed codes never render.
    assert hesitation_line({"code": "other_player_keep", "severity": 1.0,
                            "evidence": {"asset": "vet", "list": "untouchable"}},
                           _HES_PLAYERS) is None
    assert hesitation_line({"code": "shape_aversion", "evidence": {}},
                           _HES_PLAYERS) is None
    assert hesitation_line({"code": None, "evidence": {}}, _HES_PLAYERS) is None
    assert hesitation_line({"evidence": {}}, _HES_PLAYERS) is None

    # A window claim requires a window, and a value claim requires the
    # consensus basis (board basis is ineligible outright, D-7).
    for outlook in (None, "not_sure", "", "REBUILDER"):
        assert hesitation_line(_objection("fit_outlook.rebuild",
                                          outlook=outlook), _HES_PLAYERS) is None
    for basis in ("board", None, ""):
        assert hesitation_line(_objection("value_giving", basis=basis),
                               _HES_PLAYERS) is None


def test_hesitation_line_never_raises():
    """Any internal error degrades to None; the caller stamps
    `suppressed="template_error"` (E-15) and never sees an exception."""
    garbage = [None, "", 0, [], ("code", "fit_duplicate"), object(),
               {"code": "fit_duplicate"},
               {"code": "fit_duplicate", "evidence": None},
               {"code": "fit_duplicate", "evidence": "pos=WR"},
               {"code": "roster_crunch", "evidence": {"extra": "two"}},
               {"code": "roster_crunch", "evidence": {"extra": True}},
               {"code": "roster_crunch", "evidence": {"extra": float("nan")}},
               {"code": "fit_new_weakness", "evidence": {"pos": 7, "asset": "te"}},
               {"code": "fit_outlook", "evidence": {"outlook": ["rebuilder"]}}]
    for bad in garbage:
        assert hesitation_line(bad, _HES_PLAYERS) is None, bad
    for bad_players in (None, "", 0, []):
        for key in _OBJECTIONS:
            assert isinstance(
                hesitation_line(_OBJECTIONS[key], bad_players), (str, type(None)))
    # A player object with no resolvable name is silence, not "None".
    assert hesitation_line(_OBJECTIONS["fit_new_weakness"],
                           {"te": object()}) is None


def test_hesitation_line_is_deterministic_and_pure():
    """Same inputs ⇒ same output; and the module reads no flag, no knob, and
    never imports the breaker (the breaker calls US)."""
    # Runtime-level: `sys.modules` is process-global and the breaker's own
    # test file legitimately imports it, so drop the module first, render
    # every class, and prove NOTHING here re-imported it — then restore the
    # registry for the rest of the suite (`test_organic_never_imports_fit`
    # precedent, test_trade_gen_fit.py:883).
    saved = sys.modules.pop("backend.trade_breaker", None)
    try:
        for key in _OBJECTIONS:
            first = hesitation_line(_OBJECTIONS[key], _HES_PLAYERS)
            for _ in range(3):
                assert hesitation_line(_OBJECTIONS[key], _HES_PLAYERS) == first
        assert "backend.trade_breaker" not in sys.modules
    finally:
        if saved is not None:
            sys.modules["backend.trade_breaker"] = saved

    # Purity as code, not as prose: walk the AST so the module's own comments
    # and docstrings (which legitimately NAME the breaker) don't mask a real
    # import or call. Only `trade_service` may be imported, and only lazily.
    import ast
    tree = ast.parse(open(tn.__file__, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(a.name for a in node.names)
    for forbidden in ("trade_breaker", "feature_flags", "database"):
        assert not any(forbidden in m for m in imported), (forbidden, imported)
    identifiers = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for forbidden in ("is_enabled", "get_config", "FLAGS", "reload_config",
                      "_cfg", "_c"):
        assert forbidden not in identifiers, forbidden


# ── PRD §5.4 tone rules, in their mechanically checkable form ──

#: Verbs that assert what is inside the other manager's head. Banned when
#: attached to a "they" subject without an intervening hedge (rule 3). "look",
#: "leans", and "seem" are NOT here — PRD rule 2 lists them as hedges.
_MENTAL_STATE_VERBS = {
    "want", "wants", "think", "thinks", "believe", "believes", "feel", "feels",
    "rate", "rates", "value", "values", "like", "likes", "dislike", "dislikes",
    "prefer", "prefers", "know", "knows", "expect", "expects", "see", "sees",
    "view", "views", "consider", "considers", "mind", "minds", "care", "cares",
    "hate", "hates", "love", "loves", "doubt", "doubts", "intend", "intends",
    "refuse", "refuses", "trust", "trusts", "assume", "assumes", "hope",
    "hopes", "fear", "fears", "understand", "understands",
    # predicate-adjective forms of the same claim ("they're not interested")
    "interested", "keen", "sold", "aware", "willing", "unwilling",
    "reluctant", "happy", "unhappy", "convinced", "worried",
}
_HEDGES = {"likely", "may", "might", "probably", "could", "look", "looks",
           "leans", "lean", "seem", "seems", "appear", "appears", "would",
           "should"}
#: Templates whose body states countable roster arithmetic rather than
#: characterising the partner — the lead-in's "likely" is the whole hedge.
_OBSERVABLE_ONLY_BODIES = frozenset({"roster_crunch", "roster_crunch.one"})
_BODY_HEDGES = ("likely", "may", "might", "look", "leans")
_SUBJECT_AUX = {"do", "does", "did", "will", "would", "are", "is", "was",
                "were", "have", "has", "not", "never", "just", "really",
                "already", "still", "simply"}


def _unhedged_mental_state_verbs(sentence: str) -> list[str]:
    """Every mental-state verb bound to a "they" subject with no hedge in
    between. "they'd likely see" is fine; "they see" / "they don't want" is
    mind-reading. Negative contractions are expanded first, so `won't want`
    reads as `will not want`."""
    text = (sentence.lower()
            .replace("won't", "will not").replace("can't", "can not"))
    text = re.sub(r"n't\b", " not", text)
    tokens = re.findall(r"[a-z']+", text)
    hits = []
    for i, tok in enumerate(tokens):
        if tok.split("'")[0] != "they":
            continue
        for nxt in tokens[i + 1:]:
            stem = nxt.strip("'")
            if stem in _HEDGES:
                break                       # hedged — rule 2 satisfied
            if stem in _MENTAL_STATE_VERBS:
                hits.append(nxt)
                break
            if stem not in _SUBJECT_AUX:
                break                       # subject ran out; not a claim
    return hits


def test_unhedged_mental_state_detector_is_not_vacuous():
    """The deny-list check above must actually reject the PRD's own banned
    examples — a detector that passes everything guards nothing."""
    for banned in ("they don't rate your RB",
                   "they won't want another WR",
                   "they're not interested in picks",
                   "they see this as a downgrade",
                   "they value their own board more"):
        assert _unhedged_mental_state_verbs(banned), banned
    for allowed in ("they'd likely see this as giving up more",
                    "they look win-now",
                    "their roster leans rebuild",
                    "they may not want it"):
        assert not _unhedged_mental_state_verbs(allowed), allowed


def test_hesitation_tone_rules():
    """PRD §5.4 rules 1, 2, 3, 5, 6 over every template, rendered at both the
    canonical and the worst-case interpolation."""
    for key, tmpl in HESITATION_TEMPLATES.items():
        renders = [tmpl.format(**{f: _WORST[f]
                                  for f in HESITATION_TEMPLATE_FIELDS[key]}),
                   hesitation_line(_OBJECTIONS[key], _HES_PLAYERS)]
        for text in renders:
            # 1 — fixed lead-in label, once, at the front.
            assert text.startswith(HESITATION_LEAD_IN + " "), key
            assert text.count(HESITATION_LEAD_IN) == 1, key
            # 2 — hedged modality. The lead-in carries "likely" for every
            #     template; any template whose BODY characterises the partner
            #     (rather than stating roster arithmetic) hedges again on its
            #     own. `roster_crunch` is the listed exception: its body is a
            #     countable roster fact, not a disposition.
            assert "likely" in HESITATION_LEAD_IN.lower()
            body = text[len(HESITATION_LEAD_IN):].lower()
            if key not in _OBSERVABLE_ONLY_BODIES:
                assert any(h in body for h in _BODY_HEDGES), (key, body)
            # 3 — no unhedged mind-reading.
            assert not _unhedged_mental_state_verbs(text), (key, text)
            # 5 — no surveillance framing.
            low = text.lower()
            for banned in ("ftf", "our data", "data shows", "we know",
                           "we can see", "according to"):
                assert banned not in low, (key, banned)
            # 6 — exactly one sentence.
            assert text.endswith("."), key
            assert text.count(".") == 1, key
            assert "\n" not in text, key


# ── LLD §3.3 / §7.1 — the same-scalar XOR coherence precondition ──

_OUTLOOKS = ("rebuilder", "jets", "contender", "championship")
_LEAN_GRID = (-0.2, -0.05, 0.0, 0.05, 0.2)


def _breaker_fit_outlook_push(outlook, lean):
    """LLD §3.3, mirrored. `trade_breaker` is owned elsewhere and must not be
    imported here (the breaker calls US); this is the spec's arithmetic held
    against `_opponent_frame`'s thresholds. If the two ever disagree the
    breaker-side `test_lean_quantity_parity` and this test both go red."""
    if outlook in ("rebuilder", "jets"):
        return max(0.0, lean - 0.05)          # aging assets pushed at a rebuild
    if outlook in ("contender", "championship"):
        return max(0.0, -lean - 0.05)         # youth/picks pushed at a win-now
    return 0.0


def test_opponent_frame_thresholds_pinned():
    """Characterization: `_opponent_frame`'s ±0.05 cuts and its outlook enum
    are what the XOR proof below rests on. A threshold or enum change lands
    here first, and must land breaker-side in the same change (HLD §2.4)."""
    import inspect
    src = inspect.getsource(tn._opponent_frame)
    assert 'outlook not in ("rebuilder", "jets", "contender", "championship")' in src
    assert 'if outlook in ("rebuilder", "jets") and lean <= -0.05:' in src
    assert 'if outlook in ("contender", "championship") and lean >= 0.05:' in src


def test_opponent_frame_breaker_coherence(monkeypatch):
    """The two writers consume the SAME scalar (`_give_side_now_lean`) and the
    same outlook value, so they can never both speak about the window on one
    card: `_opponent_frame` says the package FITS their window, the breaker's
    `fit_outlook` says it PUSHES against it. Disjoint by construction — pinned
    as a characterization test over the grid."""
    players = {"r1": _P("r1", "Bijan Robinson", "RB")}
    card = _Card(give_player_ids=["g"], receive_player_ids=["r1"])

    seen_outlooks = []
    real_frame = tn._opponent_frame

    def _spy(card_, ctx_, players_):
        seen_outlooks.append(((ctx_ or {}).get("opponent_outlook") or {}).get("value"))
        return real_frame(card_, ctx_, players_)

    for outlook, lean in itertools.product(_OUTLOOKS + ("not_sure", None),
                                           _LEAN_GRID):
        monkeypatch.setattr(tn, "_give_side_now_lean", lambda c, p, _l=lean: _l)
        ctx = {"opponent_outlook": {"value": outlook}}
        frame = _spy(card, ctx, players)
        push = _breaker_fit_outlook_push(outlook, lean)

        # Precondition (HLD §2.4): both writers read the one outlook value.
        assert seen_outlooks[-1] == outlook

        assert not (frame is not None and push > 0.0), (
            f"outlook={outlook} lean={lean}: frame={frame!r} push={push}")

        # And when the breaker DOES fire, the sentence it would render asserts
        # the opposite direction to the frame sentence that did not fire.
        if push > 0.0:
            key = ("fit_outlook.rebuild"
                   if outlook in ("rebuilder", "jets") else "fit_outlook.win_now")
            sentence = hesitation_line(
                _objection(key, outlook=outlook, lean=lean), _HES_PLAYERS)
            assert sentence is not None
            assert ("fits their timeline" not in sentence
                    and "fit their window" not in sentence)

    # The grid is not vacuous: the frame fires somewhere and so does the push.
    monkeypatch.setattr(tn, "_give_side_now_lean", lambda c, p: -0.2)
    assert real_frame(card, {"opponent_outlook": {"value": "rebuilder"}},
                      players) is not None
    assert _breaker_fit_outlook_push("contender", -0.2) > 0.0
