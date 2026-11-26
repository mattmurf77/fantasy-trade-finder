#!/usr/bin/env python3
"""grant_lifetime_pro_existing_users.py — lifetime Pro for every existing user at paid launch.

Operator decision, 2026-11-22: "All current app users get free pro for life."
The cut-off is every account that exists at the moment paid enforcement is
switched on (turn-on runbook step B6); people who join after that pay. Runbook:
docs/plans/monetization-launch/paid-launch/turn-on-runbook.md, steps A6 and B5a.

WHO IS A USER. One person = one working key, the id entitlements resolve on:
  * a `users` row keyed by a Sleeper id (all digits): Sleeper sign-in, typed
    username or verified;
  * an `accounts` row (Sign in with Apple / Google, or the ESPN/MFL platform
    sign-in). Bound to a Sleeper id → that Sleeper id; unbound (or bound to
    a Sleeper id with no users row) → `acct_<id>`;
  * a legacy `users` row keyed `acct_<id>` → the same key as its account
    (dropped when the account no longer exists);
  * a legacy `entry:*` ESPN/MFL user only when `verified_via` is set (the
    unverified ones were purged; see purge_entry_users.py).
Everything else in `users` is synthetic (demo_user_*, qa_*, test_*, espn:,
mfl:, …) and is counted and skipped. An account bound to a Sleeper id and the
Sleeper id's own users row are ONE person, so one grant: the bulk-grant route
stamps the account_id on the row (entitlements.grant → _account_for_user), and
read-time resolution matches user_id OR account_id, so the one row also follows
the account through a re-link.

ALREADY ENTITLED. A person is skipped when an entitlements row with
entitlement 'pro', status 'active' and expires_at NULL already matches their
key or their account (the same match entitlements._active_rows makes). So a
re-run just before enforcement grants only accounts created since the last
run, and a founder_iap buyer is not granted twice. A time-limited subscriber
(apple_iap, trial) IS granted: lifetime Pro is the decision; their Apple
subscription keeps billing until they cancel it in Apple's settings.

WHY HTTP FOR THE WRITES. Listing has to read the database (no admin route
lists users), but the grants go through `POST /api/admin/entitlements/bulk-grant`:
  * the database connection this script opens is READ-ONLY on Postgres
    (`default_transaction_read_only=on`), so the script itself cannot write
    the prod DB, whatever goes wrong in it;
  * the rows are written by the deployed server's own entitlements.grant
    (source `manual_grant`, granted_by `operator`), the same path the runbook's
    B4 grant uses, logged in Render's request log, not by whatever code is
    checked out on the operator's laptop;
  * it matches the repo's ops scripts that change prod (set_knob.py,
    refresh_usage_trends.py --remote): an X-Cron-Secret admin route.
After the last batch the script re-reads the database and checks that every
key it sent now holds perpetual Pro. That catches a --base-url and a
DATABASE_URL that point at different environments.

Usage, from the repo root (secrets from the gitignored secrets.local.env):
    set -a; . ./secrets.local.env; set +a
    export DATABASE_URL="$DATABASE_URL_PROD"
    # dry run (default): counts, and the would-grant list written to --out
    python3 scripts/grant_lifetime_pro_existing_users.py \
        --exclude <demo B username or id> --out feedback-workspace/lifetime-pro/would-grant.txt
    # apply
    python3 scripts/grant_lifetime_pro_existing_users.py \
        --exclude <demo B username or id> --out feedback-workspace/lifetime-pro/granted.txt \
        --apply --base-url https://<render-host>
    (add --allow-local only for a local SQLite test run)

`--exclude` (repeatable) and `--exclude-file` (one identifier per line, `#`
comments) name people who must NOT be granted: App Review's demo B, and any
never-entitled test account. Each is resolved like the admin routes resolve
(Sleeper id, Sleeper username, acct_*, bare account id); one that does not
resolve stops the run before anything is written. `--created-before` (a full
ISO datetime with a timezone) limits the grant to people whose earliest
users/accounts created_at is before it; undated rows are included and counted.

Secrets: CRON_SECRET from the environment only, never argv, never printed.
Output is counts only; ids appear only in the --out file (mode 0600) and,
with --verbose, on stdout.

Exit codes: 0 done; 1 a grant failed or the read-back found a key without
perpetual Pro; 2 refused (local DB, unresolvable exclude, missing --base-url
or CRON_SECRET, bad arguments); 3 an unexpected error (its type only).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from sqlalchemy import create_engine, select  # noqa: E402

from backend import database as db, entitlements  # noqa: E402

NOTE = "lifetime-pro: existing user at paid launch (operator 2026-11-22)"
ROUTE = "/api/admin/entitlements/bulk-grant"
SECRET_ENV = "CRON_SECRET"   # what server._require_cron_auth compares X-Cron-Secret to
ACCT = "acct_"
ENTRY = "entry:"
_SLEEPER_ID = re.compile(r"^\d+$")
_CUTOFF = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})")


class Refused(Exception):
    """A precondition failed; nothing was written."""


# ---------------------------------------------------------------------------
# Database (read-only)
# ---------------------------------------------------------------------------

def _identity(url) -> str:
    """Which database this is, without credentials."""
    host = url.host or ""
    label = "***" if not host or host.replace(".", "").isdigit() else host.split(".")[0]
    name = url.database or "***"
    if url.get_backend_name() == "sqlite":
        name = Path(name).name
    return f"database: {url.get_backend_name()}; host: {label}; name: {name}"


@contextmanager
def _read_only():
    """Swap db.engine for a read-only engine that never renders bound
    parameters (ids) into an error, so entitlements.resolve_user reads
    through it too. Restored before any grant is sent."""
    saved = db.engine
    url = saved.url
    args = ({"check_same_thread": False} if url.get_backend_name() == "sqlite"
            else {"options": "-c default_transaction_read_only=on"})
    ro = create_engine(url, future=True, hide_parameters=True, connect_args=args)
    db.engine = ro
    try:
        yield
    finally:
        db.engine = saved
        ro.dispose()


def _parse_iso(value) -> datetime | None:
    """A stored created_at (lenient; naive reads as UTC)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_cutoff(text) -> datetime | None:
    if not isinstance(text, str) or not _CUTOFF.fullmatch(text):
        return None
    try:
        return datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError:
        return None


