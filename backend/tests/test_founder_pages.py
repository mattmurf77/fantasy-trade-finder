"""Founders' review, "Review pages" (docs/plans/founder-review/pages-design.md).

Isolated in-memory SQLite engine, the Flask test client, synthetic sessions. No network, no
production database, no real page content (the documents here are a few lines of synthetic
HTML).

- The founder routes answer only a founder session with both flags on (founder.review AND
  founder.review_pages): flag off, allow-list unset, account not listed, unverified, demo, no
  token, a device id or a body identity -> 404 {"error": "not_found"} and no write.
- Uploads (X-Cron-Secret): slug, empty body, DOCTYPE, UTF-8, title, the 8 MiB cap (by
  Content-Length before the read and at the read for a chunked body); a 2.5 MB page goes
  through; a re-upload replaces.
- Round trip: list -> page -> notes -> page shows the notes; notes are per account; a blank
  body deletes the row; unknown slug 404; over 200 keys and oversize values 400.
- Operator auth: wrong / missing secret 401; production without a secret fails closed (503);
  the notes readback never carries an account id; delete removes the page and its notes.
- Storage: both tables additive; founder_page_notes deleted and exported with the account.
"""
import io
import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

from backend import accounts, database as db, feature_flags as ff, founder_pages as fp
from backend import server

ME, OTHER, STRANGER = "acct-founder-test-1", "acct-founder-test-2", "acct-not-founder-3"
TOKENS = {ME: "tok-founder-pages-1", OTHER: "tok-founder-pages-2", STRANGER: "tok-founder-pages-3"}
SECRET = "test-cron-secret"
PAGE = "<!DOCTYPE html>\n<html><head><title>T</title></head><body>" \
       "<textarea data-k=\"q1\" data-label=\"Question 1\"></textarea></body></html>"


def H(who=ME, **extra):
    return {"X-Session-Token": TOKENS[who], **extra}


ADMIN = {"X-Cron-Secret": SECRET}


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(engine)
    ff.flags_dict()
    monkeypatch.setitem(ff._flags_cache, "founder.review", True)
    monkeypatch.setitem(ff._flags_cache, "founder.review_pages", True)
    monkeypatch.setenv("FOUNDER_ACCOUNTS", f"someone-else, {ME}, {OTHER}")
    monkeypatch.setattr(server, "_CRON_SECRET", SECRET)
    server.app.config["TESTING"] = True
    with patch.object(db, "engine", engine):
        for who, token in TOKENS.items():
            monkeypatch.setitem(server._sessions, token, {
                "verified": True, "user_id": who, "username": who, "display_name": who,
                "active_format": "1qb_ppr", "last_active": 0.0})
        yield server.app.test_client()


class _CountingStream(io.BytesIO):
    """Records how many body bytes the server actually read (test_events_api's)."""
    taken = 0

    def read(self, size=-1):
        out = super().read(size)
        self.taken += len(out)
        return out

    def readinto(self, buf):
        n = super().readinto(buf)
        self.taken += n or 0
        return n


def upload(client, slug="review-one", body=PAGE, title="Review one", headers=ADMIN):
    data = body.encode("utf-8") if isinstance(body, str) else body
    return client.put(f"/api/admin/founder-pages/{slug}?title={title}", data=data,
                      headers=headers, content_type="text/html")


def table(name):
    with db.engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(select(db.metadata.tables[name]))]


# ── the gate ──────────────────────────────────────────────────────────────────

FOUNDER_ROUTES = (("GET", "/api/founder/pages"), ("GET", "/api/founder/pages/review-one"),
                  ("PUT", "/api/founder/pages/review-one/notes"))


@pytest.mark.parametrize("case", ["flag_off", "pages_flag_off", "env_unset", "not_listed", "unverified",
                                  "demo", "no_token", "device_id", "body_identity"])
