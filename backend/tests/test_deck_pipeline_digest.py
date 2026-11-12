"""CI guard: server.py's deck-shaping code can't change without a deck pipeline bump.

server.py isn't in the engine code hash (that would cold every stored page on
every deploy), so a change to its deck layers reaches stored pages only through
the manual `DECK_PIPELINE_VERSION` bump (and, after 11-10, it's a MOD-M1 re-run
trigger). Pinned here, per models-eng's classification (2026-10-26):
  * `server.DECK_PIPELINE_PINS[DECK_PIPELINE_VERSION]` = the digest of the
    functions in `DECK_PIPELINE_FUNCTIONS` (their AST with docstrings
    stripped, so a comment, docstring or formatting edit doesn't trip it and
    a logic edit does) and of the constants in `DECK_PIPELINE_CONSTANTS` (by
    value);
  * the pins are append-only: FROZEN_PINS below is a copy of every row, so a
    version re-pinned in place (its stored pages would stay stamped current)
    fails;
  * the closure: every server.py function or literal module constant a listed
    function references is listed, a listed constant, or in
    `DECK_PIPELINE_IGNORED` with a reason, so a new helper can't slip past.

On a digest failure: bump DECK_PIPELINE_VERSION, add its row to
DECK_PIPELINE_PINS with `server._deck_pipeline_digest()` and copy that row into
FROZEN_PINS, and have models-eng review. On a closure failure: classify the
names it lists.
"""
import ast
import inspect
from pathlib import Path

import pytest

import backend.server as server

MESSAGE = "bump DECK_PIPELINE_VERSION and re-pin (models-eng reviews)"
CLASSIFY = "classify in DECK_PIPELINE_FUNCTIONS / _CONSTANTS / _IGNORED (models-eng reviews)"
LITERAL_CALLS = {"frozenset", "set", "tuple", "dict", "float", "int", "str", "list"}

# Every DECK_PIPELINE_PINS row ever pinned. Append-only: a bump copies its new
# row here; an existing row never changes.
FROZEN_PINS = {
    1: "38068a074677acaa",
    2: "9e79b6087f6e1a42",
    3: "97404fc8bab683f2",
    4: "864cf30974da20ea",
    5: "99d62fcaf7ad01ef",
    6: "d5176ae18c66d208",
    7: "facf9a9f34b7529a",
    8: "f7ed33e6ab94af03",
    9: "28d212cdc5c6cb05",
    10: "cdabd9935a58d51d",
    11: "8a3fa8db29d87e39",  # Evidence-bound bilateral v3 and private input capture.
    12: "3b5a7de53dd0081e",  # Frozen calibration suppression input seam; organic defaults preserved.
    13: "1939e93dc5fd7de5",  # Cooperative cancellation; current-job terms/order preserved.
    14: "c35ce67a4434a981",  # Owner searches enforce every explicit give-all pin.
    15: "1a34729ff2b291ac",  # D-212 trade_block: viewer list carried by the job; owner-context flag gate.
    16: "e155ed45d1a02a13",  # ADR-028: fast deck and shadow hooks in the owner generator call (flags trade.fast_deck*, default off); flags off: same call, terms and order unchanged.
    17: "a344340932da4f13",  # trade.fit_first_copy (default off): trade_card_to_dict adds fit_lines to bilateral cards whose proof supports a specific reason; flag off: no key, payload byte-identical.
    18: "560661f3c6d76b8d",  # Bilateral revision 4 (selector owner_bilateral_revision_4_enabled, default 0): presentment takes its version; the dark key is dropped from the request hash unless exactly 1; selector off: terms and order unchanged.
    19: "41b3e46c2f4c2e68",  # Fit block v3 (trade.fit_first_copy, default off): one league-wide rank context per job, stamped on owner cards; trade_card_to_dict adds fit_block; flag off: no context, no key, payload byte-identical.
    20: "4e8e4cbd886c9149",  # Partner activity (trade.partner_activity, default off; revision 4 only): the owner context carries the league's public completed-trade counts; flag off or revision 4 not selected: context, hash, terms and order unchanged.
    21: "6b0e0c0fe51fb2ef",  # Revised-offer cards (trade.next_move, default off): the user's declined Sleeper offers lead the organic owner deck, proven by the owner evaluator, and carry the job's fit context; flag off: no read, no card, terms and order unchanged.
    22: "6eb0e82ee1b62e47",  # ADR-030 rules-first construction (deck.rules_first); flag off: terms and order unchanged.
    23: "68e072f20220238b",  # trade.partner_outlook_projection: projection-based partner outlooks in the owner context and fit tag sources; flag off: unchanged.
    24: "0622c34be2da22ae",  # trade.fit_position_ranks (default off): no position-value walk and no league rank in the fit block; on: byte-identical to v22.
    25: "b00f8f62029606ed",  # Win-now season signal (trade.season_signal, default off; revision 5 selector default 0); flag off and selector 0: context, hash, terms, order and payload unchanged.
    26: "2d4aef7d5d0261fb",  # Projected slot value (picks.projected_slot_value, default off): owned next-draft firsts price by the original team's projected slot from the saved league forecast (_league_pick_projection hoisted beside _league_slot_order into _priced_pick_value and the label, which names the projected slot, and player_to_dict emits proj_slot / proj_name); flag off or weight 0: projection None, prices, labels, terms and order unchanged.
    27: "68bb3f499c837968",  # Keep is a hard rule (owner_untouchable_hard, default 1); knob 0: request hash, terms and order unchanged.
    28: "88322edc6a469414",  # Viewer label fit (season_viewer_label_fit, default 1; revision 5 only); knob 0 or revision 5 not selected: request hash, terms and order unchanged.
}
PINNED = server.DECK_PIPELINE_PINS.get(server.DECK_PIPELINE_VERSION)