def discover(created_before: datetime | None) -> dict:
    """Every person, by canonical working key, with skip counts."""
    counts = {"users_rows": 0, "accounts_rows": 0, "synthetic": 0,
              "orphan_acct": 0, "unverified_entry": 0, "after_cutoff": 0,
              "undated": 0}
    with db.engine.connect() as conn:
        accts = {r.account_id: r for r in conn.execute(select(
            db.accounts_table.c.account_id, db.accounts_table.c.sleeper_user_id,
            db.accounts_table.c.created_at))}
        users = conn.execute(select(
            db.users_table.c.sleeper_user_id, db.users_table.c.created_at,
            db.users_table.c.verified_via)).fetchall()
    counts["users_rows"], counts["accounts_rows"] = len(users), len(accts)

    born: dict[str, list] = {}   # key -> created_at datetimes (None = undated)
    present = {str(r.sleeper_user_id) for r in users}

    def add(key, created):
        born.setdefault(key, []).append(_parse_iso(created))

    def account_key(aid):
        """The key one account is granted under. Bound to a Sleeper (or
        entry:) id that has a users row → that id. Otherwise acct_<id>: the
        bulk-grant route resolves acct_* through the accounts row (to the
        bound id, if any), but resolves a bare Sleeper id only through users.
        None = bound to a synthetic id."""
        bound = accts[aid].sleeper_user_id
        if bound and bound in present:
            return bound if (_SLEEPER_ID.match(bound) or bound.startswith(ENTRY)) else None
        return f"{ACCT}{aid}"

    for r in users:
        uid = str(r.sleeper_user_id or "")
        if _SLEEPER_ID.match(uid):
            add(uid, r.created_at)
        elif uid.startswith(ACCT):
            aid = uid[len(ACCT):]
            if aid not in accts:
                counts["orphan_acct"] += 1
            elif (key := account_key(aid)) is None:
                counts["synthetic"] += 1
            else:
                add(key, r.created_at)
        elif uid.startswith(ENTRY):
            if (r.verified_via or "").strip():
                add(uid, r.created_at)
            else:
                counts["unverified_entry"] += 1
        else:
            counts["synthetic"] += 1

    for aid, a in accts.items():
        key = account_key(aid)
        if key is None:
            counts["synthetic"] += 1
        else:
            add(key, a.created_at)

    people = set()
    for key, times in born.items():
        dated = [t for t in times if t is not None]
        first = min(dated) if dated else None
        if created_before is not None and first is not None and first >= created_before:
            counts["after_cutoff"] += 1
            continue
        if first is None:
            counts["undated"] += 1
        people.add(key)
    account_of = {a.sleeper_user_id: aid for aid, a in accts.items() if a.sleeper_user_id}
    return {"people": people, "counts": counts, "account_of": account_of}


