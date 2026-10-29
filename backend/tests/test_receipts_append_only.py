"""T-10: the receipts tables are append-only (HLD D-3; docs/plans/receipts/LLD.md §7).

Rebuilt on the syntax tree after release-lead's #544 QA (P1-1): the old
line-regex over two files let 21 of 27 injected writes through. Every non-test
Python file under backend/ and scripts/ is parsed. In each function (and at
module level) the names bound to a receipts table are followed, through
assignments, annotations, walruses, tuple unpacking, loops and comprehensions,
`.alias()`, `metadata.tables[...]` and `getattr`. A finding is:

- W: `delete(t)` / `update(t)` of a receipts table, `t.delete()` / `t.update()`,
  an upsert (`on_conflict_do_update`, `on_duplicate_key_update`) or an
  `OR REPLACE` prefix on a statement built from one;
- S: a SQL string (its static parts joined, f-strings and `+` resolved, case
  and whitespace ignored) that deletes from, updates, replaces into, truncates,
  drops or alters a receipts table, or upserts into one;
- N: a receipts table's bare name (or `<name>_table`), which is how a dynamic
  lookup reaches a table, outside the sites in NAME_SITES;
- P: a reference to the retention delete outside its one caller chain.

The one sanctioned write is legal's 365-day cap (R28.20 (iii), head-eng
2026-10-29): `_delete_deck` deletes a deck's grades with the deck, and only its
two statements in SANCTIONED_WRITES are allowed. `_delete_deck` is referenced
only by `purge_deck_evidence`, which is referenced only by the cleanup tick's
`server._prune_deck_evidence`, never with `now=`. Account deletion reaches
`receipts_grades` through accounts' `_ADDITIONAL_PRIVATE_TABLES`.

The residual: a table reached only through a value computed at run time across
statements (a name built in a variable, then looked up) isn't resolved.
"""
import ast
import re
import warnings
from functools import lru_cache
from pathlib import Path

import pytest

from backend import database as db

REPO = Path(__file__).resolve().parents[2]
TABLES = frozenset(t for t in db.metadata.tables if t.startswith("receipts_"))
REF_NAMES = frozenset(f"{t}_table" for t in TABLES)

SANCTIONED_WRITES = frozenset({
    ("backend/database.py", "_delete_deck",
     "delete(g).where(g.c.impression_id.in_(contract_ids[k:k + 500]))"),
    ("backend/database.py", "_delete_deck",
     "delete(g).where(g.c.impression_id.in_(row_ids))"),
})
NAME_SITES = frozenset({
    ("backend/database.py", "_delete_deck"),                          # its count's label
    ("backend/accounts.py", "<module>:_ADDITIONAL_PRIVATE_TABLES"),   # account deletion
})
PINNED = {
    "_delete_deck": frozenset({("backend/database.py", "purge_deck_evidence")}),
    "purge_deck_evidence": frozenset({("backend/server.py", "_prune_deck_evidence")}),
}
SQL_WRITE = re.compile(
    r"\b(?:delete\s+from|update|truncate(?:\s+table)?|replace\s+into"
    r"|insert\s+or\s+replace\s+into|drop\s+table(?:\s+if\s+exists)?|alter\s+table)"
    r"\s+[\"`\[]?(?:\w+\.)?receipts_\w+")