def test_every_founder_route_is_refused_404_with_no_write(client, monkeypatch, case):
    """Sabotage A: _founder_pages_session returns _founder_session() without the
    founder.review_pages check -> the pages_flag_off case answers 200."""
    assert upload(client).status_code == 200
    headers = H()
    sess = server._sessions[TOKENS[ME]]
    if case == "flag_off":
        monkeypatch.setitem(ff._flags_cache, "founder.review", False)
    elif case == "pages_flag_off":
        monkeypatch.setitem(ff._flags_cache, "founder.review_pages", False)
    elif case == "env_unset":
        monkeypatch.delenv("FOUNDER_ACCOUNTS")
    elif case == "not_listed":
        headers = H(STRANGER)
    elif case == "unverified":
        monkeypatch.setitem(sess, "verified", False)
    elif case == "demo":
        monkeypatch.setitem(sess, "user_id", "demo_user_1")
        monkeypatch.setitem(sess, "is_demo", True)
        monkeypatch.setenv("FOUNDER_ACCOUNTS", "demo_user_1")
    elif case == "no_token":
        headers = {}
    elif case in ("device_id", "body_identity"):
        headers = H(STRANGER, **{"X-Device-Id": ME, "X-User-Id": ME})
    body = {"set": {"q1": {"label": "Question 1", "body": "an answer"}},
            **({"user_id": ME, "account_id": ME} if case == "body_identity" else {})}
    for method, path in FOUNDER_ROUTES:
        response = getattr(client, method.lower())(path, json=body, headers=headers)
        assert response.status_code == 404 and response.json == {"error": "not_found"}, (case, method, path)
    assert table("founder_page_notes") == []


def test_the_list_answers_a_founder(client):
    assert client.get("/api/founder/pages", headers=H()).json == {"pages": []}


# ── uploads ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("slug, body, code, status", [
    ("Bad_Slug", PAGE, "invalid_slug", 400),
    ("x" * 65, PAGE, "invalid_slug", 400),
    ("review-one", "", "empty_body", 400),
    ("review-one", "<html><body>no doctype</body></html>", "not_html", 400),
    ("review-one", b"<!DOCTYPE html>\xff\xfe", "not_utf8", 400),
])
def test_upload_validation(client, slug, body, code, status):
    response = upload(client, slug=slug, body=body)
    assert response.status_code == status and response.json["error"] == code
    assert table("founder_pages") == []


def test_doctype_is_case_insensitive_after_whitespace_and_a_title_defaults_to_the_slug(client):
    response = client.put("/api/admin/founder-pages/review-two", data=b"\n  \xef\xbb\xbf<!doctype HTML><p>x",
                          headers=ADMIN, content_type="text/html")
    assert response.status_code == 200 and response.json["title"] == "review-two"
    assert upload(client, title="t" * (fp.MAX_TITLE_CHARS + 1)).json["error"] == "title_too_long"


def test_the_size_cap_is_checked_before_and_at_the_read(client):
    """Sabotage B: drop the read-time cap (request.max_content_length) in
    _founder_pages_body -> the chunked over-cap upload is stored."""
    big = PAGE.encode() + b" " * 2_500_000            # a 2.5 MB page goes through
    ok = upload(client, body=big)
    assert ok.status_code == 200 and ok.json["bytes"] == len(big) and ok.json["created"] is True
    over = PAGE.encode() + b" " * (fp.MAX_PAGE_BYTES - len(PAGE.encode()) + 1)
    declared = upload(client, slug="too-big", body=over)
    assert declared.status_code == 413 and declared.json["error"] == "too_large"

    # A chunked body has no Content-Length: the read itself is capped.
    stream = _CountingStream(over + b" " * (1 << 20))
    chunked = client.put("/api/admin/founder-pages/too-big-chunked", input_stream=stream,
                         headers={**ADMIN, "Transfer-Encoding": "chunked"}, content_type="text/html",
                         environ_overrides={"wsgi.input_terminated": True})
    assert chunked.status_code == 413 and chunked.json["error"] == "too_large"
    assert stream.taken <= fp.MAX_PAGE_BYTES + 1               # never the whole body
    with patch.object(server.app.request_class, "get_data",
                      side_effect=AssertionError("body read before the Content-Length check")):
        assert upload(client, slug="too-big", body=over).status_code == 413
    assert [p["slug"] for p in table("founder_pages")] == ["review-one"]
    exact = PAGE.encode() + b" " * (fp.MAX_PAGE_BYTES - len(PAGE.encode()))
    assert upload(client, slug="exactly-cap", body=exact).status_code == 200


