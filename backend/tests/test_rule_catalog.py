"""The rule catalog (founder review, use case 2; docs/plans/founder-review/rule-waterfall-design.md §2).

Completeness, by AST inventory of the served engine (owner bilateral revisions 1, 2 and 5 and
the owner evaluator they share), so the catalog cannot silently go stale:
- every literal reason the owner evaluator's ``finish(...)`` can record, including the computed
  ``name + "_no_benefit"`` (resolved from its loop); an argument the walk cannot resolve fails;
- every reason the bilateral search classes assign (``reason = "..."`` and ``reason="..."``);
- every reason ``deck_quality.card_rule`` returns and ``DeckRules.reason`` assigns;
- the labels the rules-first module builds its private rejections with are known non-rules;
- and the other way: no catalog engine reason the engine no longer produces;
- the fixable-reason list the generator expands from equals the page search's copy.

Shape and plain language: valid stage/kind/protects, waterfall order follows the stage order,
unique keys, a name of at most five words, a description of one to three sentences, and no code
identifiers (snake_case, camelCase, calls, file names) in a name or description; every rule
names its source file and whether it is counted today.
"""
import ast
import re
from pathlib import Path

import pytest

from backend import rule_catalog as rc, trade_first_page

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
SERVED_GENERATORS = ("trade_gen_owner.py", "trade_gen_bilateral.py", "trade_gen_bilateral_candidate.py",
                     "trade_gen_bilateral_season.py")
# Labels the rules-first construction gives its own private rejections: a package the gated
# full solve skips because the deck rules already reject it (counted under those rules).
NON_RULE_LABELS = {"deck_rules"}


def _tree(name):
    return ast.parse((BACKEND / name).read_text())


def _resolve_concat(call, parents):
    """``finish(name + "_suffix")`` -> the suffix joined to each first-element constant of the
    enclosing ``for name, ... in ((...), ...)`` loop."""
    arg = call.args[0]
    if not (isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add)
            and isinstance(arg.left, ast.Name) and isinstance(arg.right, ast.Constant)):
        return None
    node = parents.get(call)
    while node is not None:
        if isinstance(node, ast.For):
            target = node.target.elts[0] if isinstance(node.target, ast.Tuple) else node.target
            if isinstance(target, ast.Name) and target.id == arg.left.id and isinstance(node.iter, ast.Tuple):
                firsts = [e.elts[0] if isinstance(e, ast.Tuple) else e for e in node.iter.elts]
                if all(isinstance(f, ast.Constant) and isinstance(f.value, str) for f in firsts):
                    return {f.value + arg.right.value for f in firsts}
        node = parents.get(node)
    return None


def engine_reasons():
    found, unresolved = set(), []
    for name in SERVED_GENERATORS:
        tree = _tree(name)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
            for node in ast.walk(cls):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "finish":
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        found.add(arg.value)
                    else:
                        resolved = _resolve_concat(node, parents)
                        if resolved is None:
                            unresolved.append((name, node.lineno))
                        else:
                            found |= resolved
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "reason"
                                                        for t in node.targets):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        found.add(node.value.value)
                if isinstance(node, ast.Call):
                    for kw in node.keywords:
                        if kw.arg == "reason" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                            found.add(kw.value.value)
    found.discard("eligible")
    return found, unresolved


def deck_rule_reasons():
    found = set()
    quality = _tree("deck_quality.py")
    card_rule = next(n for n in ast.walk(quality) if isinstance(n, ast.FunctionDef) and n.name == "card_rule")
    found |= {n.value.value for n in ast.walk(card_rule)
              if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}
    rules = _tree("deck_rules.py")
    reason = next(n for n in ast.walk(rules) if isinstance(n, ast.FunctionDef) and n.name == "reason")
    found |= {n.value.value for n in ast.walk(reason) if isinstance(n, ast.Assign)
              and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}
    return found


def private_labels():
    tree = _tree("trade_fast_deck.py")
    return {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call)
            and getattr(n.func, "attr", getattr(n.func, "id", None)) in ("_Rejected", "_GenerationRejection")
            and n.args and isinstance(n.args[0], ast.Constant)}