SQL_UPSERT = re.compile(
    r"\binsert\s+into\s+[\"`\[]?(?:\w+\.)?receipts_\w+.*\bon\s+(?:conflict|duplicate\s+key)\b.*\bupdate\b")
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _files():
    for base in ("backend", "scripts"):
        for path in sorted((REPO / base).rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            if not rel.startswith("backend/tests/"):
                yield rel, path.read_text()


class Scan:
    """One file's findings, and the sanctioned writes and pinned calls it saw."""

    def __init__(self, rel: str, source: str):
        self.rel, self.findings = rel, []
        self.sanctioned, self.pinned_calls = set(), []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)   # a repo file's "\ " escape
            tree = ast.parse(source)
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                child._t10_parent = node
        self.imports = {a.asname or a.name: a.name for n in ast.walk(tree)
                        if isinstance(n, ast.ImportFrom) for a in n.names}
        self._scope(tree, "<module>", set(), set(), {})

    # ── scopes and bindings ──────────────────────────────────────────────
    @staticmethod
    def _own(node):
        """The nodes of `node`'s scope, not descending into nested scopes."""
        stack = list(ast.iter_child_nodes(node))
        while stack:
            n = stack.pop()
            yield n
            if not isinstance(n, _SCOPES):
                stack.extend(ast.iter_child_nodes(n))

    def _scope(self, node, qual, taint, ctaint, lits):
        own = list(self._own(node))
        taint, ctaint, lits = set(taint), set(ctaint), dict(lits)
        for n in own:
            if (isinstance(n, ast.Assign) and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name) and isinstance(n.value, (ast.Tuple, ast.List))):
                lits[n.targets[0].id] = n.value
        changed = True
        while changed:
            changed = False
            for n in own:
                for target, value in self._pairs(n, lits, taint, ctaint):
                    for name in self._bind(target, value, taint, ctaint):
                        if name not in taint:
                            taint.add(name)
                            changed = True
                    if self._contains_ref(value, taint, ctaint):
                        for name in self._names(target):
                            if name not in ctaint:
                                ctaint.add(name)
                                changed = True
        for n in own:
            self._check(n, qual, taint, ctaint)
        for n in own:
            if isinstance(n, _SCOPES):
                name = getattr(n, "name", "<lambda>")
                self._scope(n, name if qual == "<module>" else f"{qual}.{name}", taint, ctaint, lits)

    def _pairs(self, n, lits, taint, ctaint):
        if isinstance(n, ast.Assign):
            return [(t, n.value) for t in n.targets]
        if isinstance(n, (ast.AnnAssign, ast.AugAssign)) and n.value is not None:
            return [(n.target, n.value)]
        if isinstance(n, ast.NamedExpr):
            return [(n.target, n.value)]
        if isinstance(n, ast.withitem) and n.optional_vars is not None:
            return [(n.optional_vars, n.context_expr)]
        if isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            it = n.iter
            if isinstance(it, ast.Name) and it.id in lits:
                it = lits[it.id]
            if isinstance(it, (ast.Tuple, ast.List, ast.Set)):
                return [(n.target, e) for e in it.elts]
            return [(n.target, it)] if self._contains_ref(it, taint, ctaint) else []
        return []

    @staticmethod
    def _names(target):
        return [x.id for x in ast.walk(target) if isinstance(x, ast.Name)]

    def _bind(self, target, value, taint, ctaint):
        if isinstance(target, ast.Starred):
            target = target.value
        if isinstance(target, ast.Name):
            return [target.id] if self._is_ref(value, taint) else []
        if isinstance(target, (ast.Tuple, ast.List)):
            if (isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts)
                    and not any(isinstance(e, ast.Starred) for e in target.elts + value.elts)):
                return [x for t, v in zip(target.elts, value.elts)
                        for x in self._bind(t, v, taint, ctaint)]
            if self._contains_ref(value, taint, set()):
                return self._names(target)          # can't pair them up: all of them
        return []

    # ── what is a receipts table ─────────────────────────────────────────
    @staticmethod
    def _tables_lookup(node):
        return (isinstance(node, ast.Attribute) and node.attr == "tables") or (
            isinstance(node, ast.Name) and node.id == "tables")

    def _is_ref(self, node, taint):
        if isinstance(node, ast.Name):
            return node.id in REF_NAMES or node.id in taint
        if isinstance(node, ast.Attribute):
            return node.attr in REF_NAMES
        if isinstance(node, ast.Subscript):
            return self._tables_lookup(node.value) and self._render(node.slice, taint) in TABLES
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
            first = node.args[0] if node.args else None
            if isinstance(f, ast.Attribute) and name in ("alias", "_clone", "tablesample") \
                    and self._is_ref(f.value, taint):
                return True
            if name in ("aliased", "alias") and first is not None and self._is_ref(first, taint):
                return True
            if name == "getattr" and len(node.args) >= 2:
                return self._render(node.args[1], taint) in REF_NAMES
            if name == "get" and isinstance(f, ast.Attribute) and self._tables_lookup(f.value):
                return first is not None and self._render(first, taint) in TABLES
            if name == "Table" and first is not None:
                return self._render(first, taint) in TABLES
            return False
        if isinstance(node, ast.IfExp):
            return self._is_ref(node.body, taint) or self._is_ref(node.orelse, taint)
        if isinstance(node, ast.BoolOp):
            return any(self._is_ref(v, taint) for v in node.values)
        if isinstance(node, ast.NamedExpr):
            return self._is_ref(node.value, taint)
        return False

    def _contains_ref(self, node, taint, ctaint):
        return any(self._is_ref(x, taint) or (isinstance(x, ast.Name) and x.id in ctaint)
                   for x in ast.walk(node))

    # ── strings ──────────────────────────────────────────────────────────
    def _render(self, node, taint):
        """A string expression's static text: f-string parts and `+` joined, a
        receipts table's `.name` resolved, anything else as "{?}"."""
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) else None
        if isinstance(node, ast.JoinedStr):
            out = []
            for part in node.values:
                if isinstance(part, ast.Constant):
                    out.append(str(part.value))
                else:
                    out.append(self._render_value(part.value, taint))
            return "".join(out)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = self._render(node.left, taint), self._render(node.right, taint)
            if left is None and right is None:
                return None
            return (left if left is not None else "{?}") + (right if right is not None else "{?}")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            left = self._render(node.left, taint)
            return None if left is None else left.replace(
                "%s", self._render_value(node.right, taint))
        return None

    def _render_value(self, node, taint):
        if isinstance(node, ast.Attribute) and node.attr in ("name", "fullname") \
                and self._is_ref(node.value, taint):
            return "receipts_table"
        text = self._render(node, taint)
        return text if text is not None else "{?}"

    # ── the checks ───────────────────────────────────────────────────────
    def _flag(self, rule, node, why):
        self.findings.append(f"{self.rel}:{node.lineno}: {rule}: {why}")

    @staticmethod
    def _parent(node):
        return getattr(node, "_t10_parent", None)

    def _chain_top(self, node):
        while True:
            attr = self._parent(node)
            call = self._parent(attr) if attr is not None else None
            if isinstance(attr, ast.Attribute) and attr.value is node \
                    and isinstance(call, ast.Call) and call.func is attr:
                node = call
            else:
                return node

    def _site(self, node, qual):
        if qual != "<module>":
            return qual
        while self._parent(node) is not None and not isinstance(self._parent(node), ast.Module):
            node = self._parent(node)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(target, ast.Name):
                return f"<module>:{target.id}"
        return "<module>"

    def _fname(self, func):
        if isinstance(func, ast.Attribute):
            return func.attr
        if isinstance(func, ast.Name):
            return self.imports.get(func.id, func.id)
        return None

    def _check(self, n, qual, taint, ctaint):
        if isinstance(n, ast.Call):
            f, fname = n.func, self._fname(n.func)
            hit = False
            if fname in ("delete", "update"):
                targets = n.args[:1] + [k.value for k in n.keywords if k.arg == "table"]
                hit = any(self._is_ref(t, taint) for t in targets) or (
                    isinstance(f, ast.Attribute) and self._is_ref(f.value, taint))
            elif fname in ("on_conflict_do_update", "on_duplicate_key_update"):
                hit = isinstance(f, ast.Attribute) and self._contains_ref(f.value, taint, ctaint)
            elif fname == "prefix_with":
                hit = (any("replace" in (self._render(a, taint) or "").lower() for a in n.args)
                       and isinstance(f, ast.Attribute) and self._contains_ref(f.value, taint, ctaint))
            if hit:
                key = (self.rel, qual, ast.unparse(self._chain_top(n)))
                if key in SANCTIONED_WRITES:
                    self.sanctioned.add(key)
                else:
                    self._flag("W", n, f"a write to a receipts table in {qual}: {key[2][:120]}")
            if fname == "purge_deck_evidence" and any(k.arg in ("now", None) for k in n.keywords):
                self._flag("P", n, "purge_deck_evidence called with now= or **kwargs")
            if fname in PINNED:
                self.pinned_calls.append((fname, self.rel, qual))
        if isinstance(n, (ast.Name, ast.Attribute)):
            ident = n.id if isinstance(n, ast.Name) else n.attr
            if ident in PINNED and (self.rel, qual) not in PINNED[ident]:
                self._flag("P", n, f"{ident} referenced from {qual}")
        if isinstance(n, ast.alias) and n.name in PINNED and (self.rel, qual) not in PINNED[n.name]:
            self._flag("P", self._parent(n), f"{n.name} imported in {qual}")
        if isinstance(n, (ast.Constant, ast.JoinedStr, ast.BinOp)):
            parent = self._parent(n)
            if isinstance(parent, (ast.JoinedStr, ast.FormattedValue)) or (
                    isinstance(parent, ast.BinOp) and isinstance(parent.op, (ast.Add, ast.Mod))
                    and self._render(parent, taint) is not None):
                return                                  # part of a larger string
            if isinstance(parent, ast.Expr):
                return                                  # a docstring or bare string
            text = self._render(n, taint)
            if text is None:
                return
            sql = " ".join(text.lower().split())
            if SQL_WRITE.search(sql) or SQL_UPSERT.search(sql):
                self._flag("S", n, f"SQL writing a receipts table: {sql[:120]}")
            if text.strip() in TABLES | REF_NAMES | set(PINNED):
                is_table_def = (isinstance(parent, ast.Call) and self._fname(parent.func) == "Table"
                                and parent.args and parent.args[0] is n)
                if not is_table_def and (self.rel, self._site(n, qual)) not in NAME_SITES:
                    self._flag("N", n, f"the name {text.strip()!r} as a string in {qual}")


