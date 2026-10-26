"""#406 ↔ #370 pin (models-lead condition 2(a)): the three spellings of the
Calibration-refresh deck_source must agree.

eval.data excludes a deck whose cards carry deck_source CALIBRATION_REFRESH_SOURCE;
database._CALIBRATION_REFRESH_MARKERS is the receipts queue's LIKE match on the
features_json dump, in both JSON spellings; server.py stamps it (the job's
`source`, which becomes deck_source) where Calibration pre-generates its targets,
and S4's guards compare a job's source against it. A rename in any one place alone
would silently let refresh decks back into Trades, receipts or eval."""
import ast
import pathlib

from backend import database
from backend.eval import data as eval_data

SERVER = pathlib.Path(database.__file__).with_name("server.py")


def test_every_receipts_marker_names_evals_refresh_source():
    source = eval_data.CALIBRATION_REFRESH_SOURCE
    assert source == "grading_refresh"
    assert len(database._CALIBRATION_REFRESH_MARKERS) == 2
    for marker in database._CALIBRATION_REFRESH_MARKERS:
        assert f'"{source}"' in marker and '"deck_source"' in marker


def test_both_json_spellings_are_matched():
    source = eval_data.CALIBRATION_REFRESH_SOURCE
    assert set(database._CALIBRATION_REFRESH_MARKERS) == {
        f'"deck_source": "{source}"', f'"deck_source":"{source}"'}


def _server_tree():
    return ast.parse(SERVER.read_text())


def test_the_server_stamps_evals_refresh_source_where_calibration_pregenerates():
    """The stamp: _pregenerate_grading_targets builds each target's deck with
    _replenish_deck_for(..., source=<the refresh source>)."""
    fn = next(n for n in _server_tree().body
              if isinstance(n, ast.FunctionDef) and n.name == "_pregenerate_grading_targets")
    stamps = [kw.value.value for call in ast.walk(fn) if isinstance(call, ast.Call)
              and getattr(call.func, "id", None) == "_replenish_deck_for"
              for kw in call.keywords if kw.arg == "source" and isinstance(kw.value, ast.Constant)]
    assert stamps == [eval_data.CALIBRATION_REFRESH_SOURCE]


def _source_comparison_literals():
    """Every string literal a `source` / `job_source` value is compared against
    (==, !=, in, not in, including tuple members) anywhere in server.py."""
    def is_source(node):
        return isinstance(node, ast.Name) and node.id in ("source", "job_source")
    out = []
    for node in ast.walk(_server_tree()):
        if isinstance(node, ast.Compare) and is_source(node.left):
            for comp in node.comparators:
                items = comp.elts if isinstance(comp, (ast.Tuple, ast.List, ast.Set)) else [comp]
                out += [i.value for i in items if isinstance(i, ast.Constant) and isinstance(i.value, str)]
    return out


def test_every_server_guard_on_the_refresh_source_uses_evals_spelling():
    """S4's guards (no trades_generated, no trade_impressions, never pinned under
    the Trades key, never prepared-adopted) all compare against the same string."""
    refresh = [lit for lit in _source_comparison_literals() if "refresh" in lit]
    assert len(refresh) >= 4, refresh
    assert set(refresh) == {eval_data.CALIBRATION_REFRESH_SOURCE}
