"""Founders' review, use case 2: the decline waterfall's routes and its run (rule-waterfall-design.md §7).

Runs on the owner worker harness with production's flags (``test_trade_fast_deck.production``:
owner-only serving of revision 2, rules-first construction, likes-you, decline suppression,
standing offers, suggestion telemetry, significance enforced, quality filters), the real
generator and an isolated SQLite engine. No network, no production database.

- The founder gate on every new route (flag off, allow-list unset or blank, account not listed,
  unverified session, demo session, a device id or body identity never grants): 404 and no
  state change. The operator read needs the cron secret.
- The run's lifecycle: POST 202 -> GET running -> a second POST 409 -> complete; the 60-second
  cap fails the run with a clear error; a deck that is not built rules-first is "unsupported";
  a league other than the session's selected one is 400; a restart (empty memory) reads "none".
- Honesty: the run's waterfall equals ``rule_waterfall.compute`` on the inputs a real job for
  the same founder and league builds, and its served count equals the size of the deck that real
  job publishes (liked trades added on top included).
- Isolation: a run writes nothing a real request reads (every database table, the job tables,
  the session's card store and significance provenance, the session itself, analytics events),
  and the founder's next real deck is the same with or without a run in between.
- A real job (probe None) is unchanged: the probe is one guarded call, and the job's output is
  byte-identical with the probe absent (the freeze and golden suites run unchanged too).
- Notes through the routes: save, edit, clear, history, cap, unknown rule, rate limit; the
  operator read lists every version with author "founder" and no account id.
- Aggregate-only output.
"""
import ast
import copy
import functools
import inspect
import json
import textwrap

import pytest
from sqlalchemy import select

from backend import database as db, feature_flags as ff, rule_catalog as rc, rule_waterfall as rw
from backend import server, trade_fast_deck as fast, trade_service as ts
from backend.tests.test_trade_fast_deck import (  # noqa: F401  (fixtures)
    GENERATED, LIKED, LEAGUE, ME, OPP, TOKEN, harness, like, owner_harness, production, revised, run)
from backend.tests.test_fair_packages import OPP2, SEED
from backend.tests.test_rule_waterfall import check_sums

ROUTES = (("GET", f"/api/founder/rule-waterfall?league_id={LEAGUE}"),
          ("POST", "/api/founder/rule-waterfall"),
          ("GET", "/api/founder/rule-notes/market_floor"),
          ("PUT", "/api/founder/rule-notes/market_floor"))


def H(**extra):
    return {"X-Session-Token": TOKEN, **extra}


@pytest.fixture
def founder(production, monkeypatch):
    ff._flags_cache["deck.rules_first"] = True
    ff._flags_cache["founder.review"] = True
    monkeypatch.setenv("FOUNDER_ACCOUNTS", f"someone-else, {ME}")
    monkeypatch.setattr(server, "_rule_waterfall_results", {})
    monkeypatch.setattr(server, "_rule_waterfall_running", None)
    monkeypatch.setattr(server, "_rule_note_saves", {})
    threads = []
    monkeypatch.setattr(server, "_start_trade_job_thread",
                        lambda *, target, args, kwargs: threads.append((target, args, kwargs)))
    client = production[0]
    return client, threads


def call(client, method, path, **kwargs):
    return getattr(client, method.lower())(path, **kwargs)


def start_and_finish(client, threads, **job_kwargs):
    response = client.post("/api/founder/rule-waterfall", json={"league_id": LEAGUE}, headers=H())
    assert response.status_code == 202, response.json
    target, args, kwargs = threads.pop()
    target(*args, **{**kwargs, **job_kwargs})
    return client.get(f"/api/founder/rule-waterfall?league_id={LEAGUE}", headers=H()).json


def all_rows():
    with db.engine.connect() as conn:
        return {t.name: sorted(map(repr, (tuple(r) for r in conn.execute(select(t)))))
                for t in db.metadata.sorted_tables}


# ── the gate ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("case", ["flag_off", "env_unset", "env_blank", "not_listed", "unverified",
                                  "demo", "no_token", "device_id", "body_identity"])