@lru_cache(maxsize=None)
def _clean_scans() -> dict:
    return {rel: Scan(rel, src) for rel, src in _files()}


def scan_all(overrides: dict | None = None) -> list[Scan]:
    """Every file's scan: the tree's, with `overrides` ({path: source})
    scanned in their place."""
    scans = dict(_clean_scans())
    scans.update({rel: Scan(rel, src) for rel, src in (overrides or {}).items()})
    return [scans[rel] for rel in sorted(scans)]


def test_t10_no_update_or_delete_path_exists_for_receipts_tables():
    """No write to a receipts table anywhere in backend/ or scripts/ but the
    retention cap's two sanctioned statements; the retention delete reached
    only through its one caller chain, never with `now=`."""
    scans = scan_all()
    findings = [f for s in scans for f in s.findings]
    assert findings == [], (
        "a write path against a receipts table exists:\n" + "\n".join(findings)
        + "\nCorrections are a grader_version bump plus a regrade, with the old rows "
          "retained. Editing or deleting a grade destroys the audit trail that makes "
          "the preregistration claim checkable.")
    # The sanctioned writes and the caller chain are really there, so the
    # allowlist can't go stale and silently allow a different statement.
    assert set().union(*(s.sanctioned for s in scans)) == SANCTIONED_WRITES
    calls = [c for s in scans for c in s.pinned_calls]
    assert sorted(calls) == [("_delete_deck", "backend/database.py", "purge_deck_evidence"),
                             ("purge_deck_evidence", "backend/server.py", "_prune_deck_evidence")]


