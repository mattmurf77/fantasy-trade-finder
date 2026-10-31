"""T-10: the receipts tables are append-only (HLD D-3; docs/plans/receipts/LLD.md §7).

An allowlist of USES, after release-lead's #544 QA (round 1: a line-regex let
21 of 27 injected writes through; round 2: a deny-list of writes let 22 of 39
new forms through). Every non-test Python file under backend/ and scripts/ is
parsed, and every .sql file there is read.

A reference to a receipts table, or a name bound to one, may appear only:
- as the subject of select / select_from / join / outerjoin / insert /
  _dialect_insert / exists, or of `.c`, `.insert()`, `.join()`, `.outerjoin()`,
  `.select()`, `.alias()`;
- as `.name` inside SQL text, which the SQL rule then checks;
- bound to a local name in a function (an alias, followed from there), or at
  module level as the table's own definition or an import of it;
- in the sanctioned statements: `_delete_deck`'s two grade deletes (legal's
  365-day cap, R28.20 (iii)).
Account deletion (a user's rights) deletes receipts_grades by name, looping
over every private table (accounts._ADDITIONAL_PRIVATE_TABLES); in
`accounts._delete_user_data` a lookup built from a name isn't resolved, and a
direct reference is still checked.
Passing it as an argument, returning or yielding it, storing it (a tuple, a
dict, an attribute, a class body, a global), using it as a default, starring
it, or any other method or attribute on it is a finding (U). So are:
- W: a delete/update of one, or an upsert / OR REPLACE on a statement built
  from one (kept beside U for clearer messages);
- S: SQL text that writes one: comments and quotes stripped, case and
  whitespace ignored, ONLY and a schema accepted, MERGE ... THEN DELETE/UPDATE,
  the text resolved through f-strings, `+`, `%`, `.format`, `.join` and names
  bound to static strings;
- P: the retention delete referenced outside its one caller chain
  (`_delete_deck` <- `purge_deck_evidence` <- `server._prune_deck_evidence`,
  never with `now=` or `**`), or a rebinding of the names its sanctioned
  statements read (`g`, `i`, `contract_ids`, `row_ids`).
A string naming a receipts table (a constant, a concatenation, a loop variable
over such strings) makes a `metadata.tables[...]`, `getattr(...)`,
`Table(...)` or `table(...)` lookup a reference, governed as above.

The residual (documented, not caught; T-10 catches accidents, not deliberate
evasion: release-lead's #544 round-3 ruling):
- a table reached through a value computed at run time across functions (a
  name returned by a helper), or by a runtime search (`metadata.sorted_tables`
  filtered by prefix);
- a back-reference from an allowed use: `t.c.<col>.table`, `insert(t).table`,
  `select(t).get_final_froms()[0]`;
- SQL text the renderer doesn't resolve: `"%(t)s" % {...}`, `.format_map`,
  `string.Template`, `b"...".decode()`, and SQL built by `list.append` then
  `' '.join`;
- code or SQL that only exists at run time (`exec`/`eval`, a file read and
  executed);
- the ORM (a mapped class: `session.query(Grade).delete()`, `delete(Grade)`);
  the codebase has no ORM.
A static name looked up in a namespace (`globals()[...]`, `vars(m)[...]`,
`m.__dict__[...]`, `operator.attrgetter(...)(m)`, `m.__getattribute__(...)`)
IS resolved.
"""
import ast
import importlib.util
import inspect
import re
import warnings
from functools import lru_cache
from pathlib import Path

import pytest

from backend import database as db

REPO = Path(__file__).resolve().parents[2]
TABLES = frozenset(t for t in db.metadata.tables if t.startswith("receipts_"))
REF_NAMES = frozenset(f"{t}_table" for t in TABLES)
A_TABLE = sorted(TABLES)[0]          # what a name-carrying string renders as

ALLOWED_CALLS = frozenset({"select", "select_from", "join", "outerjoin", "insert",
                           "_dialect_insert", "exists"})
ALLOWED_ATTRS = frozenset({"c", "insert", "join", "outerjoin", "select"})
DERIVE_ATTRS = frozenset({"alias", "_clone", "tablesample"})
DERIVE_CALLS = frozenset({"aliased", "alias"})

SANCTIONED_WRITES = frozenset({
    ("backend/database.py", "_delete_deck.<comp>",          # inside its chunking generator
     "delete(g).where(g.c.impression_id.in_(contract_ids[k:k + 500]))"),
    ("backend/database.py", "_delete_deck",
     "delete(g).where(g.c.impression_id.in_(row_ids))"),
})
# Account deletion (a user's rights) loops over every private table by NAME,
# receipts_grades among them (accounts._ADDITIONAL_PRIVATE_TABLES), and reuses
# its loop variables across loops. There, a lookup built from a name isn't
# resolved; a direct reference to a receipts table is still checked.
NAME_LOOKUPS_UNRESOLVED = frozenset({
    ("backend/accounts.py", "_delete_user_data"),
    ("backend/accounts.py", "_delete_user_data._del"),
})
# The names the sanctioned statements read, and their one binding each.
PINNED_BINDINGS = {
    ("backend/database.py", "_delete_deck"): {
        "g": "r, sh, g = (trade_pass_reasons_table, trade_policy_shadow_table, receipts_grades_table)",
        "i": "i, o, p = (deck_impressions_table, deck_outcomes_table, deck_evidence_packs_table)",
        "contract_ids": "contract_ids = [f'{deck_job_id}:{k}' for k in range(card_count)]",
        "row_ids": "row_ids = select(i.c.impression_id).where(i.c.deck_job_id == deck_job_id)",
    },
}
PINNED = {
    "_delete_deck": frozenset({("backend/database.py", "purge_deck_evidence")}),
    "purge_deck_evidence": frozenset({("backend/server.py", "_prune_deck_evidence")}),
}
_SQL_TABLE = r"(?:only\s+)?(?:\w+\.)?receipts_\w+"
SQL_WRITES = (
    re.compile(r"\b(?:delete\s+from|update|truncate(?:\s+table)?|replace\s+into"
               r"|insert\s+or\s+replace\s+into|drop\s+table(?:\s+if\s+exists)?|alter\s+table)\s+"
               + _SQL_TABLE),
    re.compile(r"\binsert\s+into\s+" + _SQL_TABLE
               + r".*\bon\s+(?:conflict|duplicate\s+key)\b.*\bupdate\b"),
    re.compile(r"\bmerge\s+into\s+" + _SQL_TABLE + r".*\bthen\s+(?:delete|update)\b"),
)
_COMPS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef) + _COMPS
_BINDERS = (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr, ast.For, ast.AsyncFor,
            ast.comprehension, ast.withitem)


