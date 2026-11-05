"""Merge traps in backend/server.py: a duplicated block must fail CI.

Release-lead's #368 QA (P3): a resync of a long-lived branch with main can
silently auto-merge a second copy of a top-level block. With the S0 roster-
change block that left everything green while two handlers ran on every
roster change. Pinned here:
  * the S0 roster-change handler is registered exactly once;
  * server.py defines no top-level function or class name twice (a later
    definition silently replaces the earlier one), except the names in
    ALLOWED_REDEFINITIONS, each with its reason. Main has none today.
"""
import ast
import collections
from pathlib import Path

import backend.server as server
from backend import roster_snapshot

ALLOWED_REDEFINITIONS: dict[str, str] = {}


def test_the_roster_change_handler_is_registered_exactly_once():
    handlers = [h for h in roster_snapshot._roster_change_handlers
                if getattr(h, "__name__", None) == "_invalidate_league_trade_jobs_on_roster_change"
                and getattr(h, "__module__", None) == server.__name__]
    assert len(handlers) == 1, f"{len(handlers)} copies of S0's roster-change handler are registered"
    assert handlers[0] is server._invalidate_league_trade_jobs_on_roster_change


def test_server_py_defines_no_top_level_name_twice():
    tree = ast.parse(Path(server.__file__).read_text())
    counts = collections.Counter(node.name for node in tree.body
                                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                      ast.ClassDef)))
    duplicates = sorted(name for name, n in counts.items()
                        if n > 1 and name not in ALLOWED_REDEFINITIONS)
    assert not duplicates, f"defined more than once in server.py (a merge duplicate?): {duplicates}"


def test_feedback_and_signin_keep_one_trusted_proxy_hop_constant():
    """#430/main resync: the second constant would silently shadow policy."""
    tree = ast.parse(Path(server.__file__).read_text())
    definitions = [node for node in tree.body
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name)
                           and target.id == "_SIGNIN_TRUSTED_PROXY_HOPS"
                           for target in node.targets)]
    assert len(definitions) == 1


def test_feedback_and_signin_use_the_same_configured_proxy_hop(monkeypatch):
    """Both public paths read the shared policy, ignoring a spoofed left hop."""
    monkeypatch.setattr(server, "_SIGNIN_TRUSTED_PROXY_HOPS", 2)
    with server.app.test_request_context(
            headers={"X-Forwarded-For": "spoofed, client-at-proxy, nearest-proxy"},
            environ_base={"REMOTE_ADDR": "socket-peer"}):
        assert server._feedback_rate_key(None) == "ip:client-at-proxy"
        assert server._signin_limit_keys("mfl", "subject")[0][0] == "ip:client-at-proxy"
