"""Email capture behind `auth.email_capture` (2026-07-17 spec):

  * Flag OFF → plaintext is never stored, hash-only behavior unchanged.
  * Flag ON (shipped 2026-08-11, P1-3) → the Apple/Google identity-token
    email claim lands on accounts.email with a consent stamp; later auths
    backfill a missing email but never overwrite one; set_account_email()
    (the future Settings capture path) stores/refreshes.

The first four tests monkeypatch `_email_capture_enabled`, so they are
deliberately independent of the flag's real value — if one of them moves
when the flag moves, something other than the flag moved.

The three tests at the bottom pin the *governance*, not the mechanism: the
flag and the published privacy policy must ship together, and the deletion
and export promises that policy now makes must stay true.

Same isolated in-memory engine pattern as test_accounts.py.
"""
import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select

import backend.accounts as accounts
import backend.database as db_module
from backend.database import metadata

REPO_ROOT = Path(__file__).resolve().parents[2]


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


# ---------------------------------------------------------------------------
# Governance pins (P1-3, 2026-08-11). These do not test the capture
# mechanism — they test that the published claims about it stay true.
# ---------------------------------------------------------------------------

# The two sentences the policy carried while capture was off. Either one
# returning while the flag is on is a public misrepresentation, not a typo.
RETIRED_POLICY_CLAIMS = (
    "We never store your email",
    "No email addresses",
)


def test_release_flag_and_privacy_policy_ship_together():
    """`auth.email_capture` ON ⇒ the policy no longer denies collection.

    The flag and web/privacy.html ship in one commit (DECISIONS.md D-044);
    this is the mechanism that keeps them that way after everyone has
    forgotten. Deliberately asymmetric: policy-ahead-of-flag passes, because
    describing data you do not yet hold is over-disclosure, not a breach.
    Flag-ahead-of-policy is red.
    """
    flags = json.loads((REPO_ROOT / "config" / "features.json").read_text())
    source = (REPO_ROOT / "web" / "privacy.html").read_text()

    if not flags.get("auth.email_capture"):
        pytest.skip("auth.email_capture is off — nothing to disclose")

    # Only what the page actually serves counts. The file's header comment
    # quotes both retired sentences deliberately, as provenance for why they
    # were retired; a comment is not a claim to a reader.
    policy = re.sub(r"<!--.*?-->", "", source, flags=re.DOTALL)

    for claim in RETIRED_POLICY_CLAIMS:
        assert claim not in policy, (
            f"web/privacy.html still says {claim!r} while "
            "auth.email_capture is true. The flag and the policy ship "
            "together — revert one or fix the other."
        )


def test_delete_account_removes_email(engine, monkeypatch):
    """§6's deletion promise: the address is deleted, not blanked.

    Pins the whole accounts row being hard-deleted by delete_user_data. A
    refactor that switched to nulling columns would keep the row (and any
    column added later) alive, quietly breaking the published claim.
    """
    _flag(monkeypatch, True)
    a = accounts.find_or_create_account(
        "apple", "sub-del", accounts.hash_email("Gone@Example.com"),
        email="Gone@Example.com")
    assert _account_row(engine, a["account_id"]).email == "gone@example.com"

    accounts.delete_user_data("no-such-sleeper-user",
                              account_id=a["account_id"])

    assert _account_row(engine, a["account_id"]) is None


def test_export_includes_account_email(engine, monkeypatch):
    """§6's export promise: the address is in the archive.

    `accounts` is handled outside _EXPORT_TABLES, so a future refactor that
    folded it in would silently drop the identity layer from the export.
    """
    _flag(monkeypatch, True)
    a = accounts.find_or_create_account(
        "apple", "sub-exp", accounts.hash_email("Keep@Example.com"),
        email="Keep@Example.com")

    out = accounts.export_user_data("no-such-sleeper-user",
                                    account_id=a["account_id"])

    rows = out["tables"]["accounts"]
    assert len(rows) == 1
    assert rows[0]["email"] == "keep@example.com"
    assert rows[0]["email_source"] == "apple"
    assert rows[0]["email_consent_at"]