def test_every_route_is_refused_404_with_no_state_change(founder, monkeypatch, case):
    """Sabotage: drop the founder check from one of the new routes."""
    client, threads = founder
    sess = server._sessions[TOKEN]
    headers = H()
    if case == "flag_off":
        ff._flags_cache["founder.review"] = False
    elif case == "env_unset":
        monkeypatch.delenv("FOUNDER_ACCOUNTS")
    elif case == "env_blank":
        monkeypatch.setenv("FOUNDER_ACCOUNTS", " , ")
    elif case == "not_listed":
        monkeypatch.setenv("FOUNDER_ACCOUNTS", "someone-else")
    elif case == "unverified":
        monkeypatch.setitem(sess, "verified", False)
    elif case == "demo":
        monkeypatch.setitem(sess, "user_id", "demo_user_1")
        monkeypatch.setitem(sess, "is_demo", True)
        monkeypatch.setenv("FOUNDER_ACCOUNTS", "demo_user_1")
    elif case == "no_token":
        headers = {}
    elif case in ("device_id", "body_identity"):
        monkeypatch.setenv("FOUNDER_ACCOUNTS", "the-founder")
        headers = H(**{"X-Device-Id": "the-founder", "X-User-Id": "the-founder"})
    body = {"league_id": LEAGUE, "body": "a question",
            **({"user_id": "the-founder", "account_id": "the-founder"} if case == "body_identity" else {})}
    before = all_rows()
    for method, path in ROUTES:
        response = call(client, method, path, json=body, headers=headers)
        assert response.status_code == 404 and response.json == {"error": "not_found"}, (method, path)
    assert threads == [] and server._rule_waterfall_running is None
    assert server._rule_waterfall_results == {} and all_rows() == before


def test_the_operator_read_needs_the_cron_secret(founder, monkeypatch):
    client, _ = founder
    monkeypatch.setattr(server, "_CRON_SECRET", "s3cret")
    assert client.get("/api/admin/founder/rule-notes").status_code == 401
    assert client.get("/api/admin/founder/rule-notes", headers={"X-Cron-Secret": "wrong"}).status_code == 401
    assert client.get("/api/admin/founder/rule-notes", headers={"X-Cron-Secret": "s3cret"}).status_code == 200


# ── the run ─────────────────────────────────────────────────────────────────────────────────

def test_before_any_run_the_page_lists_every_rule_from_the_catalog(founder):
    client, _ = founder
    body = client.get(f"/api/founder/rule-waterfall?league_id={LEAGUE}", headers=H()).json
    assert body["status"] == "none" and body["waterfall"] is None and body["run_at"] is None
    assert [r["key"] for r in body["catalog"]] == [r.key for r in rc.RULES]
    assert all(r["name"] and r["description"] for r in body["catalog"])
    assert not any("source" in r or "counted" in r for r in body["catalog"])
    assert body["notes"] == []


def test_a_run_goes_running_then_complete_and_a_second_start_is_409(founder):
    """Sabotage: drop the one-run lock (the second POST starts another run)."""
    client, threads = founder
    response = client.post("/api/founder/rule-waterfall", json={"league_id": LEAGUE}, headers=H())
    assert response.status_code == 202 and response.json["status"] == "running" and response.json["run_id"]
    assert client.get(f"/api/founder/rule-waterfall?league_id={LEAGUE}", headers=H()).json["status"] == "running"
    again = client.post("/api/founder/rule-waterfall", json={"league_id": LEAGUE}, headers=H())
    assert again.status_code == 409 and again.json == {"error": "run_in_progress"} and len(threads) == 1
    target, args, kwargs = threads.pop()
    target(*args, **kwargs)
    body = client.get(f"/api/founder/rule-waterfall?league_id={LEAGUE}", headers=H()).json
    assert body["status"] == "complete" and body["error"] is None and body["run_at"]
    out = body["waterfall"]
    check_sums(out)
    assert out["basis"] == "diagnostic_full_solve" and out["started_definition"] == rw.STARTED_DEFINITION
    assert out["started"] > out["served"] > 0
    assert server._rule_waterfall_running is None
    assert client.post("/api/founder/rule-waterfall", json={"league_id": LEAGUE}, headers=H()).status_code == 202