def _account_for(key: str, account_of: dict) -> str | None:
    return key[len(ACCT):] if key.startswith(ACCT) else account_of.get(key)


def perpetual_pro_holders(people, account_of) -> set:
    """Keys whose active, unrevoked, non-expiring 'pro' row already exists,
    matched on user_id or account_id like entitlements._active_rows."""
    t = db.entitlements_table
    with db.engine.connect() as conn:
        rows = conn.execute(
            select(t.c.user_id, t.c.account_id)
            .where(t.c.entitlement == "pro")
            .where(t.c.status == "active")
            .where(t.c.expires_at.is_(None))
        ).fetchall()
    by_user = {r.user_id for r in rows}
    by_acct = {r.account_id for r in rows if r.account_id}
    bound_of = {aid: sid for sid, aid in account_of.items()}

    def held(k):
        aid = _account_for(k, account_of)
        return (k in by_user or aid in by_acct
                or (aid is not None and bound_of.get(aid) in by_user))
    return {k for k in people if held(k)}


def resolve_excludes(idents, account_of) -> tuple[set, list]:
    """(keys to exclude, identifiers that did not resolve)."""
    keys, missing = set(), []
    for ident in idents:
        user_id, account_id = entitlements.resolve_user(ident)
        if user_id is None:
            missing.append(ident)
            continue
        keys.add(user_id)
        if account_id:
            keys.add(f"{ACCT}{account_id}")
    # a bound account's acct_ key and its Sleeper id are the same person
    keys |= {sid for sid, aid in account_of.items() if f"{ACCT}{aid}" in keys}
    return keys, missing


# ---------------------------------------------------------------------------
# Grants (HTTP)
# ---------------------------------------------------------------------------

def _post_bulk(base_url: str, secret: str, body: dict, timeout: int = 120):
    """POST one batch. Returns (http_status, json_or_None); 0 = unreachable."""
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{ROUTE}", method="POST",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Cron-Secret": secret},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, None


def apply(keys, base_url, secret, batch_size, note: str = NOTE) -> list:
    """Send every key in batches; returns [(key, reason)] failures.
    `note` is stored on each grant (grant_pro_to_users.py passes its own)."""
    failures = []
    keys = sorted(keys)
    for i in range(0, len(keys), batch_size):
        chunk = keys[i:i + batch_size]
        status, payload = _post_bulk(base_url, secret, {
            "users": chunk, "entitlement": "pro", "perpetual": True, "note": note})
        if status != 201 or not isinstance(payload, dict):
            failures += [(k, f"http {status or 'unreachable'}") for k in chunk]
            print(f"  batch {i // batch_size + 1}: FAILED (http {status or 'unreachable'}), "
                  f"{len(chunk)} not granted")
            continue
        failed = payload.get("failed") or []
        failures += [(str(f.get("user")), str(f.get("error"))) for f in failed]
        print(f"  batch {i // batch_size + 1}: granted {len(payload.get('granted') or [])}, "
              f"failed {len(failed)}")
    return failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _read_exclude_file(path: str) -> list[str]:
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _write_out(path: str, keys) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(f"{k}\n" for k in sorted(keys)))
    os.chmod(p, 0o600)


