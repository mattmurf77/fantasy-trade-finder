"""backend.eval.redaction: the deletion scrub's hook for the value-model
store (models-lead E-b3). Every record's partner_rates keys naming a deleted
user, as viewer or partner, take that user's token; rates, other keys and
unparseable lines are kept; the rewrite is atomic and idempotent, and the
serve-time cache reloads it."""

import json
import os

import pytest

from backend import value_model as vm
from backend.eval import redaction
from backend.eval.contract import REDACTED_PARTNER_PREFIX

TOKEN = f"{REDACTED_PARTNER_PREFIX}9f0c"


def _model(rates):
    return vm.ValueModel(
        like_head=vm.LogisticHead(weights={"bias": -0.4}), propose_head=None,
        propose_constant=0.2, partner_rates=rates, global_like_rate=0.3, position_mean=0.4,
        trained_at="t", train_date="2026-10-27")


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("VALUE_MODEL_DIR", str(tmp_path))
    vm.append_model(_model({"gone|p1": 0.7, "u1|gone": 0.4, "u1|p2": 0.5}))
    with open(vm.models_path(), "a", encoding="utf-8") as fh:
        fh.write("{torn\n")
    vm.append_model(_model({"u2|gone": 0.6, "u2|p3": 0.2}))
    return vm.models_path()


def _rates(path):
    out = []
    for line in open(path, encoding="utf-8").read().splitlines():
        try:
            out.append(json.loads(line)["model"]["partner_rates"])
        except json.JSONDecodeError:
            out.append(line)
    return out


def test_every_key_naming_the_deleted_user_takes_the_token(store):
    assert redaction.redact_model_store({"gone": TOKEN}) == 3
    assert _rates(store) == [
        {f"{TOKEN}|p1": 0.7, f"u1|{TOKEN}": 0.4, "u1|p2": 0.5},
        "{torn",
        {f"u2|{TOKEN}": 0.6, "u2|p3": 0.2},
    ]
    assert "gone" not in open(store, encoding="utf-8").read()


def test_a_re_run_changes_nothing_and_no_temp_file_is_left(store):
    redaction.redact_model_store({"gone": TOKEN})
    before = open(store, encoding="utf-8").read()
    assert redaction.redact_model_store({"gone": TOKEN}) == 0
    assert open(store, encoding="utf-8").read() == before
    assert [f for f in os.listdir(os.path.dirname(store)) if f.endswith(".redact")] == []


def test_the_serve_cache_reloads_the_redacted_model(store):
    assert vm.load_latest_model().partner_rates == {"u2|gone": 0.6, "u2|p3": 0.2}
    redaction.redact_model_store({"gone": TOKEN})
    assert vm.load_latest_model().partner_rates == {f"u2|{TOKEN}": 0.6, "u2|p3": 0.2}


def test_nothing_to_do_returns_0(store, tmp_path):
    assert redaction.redact_model_store({}) == 0
    assert redaction.redact_model_store({"nobody": TOKEN}) == 0
    assert redaction.redact_model_store({"gone": TOKEN}, path=str(tmp_path / "absent")) == 0


def test_a_store_that_keeps_changing_raises_for_the_scrub_to_retry(store, monkeypatch):
    """An append between the read and the replace (the nightly fit) makes it
    read again; one that never stops raises, and the file is untouched."""
    before = open(store, encoding="utf-8").read()
    ticks = iter(range(100))
    monkeypatch.setattr(redaction, "_signature", lambda path: next(ticks))
    with pytest.raises(RuntimeError, match="kept changing"):
        redaction.redact_model_store({"gone": TOKEN})
    assert open(store, encoding="utf-8").read() == before