def test_the_cap_fails_the_run_with_a_clear_error_and_keeps_the_last_result(founder, monkeypatch):
    """Sabotage: ignore the deadline in the run's work check."""
    client, threads = founder
    first = start_and_finish(client, threads)
    assert first["status"] == "complete"
    body = start_and_finish(client, threads, cap_s=-1.0)
    assert body["status"] == "failed"
    assert body["error"] == "The run took longer than 60 seconds and was stopped."
    assert body["waterfall"] == first["waterfall"] and body["run_at"] == first["run_at"]
    assert server._rule_waterfall_running is None and not any(
        j.get("source") == server._RULE_WATERFALL_SOURCE for j in server._trade_jobs.values())


def test_a_deck_not_built_rules_first_is_unsupported(founder):
    client, threads = founder
    ts._cfg["bakeoff_owner_only"] = 0.
    response = client.post("/api/founder/rule-waterfall", json={"league_id": LEAGUE}, headers=H())
    assert response.status_code == 200 and response.json["status"] == "unsupported" and threads == []
    body = client.get(f"/api/founder/rule-waterfall?league_id={LEAGUE}", headers=H()).json
    assert body["status"] == "unsupported" and "rules-first" in body["error"]
    ts._cfg["bakeoff_owner_only"] = 1.
    ff._flags_cache["deck.rules_first"] = False
    assert client.post("/api/founder/rule-waterfall", json={"league_id": LEAGUE},
                       headers=H()).json["status"] == "unsupported"


def test_the_probe_reports_unsupported_when_the_job_has_no_rules(founder, monkeypatch):
    """The scope check passed, but the job could not build the rules: the run stops anyway."""
    client, threads = founder
    monkeypatch.setattr(server, "_rules_first_deck_rules", lambda **kw: (_ for _ in ()).throw(RuntimeError("x")))
    body = start_and_finish(client, threads)
    assert body["status"] == "unsupported" and body["waterfall"] is None


def test_league_required_and_league_not_selected(founder):
    client, threads = founder
    assert client.post("/api/founder/rule-waterfall", json={}, headers=H()).json == {"error": "league_required"}
    assert client.get("/api/founder/rule-waterfall", headers=H()).status_code == 400
    response = client.post("/api/founder/rule-waterfall", json={"league_id": "other"}, headers=H())
    assert response.status_code == 400 and response.json == {"error": "league_not_selected"} and threads == []


def test_a_restart_reads_none(founder, monkeypatch):
    client, threads = founder
    assert start_and_finish(client, threads)["status"] == "complete"
    monkeypatch.setattr(server, "_rule_waterfall_results", {})      # a new process
    body = client.get(f"/api/founder/rule-waterfall?league_id={LEAGUE}", headers=H()).json
    assert (body["status"], body["waterfall"], body["run_at"]) == ("none", None, None)


# ── honesty: the same inputs as a real job, the same served count ─────────────────────────────

def test_the_run_equals_compute_on_a_real_jobs_inputs_and_its_published_deck(founder, monkeypatch):
    """Sabotage: give the run's probe a different fairness or drop the after-the-deck stages."""
    client, threads = founder
    like("calcq_liked", LIKED)            # fails a deck rule: added on top of the deck
    like("calcq_generated", GENERATED)    # the generator builds it: flagged in place
    # The run takes the fairness of the founder's last organic deck request (what
    # /api/trades/generate stores on the session); the harness's real job asks for 0.5.
    monkeypatch.setitem(server._sessions[TOKEN], "trade_fairness_threshold", .5)
    body = start_and_finish(client, threads)
    assert body["status"] == "complete", body
    ran = body["waterfall"]

    measured = []
    real = fast.serve

    def measure(generate, context, rules, *, check=None):
        stages = rw.server_stages(server, context=context, rules=rules, league=context["league"],
                                  league_id=LEAGUE, significance_capture=server._capture_trade_significance())
        measured.append(rw.compute(generate, context, rules, after=stages))
        return real(generate, context, rules, check=check)
    monkeypatch.setattr(fast, "serve", functools.wraps(real)(measure))
    job = run(monkeypatch)
    (expected,) = measured
    strip = lambda out: {k: v for k, v in out.items() if k != "elapsed_ms"}
    assert strip(ran) == strip(expected)
    assert ran["served"] == len(job["cards"]) and ran["added"] == 1
    assert ran["added"] == sum(c["trade_id"].startswith("likesyou_") for c in job["cards"])