def _run(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], allow_abbrev=False)
    ap.add_argument("--out", required=True,
                    help="file to write the would-grant (dry run) or sent (--apply) keys to")
    ap.add_argument("--exclude", action="append", default=[], metavar="ID",
                    help="identifier never to grant (repeatable): Sleeper id or username, "
                         "acct_*, or account id")
    ap.add_argument("--exclude-file", metavar="PATH",
                    help="file of identifiers never to grant, one per line")
    ap.add_argument("--created-before", metavar="ISO",
                    help="only people created before this full datetime with a timezone, "
                         "e.g. 2026-11-23T18:00:00Z (default: everyone present now)")
    ap.add_argument("--apply", action="store_true",
                    help="send the grants (default is a dry run that writes nothing)")
    ap.add_argument("--base-url", help="with --apply: the API base, e.g. https://<render-host>")
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--allow-local", action="store_true",
                    help="allow a local SQLite database (local test runs only)")
    ap.add_argument("--verbose", action="store_true", help="also print ids")
    args = ap.parse_args(argv)

    cutoff = None
    if args.created_before is not None:
        cutoff = _parse_cutoff(args.created_before)
        if cutoff is None:
            ap.error("--created-before must be a full datetime with seconds and a timezone, "
                     "e.g. 2026-11-23T18:00:00Z")
    if args.batch_size < 1:
        ap.error("--batch-size must be at least 1")
    if not args.apply and args.base_url:
        ap.error("--base-url only goes with --apply")
    secret = os.environ.get(SECRET_ENV, "").strip()
    if args.apply:
        if not args.base_url:
            raise Refused("--apply needs --base-url")
        if not secret:
            raise Refused(f"--apply needs {SECRET_ENV} in the environment "
                          "(set -a; . ./secrets.local.env; set +a)")

    print(_identity(db.engine.url))
    if db.engine.url.get_backend_name() == "sqlite" and not args.allow_local:
        raise Refused("that is a local SQLite database. Set DATABASE_URL in this shell, "
                      "or pass --allow-local for a local test run")

    idents = list(args.exclude)
    if args.exclude_file:
        idents += _read_exclude_file(args.exclude_file)

    with _read_only():
        found = discover(cutoff)
        people, account_of = found["people"], found["account_of"]
        excluded, missing = resolve_excludes(idents, account_of)
        if missing:
            if args.verbose:
                for ident in missing:
                    print(f"  unresolved exclude: {ident}")
            raise Refused(f"{len(missing)} --exclude identifier(s) match no user "
                          "(--verbose lists them). Nothing was granted")
        held = perpetual_pro_holders(people, account_of)

    c = found["counts"]
    excluded_people = people & excluded
    excluded_held = excluded_people & held
    todo = people - held - excluded
    print(f"users rows read: {c['users_rows']}; accounts rows read: {c['accounts_rows']}")
    print(f"skipped: synthetic ids {c['synthetic']}, acct_ keys with no account "
          f"{c['orphan_acct']}, unverified entry users {c['unverified_entry']}, "
          f"created on/after --created-before {c['after_cutoff']}")
    print(f"users found (one per person): {len(people)} (of which undated: {c['undated']})")
    print(f"already hold active perpetual pro: {len(held - excluded)}")
    print(f"excluded: {len(excluded_people)} (exclude identifiers given: {len(idents)})")
    if excluded_held:
        print(f"WARNING: {len(excluded_held)} excluded user(s) ALREADY hold perpetual pro. "
              "This script never revokes; check them with GET /api/admin/entitlements?user=")
    print(f"{'to grant' if args.apply else 'would grant'}: {len(todo)}")
    if args.verbose:
        for k in sorted(todo):
            print(f"  {k}")
    _write_out(args.out, todo)
    print(f"list written to {args.out}")

    if not args.apply:
        print("DRY RUN: nothing written. Re-run with --apply --base-url <url> to grant.")
        return 0
    if not todo:
        print("nothing to grant.")
        return 0

    failures = apply(todo, args.base_url, secret, args.batch_size)
    with _read_only():
        now_held = perpetual_pro_holders(todo, account_of)
    reported = {k for k, _ in failures}
    unconfirmed = sorted(todo - now_held - reported)
    failures += [(k, "not perpetual pro on read-back") for k in unconfirmed]
    if args.verbose:
        for k, reason in failures:
            print(f"  failed: {k} ({reason})")
    print(f"SUMMARY: sent {len(todo)}; confirmed perpetual pro on read-back "
          f"{len(todo & now_held)}; failures {len(failures)}"
          + (f" (of which not seen on read-back: {len(unconfirmed)}, so DATABASE_URL and "
             "--base-url may be different environments)" if unconfirmed else ""))
    if failures:
        print("Re-run the same command: users already granted are skipped.")
        return 1
    return 0


def main(argv=None) -> int:
    try:
        return _run(argv)
    except Refused as e:
        print(f"grant_lifetime_pro_existing_users: REFUSED. {e}")
        return 2
    except Exception as e:  # never str(e): a DB error can carry ids
        print(f"grant_lifetime_pro_existing_users: ERROR ({type(e).__name__}). Details are "
              "withheld because they can name ids. Nothing more was sent; re-run the dry run.",
              file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
