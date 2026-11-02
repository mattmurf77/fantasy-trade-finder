"""G-068 rule at the server-written stamps (head-eng, 2026-10-31).

Scope: docs/plans/win-now/scope-device-type-source.md. A missing client
signal must never be stored as another client's name. Three sites used to
guess "web" (or pass X-Source through raw); `backend/client_device.py` now
resolves them in one place:

  * overhaul `fire()` → `user_events.device_type`
  * win_now search → `device_type` and `props.platform`
  * GET /api/feature-flags → the experiment `platform` targeting attribute

Every case asserts the value passed to `record_event` / `resolve_for_unit`.
The overhaul and win_now cases reuse those suites' harnesses.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine

import backend.database as db_module
import backend.experiments as experiments
import backend.server as server
from backend.tests.test_overhaul_api import api, world, _create, _h, _settings  # noqa: F401 (fixtures)
from backend.tests.test_win_now_api import evaluate_body, harness  # noqa: F401 (fixture)


# ── overhaul fire() ─────────────────────────────────────────────────────────

def _overhaul_device_type(api, world, headers):
    v = _create(api)
    v = _settings(api, v["overhaul_id"], v["revision"], outlook="push_all_in",
                  eligible_asset_ids=["A", "B", "C", "D", "E"])
    r = api.post(f"/api/overhauls/{v['overhaul_id']}/generate", json={"revision": v["revision"]},
                 headers={**_h(), **headers})
    assert r.status_code == 200, r.get_json()
    name, _props, device_type = world.events[-1]
    assert name == "overhaul_generation_completed"
    return device_type


def test_overhaul_no_client_signal_stores_null_not_web(api, world):
    device_type = _overhaul_device_type(api, world, {})
    assert device_type is None
    assert device_type != "web"


@pytest.mark.parametrize("headers,expected", [
    ({"X-Device": "iphone"}, "iphone"),
    ({"X-Source": "web"}, "web"),
    ({"X-Source": "api"}, None),
], ids=["x-device-iphone", "x-source-web", "x-source-api"])
def test_overhaul_device_type_resolution(api, world, headers, expected):
    assert _overhaul_device_type(api, world, headers) == expected


# ── win_now search ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("headers,device_type,platform", [
    ({}, None, None),
    ({"X-Source": "web"}, "web", "web"),
    ({"X-Source": "extension"}, "extension", "extension"),
    ({"X-Device": "iphone"}, "iphone", "ios"),
    ({"X-Device": "android"}, "android", "android"),
    ({"X-Source": "server"}, None, None),
], ids=["headerless", "x-source-web", "x-source-extension", "x-device-iphone",
        "x-device-android", "x-source-server"])
def test_win_now_search_stamps(harness, headers, device_type, platform):
    r = harness.client.post("/api/win-now/search", json=evaluate_body(), headers=headers)
    assert r.status_code == 202, r.get_json()
    (args, kwargs), = harness.events
    assert args[1] == "win_now_objective_selected"
    assert kwargs["device_type"] == device_type
    assert kwargs["props"]["platform"] == platform


# ── GET /api/feature-flags header_attrs["platform"] ─────────────────────────

@pytest.fixture()
def flags_client(monkeypatch):
    captured = []

    def resolve(unit, attrs=None):
        captured.append((unit, attrs))
        return {}, {}

    # The route swallows every exception, so each case asserts the capture.
    monkeypatch.setattr(experiments, "resolve_for_unit", resolve)
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db_module.metadata.create_all(eng)
    server.app.config["TESTING"] = True
    with patch.object(db_module, "engine", eng):
        yield server.app.test_client(), captured
    eng.dispose()


@pytest.mark.parametrize("headers,expected", [
    ({"X-Source": "web"}, "web"),
    ({"X-Source": "extension"}, "extension"),
    ({"X-Source": "api"}, None),
    ({"X-Source": "mobile"}, None),
    ({"X-Source": "foo"}, None),
    ({"X-Source": "mobile", "X-Device": "iphone"}, "ios"),
    ({"X-Device": "ipad"}, "ios"),
    ({}, None),
], ids=["web", "extension", "api", "mobile", "foo", "mobile+iphone", "ipad", "nothing"])
def test_feature_flags_platform_attribute(flags_client, headers, expected):
    client, captured = flags_client
    r = client.get("/api/feature-flags", headers={"X-Device-Id": "dev_g068", **headers})
    assert r.status_code == 200
    assert [unit for unit, _ in captured] == ["device:dev_g068"]
    assert captured[0][1]["platform"] == expected