def test_the_deck_pipeline_digest_is_pinned():
    if server._deck_pipeline_digest() != PINNED:
        pytest.fail(MESSAGE)


def test_no_pinned_version_ever_changes_its_digest():
    pins = server.DECK_PIPELINE_PINS
    changed = {v: (digest, pins.get(v)) for v, digest in FROZEN_PINS.items() if pins.get(v) != digest}
    assert not changed, (f"re-pinned or dropped in place (frozen, now): {changed}; "
                         "bump DECK_PIPELINE_VERSION and add a row instead")
    new = sorted(set(pins) - set(FROZEN_PINS))
    assert not new, f"copy the new pins {new} into FROZEN_PINS"
    assert server.DECK_PIPELINE_VERSION == max(pins), "DECK_PIPELINE_VERSION is the newest pin"


# ── The closure ─────────────────────────────────────────────────────────────

def _module_tables(tree):
    """server.py's module-level functions, and its literal constants: names
    assigned only literals (scalars, non-empty tuples/lists/sets/dicts of
    literals, frozenset(...)-style calls, arithmetic on them, or other literal
    constants). An empty container is state (a cache, a registry), not a
    constant."""
    funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assigned = {}
    for node in tree.body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        for target in targets:
            if isinstance(target, ast.Name) and node.value is not None:
                assigned.setdefault(target.id, []).append(node.value)
    literal = set()

    def is_literal(node):
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return all(is_literal(e) for e in node.elts)
        if isinstance(node, ast.Dict):
            return (all(k is not None and is_literal(k) for k in node.keys)
                    and all(is_literal(v) for v in node.values))
        if isinstance(node, ast.UnaryOp):
            return is_literal(node.operand)
        if isinstance(node, ast.BinOp):
            return is_literal(node.left) and is_literal(node.right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in LITERAL_CALLS:
            return not node.keywords and all(is_literal(a) for a in node.args)
        return isinstance(node, ast.Name) and node.id in literal

    def is_empty(node):
        if isinstance(node, ast.Dict):
            return not node.keys
        if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            return not node.elts
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in LITERAL_CALLS and not node.args and not node.keywords)

    changed = True
    while changed:
        changed = False
        for name, values in assigned.items():
            if (name not in literal and name not in funcs and all(map(is_literal, values))
                    and not any(map(is_empty, values))):
                literal.add(name)
                changed = True
    return funcs, literal


def _local_names(fn):
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node is not fn:
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    for node in ast.walk(fn):
        if isinstance(node, ast.Global):
            names.difference_update(node.names)
    return names