def test_a_reupload_replaces_the_page_and_keeps_its_notes(client):
    upload(client)
    client.put("/api/founder/pages/review-one/notes", json={"set": {"q1": {"label": "Q", "body": "kept"}}},
               headers=H())
    again = upload(client, body=PAGE + "<!-- v2 -->", title="Review one v2")
    assert again.status_code == 200 and again.json["created"] is False
    page = client.get("/api/founder/pages/review-one", headers=H()).json
    assert page["title"] == "Review one v2" and page["html"].endswith("<!-- v2 -->")
    assert page["notes"] == {"q1": "kept"} and len(table("founder_pages")) == 1


# ── round trip ────────────────────────────────────────────────────────────────

def test_round_trip_of_page_and_notes(client):
    upload(client)
    (row,) = client.get("/api/founder/pages", headers=H()).json["pages"]
    assert set(row) == {"slug", "title", "bytes", "updated_at", "notes"}
    assert row["slug"] == "review-one" and row["title"] == "Review one" and row["notes"] == 0
    assert row["bytes"] == len(PAGE.encode())
    page = client.get("/api/founder/pages/review-one", headers=H()).json
    assert set(page) == {"slug", "title", "updated_at", "html", "notes"}
    assert page["html"] == PAGE and page["notes"] == {}
    saved = client.put("/api/founder/pages/review-one/notes", headers=H(), json={"set": {
        "q1": {"label": "Question 1", "body": "First answer"},
        "free text key / with spaces": {"body": "Second"}}})
    assert saved.status_code == 200 and saved.json == {"saved": 2, "cleared": 0}
    again = client.put("/api/founder/pages/review-one/notes", headers=H(),
                       json={"set": {"q1": {"label": "Question 1", "body": "Edited"}}})
    assert again.json == {"saved": 1, "cleared": 0}
    assert client.get("/api/founder/pages/review-one", headers=H()).json["notes"] == {
        "q1": "Edited", "free text key / with spaces": "Second"}
    assert client.get("/api/founder/pages", headers=H()).json["pages"][0]["notes"] == 2
    assert len(table("founder_page_notes")) == 2


def test_notes_are_isolated_per_account(client):
    """Sabotage C: drop the user_id filter in load_founder_page_notes -> the other
    founder sees my note."""
    upload(client)
    client.put("/api/founder/pages/review-one/notes", headers=H(ME),
               json={"set": {"q1": {"label": "Q", "body": "mine"}}})
    assert client.get("/api/founder/pages/review-one", headers=H(OTHER)).json["notes"] == {}
    assert client.get("/api/founder/pages", headers=H(OTHER)).json["pages"][0]["notes"] == 0
    client.put("/api/founder/pages/review-one/notes", headers=H(OTHER),
               json={"set": {"q1": {"label": "Q", "body": "theirs"}}})
    assert client.get("/api/founder/pages/review-one", headers=H(ME)).json["notes"] == {"q1": "mine"}
    assert client.get("/api/founder/pages/review-one", headers=H(OTHER)).json["notes"] == {"q1": "theirs"}
    assert client.get("/api/admin/founder-pages", headers=ADMIN).json["pages"][0]["notes"] == 2


def test_a_blank_body_clears_the_note(client):
    upload(client)
    client.put("/api/founder/pages/review-one/notes", headers=H(),
               json={"set": {"q1": {"label": "Q", "body": "x"}, "q2": {"label": "", "body": "y"}}})
    cleared = client.put("/api/founder/pages/review-one/notes", headers=H(),
                         json={"set": {"q1": {"label": "Q", "body": ""}, "q2": {"body": "   "},
                                       "never-saved": {"body": ""}}})
    assert cleared.json == {"saved": 0, "cleared": 2}
    assert table("founder_page_notes") == []