# ── isolation ─────────────────────────────────────────────────────────────────────────────────

def memory_state():
    sess = server._sessions[TOKEN]
    svc = sess["trade_svc"]
    with server._trade_jobs_lock:
        jobs = {k: copy.copy(v) for k, v in server._trade_jobs.items()}
        by_key = dict(server._trade_jobs_by_key)
        selected = dict(server._selected_trade_jobs)
        epochs = dict(server._trade_input_epochs)
    return {"jobs": jobs, "by_key": by_key, "selected": selected, "epochs": epochs,
            "cards": dict(svc._trade_cards),
            "exemptions": copy.deepcopy(getattr(svc, "_significance_exemptions", None)),
            "session": {k: v for k, v in sess.items() if k != "last_active"},
            "members": [(m.user_id, list(m.roster), dict(m.elo_ratings)) for m in sess["league"].members]}


def test_a_run_writes_nothing_a_real_request_reads(founder, monkeypatch):
    """Sabotage: give the run the session's own trade service (no isolated card store), or let
    the job continue past the probe."""
    client, threads = founder
    like("calcq_liked", LIKED)
    first = run(monkeypatch)              # a real deck: its impressions, first page, cards
    rows, memory = all_rows(), memory_state()
    events = server.record_event.call_count
    body = start_and_finish(client, threads)
    assert body["status"] == "complete"
    assert all_rows() == rows
    assert memory_state() == memory
    assert server.record_event.call_count == events
    second = run(monkeypatch)             # the founder's next deck is the one they would get anyway
    package = lambda c: (c["target_user_id"], sorted(map(str, c["give"])), sorted(map(str, c["receive"])))
    assert [package(c) for c in second["cards"]] == [package(c) for c in first["cards"]]


def test_the_run_stops_at_the_probe_and_never_reaches_generation(founder, monkeypatch):
    """Nothing after the construction inputs runs: no owner generation, no card registration, no
    sink use. Sabotage: return from the probe instead of raising."""
    client, threads = founder
    calls = []
    monkeypatch.setattr(fast, "serve", lambda *a, **k: calls.append("serve"))
    monkeypatch.setattr(server, "_fit_league_context", lambda *a, **k: calls.append("fit"))
    body = start_and_finish(client, threads)
    assert body["status"] == "complete" and calls == []


# ── a real job is unchanged ───────────────────────────────────────────────────────────────────

def test_the_probe_is_one_guarded_call_in_the_job():
    tree = ast.parse(textwrap.dedent(inspect.getsource(server._run_trade_job)))
    fn = tree.body[0]
    assert [a.arg for a in fn.args.args + fn.args.kwonlyargs][-1] == "rule_waterfall_probe"
    assert fn.args.defaults[-1].value is None
    uses = [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == "rule_waterfall_probe"]
    assert len(uses) == 2                 # the guard and the call
    (guard,) = [n for n in ast.walk(fn) if isinstance(n, ast.If)
                and ast.unparse(n.test) == "rule_waterfall_probe is not None"]
    assert len(guard.body) == 1 and not guard.orelse
    assert ast.unparse(guard.body[0]) == "rule_waterfall_probe(owner_context, deck_rules, check_current)"


def test_a_real_job_without_the_probe_is_byte_identical(founder, monkeypatch):
    """Two real jobs on the same inputs publish byte-identical decks (every card field but the
    per-job minted ids and expiry), and a real job never receives a probe (the generate route
    and the prepared runtime pass none)."""
    seen = []
    real = server._run_trade_job

    def spy(*args, **kwargs):
        seen.append(kwargs.get("rule_waterfall_probe"))
        return real(*args, **kwargs)
    monkeypatch.setattr(server, "_run_trade_job", spy)
    first = run(monkeypatch)
    second = run(monkeypatch)
    strip = lambda cards: json.dumps([{k: v for k, v in c.items() if k not in ("impression_id", "trade_id", "expires_at")}
                                      for c in cards], sort_keys=True, default=str)
    assert strip(first["cards"]) == strip(second["cards"]) and first["cards"]
    assert seen == [None, None]
    source = inspect.getsource(server)
    assert source.count("rule_waterfall_probe=") == 2       # the parameter and the run's own call