def _unclassified(source: str):
    """{name: {listed functions referencing it}} for every server.py function
    or literal constant a listed function references (an ast.Name load) that
    isn't listed, a listed constant, or ignored."""
    tree = ast.parse(source)
    funcs, literal = _module_tables(tree)
    listed, constants = set(server.DECK_PIPELINE_FUNCTIONS), set(server.DECK_PIPELINE_CONSTANTS)
    out = {}
    for name in server.DECK_PIPELINE_FUNCTIONS:
        local = _local_names(funcs[name])
        for node in ast.walk(funcs[name]):
            if not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)) or node.id in local:
                continue
            ref = node.id
            if ((ref in funcs and ref not in listed or ref in literal and ref not in constants)
                    and ref not in server.DECK_PIPELINE_IGNORED):
                out.setdefault(ref, set()).add(name)
    return out


SERVER_SOURCE = Path(server.__file__).read_text()


def test_every_name_the_pipeline_references_is_classified():
    missing = _unclassified(SERVER_SOURCE)
    if missing:
        pytest.fail(f"{sorted(missing)}: {CLASSIFY}")


def test_the_three_lists_are_consistent():
    tree = ast.parse(SERVER_SOURCE)
    funcs, literal = _module_tables(tree)
    functions, constants = server.DECK_PIPELINE_FUNCTIONS, server.DECK_PIPELINE_CONSTANTS
    assert len(set(functions)) == len(functions) and len(set(constants)) == len(constants)
    assert all(inspect.isfunction(getattr(server, name, None)) for name in functions)
    assert set(constants) <= literal, set(constants) - literal
    assert not (set(functions) | set(constants)) & set(server.DECK_PIPELINE_IGNORED)
    assert all(isinstance(reason, str) and reason for reason in server.DECK_PIPELINE_IGNORED.values())
    # Ignored names are real server.py names, not stale entries.
    assigned = {t.id for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
                if isinstance(t, ast.Name)}
    stale = set(server.DECK_PIPELINE_IGNORED) - set(funcs) - assigned
    assert not stale, stale


def test_a_new_unclassified_helper_fails_the_closure():
    source = SERVER_SOURCE.replace(
        "def _order_deck(", "def _brand_new_helper():\n    return 1\n\n\ndef _order_deck(", 1)
    order = inspect.getsource(server._order_deck)
    assert source.count(order) == 1
    patched = source.replace(order, order.rstrip("\n") + "\n    _brand_new_helper()\n", 1)
    assert _unclassified(patched) == {"_brand_new_helper": {"_order_deck"}}


# ── What moves the digest ───────────────────────────────────────────────────

def _digest_with(name, edit):
    """The digest with one listed function's source edited."""
    real = lambda fn: inspect.getsource(getattr(server, fn))
    return server._deck_pipeline_digest(
        source_of=lambda fn: edit(real(fn)) if fn == name else real(fn))


def test_comment_docstring_and_formatting_edits_keep_the_digest():
    def cosmetic(source):
        lines = source.splitlines()
        lines.insert(1, "    # a new comment")
        source = "\n".join(lines) + "\n"
        return source.replace('"""', '"""Reworded. ', 1).replace(", ", ",  ")
    assert _digest_with("_order_deck", cosmetic) == PINNED


def test_a_one_token_logic_edit_moves_the_digest():
    source = inspect.getsource(server._apply_deck_suppression)
    assert "max(declines)" in source
    assert _digest_with("_apply_deck_suppression",
                        lambda s: s.replace("max(declines)", "min(declines)", 1)) != PINNED


def test_a_constant_value_change_moves_the_digest():
    real = lambda name: getattr(server, name)
    moved = server._deck_pipeline_digest(
        value_of=lambda name: real(name) + 1 if name == "_DECK_MIN_CARDS" else real(name))
    assert moved != PINNED
    reordered = server._deck_pipeline_digest(
        value_of=lambda name: frozenset(sorted(real(name), reverse=True))
        if name == "_AUDITION_ESTABLISHED" else real(name))
    assert reordered == PINNED       # a set's order never matters