def test_t10_scans_every_backend_and_scripts_file():
    rels = {rel for rel, _src in _files()}
    for rel in ("backend/database.py", "backend/receipts_service.py", "backend/accounts.py",
                "backend/server.py", "backend/eval/redaction.py", "scripts/purge_entry_users.py"):
        assert rel in rels
    assert not any(r.startswith("backend/tests/") for r in rels)
    assert TABLES == {"receipts_grades", "receipts_grade_runs"}


# ── release-lead's #544 QA matrix, as unit tests of the scanner ─────────────
# Each case injects valid Python into an in-memory copy of a real file; T-10
# must find it. END appends to the file; any other anchor is replaced by the
# code followed by the anchor (QA's t10_matrix.py, 27 cases, plus more).

D, R, S = "backend/database.py", "backend/receipts_service.py", "backend/server.py"
END = "<END>"
AFTER_DD = "\n\ndef _delete_old_trade_impressions("
IN_DD = '            ("deck_evidence_packs", delete(p).where(p.c.run_id == deck_job_id))):'
CASES = {
    "alias_fn_delete": (D, END, "def _qa(conn):\n    g = receipts_grades_table\n"
                                "    conn.execute(delete(g).where(g.c.id == 1))\n"),
    "tuple_alias_update": (D, END, "def _qa(conn):\n    o, g = deck_outcomes_table, receipts_grades_table\n"
                                   "    conn.execute(update(g).values(status='graded'))\n"),
    "table_method_delete": (D, END, "def _qa(conn):\n    conn.execute(receipts_grades_table.delete())\n"),
    "upper_text_sql": (D, END, "def _qa(conn):\n"
                               "    conn.execute(text('DELETE FROM receipts_grades WHERE id = 1'))\n"),
    "direct_fn_delete": (D, END, "def _qa(conn):\n    conn.execute(delete(receipts_grades_table)"
                                 ".where(receipts_grades_table.c.id == 1))\n"),
    "direct_fn_update": (D, END, "def _qa(conn):\n"
                                 "    conn.execute(update(receipts_grades_table).values(status='graded'))\n"),
    "direct_fn_delete_runs": (D, END, "def _qa(conn):\n    conn.execute(delete(receipts_grade_runs_table))\n"),
    "alias_method_delete": (D, END, "def _qa(conn):\n    g = receipts_grades_table\n"
                                    "    conn.execute(g.delete().where(g.c.id == 1))\n"),
    "alias_multiline": (D, END, "def _qa(conn):\n    g = receipts_grades_table\n"
                                "    conn.execute(delete(\n        g).where(g.c.id == 1))\n"),
    "annotated_alias": (D, END, "def _qa(conn):\n    g: Table = receipts_grades_table\n"
                                "    conn.execute(delete(g))\n"),
    "metadata_lookup_alias": (D, END, "def _qa(conn):\n    g = metadata.tables['receipts_grades']\n"
                                      "    conn.execute(delete(g))\n"),
    "fresh_annotated_alias": (D, END, "def _qa(conn):\n    rg: Table = receipts_grades_table\n"
                                      "    conn.execute(delete(rg))\n"),
    "fresh_metadata_alias": (D, END, "def _qa(conn):\n    rg = metadata.tables['receipts_grades']\n"
                                     "    conn.execute(delete(rg))\n"),
    "fresh_alias_method": (D, END, "def _qa(conn):\n    rg = receipts_grades_table\n"
                                   "    conn.execute(rg.update().values(status='x'))\n"),
    "inside_delete_deck_correction": (D, IN_DD, "            ('receipts_grades', delete(g).where("
                                                "g.c.grader_version == 'receipts-1')),"),
    "lower_text_sql": (D, END, "def _qa(conn):\n"
                               "    conn.execute(text('delete from receipts_grades where id = 1'))\n"),
    "fstring_sql": (D, END, "def _qa(conn):\n    conn.execute(text(f'DELETE FROM "
                            "{receipts_grades_table.name} WHERE id = 1'))\n"),
    "split_sql": (D, END, "def _qa(conn):\n    conn.execute(text('DELETE FROM '\n"
                          "                      'receipts_grades WHERE id = 1'))\n"),
    "upsert_do_update": (D, END, "def _qa(conn, row):\n"
                                 "    from sqlalchemy.dialects.sqlite import insert as _i\n"
                                 "    conn.execute(_i(receipts_grades_table).values(**row).on_conflict_do_update(\n"
                                 "        index_elements=['impression_id'], set_={'status': 'x'}))\n"),
    "insert_or_replace": (D, END, "def _qa(conn, row):\n    conn.execute(receipts_grades_table.insert()"
                                  ".prefix_with('OR REPLACE').values(**row))\n"),
    "reuse_delete_deck": (D, END, "def regrade_reset(deck_job_id, card_count):\n"
                                  "    with engine.begin() as conn:\n"
                                  "        _delete_deck(conn, deck_job_id, 'u', 'lg', card_count)\n"),
    "reuse_purge_future_now": (R, END, "def _qa_reset_all():\n    db.purge_deck_evidence("
                                       "days=56, now=datetime(2100, 1, 1, tzinfo=timezone.utc))\n"),
    "module_level_after_delete_deck": (D, AFTER_DD, "\n\n_QA_WIPE = delete(g := receipts_grades_table)\n"
                                                    "_QA_WIPE2 = delete(g)\n"),
    "class_after_delete_deck": (D, AFTER_DD, "\n\nclass _QaGrades:\n    def wipe(self, conn):\n"
                                             "        g = receipts_grades_table\n"
                                             "        conn.execute(delete(g))\n"),
    "service_db_attr_delete": (R, END, "def _qa():\n    from sqlalchemy import delete as _d\n"
                                       "    with db.engine.begin() as conn:\n"
                                       "        conn.execute(_d(db.receipts_grades_table))\n"),
    "service_alias_delete": (R, END, "def _qa():\n    from sqlalchemy import delete\n"
                                     "    g = db.receipts_grades_table\n    with db.engine.begin() as conn:\n"
                                     "        conn.execute(delete(g))\n"),
    "other_module_server": (S, END, "def _qa():\n    from .database import engine as _e\n"
                                    "    with _e.begin() as conn:\n"
                                    "        conn.execute(text('DELETE FROM receipts_grades'))\n"),
    # beyond QA's matrix
    "loop_over_tables": (D, END, "def _qa(conn):\n    for t in (deck_outcomes_table, receipts_grades_table):\n"
                                 "        conn.execute(delete(t))\n"),
    "comprehension_pairs": (D, END, "def _qa(conn):\n    for _n, t in (('a', deck_outcomes_table), "
                                    "('b', receipts_grade_runs_table)):\n        conn.execute(t.delete())\n"),
    "module_tuple_then_loop": (D, END, "_QA_T = (deck_outcomes_table, receipts_grades_table)\n\n"
                                       "def _qa(conn):\n    for t in _QA_T:\n        conn.execute(delete(t))\n"),
    "getattr_lookup": (R, END, "def _qa(conn):\n    g = getattr(db, 'receipts_grades_table')\n"
                               "    conn.execute(delete(g))\n"),
    "getattr_concat_name": (R, END, "def _qa(conn):\n    conn.execute(delete(getattr(db, "
                                    "'receipts_grades' + '_table')))\n"),
    "tables_get": (D, END, "def _qa(conn):\n    conn.execute(delete(metadata.tables.get('receipts_grades')))\n"),
    "alias_method_on_table": (D, END, "def _qa(conn):\n    a = receipts_grades_table.alias('x')\n"
                                      "    conn.execute(delete(a))\n"),
    "statement_var_upsert": (D, END, "def _qa(conn):\n    from sqlalchemy.dialects.postgresql import insert\n"
                                     "    s = insert(receipts_grades_table).values(status='x')\n"
                                     "    conn.execute(s.on_conflict_do_update(index_elements=['id'], "
                                     "set_={'status': 'y'}))\n"),
    "table_keyword": (D, END, "def _qa(conn):\n    conn.execute(delete(table=receipts_grades_table))\n"),
    "sa_module_delete": (D, END, "def _qa(conn):\n    import sqlalchemy as sa\n"
                                 "    conn.execute(sa.delete(receipts_grades_table))\n"),
    "percent_sql": (D, END, "def _qa(conn):\n    conn.execute(text('DELETE FROM %s' % 'receipts_grades'))\n"),
    "truncate_sql": (S, END, "def _qa(conn):\n    conn.execute(text('TRUNCATE receipts_grade_runs'))\n"),
    "upsert_sql": (S, END, "def _qa(conn):\n    conn.execute(text('INSERT INTO receipts_grades (id) VALUES (1) "
                           "ON CONFLICT (id) DO UPDATE SET status = 1'))\n"),
    "replace_sql": (S, END, "def _qa(conn):\n    conn.execute(text('replace into receipts_grades values (1)'))\n"),
    "dynamic_name_list": (D, END, "_QA_TABLES = ('deck_outcomes', 'receipts_grades')\n"),
    "delete_deck_by_reference": (R, END, "_wipe = db._delete_deck\n"),
    "delete_deck_imported": (S, END, "def _qa():\n    from .database import _delete_deck as _dd\n"),
    "purge_with_kwargs": (S, "        pruned = purge_deck_evidence(\n",
                          "        pruned = purge_deck_evidence(**{'days': 56})\n"),
    "nested_function_in_delete_deck": (D, IN_DD, "            *[(n, s) for n, s in (lambda: [('x', delete(g))])()],"),
    "scripts_file": ("scripts/receipts_backfill.py", END,
                     "def _qa(conn):\n    from backend import database as db\n"
                     "    conn.execute(db.receipts_grades_table.delete())\n"),
}