@pytest.mark.parametrize("body, code", [
    (None, "invalid_body"),
    ({"set": []}, "invalid_body"),
    ({"set": {f"k{i}": {"body": "x"} for i in range(fp.MAX_KEYS_PER_SAVE + 1)}}, "too_many_keys"),
    ({"set": {"k" * (fp.MAX_KEY_CHARS + 1): {"body": "x"}}}, "invalid_key"),
    ({"set": {"": {"body": "x"}}}, "invalid_key"),
    ({"set": {"q1": "just text"}}, "invalid_note"),
    ({"set": {"q1": {"body": 5}}}, "invalid_note"),
    ({"set": {"q1": {"label": "l" * (fp.MAX_LABEL_CHARS + 1), "body": "x"}}}, "label_too_long"),
    ({"set": {"q1": {"body": "b" * (fp.MAX_BODY_CHARS + 1)}}}, "body_too_long"),
])
def test_note_writes_are_validated_with_no_write(client, body, code):
    upload(client)
    response = client.put("/api/founder/pages/review-one/notes", headers=H(),
                          data=json.dumps(body), content_type="application/json")
    assert response.status_code == 400 and response.json == {"error": code}
    assert table("founder_page_notes") == []


def test_the_limits_themselves_are_accepted(client):
    upload(client)
    body = {"set": {f"{i:03d}" + "k" * (fp.MAX_KEY_CHARS - 3): {"label": "l" * fp.MAX_LABEL_CHARS,
                                                                "body": "b" * fp.MAX_BODY_CHARS}
                    for i in range(fp.MAX_KEYS_PER_SAVE)}}
    response = client.put("/api/founder/pages/review-one/notes", headers=H(), json=body)
    assert response.json == {"saved": fp.MAX_KEYS_PER_SAVE, "cleared": 0}


def test_unknown_pages_are_404(client):
    for path in ("/api/founder/pages/nope", "/api/founder/pages/Not_A_Slug"):
        assert client.get(path, headers=H()).status_code == 404
    response = client.put("/api/founder/pages/nope/notes", headers=H(), json={"set": {"q1": {"body": "x"}}})
    assert response.status_code == 404 and table("founder_page_notes") == []
    assert client.get("/api/admin/founder-pages/nope/notes", headers=ADMIN).status_code == 404
    assert client.delete("/api/admin/founder-pages/nope", headers=ADMIN).status_code == 404


# ── operator routes ───────────────────────────────────────────────────────────

ADMIN_ROUTES = (("GET", "/api/admin/founder-pages"), ("PUT", "/api/admin/founder-pages/review-two"),
                ("GET", "/api/admin/founder-pages/review-one/notes"),
                ("DELETE", "/api/admin/founder-pages/review-one"))


def test_operator_routes_need_the_secret(client, monkeypatch):
    upload(client)
    for headers in ({}, {"X-Cron-Secret": "wrong"}, H()):
        for method, path in ADMIN_ROUTES:
            response = getattr(client, method.lower())(path, data=PAGE.encode(), headers=headers,
                                                       content_type="text/html")
            assert response.status_code == 401, (headers, method, path)
    # Production without a secret fails closed.
    monkeypatch.setattr(server, "_CRON_SECRET", "")
    monkeypatch.setattr(server, "_IS_PROD_ENV", True)
    for method, path in ADMIN_ROUTES:
        response = getattr(client, method.lower())(path, data=PAGE.encode(), headers=ADMIN,
                                                   content_type="text/html")
        assert response.status_code == 503, (method, path)
    assert [p["slug"] for p in table("founder_pages")] == ["review-one"]


def test_operator_routes_do_not_need_the_flag(client, monkeypatch):
    monkeypatch.setitem(ff._flags_cache, "founder.review", False)
    monkeypatch.setitem(ff._flags_cache, "founder.review_pages", False)
    assert upload(client).status_code == 200
    assert client.get("/api/admin/founder-pages", headers=ADMIN).json["pages"][0]["slug"] == "review-one"