# ── notes ─────────────────────────────────────────────────────────────────────────────────────

def test_notes_save_edit_clear_and_history_through_the_routes(founder):
    client, _ = founder
    put = lambda body: client.put("/api/founder/rule-notes/market_floor", json={"body": body}, headers=H())
    first = put("  Why 65%?  ")
    assert first.status_code == 200
    assert {k: first.json[k] for k in ("rule_key", "rule_name", "body", "author", "versions")} == {
        "rule_key": "market_floor", "rule_name": "Fair by market value", "body": "Why 65%?",
        "author": "you", "versions": 1}
    assert put("Why 65%? And why not 70%?").json["versions"] == 2
    assert put("").json["body"] == ""
    history = client.get("/api/founder/rule-notes/market_floor", headers=H()).json
    assert [h["body"] for h in history["history"]] == ["Why 65%?", "Why 65%? And why not 70%?", ""]
    assert {h["author"] for h in history["history"]} == {"you"}
    assert put("again").status_code == 200
    page = client.get(f"/api/founder/rule-waterfall?league_id={LEAGUE}", headers=H()).json
    assert [(n["rule_key"], n["body"], n["versions"]) for n in page["notes"]] == [("market_floor", "again", 4)]
    assert put("x" * 2001).json == {"error": "too_long"} and put("x" * 2001).status_code == 400
    assert put("x" * 2000).status_code == 200
    assert client.put("/api/founder/rule-notes/market_floor", json={"body": 3}, headers=H()).json == {
        "error": "invalid_body"}
    missing = client.put("/api/founder/rule-notes/no_such_rule", json={"body": "?"}, headers=H())
    assert missing.status_code == 404 and missing.json == {"error": "unknown_rule"}
    assert client.get("/api/founder/rule-notes/no_such_rule", headers=H()).status_code == 404


def test_note_saves_are_rate_limited(founder, monkeypatch):
    client, _ = founder
    monkeypatch.setattr(server, "_RULE_NOTE_SAVES_PER_HOUR", 3)
    codes = [client.put("/api/founder/rule-notes/filler", json={"body": str(i)}, headers=H()).status_code
             for i in range(4)]
    assert codes == [200, 200, 200, 429]


def test_the_operator_read_lists_every_version_without_account_ids(founder, monkeypatch):
    client, _ = founder
    monkeypatch.setattr(server, "_CRON_SECRET", "s3cret")
    for body in ("Is 450 right?", "Is 450 right for superflex?"):
        client.put("/api/founder/rule-notes/filler", json={"body": body}, headers=H())
    client.put("/api/founder/rule-notes/pool", json={"body": "Why 16?"}, headers=H())
    client.put("/api/founder/rule-notes/pool", json={"body": ""}, headers=H())      # cleared, kept
    out = client.get("/api/admin/founder/rule-notes", headers={"X-Cron-Secret": "s3cret"}).json
    assert out["catalog_version"] == rc.VERSION
    by_key = {n["rule_key"]: n for n in out["notes"]}
    assert list(by_key) == ["pool", "filler"]          # catalog order; rules never noted are absent
    assert by_key["filler"]["body"] == "Is 450 right for superflex?" and by_key["pool"]["body"] == ""
    assert [h["body"] for h in by_key["pool"]["history"]] == ["Why 16?", ""]
    authors = {by_key[k]["author"] for k in by_key} | {h["author"] for n in out["notes"] for h in n["history"]}
    assert authors == {"founder"}
    assert ME not in json.dumps(out)


# ── aggregate only ────────────────────────────────────────────────────────────────────────────

def test_the_page_is_aggregate_only(founder):
    client, threads = founder
    client.put("/api/founder/rule-notes/filler", json={"body": "note"}, headers=H())
    body = start_and_finish(client, threads)
    text = json.dumps(body)
    ids = set(SEED) | {ME, OPP, OPP2, LEAGUE}
    assert not [i for i in ids if f'"{i}"' in text]