def _inject(path, where, code):
    src = (REPO / path).read_text()
    if where == END:
        return src.rstrip("\n") + "\n\n\n" + code
    assert src.count(where) == 1, (path, where)
    return src.replace(where, code.rstrip("\n") + "\n" + where, 1)


@pytest.mark.parametrize("case", sorted(CASES))
def test_t10_catches_each_injected_write(case):
    path, where, code = CASES[case]
    scans = scan_all({path: _inject(path, where, code)})
    assert [f for s in scans for f in s.findings], f"T-10 let {case} through"


def test_t10_the_clean_tree_finds_nothing_and_the_readers_stay_allowed():
    """The scanner sees reads and inserts and lets them be: a select, an
    insert with on_conflict_do_nothing, the run ledger's insert, a SQL read."""
    code = ("def _qa_reads(conn):\n    g = receipts_grades_table\n"
            "    conn.execute(select(g).where(g.c.id == 1))\n"
            "    conn.execute(_dialect_insert(g).values(id=1).on_conflict_do_nothing())\n"
            "    conn.execute(receipts_grade_runs_table.insert().values(run_id='r'))\n"
            "    conn.execute(text('SELECT count(*) FROM receipts_grades'))\n"
            "    counts = {}\n    counts.update(n=1)\n")
    scans = scan_all({D: _inject(D, END, code)})
    assert [f for s in scans for f in s.findings] == []