def test_operator_notes_readback_has_no_account_id(client):
    """Sabotage D: return select(t) rows (user_id included) from
    load_founder_page_notes_for_operator -> the account ids appear."""
    upload(client)
    client.put("/api/founder/pages/review-one/notes", headers=H(ME),
               json={"set": {"q1": {"label": "Question 1", "body": "mine"}}})
    client.put("/api/founder/pages/review-one/notes", headers=H(OTHER),
               json={"set": {"q1": {"label": "Question 1", "body": "theirs"},
                             "q2": {"label": "Question 2", "body": "more"}}})
    response = client.get("/api/admin/founder-pages/review-one/notes", headers=ADMIN)
    assert response.status_code == 200 and response.json["slug"] == "review-one"
    notes = response.json["notes"]
    assert all(set(n) == {"key", "label", "body", "updated_at"} for n in notes)
    assert sorted((n["key"], n["body"]) for n in notes) == [("q1", "mine"), ("q1", "theirs"), ("q2", "more")]
    text = json.dumps(response.json) + json.dumps(client.get("/api/admin/founder-pages", headers=ADMIN).json)
    assert ME not in text and OTHER not in text


def test_delete_removes_the_page_and_its_notes(client):
    upload(client)
    upload(client, slug="review-two")
    client.put("/api/founder/pages/review-one/notes", headers=H(), json={"set": {"q1": {"body": "x"}}})
    client.put("/api/founder/pages/review-two/notes", headers=H(), json={"set": {"q1": {"body": "y"}}})
    response = client.delete("/api/admin/founder-pages/review-one", headers=ADMIN)
    assert response.status_code == 200 and response.json == {"deleted": True, "notes": 1}
    assert [p["slug"] for p in table("founder_pages")] == ["review-two"]
    assert [n["page_slug"] for n in table("founder_page_notes")] == ["review-two"]
    assert client.get("/api/founder/pages/review-one", headers=H()).status_code == 404


def test_logs_carry_counts_only(client, caplog):
    import logging
    with caplog.at_level(logging.INFO):
        upload(client)
        client.put("/api/founder/pages/review-one/notes", headers=H(),
                   json={"set": {"q1": {"label": "Secret label", "body": "Secret body"}}})
    lines = [r.getMessage() for r in caplog.records if "founder-pages" in r.getMessage()]
    assert lines and not any(s in line for line in lines
                             for s in ("Secret", ME, "review-one", "Review one", "<!DOCTYPE"))


# ── storage ───────────────────────────────────────────────────────────────────

def test_the_tables_are_additive(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    new = {"founder_pages", "founder_page_notes"}
    db.metadata.create_all(engine, tables=[t for t in db.metadata.sorted_tables if t.name not in new])
    with engine.begin() as conn:
        conn.execute(insert(db.users_table).values(sleeper_user_id="u1"))
    db.metadata.create_all(engine)
    with engine.connect() as conn:
        assert [r.sleeper_user_id for r in conn.execute(select(db.users_table))] == ["u1"]
        for name in new:
            assert conn.execute(select(db.metadata.tables[name])).fetchall() == []


def test_notes_are_deleted_and_exported_with_the_account():
    assert "founder_page_notes" in accounts._ADDITIONAL_PRIVATE_TABLES
    assert any(entry[0] == "founder_page_notes" for entry in accounts._EXPORT_TABLES)
    assert "founder_pages" not in accounts._ADDITIONAL_PRIVATE_TABLES


def test_the_flag_defaults_off_in_code_and_ships_on():
    from pathlib import Path
    assert ff.DEFAULT_FLAGS["founder.review_pages"] is False
    root = Path(__file__).resolve().parents[2]
    for rel in ("config/features.json", "backend/tests/fixtures/flags/release.json",
                "backend/tests/fixtures/flags/onboarding-v2.json", "backend/tests/fixtures/flags/profiles-on.json"):
        assert json.loads((root / rel).read_text())["founder.review_pages"] is True, rel
