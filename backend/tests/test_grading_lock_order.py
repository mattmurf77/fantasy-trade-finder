"""Calibration's grading writers take the session row before its cards.

answer_grading_card, fold_grading_cards and the retention prune
(_delete_old_grading_sessions) each touch grading_sessions and grading_cards in
one transaction. On Postgres, two of them taking the rows in opposite orders
deadlock: measured on Postgres 18 (2026-10-31, release-lead's #544 race test
plus a fold/answer one) before answer_grading_card locked its session first,
the prune against an answer and a fold against an answer both deadlocked in
both interleavings; after, none did. SQLite takes no row locks, so the order is
pinned on the source: in every function of backend/database.py that writes or
locks a card and touches the session table, the first write or lock is on the
session.
"""
import ast
import inspect
import textwrap

from backend import database as db

TABLES = {"grading_sessions_table": "session", "grading_cards_table": "card"}


def locking_ops(source: str) -> list[tuple[int, int, str, str]]:
    """(line, col, table kind, operation) for each write or lock on a grading
    table, in source order: update / delete / insert of one, `.insert()` on
    one, and `.with_for_update()` on a select naming one."""
    tree = ast.parse(textwrap.dedent(source))
    alias = dict(TABLES)
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and len(n.targets) == 1:
            t, v = n.targets[0], n.value
            pairs = (zip(t.elts, v.elts) if isinstance(t, ast.Tuple) and isinstance(v, ast.Tuple)
                     else [(t, v)])
            for target, value in pairs:
                if isinstance(target, ast.Name) and isinstance(value, ast.Name) and value.id in alias:
                    alias[target.id] = alias[value.id]

    def kind(node):
        return alias.get(node.id) if isinstance(node, ast.Name) else None

    ops = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        if name in ("update", "delete", "insert") and n.args and kind(n.args[0]):
            ops.append((n.lineno, n.col_offset, kind(n.args[0]), name))
        elif name == "insert" and isinstance(f, ast.Attribute) and kind(f.value):
            ops.append((n.lineno, n.col_offset, kind(f.value), "insert"))
        elif name == "with_for_update" and isinstance(f, ast.Attribute):
            kinds = sorted({kind(x) for x in ast.walk(f.value) if kind(x)})
            ops.append((n.lineno, n.col_offset, "+".join(kinds), "for update"))
    return sorted(ops)


def _grading_writers():
    """Every function in database.py that writes or locks a grading card and
    also touches the session table."""
    out = {}
    for name, fn in inspect.getmembers(db, inspect.isfunction):
        if fn.__module__ != db.__name__:
            continue
        ops = locking_ops(inspect.getsource(fn))
        if any(k == "card" for _l, _c, k, _o in ops) and any("session" in k for _l, _c, k, _o in ops):
            out[name] = ops
    return out


def test_every_grading_writer_takes_the_session_first():
    writers = _grading_writers()
    # The ones known today (a new one is covered by the rule below too).
    assert {"insert_grading_session", "finish_grading_session_build", "fold_grading_cards",
            "answer_grading_card", "_delete_old_grading_sessions"} <= set(writers)
    wrong = {name: ops[0] for name, ops in writers.items() if ops[0][2] != "session"}
    assert not wrong, f"takes a card before its session (deadlocks on Postgres): {wrong}"


def test_the_answer_locks_its_session_for_update_before_the_card():
    ops = locking_ops(inspect.getsource(db.answer_grading_card))
    assert ops[0][2:] == ("session", "for update")
    assert [o for _l, _c, _k, o in ops].index("update") > 0


def test_an_answer_to_a_session_already_gone_is_not_found(monkeypatch):
    """The prune took the session between the answer's read and its lock:
    the answer finds nothing to lock and returns None (the route's 404)."""
    from sqlalchemy import create_engine, event, insert, select
    eng = create_engine("sqlite:///:memory:")
    db.metadata.create_all(eng)
    monkeypatch.setattr(db, "engine", eng)
    gs, gc = db.grading_sessions_table, db.grading_cards_table
    with eng.begin() as c:
        c.execute(insert(gs).values(session_id="s", user_id="u1", league_id="lg", status="open",
                                    seed="1", created_at="2026-01-01T00:00:00+00:00",
                                    counts_json="{}", source_json="{}"))
        c.execute(insert(gc).values(card_id="c", session_id="s", user_id="u1", position=1,
                                    arms_json="{}", trade_json="{}"))
    seen = []

    def gone(conn, cursor, statement, params, context, many):
        # The status read under the lock: the session is deleted just before it.
        s = " ".join(statement.split()).upper()
        if s.startswith("SELECT GRADING_SESSIONS.STATUS") and not seen:
            seen.append(1)
            cursor.execute("DELETE FROM grading_sessions WHERE session_id = 's'")
    event.listen(eng, "before_cursor_execute", gone)
    try:
        got = db.answer_grading_card("c", "u1", grade=4, skipped=False, tags_json="[]",
                                     now="2026-10-31T00:00:00+00:00")
    finally:
        event.remove(eng, "before_cursor_execute", gone)
    assert seen and got is None
    with eng.connect() as c:
        assert c.execute(select(gc.c.grade).where(gc.c.card_id == "c")).scalar() is None
