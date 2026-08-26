"""M1 — the model_config knob log (fit-challenger measurement rail).

Pins the LLD §5.1/§6.3 contract:

  - set_config() stamps model_config.updated_at AND appends a
    model_config_changes row (key, old_value, new_value, changed_at, source)
    in one transaction, and returns old_value.
  - Unknown keys still raise KeyError, and no change row is written.
  - PUT /api/admin/config/<key> passes body["source"] through (default
    "admin-api") and its response carries old_value.
  - The migration is additive and idempotent: an old-schema DB gains
    updated_at + the model_config_changes table with pre-existing rows
    (including manually-tuned values) untouched, updated_at NULL until a
    key's first logged write.
  - All 17 fit/bakeoff knobs are seeded in _MODEL_CONFIG_DEFAULTS so
    set_config / the PUT route never KeyError on them (HLD F-1).

Per PRD-build's PR-M note, the logging tests exercise an ALREADY-registered
live knob (max_overpay_frac), not a fit_* key — the fit keys get their own
route-level variants in PR-F2.

Harness: test_analytics_p0.py idiom — file-backed SQLite engine patched into
backend.database; Flask test client with X-Cron-Secret for the route test.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, insert, select, text

import backend.database as db_module
import backend.server as server
from backend.database import (
    metadata,
    model_config_changes_table,
    model_config_table,
)

SECRET = "unit-test-cron-secret"

#: The 17 fit-challenger knobs (LLD §4 — final count) with their defaults.
_FIT_KNOBS = {
    "fit_score_scale":           400.0,
    "fit_score_even":             50.0,
    "fit_w_board":                 0.40,
    "fit_w_div":                   0.30,
    "fit_w_cons":                  0.30,
    "fit_pool_consensus":          8.0,
    "fit_pool_div_seed":           8.0,
    "fit_pool_div_opp":            8.0,
    "fit_pool_cap":               15.0,
    "fit_max_packages_per_pair": 20000.0,
    "fit_expand_from":            25.0,
    "fit_min_them":                0.0,
    "fit_min_aggregate":           0.0,
    "fit_r5_mode":                 1.0,
    "fit_junk_floor":              0.0,
    "bakeoff_include_fit":         0.0,
    "bakeoff_serve_fit":           0.0,
}


def _engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'cfg.db'}",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    return eng


def _seed(eng, key="max_overpay_frac", value=0.25):
    with eng.begin() as conn:
        conn.execute(insert(model_config_table).values(
            key=key, value=value, description="seeded by test"))


def _config_row(eng, key):
    with eng.connect() as conn:
        return conn.execute(
            select(model_config_table).where(model_config_table.c.key == key)
        ).fetchone()


def _change_rows(eng):
    with eng.connect() as conn:
        return conn.execute(
            select(model_config_changes_table)
            .order_by(model_config_changes_table.c.id)
        ).fetchall()


# ---------------------------------------------------------------------------
# set_config — the single write funnel
# ---------------------------------------------------------------------------

def test_set_config_logs_change(tmp_path):
    eng = _engine(tmp_path)
    _seed(eng)                                     # live knob, default 0.25
    with patch.object(db_module, "engine", eng):
        result = db_module.set_config("max_overpay_frac", 0.30, source="test")

    assert result == {"key": "max_overpay_frac", "value": 0.30,
                      "old_value": 0.25}

    row = _config_row(eng, "max_overpay_frac")
    assert row.value == 0.30
    assert row.updated_at is not None              # stamped in the same txn

    changes = _change_rows(eng)
    assert len(changes) == 1
    ch = changes[0]
    assert ch.key == "max_overpay_frac"
    assert ch.old_value == 0.25
    assert ch.new_value == 0.30
    assert ch.source == "test"
    assert ch.changed_at == row.updated_at         # one instant, one txn


def test_set_config_unknown_key_still_raises(tmp_path):
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng):
        with pytest.raises(KeyError):
            db_module.set_config("no_such_knob_ever", 1.0, source="test")
    assert _change_rows(eng) == []                 # nothing logged


# ---------------------------------------------------------------------------
# PUT /api/admin/config/<key> — source pass-through + old_value
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    return server.app.test_client()


def _put(client, key, body):
    return client.put(f"/api/admin/config/{key}",
                      headers={"X-Cron-Secret": SECRET},
                      data=json.dumps(body),
                      content_type="application/json")


def test_admin_put_stamps_source(tmp_path, client):
    eng = _engine(tmp_path)
    _seed(eng)
    with patch.object(db_module, "engine", eng), \
         patch.object(server, "_CRON_SECRET", SECRET), \
         patch.object(server, "_IS_PROD_ENV", True), \
         patch.object(server._trade_service_mod, "reload_config", MagicMock()), \
         patch.object(server._ranking_service_mod, "reload_config", MagicMock()):
        # explicit source rides through to the change row
        resp = _put(client, "max_overpay_frac",
                    {"value": 0.30, "source": "operator"})
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["old_value"] == 0.25        # response gains old_value
        assert payload["value"] == 0.30

        # no source => "admin-api"
        resp2 = _put(client, "max_overpay_frac", {"value": 0.25})
        assert resp2.status_code == 200

    changes = _change_rows(eng)
    assert [c.source for c in changes] == ["operator", "admin-api"]
    assert changes[1].old_value == 0.30            # chained old_value


def test_admin_put_unknown_key_404s(tmp_path, client):
    """set_knob.py refusal case 2 depends on this exact status."""
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng), \
         patch.object(server, "_CRON_SECRET", SECRET), \
         patch.object(server, "_IS_PROD_ENV", True):
        resp = _put(client, "no_such_knob_ever", {"value": 1.0})
    assert resp.status_code == 404
    assert _change_rows(eng) == []


# ---------------------------------------------------------------------------
# Migration — additive + idempotent
# ---------------------------------------------------------------------------

def _schema_dump(eng):
    with eng.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
    return [tuple(r) for r in rows]


def test_migration_additive(tmp_path):
    """_migrate_db() twice on a pre-M1 DB: pre-existing (manually-tuned)
    model_config rows untouched, updated_at added and NULL until the first
    logged write, model_config_changes created, second run a no-op."""
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}",
                        connect_args={"check_same_thread": False})
    # Recreate the PRE-M1 model_config shape by hand, with a manually-tuned
    # row that a re-deploy must never clobber (INSERT OR IGNORE contract).
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE model_config ("
            "  key VARCHAR PRIMARY KEY, value FLOAT NOT NULL,"
            "  description VARCHAR)"))
        conn.execute(text(
            "INSERT INTO model_config (key, value, description) "
            "VALUES ('vet_age', 99.0, 'manually tuned')"))
    metadata.create_all(eng)   # rest of the schema; existing table untouched

    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "DATABASE_URL", "sqlite:///m1"):
        db_module._migrate_db()
        dump1 = _schema_dump(eng)
        db_module._migrate_db()
        dump2 = _schema_dump(eng)
    assert dump1 == dump2, "second _migrate_db() run changed the schema"

    row = _config_row(eng, "vet_age")
    assert row.value == 99.0                       # tuned value survived, twice
    assert row.updated_at is None                  # no backfill
    assert _change_rows(eng) == []                 # migration logs nothing

    # updated_at flips non-NULL only on the first funneled write.
    with patch.object(db_module, "engine", eng):
        db_module.set_config("vet_age", 27.0, source="test")
    row = _config_row(eng, "vet_age")
    assert row.value == 27.0
    assert row.updated_at is not None


def test_fit_knob_defaults_seeded(tmp_path):
    """All 17 fit/bakeoff knobs (LLD §4) are registered so set_config and
    the PUT route never KeyError on them — the HLD F-1 trap."""
    seeded = {k: v for k, v, _d in db_module._MODEL_CONFIG_DEFAULTS}
    for key, default in _FIT_KNOBS.items():
        assert key in seeded, f"missing _MODEL_CONFIG_DEFAULTS row: {key}"
        assert seeded[key] == default, (
            f"{key}: seeded {seeded[key]}, LLD §4 says {default}")

    # And they land in the DB via migration, writable through the funnel.
    eng = _engine(tmp_path)
    with patch.object(db_module, "engine", eng), \
         patch.object(db_module, "DATABASE_URL", "sqlite:///m1"):
        db_module._migrate_db()
        assert _config_row(eng, "fit_score_scale").value == 400.0
        result = db_module.set_config("bakeoff_serve_fit", 1.0, source="test")
    assert result["old_value"] == 0.0