def test_every_engine_rejection_reason_is_in_the_catalog():
    reasons, unresolved = engine_reasons()
    assert not unresolved, f"finish(...) arguments the inventory cannot resolve: {unresolved}"
    reasons |= deck_rule_reasons()
    assert len(reasons) >= 29           # the walk itself found the engine (29 on 2026-11-11)
    missing = sorted(reasons - set(rc.BY_KEY))
    assert missing == [], f"engine reasons the rule catalog does not list: {missing}"


def test_no_catalog_reason_the_engine_no_longer_produces():
    reasons, _ = engine_reasons()
    reasons |= deck_rule_reasons()
    stale = sorted(rc.ENGINE_REASONS - reasons)
    assert stale == [], f"catalog rows the engine never records: {stale}"


def test_rules_first_private_labels_are_known_non_rules():
    assert private_labels() == NON_RULE_LABELS
    assert not NON_RULE_LABELS & set(rc.BY_KEY)


def test_the_fixable_reasons_the_generator_expands_are_the_page_searchs_copy():
    """trade_gen_bilateral.candidates names the reasons an extra piece can cure inline;
    trade_first_page._CURABLE repeats them. The waterfall's 'not worth adding a piece' row reads
    the page's copy, so the two must not drift."""
    tree = _tree("trade_gen_bilateral.py")
    found = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.NotIn)
                and isinstance(node.comparators[0], ast.Tuple)
                and getattr(node.left, "attr", None) == "reason"):
            found = tuple(e.value for e in node.comparators[0].elts)
    assert found is not None and set(found) == set(trade_first_page._CURABLE)
    assert all(rc.BY_KEY[key].stage == rc.BOTH_SIDES for key in found)


def test_rows_have_valid_shape_and_order():
    keys = [r.key for r in rc.RULES]
    assert len(keys) == len(set(keys))
    stage_index = [rc.STAGES.index(r.stage) for r in rc.RULES]
    assert stage_index == sorted(stage_index)        # stages appear in waterfall order
    for r in rc.RULES:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", r.key), r.key
        assert r.kind in rc.KINDS and r.protects in rc.PROTECTS, r.key
        assert ".py" in r.source and r.counted and r.setting, r.key
        assert isinstance(r.live, bool)
    assert [r.key for r in rc.waterfall_rules()] == [r.key for r in rc.RULES if r.kind in rc.WATERFALL_KINDS]
    assert {r["key"] for r in rc.as_rows()} == set(keys)


_IDENTIFIER = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b|\b[a-z]+[A-Z][A-Za-z]*\b|\w\(|\.py\b|\b\w+\.\w+\(")


@pytest.mark.parametrize("rule", rc.RULES, ids=lambda r: r.key)
def test_names_and_descriptions_are_plain_language(rule):
    assert 1 <= len(rule.name.split()) <= 5, rule.name
    assert rule.description.strip()
    sentences = [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", rule.description.strip()) if s]
    assert 1 <= len(sentences) <= 3, sentences
    for text in (rule.name, rule.description):
        assert not _IDENTIFIER.search(text), (rule.key, _IDENTIFIER.search(text).group())


def test_rules_with_thresholds_state_their_numbers():
    """The founder must be able to judge a threshold without reading code."""
    for key in ("market_floor", "market_overpay", "viewer_no_benefit", "breakup", "filler", "redundant",
                "previous_disposition", "decline_window", "decline_floor", "pool", "repeat_cap",
                "tanking_rb_without_long_term_exception", "tanking_favored_young_asset",
                "known_preference_harm", "likes_you_added"):
        assert re.search(r"\d", rc.BY_KEY[key].description), key


def test_the_lint_catches_a_code_name():
    assert _IDENTIFIER.search("Rejects when market_floor fails")
    assert _IDENTIFIER.search("see filter_deck(cards)")
    assert _IDENTIFIER.search("the weakerSupport term")
    assert not _IDENTIFIER.search("A piece worth under 450, or under a quarter of the best player.")