def sql_text(text: str) -> str:
    """SQL as the S rule reads it: comments and identifier quotes gone,
    lower-case, single-spaced."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"--[^\n]*", " ", text)
    text = re.sub(r"[\"`\[\]]", "", text)
    return " ".join(text.lower().split())


def sql_writes(text: str) -> bool:
    sql = sql_text(text)
    return any(p.search(sql) for p in SQL_WRITES)


def _files():
    for base in ("backend", "scripts"):
        for path in sorted((REPO / base).rglob("*")):
            rel = path.relative_to(REPO).as_posix()
            if path.suffix in (".py", ".sql") and not rel.startswith("backend/tests/"):
                yield rel, path.read_text()


class _State:
    """One scope's bindings: table aliases, statement variables (built from a
    table), name-carrying strings, static strings, and literal tuples."""

    def __init__(self, parent=None):
        self.taint = set(parent.taint) if parent else set()
        self.ctaint = set(parent.ctaint) if parent else set()
        self.ntaint = set(parent.ntaint) if parent else set()
        self.strs = dict(parent.strs) if parent else {}
        self.lits = dict(parent.lits) if parent else {}
        self.tabmaps = set(parent.tabmaps) if parent else set()   # names bound to `<x>.tables`
        self.globals = set()
        self.names_resolved = True

    def shadow(self, names):
        for name in names:
            for bag in (self.taint, self.ctaint, self.ntaint, self.tabmaps):
                bag.discard(name)
            self.strs.pop(name, None)
            self.lits.pop(name, None)


class Scan:
    """One file's findings, and the sanctioned statements and pinned calls it saw."""

    def __init__(self, rel: str, source: str):
        self.rel, self.findings = rel, []
        self.sanctioned, self.uses, self.pinned_calls, self.bindings = set(), set(), [], set()
        if rel.endswith(".sql"):
            for n, line in enumerate(source.split(";"), 1):
                if sql_writes(line):
                    self.findings.append(f"{rel}: S: SQL writing a receipts table: {sql_text(line)[:120]}")
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)   # a repo file's "\ " escape
            tree = ast.parse(source)
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                child._t10_parent = node
        self.imports = {a.asname or a.name: a.name for n in ast.walk(tree)
                        if isinstance(n, ast.ImportFrom) for a in n.names}
        self._scope(tree, "<module>", "module", _State())

    # ── scopes and bindings ──────────────────────────────────────────────
    @staticmethod
    def _own(node):
        stack = list(ast.iter_child_nodes(node))
        while stack:
            n = stack.pop()
            yield n
            if not isinstance(n, _SCOPES):
                stack.extend(ast.iter_child_nodes(n))

    def _scope(self, node, qual, kind, parent_state):
        own = list(self._own(node))
        st = _State(parent_state)
        st.names_resolved = (self.rel, qual) not in NAME_LOOKUPS_UNRESOLVED
        if not st.names_resolved:
            st.ntaint.clear()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = node.args
            st.shadow(x.arg for x in a.posonlyargs + a.args + a.kwonlyargs
                      + [v for v in (a.vararg, a.kwarg) if v is not None])
        if kind != "module":
            declared = {x for n in own if isinstance(n, (ast.Global, ast.Nonlocal)) for x in n.names}
            st.shadow(self._locals(own) - declared)
        for n in own:
            if isinstance(n, (ast.Global, ast.Nonlocal)):
                st.globals.update(n.names)
            if isinstance(n, ast.ImportFrom):
                st.taint.update(a.asname for a in n.names if a.name in REF_NAMES and a.asname)
            if (isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None
                    and isinstance(n.value, (ast.Tuple, ast.List, ast.Set))):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                if len(targets) == 1 and isinstance(targets[0], ast.Name):
                    st.lits[targets[0].id] = n.value
        str_bindings: dict[str, set] = {}
        changed = True
        while changed:
            changed = False
            for n in own:
                for target, value in self._pairs(n, st):
                    for name in self._bind(target, value, st, self._is_ref):
                        changed |= name not in st.taint
                        st.taint.add(name)
                    for name in self._bind(target, value, st, self._is_name_str):
                        changed |= name not in st.ntaint
                        st.ntaint.add(name)
                    if self._contains_ref(value, st):
                        for name in self._names(target):
                            changed |= name not in st.ctaint
                            st.ctaint.add(name)
                    if isinstance(target, ast.Name) and self._tables_lookup(value, st):
                        changed |= target.id not in st.tabmaps
                        st.tabmaps.add(target.id)
                    if isinstance(target, ast.Name) and not isinstance(n, (ast.For, ast.AsyncFor,
                                                                           ast.comprehension)):
                        text = self._render(value, st)
                        if text is not None and "{?}" not in text:
                            seen = str_bindings.setdefault(target.id, set())
                            if text not in seen:
                                seen.add(text)
                                changed = True
                            st.strs = {k: next(iter(v)) for k, v in str_bindings.items() if len(v) == 1}
        for n in own:
            self._check(n, qual, kind, st)
        self._check_pinned_bindings(own, qual)
        for n in own:
            if isinstance(n, _SCOPES):
                name = getattr(n, "name", "<comp>" if isinstance(n, _COMPS) else "<lambda>")
                sub_kind = "class" if isinstance(n, ast.ClassDef) else "function"
                self._scope(n, name if qual == "<module>" else f"{qual}.{name}", sub_kind, st)

    def _locals(self, own):
        """The names a scope binds itself."""
        out = set()
        for n in own:
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                out.add(n.id)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.add(n.name)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                out.update((a.asname or a.name).split(".")[0] for a in n.names)
        return out

    def _pairs(self, n, st):
        if isinstance(n, ast.Assign):
            return [(t, n.value) for t in n.targets]
        if isinstance(n, (ast.AnnAssign, ast.AugAssign)) and n.value is not None:
            return [(n.target, n.value)]
        if isinstance(n, ast.NamedExpr):
            return [(n.target, n.value)]
        if isinstance(n, ast.withitem) and n.optional_vars is not None:
            return [(n.optional_vars, n.context_expr)]
        if isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            it = self._literal(n.iter, st)
            if it is not None:
                return [(n.target, e) for e in self._elements(it)]
            return [(n.target, n.iter)] if self._contains_ref(n.iter, st) else []
        return []

    @staticmethod
    def _elements(literal):
        """A literal's elements, a `*(... for ...)` or `*[...]` among them
        standing for the elements it produces."""
        for e in literal.elts:
            if isinstance(e, ast.Starred) and isinstance(e.value, (ast.GeneratorExp, ast.ListComp,
                                                                   ast.SetComp)):
                yield e.value.elt
            elif isinstance(e, ast.Starred) and isinstance(e.value, (ast.Tuple, ast.List)):
                yield from e.value.elts
            else:
                yield e

    @staticmethod
    def _literal(node, st):
        if isinstance(node, ast.Name) and node.id in st.lits:
            node = st.lits[node.id]
        return node if isinstance(node, (ast.Tuple, ast.List, ast.Set)) else None

    @staticmethod
    def _names(target):
        return [x.id for x in ast.walk(target) if isinstance(x, ast.Name)]

    def _bind(self, target, value, st, pred):
        if isinstance(target, ast.Starred):
            target = target.value
        if isinstance(target, ast.Name):
            return [target.id] if pred(value, st) else []
        if isinstance(target, (ast.Tuple, ast.List)):
            if (isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts)
                    and not any(isinstance(e, ast.Starred) for e in target.elts + value.elts)):
                return [x for t, v in zip(target.elts, value.elts)
                        for x in self._bind(t, v, st, pred)]
            if any(pred(x, st) for x in ast.walk(value)):
                return self._names(target)          # can't pair them up: all of them
        return []

    # ── what is a receipts table ─────────────────────────────────────────
    def _namespace(self, node):
        """globals(), vars(...) or <x>.__dict__: a namespace a name can be looked up in."""
        if isinstance(node, ast.Call) and self._fname(node.func) in ("globals", "vars", "locals"):
            return True
        return isinstance(node, ast.Attribute) and node.attr == "__dict__"

    @staticmethod
    def _tables_lookup(node, st):
        return (isinstance(node, ast.Attribute) and node.attr == "tables") or (
            isinstance(node, ast.Name) and node.id in st.tabmaps)

    def _fname(self, func):
        if isinstance(func, ast.Attribute):
            return func.attr
        if isinstance(func, ast.Name):
            return self.imports.get(func.id, func.id)
        return None

    def _is_ref(self, node, st):
        if isinstance(node, ast.Name):
            return node.id in REF_NAMES or node.id in st.taint
        if isinstance(node, ast.Attribute):
            return node.attr in REF_NAMES
        if isinstance(node, ast.Subscript):
            if self._namespace(node.value):
                return self._render(node.slice, st) in REF_NAMES
            return self._tables_lookup(node.value, st) and self._render(node.slice, st) in TABLES
        if isinstance(node, ast.Call):
            f, name = node.func, self._fname(node.func)
            first = node.args[0] if node.args else None
            if isinstance(f, ast.Attribute) and f.attr in DERIVE_ATTRS and self._is_ref(f.value, st):
                return True
            if name in DERIVE_CALLS and first is not None and self._is_ref(first, st):
                return True
            if name == "getattr" and len(node.args) >= 2:
                return self._render(node.args[1], st) in REF_NAMES and (
                    st.names_resolved or isinstance(node.args[1], ast.Constant))
            if name == "get" and isinstance(f, ast.Attribute) and self._tables_lookup(f.value, st):
                return first is not None and self._render(first, st) in TABLES
            if name == "get" and isinstance(f, ast.Attribute) and self._namespace(f.value):
                return first is not None and self._render(first, st) in REF_NAMES
            if name == "__getattribute__" and first is not None:
                return self._render(first, st) in REF_NAMES
            if (isinstance(f, ast.Call) and self._fname(f.func) == "attrgetter" and f.args
                    and self._render(f.args[0], st) in REF_NAMES):
                return True                                 # attrgetter('<table>_table')(module)
            if name in ("Table", "table", "TableClause") and first is not None:
                return self._render(first, st) in TABLES
            return False
        if isinstance(node, ast.IfExp):
            return self._is_ref(node.body, st) or self._is_ref(node.orelse, st)
        if isinstance(node, ast.BoolOp):
            return any(self._is_ref(v, st) for v in node.values)
        if isinstance(node, ast.NamedExpr):
            return self._is_ref(node.value, st)
        return False

    def _is_name_str(self, node, st):
        return st.names_resolved and self._render(node, st) in TABLES | REF_NAMES

    def _contains_ref(self, node, st):
        return any(self._is_ref(x, st) or (isinstance(x, ast.Name) and x.id in st.ctaint)
                   for x in ast.walk(node))

    # ── strings ──────────────────────────────────────────────────────────
    def _render(self, node, st):
        """A string expression's static text, or None. Unknown parts are "{?}";
        a receipts table's `.name`, and a name-carrying variable, render as a
        receipts table's name."""
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, str) else None
        if isinstance(node, ast.Name):
            if node.id in st.ntaint:
                return A_TABLE
            return st.strs.get(node.id)
        if isinstance(node, ast.Attribute) and node.attr in ("name", "fullname") \
                and self._is_ref(node.value, st):
            return A_TABLE
        if isinstance(node, ast.JoinedStr):
            return "".join(str(p.value) if isinstance(p, ast.Constant) else self._part(p.value, st)
                           for p in node.values)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = self._render(node.left, st), self._render(node.right, st)
            if left is None and right is None:
                return None
            return (left if left is not None else "{?}") + (right if right is not None else "{?}")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            left = self._render(node.left, st)
            if left is None:
                return None
            args = node.right.elts if isinstance(node.right, ast.Tuple) else [node.right]
            for a in args:
                left = re.sub(r"%[sdr]", lambda _m, a=a: self._part(a, st).replace("\\", "\\\\"), left, count=1)
            return left
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            base = self._render(node.func.value, st)
            if base is None:
                return None
            if node.func.attr == "format":
                pos = iter([self._part(a, st) for a in node.args])
                kw = {k.arg: self._part(k.value, st) for k in node.keywords if k.arg}

                def field(m):
                    key = m.group(1).split("!")[0].split(":")[0]
                    if key == "" or key.isdigit():
                        return next(pos, "{?}")
                    return kw.get(key, "{?}")
                return re.sub(r"\{([^{}]*)\}", field, base)
            if node.func.attr == "join" and node.args:
                items = self._literal(node.args[0], st)
                if items is not None:
                    return base.join(self._part(e, st) for e in items.elts)
            if node.func.attr in ("upper", "lower", "strip"):
                return getattr(base, node.func.attr)()
        return None

    def _part(self, node, st):
        text = self._render(node, st)
        return text if text is not None else "{?}"

    # ── the checks ───────────────────────────────────────────────────────
    def _flag(self, rule, node, why):
        self.findings.append(f"{self.rel}:{getattr(node, 'lineno', '?')}: {rule}: {why}")

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

    def _sanctioned(self, call, qual):
        top = ast.unparse(self._chain_top(call))
        if (self.rel, qual, top) in SANCTIONED_WRITES:
            self.sanctioned.add((self.rel, qual, top))
            return True
        return False

    def _in_sql_text(self, attr):
        """`<table>.name` inside a string expression the S rule renders."""
        p = self._parent(attr)
        if isinstance(p, ast.FormattedValue):
            return True
        if isinstance(p, ast.BinOp) and isinstance(p.op, (ast.Add, ast.Mod)):
            return True
        if isinstance(p, ast.Tuple) and isinstance(self._parent(p), ast.BinOp):
            return True                                     # "%s %s" % (a, t.name)
        if isinstance(p, ast.Call) and isinstance(p.func, ast.Attribute) and p.func.attr == "format":
            return True
        if isinstance(p, ast.keyword):
            call = self._parent(p)
            return isinstance(call.func, ast.Attribute) and call.func.attr == "format"
        if isinstance(p, (ast.Tuple, ast.List)):
            call = self._parent(p)
            return (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "join")
        return False

    def _bound_locally(self, node, kind, st):
        """`node` reaches a binding only through tuples/lists, and its target
        there is a plain local name (or, at module level, the table's own
        definition)."""
        child, p = node, self._parent(node)
        while isinstance(p, (ast.Tuple, ast.List)):
            child, p = p, self._parent(p)
        if isinstance(p, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            if p.value is not child:
                return False
            targets = p.targets if isinstance(p, ast.Assign) else [p.target]
            outs = [self._counterpart(child, t, node) for t in targets]
        elif isinstance(p, (ast.For, ast.AsyncFor, ast.comprehension)):
            if p.iter is not child:
                return False
            outs = [self._counterpart(e, p.target, node) for e in getattr(child, "elts", [child])
                    if e is node or any(x is node for x in ast.walk(e))]
        elif isinstance(p, ast.withitem):
            outs = [self._counterpart(child, p.optional_vars, node)] if p.context_expr is child else []
        else:
            return False
        if not outs or not all(isinstance(t, ast.Name) for t in outs):
            return False
        if kind == "function":
            return not any(t.id in st.globals for t in outs)
        if kind == "module":
            return all(t.id in REF_NAMES for t in outs)
        return False                                        # a class body: an attribute

    def _counterpart(self, value, target, node):
        if value is node:
            return target
        if (isinstance(value, (ast.Tuple, ast.List)) and isinstance(target, (ast.Tuple, ast.List))
                and len(value.elts) == len(target.elts)):
            for v, t in zip(value.elts, target.elts):
                if v is node or any(x is node for x in ast.walk(v)):
                    return self._counterpart(v, t, node)
        return None

    def _use_ok(self, node, qual, kind, st):
        p = self._parent(node)
        if isinstance(p, ast.Attribute) and p.value is node:
            call = self._parent(p)
            called = isinstance(call, ast.Call) and call.func is p
            if p.attr == "c":
                return True
            if p.attr in ALLOWED_ATTRS - {"c"} or p.attr in DERIVE_ATTRS:
                return called
            if p.attr in ("name", "fullname"):
                return self._in_sql_text(p)
            return False
        if isinstance(p, ast.keyword):
            p = self._parent(p)
            if not isinstance(p, ast.Call):
                return False
        if isinstance(p, ast.Call) and p.func is not node:
            if self._fname(p.func) in ALLOWED_CALLS | DERIVE_CALLS:
                return True
            return self._sanctioned(p, qual)
        return self._bound_locally(node, kind, st)

    def _check(self, n, qual, kind, st):
        is_target = isinstance(getattr(n, "ctx", None), (ast.Store, ast.Del)) and not isinstance(
            n, ast.Subscript)                       # `x[...] = ref` is a store INTO x: checked as a use
        if not is_target and self._is_ref(n, st) and not self._use_ok(n, qual, kind, st):
            self._flag("U", n, f"a receipts table used as `{ast.unparse(self._parent(n) or n)[:100]}` "
                               f"in {qual}")
        if isinstance(n, ast.Call):
            f, fname = n.func, self._fname(n.func)
            hit = False
            if fname in ("delete", "update", "Delete", "Update"):
                targets = n.args[:1] + [k.value for k in n.keywords if k.arg == "table"]
                hit = any(self._is_ref(t, st) for t in targets) or (
                    isinstance(f, ast.Attribute) and self._is_ref(f.value, st))
            elif fname in ("on_conflict_do_update", "on_duplicate_key_update"):
                hit = isinstance(f, ast.Attribute) and self._contains_ref(f.value, st)
            elif fname == "prefix_with":
                hit = (any("replace" in (self._render(a, st) or "").lower() for a in n.args)
                       and isinstance(f, ast.Attribute) and self._contains_ref(f.value, st))
            if hit and not self._sanctioned(n, qual):
                self._flag("W", n, f"a write to a receipts table in {qual}: "
                                   f"{ast.unparse(self._chain_top(n))[:120]}")
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
        if isinstance(n, (ast.Constant, ast.JoinedStr, ast.BinOp, ast.Call)):
            parent = self._parent(n)
            if isinstance(parent, ast.Expr) and isinstance(n, ast.Constant):
                return                                  # a docstring or bare string
            if self._render(parent, st) is not None if parent is not None else False:
                return                                  # part of a larger string
            if isinstance(parent, ast.FormattedValue):
                return
            text = self._render(n, st)
            if text is not None and sql_writes(text):
                self._flag("S", n, f"SQL writing a receipts table: {sql_text(text)[:120]}")

    def _check_pinned_bindings(self, own, qual):
        pins = PINNED_BINDINGS.get((self.rel, qual))
        if pins is None:
            # A scope nested in a pinned one (a comprehension, a lambda) may not
            # rebind the pinned names at all: a walrus there would reach them.
            outer = next((pq for (pr, pq) in PINNED_BINDINGS if pr == self.rel
                          and qual.startswith(pq + ".")), None)
            if outer is None:
                return
            pins = {name: None for name in PINNED_BINDINGS[(self.rel, outer)]}
        for n in own:
            if not isinstance(n, _BINDERS):
                continue
            targets = (n.targets if isinstance(n, ast.Assign) else
                       [n.optional_vars] if isinstance(n, ast.withitem) else [n.target])
            names = {x for t in targets if t is not None for x in self._names(t)}
            for name in names & set(pins):
                stmt = ast.unparse(n)
                if stmt == pins[name]:
                    self.bindings.add((self.rel, qual, name))
                else:
                    self._flag("P", n, f"{name} rebound in {qual}: {stmt[:100]}")


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
    """No use of a receipts table but the allowed ones anywhere in backend/ or
    scripts/; the sanctioned statements, the pinned bindings and the pinned
    caller chain are all really there."""
    scans = scan_all()
    findings = [f for s in scans for f in s.findings]
    assert findings == [], (
        "a write path against a receipts table exists:\n" + "\n".join(findings)
        + "\nCorrections are a grader_version bump plus a regrade, with the old rows "
          "retained. Editing or deleting a grade destroys the audit trail that makes "
          "the preregistration claim checkable.")
    assert set().union(*(s.sanctioned for s in scans)) == SANCTIONED_WRITES
    assert set().union(*(s.bindings for s in scans)) == {
        (rel, qual, name) for (rel, qual), pins in PINNED_BINDINGS.items() for name in pins}
    calls = [c for s in scans for c in s.pinned_calls]
    assert sorted(calls) == [("_delete_deck", "backend/database.py", "purge_deck_evidence"),
                             ("purge_deck_evidence", "backend/server.py", "_prune_deck_evidence")]


def test_t10_account_deletion_still_takes_the_users_grades():
    """The one other delete of receipts_grades: account deletion, by name."""
    from backend import accounts
    assert "receipts_grades" in accounts._ADDITIONAL_PRIVATE_TABLES
    assert "receipts_grade_runs" not in accounts._ADDITIONAL_PRIVATE_TABLES   # not user-keyed
    src = inspect.getsource(accounts._delete_user_data)
    assert "for name in _ADDITIONAL_PRIVATE_TABLES:\n            _del(name, getattr(db, name + \"_table\"))" in src


def test_t10_scans_every_backend_and_scripts_file():
    rels = {rel for rel, _src in _files()}
    for rel in ("backend/database.py", "backend/receipts_service.py", "backend/accounts.py",
                "backend/server.py", "backend/eval/redaction.py", "scripts/purge_entry_users.py",
                "scripts/bakeoff_readout.sql"):
        assert rel in rels
    assert not any(r.startswith("backend/tests/") for r in rels)
    assert TABLES == {"receipts_grades", "receipts_grade_runs"}


# ── release-lead's #544 QA matrices, as unit tests of the scanner ───────────
# Each case injects valid code into an in-memory copy of a real file (or a new
# file); T-10 must find it. END appends; NEW creates the file; ("REPLACE", a)
# swaps the anchor `a` for the code; any other anchor is preceded by the code.

D, R, S, A = "backend/database.py", "backend/receipts_service.py", "backend/server.py", "backend/accounts.py"
END, NEW = "<END>", "<NEW>"
AFTER_DD = "\n\ndef _delete_old_trade_impressions("
IN_DD = '            ("deck_evidence_packs", delete(p).where(p.c.run_id == deck_job_id))):'
ROW_IDS = "    row_ids = select(i.c.impression_id).where(i.c.deck_job_id == deck_job_id)\n"


def _fn(body):
    return "def _qa(conn):\n" + "".join(f"    {line}\n" for line in body.split("\n"))


CASES = {
    # round 1: QA's 27
    "alias_fn_delete": (D, END, _fn("g = receipts_grades_table\nconn.execute(delete(g).where(g.c.id == 1))")),
    "tuple_alias_update": (D, END, _fn("o, g = deck_outcomes_table, receipts_grades_table\n"
                                       "conn.execute(update(g).values(status='graded'))")),
    "table_method_delete": (D, END, _fn("conn.execute(receipts_grades_table.delete())")),
    "upper_text_sql": (D, END, _fn("conn.execute(text('DELETE FROM receipts_grades WHERE id = 1'))")),
    "direct_fn_delete": (D, END, _fn("conn.execute(delete(receipts_grades_table)"
                                     ".where(receipts_grades_table.c.id == 1))")),
    "direct_fn_update": (D, END, _fn("conn.execute(update(receipts_grades_table).values(status='graded'))")),
    "direct_fn_delete_runs": (D, END, _fn("conn.execute(delete(receipts_grade_runs_table))")),
    "alias_method_delete": (D, END, _fn("g = receipts_grades_table\nconn.execute(g.delete().where(g.c.id == 1))")),
    "alias_multiline": (D, END, _fn("g = receipts_grades_table\nconn.execute(delete(\n    g).where(g.c.id == 1))")),
    "annotated_alias": (D, END, _fn("g: Table = receipts_grades_table\nconn.execute(delete(g))")),
    "metadata_lookup_alias": (D, END, _fn("g = metadata.tables['receipts_grades']\nconn.execute(delete(g))")),
    "fresh_annotated_alias": (D, END, _fn("rg: Table = receipts_grades_table\nconn.execute(delete(rg))")),
    "fresh_metadata_alias": (D, END, _fn("rg = metadata.tables['receipts_grades']\nconn.execute(delete(rg))")),
    "fresh_alias_method": (D, END, _fn("rg = receipts_grades_table\nconn.execute(rg.update().values(status='x'))")),
    "inside_delete_deck_correction": (D, IN_DD, "            ('receipts_grades', delete(g).where("
                                                "g.c.grader_version == 'receipts-1')),"),
    "lower_text_sql": (D, END, _fn("conn.execute(text('delete from receipts_grades where id = 1'))")),
    "fstring_sql": (D, END, _fn("conn.execute(text(f'DELETE FROM {receipts_grades_table.name} WHERE id = 1'))")),
    "split_sql": (D, END, _fn("conn.execute(text('DELETE FROM '\n                  'receipts_grades WHERE id = 1'))")),
    "upsert_do_update": (D, END, _fn("from sqlalchemy.dialects.sqlite import insert as _i\n"
                                     "conn.execute(_i(receipts_grades_table).values(id=1).on_conflict_do_update(\n"
                                     "    index_elements=['impression_id'], set_={'status': 'x'}))")),
    "insert_or_replace": (D, END, _fn("conn.execute(receipts_grades_table.insert()"
                                      ".prefix_with('OR REPLACE').values(id=1))")),
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
    "service_db_attr_delete": (R, END, _fn("from sqlalchemy import delete as _d\n"
                                           "conn.execute(_d(db.receipts_grades_table))")),
    "service_alias_delete": (R, END, _fn("from sqlalchemy import delete\ng = db.receipts_grades_table\n"
                                         "conn.execute(delete(g))")),
    "other_module_server": (S, END, _fn("conn.execute(text('DELETE FROM receipts_grades'))")),
    # round 1: trades-eng's 22
    "loop_over_tables": (D, END, _fn("for t in (deck_outcomes_table, receipts_grades_table):\n"
                                     "    conn.execute(delete(t))")),
    "comprehension_pairs": (D, END, _fn("for _n, t in (('a', deck_outcomes_table), "
                                        "('b', receipts_grade_runs_table)):\n    conn.execute(t.delete())")),
    "module_tuple_then_loop": (D, END, "_QA_T = (deck_outcomes_table, receipts_grades_table)\n\n"
                                       + _fn("for t in _QA_T:\n    conn.execute(delete(t))")),
    "getattr_lookup": (R, END, _fn("g = getattr(db, 'receipts_grades_table')\nconn.execute(delete(g))")),
    "getattr_concat_name": (R, END, _fn("conn.execute(delete(getattr(db, 'receipts_grades' + '_table')))")),
    "tables_get": (D, END, _fn("conn.execute(delete(metadata.tables.get('receipts_grades')))")),
    "alias_method_on_table": (D, END, _fn("a = receipts_grades_table.alias('x')\nconn.execute(delete(a))")),
    "statement_var_upsert": (D, END, _fn("from sqlalchemy.dialects.postgresql import insert\n"
                                         "s = insert(receipts_grades_table).values(status='x')\n"
                                         "conn.execute(s.on_conflict_do_update(index_elements=['id'], "
                                         "set_={'status': 'y'}))")),
    "table_keyword": (D, END, _fn("conn.execute(delete(table=receipts_grades_table))")),
    "sa_module_delete": (D, END, _fn("import sqlalchemy as sa\nconn.execute(sa.delete(receipts_grades_table))")),
    "percent_sql": (D, END, _fn("conn.execute(text('DELETE FROM %s' % 'receipts_grades'))")),
    "truncate_sql": (S, END, _fn("conn.execute(text('TRUNCATE receipts_grade_runs'))")),
    "upsert_sql": (S, END, _fn("conn.execute(text('INSERT INTO receipts_grades (id) VALUES (1) "
                               "ON CONFLICT (id) DO UPDATE SET status = 1'))")),
    "replace_sql": (S, END, _fn("conn.execute(text('replace into receipts_grades values (1)'))")),
    "dynamic_name_list": (D, END, "_QA_TABLES = ('deck_outcomes', 'receipts_grades')\n\n"
                                  + _fn("for name in _QA_TABLES:\n    conn.execute(delete(metadata.tables[name]))")),
    "delete_deck_by_reference": (R, END, "_wipe = db._delete_deck\n"),
    "delete_deck_imported": (S, END, "def _qa():\n    from .database import _delete_deck as _dd\n"),
    "purge_with_kwargs": (S, "        pruned = purge_deck_evidence(\n",
                          "        pruned = purge_deck_evidence(**{'days': 56})\n"),
    "nested_function_in_delete_deck": (D, IN_DD, "            *[(n, s) for n, s in (lambda: [('x', delete(g))])()],"),
    "scripts_file": ("scripts/receipts_backfill.py", END,
                     _fn("from backend import database as db\nconn.execute(db.receipts_grades_table.delete())")),
    # round 2: QA's 39 (the waived ORM pair and the residual are below, not here)
    "sa_sql_expression_delete": (D, END, _fn("import sqlalchemy.sql.expression\n"
                                             "conn.execute(sqlalchemy.sql.expression.delete(receipts_grades_table))")),
    "text_bindparams": (D, END, _fn("conn.execute(text('DELETE FROM receipts_grades WHERE id = :i').bindparams(i=1))")),
    "exec_driver_sql": (D, END, _fn("conn.exec_driver_sql('DELETE FROM receipts_grades WHERE id = 1')")),
    "sqlite_executescript": (D, END, _fn("conn.connection.driver_connection.executescript('DELETE FROM receipts_grades;')")),
    "raw_dbapi_cursor": (D, END, _fn("conn.connection.cursor().execute(\"UPDATE receipts_grades SET status = 'x'\")")),
    "autoload_table": (D, END, _fn("t = Table('receipts_grades', MetaData(), autoload_with=conn)\n"
                                   "conn.execute(t.delete())")),
    "lowercase_table_clause": (D, END, _fn("from sqlalchemy import table, column\n"
                                           "conn.execute(delete(table('receipts_grades', column('id'))))")),
    "join_built_name": (D, END, _fn("conn.execute(text('DELETE FROM ' + '_'.join(('receipts', 'grades'))))")),
    "name_across_statements": (D, END, _fn("a = 'receipts'\nb = a + '_grades'\nconn.execute(text('DELETE FROM ' + b))")),
    "dunder_import": (R, END, _fn("conn.execute(__import__('backend.database', fromlist=['x'])"
                                  ".receipts_grades_table.delete())")),
    "importlib_getattr": (R, END, _fn("import importlib\nm = importlib.import_module('backend.database')\n"
                                      "conn.execute(delete(getattr(m, 'receipts_grades' + '_table')))")),
    "scripts_helper_wraps_delete": ("scripts/qa_wipe_helper.py", NEW,
                                    "from sqlalchemy import delete\n\n\ndef wipe(conn, table):\n"
                                    "    conn.execute(delete(table))\n\n\ndef main(conn):\n"
                                    "    from backend import database as db\n"
                                    "    wipe(conn, db.receipts_grades_table)\n"),
    "helper_param_same_file": (D, END, "def _qa_wipe(conn, t):\n    conn.execute(delete(t))\n\n\n"
                                       + _fn("_qa_wipe(conn, receipts_grades_table)")),
    "default_arg_alias": (D, END, "def _qa(conn, t=receipts_grades_table):\n    conn.execute(delete(t))\n"),
    "returned_from_helper": (D, END, "def _qa_t():\n    return receipts_grades_table\n\n\n"
                                     + _fn("conn.execute(delete(_qa_t()))")),
    "lambda_param": (D, END, _fn("(lambda t: conn.execute(delete(t)))(receipts_grades_table)")),
    "class_attr_via_self": (D, END, "class _QaStore:\n    T = receipts_grades_table\n\n"
                                    "    def wipe(self, conn):\n        conn.execute(delete(self.T))\n"),
    "dict_value": (D, END, _fn("by_name = {'g': receipts_grades_table}\nconn.execute(delete(by_name['g']))")),
    "starred_arg": (D, END, _fn("conn.execute(delete(*[receipts_grades_table]))")),
    "Delete_constructor": (D, END, _fn("from sqlalchemy import Delete, Update\n"
                                       "conn.execute(Delete(receipts_grades_table))\n"
                                       "conn.execute(Update(receipts_grade_runs_table).values(kind='x'))")),
    "bound_method_reference": (D, END, _fn("wipe = receipts_grades_table.delete\nconn.execute(wipe())")),
    "getattr_method": (D, END, _fn("conn.execute(getattr(receipts_grades_table, 'delete')())")),
    "table_drop": (D, END, _fn("receipts_grades_table.drop(conn)")),
    "drop_all_tables_kw": ("scripts/qa_reset.py", NEW,
                           "from backend import database as db\n\n\ndef main():\n"
                           "    db.metadata.drop_all(db.engine, tables=[db.receipts_grades_table])\n"),
    "plus_dot_name_sql": (D, END, _fn("conn.execute(text('DELETE FROM ' + receipts_grades_table.name))")),
    "format_dot_name_sql": (D, END, _fn("conn.execute(text('DELETE FROM {}'.format(receipts_grades_table.name)))")),
    "sql_comment_between_keywords": (D, END, _fn("conn.execute(text('DELETE /* retention */ FROM receipts_grades'))")),
    "sql_delete_only": (D, END, _fn("conn.execute(text('DELETE FROM ONLY receipts_grades'))")),
    "sql_truncate_only": (D, END, _fn("conn.execute(text('TRUNCATE ONLY receipts_grade_runs'))")),
    "sql_quoted_schema": (D, END, _fn("conn.execute(text('DELETE FROM \"public\".\"receipts_grades\"'))")),
    "sql_merge": (D, END, _fn("conn.execute(text('MERGE INTO receipts_grades g USING (SELECT 1 AS id) s "
                              "ON g.id = s.id WHEN MATCHED THEN DELETE'))")),
    "sql_in_non_py_file": ("scripts/qa_wipe.sql", NEW, "DELETE FROM receipts_grades;\n"),
    "sanctioned_stmt_row_ids_widened": (D, ("REPLACE", ROW_IDS), "    row_ids = select(i.c.impression_id)\n"),
    # round 3: more of the same shapes
    "global_alias": (D, END, "_QA_G = None\n\n\ndef _qa_set():\n    global _QA_G\n"
                             "    _QA_G = receipts_grades_table\n"),
    "module_alias": (D, END, "GRADES = receipts_grades_table\n"),
    "yield_table": (D, END, "def _qa():\n    yield receipts_grades_table\n"),
    "set_attribute": (D, END, _fn("conn.info['t'] = receipts_grades_table")),
    "list_append": (D, END, _fn("tables = []\ntables.append(receipts_grades_table)")),
    "g_rebound_in_delete_deck": (D, ("REPLACE", "    contract_ids = [f\"{deck_job_id}:{k}\" for k in range(card_count)]\n"),
                                 "    g = receipts_grade_runs_table\n"
                                 "    contract_ids = [f\"{deck_job_id}:{k}\" for k in range(card_count)]\n"),
    "join_name_sql": (D, END, _fn("conn.execute(text(' '.join(['DELETE', 'FROM', receipts_grades_table.name])))")),
    "line_comment_sql": (D, END, _fn("conn.execute(text('DELETE -- old rows\\nFROM receipts_grades'))")),
    "update_only_sql": (D, END, _fn("conn.execute(text('UPDATE ONLY receipts_grades SET status = 1'))")),
    "walrus_rebinds_g_in_delete_deck": (D, ("REPLACE", "              for k in range(0, len(contract_ids), 500)),\n            (\"receipts_grades\", delete(g)"),
                                        "              for k in range(0, len(contract_ids), 500) if (g := receipts_grade_runs_table) is not None),\n            (\"receipts_grades\", delete(g)"),
    "globals_lookup": (D, END, _fn("conn.execute(delete(globals()['receipts_grades_table']))")),
    "vars_lookup": (R, END, _fn("conn.execute(delete(vars(db)['receipts_grades_table']))")),
    "dunder_dict_lookup": (R, END, _fn("conn.execute(delete(db.__dict__.get('receipts_grades_table')))")),
    "attrgetter_lookup": (R, END, _fn("import operator\nconn.execute(delete(operator.attrgetter('receipts_grades_table')(db)))")),
    "getattribute_lookup": (R, END, _fn("conn.execute(delete(db.__getattribute__('receipts_grades_table')))")),
    "accounts_second_del": (A, ("REPLACE", "        for name in _ADDITIONAL_PRIVATE_TABLES:\n"),
                            "        _del('receipts_grade_runs', getattr(db, 'receipts_grade_runs_table'))\n"
                            "        for name in _ADDITIONAL_PRIVATE_TABLES:\n"),
}

# Reads and inserts T-10 must leave alone (QA's false-positive set, and more).
FALSE_POSITIVES = {
    "fp_count_read": (D, END, _fn("return conn.execute(select(func.count())"
                                  ".select_from(receipts_grades_table)).scalar()")),
    "fp_text_read": (D, END, _fn("return conn.execute(text(\"SELECT count(*) FROM receipts_grades "
                                 "WHERE status = 'update'\")).scalar()")),
    "fp_log_message": (D, END, "def _qa(n):\n    log.info('receipts_grades rows graded: %d', n)\n"),
    "fp_insert_returning": (D, END, _fn("return conn.execute(insert(receipts_grades_table).values(id=1)"
                                        ".returning(receipts_grades_table.c.id))")),
    "fp_admin_counts_by_name": (S, END, _fn("from .database import metadata as _m\n"
                                            "return {n: conn.execute(select(func.count()).select_from(_m.tables[n]))"
                                            ".scalar() for n in ('receipts_grades', 'receipts_grade_runs')}")),
    "fp_join_read": (D, END, _fn("g, i = receipts_grades_table, deck_impressions_table\n"
                                 "return conn.execute(select(g.c.id).select_from("
                                 "g.join(i, g.c.impression_id == i.c.impression_id))).all()")),
    "fp_reads_and_inserts": (D, END, _fn("g = receipts_grades_table\n"
                                         "conn.execute(select(g).where(g.c.id == 1))\n"
                                         "conn.execute(_dialect_insert(g).values(id=1).on_conflict_do_nothing())\n"
                                         "conn.execute(receipts_grade_runs_table.insert().values(run_id='r'))\n"
                                         "counts = {}\ncounts.update(n=1)")),
    "fp_name_in_sql_read": (D, END, _fn("conn.execute(text(f'SELECT count(*) FROM {receipts_grades_table.name}'))")),
}

# The documented residual: not caught, by design (see the module docstring).
RESIDUAL = ("concat_across_functions", "sorted_tables_search", "exec_code_string",
            "sql_file_runner", "orm_query_delete", "orm_delete_mapped_class")


def _inject(path, where, code):
    if where == NEW:
        assert not (REPO / path).exists(), path
        return code
    src = (REPO / path).read_text()
    if where == END:
        return src.rstrip("\n") + "\n\n\n" + code
    if isinstance(where, tuple):
        anchor = where[1]
        assert src.count(anchor) == 1, (path, anchor)
        return src.replace(anchor, code, 1)
    assert src.count(where) == 1, (path, where)
    return src.replace(where, code.rstrip("\n") + "\n" + where, 1)


@pytest.mark.parametrize("case", sorted(CASES))
def test_t10_catches_each_injected_write(case):
    path, where, code = CASES[case]
    source = _inject(path, where, code)
    if path.endswith(".py"):
        ast.parse(source)                               # the injected code is valid Python
    scans = scan_all({path: source})
    assert [f for s in scans for f in s.findings], f"T-10 let {case} through"


@pytest.mark.parametrize("case", sorted(FALSE_POSITIVES))
def test_t10_leaves_reads_and_inserts_alone(case):
    path, where, code = FALSE_POSITIVES[case]
    scans = scan_all({path: _inject(path, where, code)})
    assert [f for s in scans for f in s.findings] == []


def test_t10_sql_text_normalisation():
    assert sql_writes('DELETE /* x */ FROM "public"."receipts_grades"')
    assert sql_writes("delete -- c\nfrom only receipts_grades")
    assert sql_writes("MERGE INTO receipts_grades USING s ON x WHEN MATCHED THEN UPDATE SET a = 1")
    assert not sql_writes("SELECT * FROM receipts_grades WHERE status = 'update'")
    assert not sql_writes("INSERT INTO receipts_grade_runs (run_id) VALUES ('r') ON CONFLICT DO NOTHING")
