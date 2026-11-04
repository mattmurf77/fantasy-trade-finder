"""No "beta" in the source strings of Win Now ``Unavailable`` messages (App Review 2.2).

``win_now_service.Unavailable(reason, message)`` carries a message the mobile
Win Now screen renders as-is (``WinNowScreen.tsx`` shows ``baseline.message``),
so the word "beta" in one reaches a shipping binary's screen.

What this pins: every ``backend/*.py`` and ``backend/**/*.py`` file outside
``backend/tests`` is parsed with ``ast``; for every call to ``Unavailable``
(a bare name or an attribute such as ``service.Unavailable``), no string
constant inside any of its arguments -- positional or keyword, including the
constant parts of an f-string -- matches ``\\bbeta\\b`` (case-insensitive),
either as written or with ``_`` read as a space. The second reading catches a
reason code like ``beta_only``: ``\\b`` treats ``_`` as a word character, yet
``Unavailable`` turns a message-less reason into the default message
("Beta only").

Honest limits: this pins source strings, not rendered output. It does not see
a message built outside the call (a variable, or a helper such as
``unsupported_slots_message``) or text assembled at runtime from non-matching
pieces. Server text sent through anything other than ``Unavailable`` is out of
scope. The positive control (at least 5 calls with a string argument)
keeps the scan from passing vacuously.
"""

import ast
import re
from pathlib import Path


BETA = re.compile(r"\bbeta\b", re.I)
BACKEND = Path(__file__).resolve().parents[1]
TESTS = BACKEND / "tests"


def _backend_sources():
    return sorted(p for p in BACKEND.rglob("*.py") if TESTS not in p.parents)


def _is_unavailable(call):
    fn = call.func
    return (isinstance(fn, ast.Name) and fn.id == "Unavailable") or (
        isinstance(fn, ast.Attribute) and fn.attr == "Unavailable"
    )


def _string_constants(call):
    """Every str constant inside the call's arguments (f-string parts included)."""
    args = list(call.args) + [kw.value for kw in call.keywords]
    for arg in args:
        for node in ast.walk(arg):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield node


def _scan():
    files = _backend_sources()
    calls_with_strings, hits = [], []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(BACKEND.parent).as_posix()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_unavailable(node)):
                continue
            strings = list(_string_constants(node))
            if strings:
                calls_with_strings.append(f"{rel}:{node.lineno}")
            for s in strings:
                if BETA.search(s.value) or BETA.search(s.value.replace("_", " ")):
                    hits.append(f"{rel}:{s.lineno} {s.value!r}")
    return files, calls_with_strings, hits


def test_no_unavailable_message_says_beta():
    _, _, hits = _scan()
    assert hits == [], "Unavailable(...) string mentions beta (App Review 2.2):\n" + "\n".join(hits)


def test_scan_is_not_vacuous():
    files, calls_with_strings, _ = _scan()
    assert any(p.name == "win_now_service.py" for p in files)
    assert len(calls_with_strings) >= 5, calls_with_strings
