"""Email capture behind `auth.email_capture` (2026-07-17 spec):

  * Flag OFF (default) → plaintext is never stored, hash-only behavior
    unchanged — the privacy policy's current "no email addresses" claim
    stays true until the capture release flips the flag.
  * Flag ON → Apple first-auth email lands on accounts.email with a consent
    stamp; later auths backfill a missing email but never overwrite one;
    set_account_email() (the future Settings capture path) stores/refreshes.

Same isolated in-memory engine pattern as test_accounts.py.
"""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.accounts as accounts
import backend.database as db_module
from backend.database import metadata


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _account_row(engine, account_id):
    with engine.connect() as conn:
        return conn.execute(
            select(db_module.accounts_table).where(
                db_module.accounts_table.c.account_id == account_id
            )
        ).fetchone()


def _flag(monkeypatch, on: bool):
    monkeypatch.setattr(accounts, "_email_capture_enabled", lambda: on)


def test_flag_off_never_stores_plaintext(engine, monkeypatch):
    _flag(monkeypatch, False)
    a = accounts.find_or_create_account(
        "apple", "sub-off", accounts.hash_email("Person@Example.com"),
        email="Person@Example.com")
    row = _account_row(engine, a["account_id"])
    assert row.email is None
    assert row.email_source is None
    assert row.email_consent_at is None


def test_flag_on_stores_normalized_email_with_consent(engine, monkeypatch):
    _flag(monkeypatch, True)
    a = accounts.find_or_create_account(
        "apple", "sub-on", accounts.hash_email("Person@Example.com"),
        email="  Person@Example.COM ")
    row = _account_row(engine, a["account_id"])
    assert row.email == "person@example.com"
    assert row.email_source == "apple"
    assert row.email_consent_at  # ISO stamp present


def test_backfill_fills_missing_but_never_overwrites(engine, monkeypatch):
    _flag(monkeypatch, False)
    a = accounts.find_or_create_account("apple", "sub-bf", "hash")
    assert _account_row(engine, a["account_id"]).email is None

    # Same identity re-auths after the flag flips → backfill.
    _flag(monkeypatch, True)
    accounts.find_or_create_account("apple", "sub-bf", "hash",
                                    email="first@example.com")
    assert _account_row(engine, a["account_id"]).email == "first@example.com"

    # A later auth with a different address must not clobber it.
    accounts.find_or_create_account("apple", "sub-bf", "hash",
                                    email="second@example.com")
    assert _account_row(engine, a["account_id"]).email == "first@example.com"


def test_set_account_email_user_path_and_gates(engine, monkeypatch):
    _flag(monkeypatch, True)
    a = accounts.find_or_create_account("apple", "sub-set", "hash")

    assert accounts.set_account_email(a["account_id"], "Me@Example.com") is True
    row = _account_row(engine, a["account_id"])
    assert row.email == "me@example.com"
    assert row.email_source == "user"

    # User-entered address may be refreshed (unlike the provider backfill).
    assert accounts.set_account_email(a["account_id"], "new@example.com")
    assert _account_row(engine, a["account_id"]).email == "new@example.com"

    # Invalid input and flag-off are both no-ops.
    assert accounts.set_account_email(a["account_id"], "not-an-email") is False
    _flag(monkeypatch, False)
    assert accounts.set_account_email(a["account_id"], "x@example.com") is False
    assert _account_row(engine, a["account_id"]).email == "new@example.com"
