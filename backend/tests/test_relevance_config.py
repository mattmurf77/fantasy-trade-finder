"""D10 config resolver + operational valves (LLD §2.1, T-28).

Every test names the sabotage it catches. The three things that must never
regress:

  1. Precedence order: per-user > overlay (REGISTERED knobs only) > model_config
     > code default.
  2. An UNREGISTERED knob never touches the overlay tier — otherwise any
     running experiment could override any relevance knob.
  3. A valve is resolver-exempt: no experiment, no per-user setting, no cache
     between the operator's kill switch and the pass that reads it.

Harness follows test_analytics_p0.py: isolated file-backed SQLite engine
patched into backend.database.
"""

import pathlib
import re

import pytest
from sqlalchemy import create_engine, insert, update

import backend.database as db_module
import backend.experiments as experiments
import backend.relevance.config as cfg
from backend.database import metadata, model_config_table


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

@pytest.fixture
def eng(tmp_path, monkeypatch):
    """Isolated product engine with the real schema, patched into database."""
    e = create_engine(f"sqlite:///{tmp_path / 'cfg.db'}",
                      connect_args={"check_same_thread": False})
    metadata.create_all(e)
    monkeypatch.setattr(db_module, "engine", e)
    return e


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Empty registries + cold cache per test; restored afterwards."""
    monkeypatch.setattr(cfg, "KNOB_EXPERIMENTS", {})
    monkeypatch.setattr(cfg, "USER_SETTING_PROVIDERS", {})
    cfg._reset_cache()
    yield
    cfg._reset_cache()


def _put(eng, key, value):
    """Seed / overwrite a model_config row and invalidate the snapshot."""
    with eng.begin() as conn:
        res = conn.execute(update(model_config_table)
                           .where(model_config_table.c.key == key)
                           .values(value=value))
        if res.rowcount == 0:
            conn.execute(insert(model_config_table)
                         .values(key=key, value=value, description="test"))
    cfg._reset_cache()


def _overlay_spy(monkeypatch, overlay, calls):
    def fake(unit_id, exp_key, header_attrs=None):
        calls.append((unit_id, exp_key))
        return "B", dict(overlay)
    monkeypatch.setattr(experiments, "variant_overlay", fake)
    return calls


# ---------------------------------------------------------------------------
# resolve() — the four precedence tiers
# ---------------------------------------------------------------------------

def test_code_default_when_nothing_configured(eng):
    # SABOTAGE: delete the final `return float(default)` (or return 0.0 from a
    # missing model_config row) ⇒ this fails.
    assert cfg.resolve("dedup_overlap_tau", 0.75) == 0.75


def test_model_config_row_beats_code_default(eng):
    # SABOTAGE: drop tier 3 (the _snapshot() lookup) ⇒ returns 0.75, fails.
    _put(eng, "dedup_overlap_tau", 0.42)
    assert cfg.resolve("dedup_overlap_tau", 0.75) == 0.42


def test_registered_overlay_beats_model_config(eng, monkeypatch):
    # SABOTAGE: order the overlay tier BELOW model_config, or drop it ⇒ 0.42.
    _put(eng, "dedup_overlap_tau", 0.42)
    monkeypatch.setattr(cfg, "KNOB_EXPERIMENTS",
                        {"dedup_overlap_tau": "relevance.dedup"})
    calls = _overlay_spy(monkeypatch, {"dedup_overlap_tau": 0.9}, [])

    assert cfg.resolve("dedup_overlap_tau", 0.75, user_id="u1") == 0.9
    assert calls == [("u1", "relevance.dedup")]


def test_unregistered_knob_skips_the_overlay_tier_entirely(eng, monkeypatch):
    # THE R10 sabotage: replace the KNOB_EXPERIMENTS lookup with "merge every
    # running experiment's model_overlay" ⇒ variant_overlay gets called and the
    # experiment's 0.9 wins over the operator's 0.42. Both asserts fail.
    _put(eng, "dedup_overlap_tau", 0.42)
    calls = _overlay_spy(monkeypatch, {"dedup_overlap_tau": 0.9}, [])

    assert cfg.resolve("dedup_overlap_tau", 0.75, user_id="u1") == 0.42
    assert calls == []          # the overlay was never consulted


def test_per_user_setting_beats_overlay_and_model_config(eng, monkeypatch):
    # SABOTAGE: reorder tiers 1 and 2 (overlay first) ⇒ 0.9, fails.
    _put(eng, "dedup_overlap_tau", 0.42)
    monkeypatch.setattr(cfg, "KNOB_EXPERIMENTS",
                        {"dedup_overlap_tau": "relevance.dedup"})
    _overlay_spy(monkeypatch, {"dedup_overlap_tau": 0.9}, [])
    monkeypatch.setitem(cfg.USER_SETTING_PROVIDERS,
                        "dedup_overlap_tau", lambda uid: 0.1)

    assert cfg.resolve("dedup_overlap_tau", 0.75, user_id="u1") == 0.1


def test_user_provider_returning_none_falls_through(eng, monkeypatch):
    # SABOTAGE: treat a provider's None as 0.0 (`float(v or 0)`) ⇒ 0.0, fails.
    _put(eng, "dedup_overlap_tau", 0.42)
    monkeypatch.setitem(cfg.USER_SETTING_PROVIDERS,
                        "dedup_overlap_tau", lambda uid: None)

    assert cfg.resolve("dedup_overlap_tau", 0.75, user_id="u1") == 0.42


def test_raising_provider_and_broken_overlay_fail_open(eng, monkeypatch):
    # SABOTAGE: remove either try/except ⇒ the exception escapes into the
    # serving path instead of degrading to the model_config value.
    _put(eng, "dedup_overlap_tau", 0.42)

    def boom(_uid):
        raise RuntimeError("pref store down")

    def boom_overlay(*_a, **_k):
        raise RuntimeError("experiment cache down")

    monkeypatch.setitem(cfg.USER_SETTING_PROVIDERS, "dedup_overlap_tau", boom)
    monkeypatch.setattr(cfg, "KNOB_EXPERIMENTS",
                        {"dedup_overlap_tau": "relevance.dedup"})
    monkeypatch.setattr(experiments, "variant_overlay", boom_overlay)

    assert cfg.resolve("dedup_overlap_tau", 0.75, user_id="u1") == 0.42


def test_anonymous_call_skips_both_user_scoped_tiers(eng, monkeypatch):
    # SABOTAGE: consult the overlay/provider with user_id=None ⇒ variant_overlay
    # is called with a None unit and the provider blows up on None.
    _put(eng, "dedup_overlap_tau", 0.42)
    monkeypatch.setattr(cfg, "KNOB_EXPERIMENTS",
                        {"dedup_overlap_tau": "relevance.dedup"})
    calls = _overlay_spy(monkeypatch, {"dedup_overlap_tau": 0.9}, [])
    seen = []
    monkeypatch.setitem(cfg.USER_SETTING_PROVIDERS, "dedup_overlap_tau",
                        lambda uid: seen.append(uid) or 0.1)

    assert cfg.resolve("dedup_overlap_tau", 0.75) == 0.42
    assert calls == [] and seen == []


def test_knob_experiments_is_a_registry_not_a_stub():
    # SABOTAGE: delete KNOB_EXPERIMENTS (or make it a set/list) ⇒ P1 has no
    # place to register a knob and the overlay tier quietly dies. Empty at P0
    # is correct; the wrong *type* is not.
    assert isinstance(cfg.KNOB_EXPERIMENTS, dict)


# ---------------------------------------------------------------------------
# valve() — resolver-exempt operational kill switches (T-28's intent)
# ---------------------------------------------------------------------------

def test_absent_valve_key_means_the_pass_runs(eng):
    # SABOTAGE: flip the polarity (default 1.0, or "absent ⇒ disabled") ⇒ a
    # missing/typo'd key silently stops a pass. Fails here.
    assert cfg.valve("cron.pass_disabled.flag_agg") == 0.0


def test_valve_reads_model_config_directly(eng):
    # SABOTAGE: point valve() at anything other than the model_config row ⇒ 0.0.
    _put(eng, "cron.pass_disabled.flag_agg", 1.0)
    assert cfg.valve("cron.pass_disabled.flag_agg") == 1.0
    _put(eng, "ingest.daily_budget", 2000.0)
    assert cfg.valve("ingest.daily_budget", 0.0) == 2000.0


def test_valve_ignores_experiment_overlay_and_per_user_setting(eng, monkeypatch):
    # THE T-28 test. An experiment must never resurrect a killed pass or raise
    # the ingest budget (HLD §2.1).
    # SABOTAGE: route valve() through resolve() ⇒ the overlay's 0.0 un-kills the
    # pass and the provider's 99999 raises the budget. Both asserts fail, and
    # the "overlay never consulted" assert fails too.
    _put(eng, "cron.pass_disabled.flag_agg", 1.0)     # operator killed it
    _put(eng, "ingest.daily_budget", 2000.0)
    monkeypatch.setattr(cfg, "KNOB_EXPERIMENTS", {
        "cron.pass_disabled.flag_agg": "relevance.revive",
        "ingest.daily_budget": "relevance.revive",
    })
    calls = _overlay_spy(monkeypatch, {"cron.pass_disabled.flag_agg": 0.0,
                                       "ingest.daily_budget": 99999.0}, [])
    monkeypatch.setitem(cfg.USER_SETTING_PROVIDERS,
                        "ingest.daily_budget", lambda uid: 99999.0)

    assert cfg.valve("cron.pass_disabled.flag_agg") == 1.0   # still dead
    assert cfg.valve("ingest.daily_budget") == 2000.0        # still capped
    assert calls == []


def test_resolve_refuses_valve_keys(eng):
    # SABOTAGE: let valves flow through resolve() ⇒ no error is raised, and the
    # only thing standing between an experiment and a killed pass is caller
    # discipline. Belt to T-28's braces.
    for key in ("cron.pass_disabled.flag_agg", "ingest.daily_budget"):
        with pytest.raises(ValueError):
            cfg.resolve(key, 0.0, user_id="u1")


def test_valve_refuses_ordinary_knobs(eng):
    # SABOTAGE: widen the whitelist (or drop the check) ⇒ any knob becomes a
    # valve and silently bypasses D10 precedence.
    _put(eng, "dedup_overlap_tau", 0.42)
    with pytest.raises(ValueError):
        cfg.valve("dedup_overlap_tau", 0.75)


def test_valve_is_uncached_so_a_kill_bites_immediately(eng):
    # SABOTAGE: serve valve() from the resolve() snapshot cache ⇒ the pass keeps
    # running for the TTL window after the operator kills it. This writes the
    # row WITHOUT resetting the cache, so a cached valve returns the stale 0.0.
    assert cfg.valve("cron.pass_disabled.flag_agg") == 0.0
    with eng.begin() as conn:
        conn.execute(insert(model_config_table).values(
            key="cron.pass_disabled.flag_agg", value=1.0, description="kill"))
    assert cfg.valve("cron.pass_disabled.flag_agg") == 1.0


def test_resolver_survives_a_missing_model_config_table(tmp_path, monkeypatch):
    # SABOTAGE: let the snapshot exception escape ⇒ every relevance read dies
    # when the DB is unreachable, instead of falling back to code defaults.
    e = create_engine(f"sqlite:///{tmp_path / 'empty.db'}",
                      connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_module, "engine", e)
    cfg._reset_cache()
    assert cfg.resolve("dedup_overlap_tau", 0.75) == 0.75
    assert cfg.valve("cron.pass_disabled.flag_agg") == 0.0


# ---------------------------------------------------------------------------
# T-28 — the lint itself
# ---------------------------------------------------------------------------

_RELEVANCE_DIR = pathlib.Path(__file__).resolve().parents[2] / "backend" / "relevance"

# Modules allowed to touch model_config directly. config.py owns the read path
# (resolve + the valve mechanism); nothing else gets to.
_MODEL_CONFIG_WHITELIST = {"config.py"}

# Modules allowed to CALL valve(). The pass registry (B1) is the first
# legitimate caller: `cron.pass_disabled.<name>` is an operational kill switch,
# and HLD §2.1 makes valves deliberately resolver-exempt so no experiment
# overlay or per-user setting can resurrect a pass an operator killed. Adding a
# name here is meant to be a visible, arguable diff — that is the whole point
# of the lint, so extend it, never delete it.
_VALVE_CALLER_WHITELIST: set[str] = {"registry.py"}

_VALVE_CALL = re.compile(r"\bvalve\s*\(")


def _relevance_sources():
    return sorted(p for p in _RELEVANCE_DIR.rglob("*.py")
                  if "__pycache__" not in p.parts)


def _references_model_config_in_code(path) -> bool:
    """True iff the file references model_config in CODE, not in prose.

    Deliberately AST-based rather than a substring scan. A raw
    `"model_config" in source` also matches comments and docstrings, so a
    module that merely *explains* why it routes through resolve() gets
    flagged — a false positive that trains people to weaken the lint, which
    is worse than not having it. Comments never reach the AST at all;
    docstrings do, so they are subtracted explicitly.

    Still catches every real bypass: imports (`from ..database import
    model_config_table`), attribute access, and raw SQL/key strings.
    """
    import ast
    tree = ast.parse(path.read_text(), filename=str(path))

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and "model_config" in node.id:
            return True
        if isinstance(node, ast.Attribute) and "model_config" in node.attr:
            return True
        if isinstance(node, ast.alias):
            if "model_config" in (node.name or "") or \
               "model_config" in (node.asname or ""):
                return True
        if isinstance(node, ast.ImportFrom) and "model_config" in (node.module or ""):
            return True
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings
                and "model_config" in node.value):
            return True
    return False


def test_t28_no_model_config_reads_outside_config_py():
    # SABOTAGE: add `from ..database import model_config_table` to any other
    # module in backend/relevance/ (the R10 resolver bypass) ⇒ this fails and
    # names the file. Also caught: attribute access and raw SQL strings.
    offenders = [str(p.relative_to(_RELEVANCE_DIR))
                 for p in _relevance_sources()
                 if p.name not in _MODEL_CONFIG_WHITELIST
                 and _references_model_config_in_code(p)]
    assert offenders == [], (
        f"model_config read outside config.py: {offenders}. "
        "Relevance knobs go through resolve(); valves through valve().")


def test_t28_model_config_lint_ignores_prose_but_catches_code(tmp_path):
    # SABOTAGE: revert the lint to a substring scan ⇒ the prose case below
    # trips it, and the lint starts crying wolf on documentation. The two
    # code cases must stay caught, or the lint is decorative.
    prose = tmp_path / "prose.py"
    prose.write_text(
        '"""Knobs route through resolve(); never read model_config here."""\n'
        "# model_config is off-limits in this module\n"
        "X = 1\n")
    assert not _references_model_config_in_code(prose)

    imported = tmp_path / "imported.py"
    imported.write_text("from backend.database import model_config_table\n")
    assert _references_model_config_in_code(imported)

    sql = tmp_path / "sql.py"
    sql.write_text('Q = "SELECT value FROM model_config WHERE key = ?"\n')
    assert _references_model_config_in_code(sql)


def test_t28_no_valve_callers_outside_the_whitelist():
    # SABOTAGE: call valve() from a derive pass to read an ordinary knob ⇒ the
    # knob escapes D10 precedence. Adding the caller to the whitelist is a
    # deliberate, reviewable diff.
    allowed = _MODEL_CONFIG_WHITELIST | _VALVE_CALLER_WHITELIST
    offenders = [str(p.relative_to(_RELEVANCE_DIR))
                 for p in _relevance_sources()
                 if p.name not in allowed and _VALVE_CALL.search(p.read_text())]
    assert offenders == [], f"unwhitelisted valve() callers: {offenders}"


def test_t28_lint_actually_scans_something():
    # SABOTAGE: point the lint at the wrong directory (a rename, a moved test)
    # ⇒ it scans zero files and passes vacuously forever.
    names = {p.name for p in _relevance_sources()}
    assert {"config.py", "batch.py", "__init__.py"} <= names


def test_relevance_package_imports_no_flask():
    # SABOTAGE (D12): import Flask anywhere in the package — directly, or
    # transitively via backend.server — ⇒ the passes stop being unit-testable
    # without an app context. Checked in a clean interpreter, because this
    # test process has already imported plenty.
    import subprocess
    import sys

    repo_root = _RELEVANCE_DIR.parents[1]
    probe = ("import sys;"
             "import backend.relevance, backend.relevance.batch,"
             " backend.relevance.config;"
             "sys.exit(1 if 'flask' in sys.modules else 0)")
    r = subprocess.run([sys.executable, "-c", probe], cwd=repo_root,
                       capture_output=True, text=True)
    assert r.returncode == 0, (
        f"backend.relevance pulls in Flask at import time.\n{r.stderr}")
