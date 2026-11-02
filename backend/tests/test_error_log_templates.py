"""Every error-level log template in backend/ and scripts/ is a constant.

backend/error_alerts.py sends a log record's template (record.msg) to Sentry
when the logger is one of ours, with every param [Filtered] (legal R28.23;
docs/plans/server-error-alerts/scope.md). That is safe only while each
template is a fixed string: log.error(f"... {username}") puts the value in
the template. This guard is pure AST and needs no SDK, so it runs whether or
not sentry-sdk is installed (it was test_error_alerts.py (i), which skips
without the SDK).

Scanned: every .error / .exception / .critical / .fatal call, and every
.log(level, ...) call, on any receiver except the known non-loggers
(_NOT_LOGGERS: argparse's `ap` / `parser`, `math`, and flip_read's
ArgumentParser subclass calling `super()`). So a chained
logging.getLogger(...).error(...) and a logger alias without "log" in its
name are scanned; a new non-logger receiver fails here until it is added.
scripts/ is scanned too: a script that logs on "trade_finder" or backend.*
sends its templates when it runs with SENTRY_DSN set.

Not followed: getattr(log, "error")(...). There the runtime layers hold:
error_alerts filters a non-str record.msg (log.error(exc)), and the pattern
scrub runs over every template.

Sabotage record (each applied, observed red, restored green):
  2026-10-31  one f-string log.error added to server.py            -> RED
  2026-10-31  logging.getLogger(__name__).error(f"…") added to       -> RED
              server.py (missed by the old "log"-named receiver rule)
"""
import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_ERROR_METHODS = {"error", "exception", "critical", "fatal"}
_NOT_LOGGERS = {"ap", "parser", "math", "super()"}


def _bound_once_to_a_str(scope, name, parents):
    """Whether `name` is bound exactly once in `scope` (any store: assignment,
    loop, with, unpacking), by `name = "<str constant>"`, and isn't a parameter."""
    if not isinstance(scope, ast.Module) and name in {a.arg for a in ast.walk(scope.args)
                                                      if isinstance(a, ast.arg)}:
        return False
    stores = [n for n in ast.walk(scope)
              if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store)]
    if len(stores) != 1:
        return False
    assign = parents.get(stores[0])
    return (isinstance(assign, ast.Assign) and len(assign.targets) == 1
            and assign.targets[0] is stores[0] and isinstance(assign.value, ast.Constant)
            and isinstance(assign.value.value, str))


def _template_violations(source):
    """(scanned, [(line, call)]): every error/exception/critical/fatal call, and
    every .log(level, …) call, on any receiver but _NOT_LOGGERS, whose template
    is not a str constant, or a name bound once, in its function, to one."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    scanned, bad = 0, []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if ast.unparse(node.func.value) in _NOT_LOGGERS:
            continue
        if node.func.attr in _ERROR_METHODS:
            index = 0
        elif node.func.attr == "log":
            index = 1
        else:
            continue
        scanned += 1
        arg = node.args[index] if len(node.args) > index else None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            continue
        if isinstance(arg, ast.Name):
            scope = parents.get(node)
            while scope is not None and not isinstance(
                    scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
                scope = parents.get(scope)
            if scope is not None and _bound_once_to_a_str(scope, arg.id, parents):
                continue
        bad.append((node.lineno, ast.unparse(node)[:120]))
    return scanned, bad


@pytest.mark.parametrize("source, ok", [
    ('log.error("x %s", a)', True),
    ('log.exception("a " "b %s", a)', True),            # implicit concatenation: a constant
    ('def f(a):\n    t = ("a %s "\n         "b")\n    log.error(t, a)', True),
    ('log.log(logging.ERROR, "x %s", a)', True),
    ('L.error("x %s", a)', True),
    ('log.error(f"x {a}")', False),
    ('logger.exception("x %s" % a)', False),
    ('self.log.critical("x {}".format(a))', False),
    ('logging.error("x " + a)', False),
    ('logging.fatal(f"x {a}")', False),
    ('log.error(str(e))', False),
    ('log.error(e)', False),
    ('log.log(level, f"x {a}")', False),
    ('logging.getLogger(__name__).error(f"x {a}")', False),
    ('L.exception(f"x {a}")', False),
    ('def f(a, b):\n    t = "x"\n    if b:\n        t = a\n    log.error(t)', False),
    ('def f(rows):\n    t = "x"\n    for t in rows:\n        log.error(t)', False),
    ('def f(t):\n    log.error(t)', False),
])
def test_template_guard_detector(source, ok):
    scanned, bad = _template_violations(source)
    assert scanned == 1 and (bad == []) is ok


@pytest.mark.parametrize("source", [
    'parser.error(f"bad {a}")', 'ap.error(f"bad {a}")', 'math.log(x)',
    'super().error(message)',
])
def test_template_guard_skips_non_loggers(source):
    assert _template_violations(source) == (0, [])


def test_every_error_log_template_is_a_constant():
    scanned, bad = 0, []
    for top in ("backend", "scripts"):
        for path in sorted((REPO / top).rglob("*.py")):
            if "tests" in path.relative_to(REPO / top).parts:
                continue
            n, violations = _template_violations(path.read_text())
            scanned += n
            bad += [f"{path.relative_to(REPO)}:{line} {call}" for line, call in violations]
    assert scanned >= 170, scanned                       # the scan sees the call sites
    assert bad == [], "error-level log templates must be constants:\n" + "\n".join(bad)
