#!/usr/bin/env python3
"""grant_pro_to_users.py — lifetime (perpetual) Pro for named people, later on.

The companion to grant_lifetime_pro_existing_users.py: that one grants every
user present at paid launch; this one grants a list of people you name, at any
time afterwards (a friend, a tester, a support make-good). Runbook:
docs/plans/monetization-launch/paid-launch/turn-on-runbook.md, "Granting
lifetime Pro to someone later".

Each identifier is resolved read-only against the database exactly as the admin
routes resolve it (entitlements.resolve_user: Sleeper id, Sleeper username,
acct_*, bare account id). Identifiers that resolve to the same person count
once. A person who already holds an active, non-expiring 'pro' row (matched on
user id or account, like entitlements._active_rows) is skipped, so a second
--apply sends nothing.

The grants go through the deployed server's `POST /api/admin/entitlements/bulk-grant`
(source manual_grant, granted_by operator, perpetual, your --note stored on the
row), and the database is then re-read to confirm each one. The reasons are the
existing script's (its docstring, "WHY HTTP FOR THE WRITES"); its helpers are
imported from it, not copied.

Usage, from the repo root (secrets from the gitignored secrets.local.env):
    set -a; . ./secrets.local.env; set +a
    export DATABASE_URL="$DATABASE_URL_PROD"
    # dry run (default): what would happen, counts only
    python3 scripts/grant_pro_to_users.py --user <sleeper username or id>
    # apply
    python3 scripts/grant_pro_to_users.py --user <sleeper username or id> \
        --apply --base-url https://<render-host> --note "<why>"
    (--users-file PATH: one identifier per line, blank lines and # comments
    ignored; --allow-local only for a local SQLite test run)

Secrets: CRON_SECRET from the environment only, never argv, never printed.
Output is counts only; identifiers and ids appear only with --verbose and in
the --out file (mode 0600).

Exit codes: 0 done; 1 a grant failed or the read-back found a key without
perpetual Pro; 2 refused (local DB, an identifier that matches no one with
--apply, missing --note / --base-url / CRON_SECRET, bad arguments); 3 an
unexpected error (its type only).
"""
from __future__ import annotations

import argparse
import os
import sys

import grant_lifetime_pro_existing_users as base  # same directory: scripts/

from backend import database as db, entitlements  # noqa: E402  (base put REPO on sys.path)

Refused = base.Refused
ACCT = base.ACCT


def resolve(idents) -> tuple[dict, dict, list]:
    """Resolve identifiers read-only. Returns
    (key -> [identifiers that resolved to it], account_of, [unresolved]).

    The key sent to bulk-grant is acct_<account id> when the person has an
    account (the route resolves acct_* through the accounts row, to the bound
    Sleeper id if any, so this works even when that Sleeper id has no users
    row), otherwise the resolved user id."""
    by_key: dict[str, list] = {}
    account_of: dict[str, str] = {}
    missing: list[str] = []
    for ident in idents:
        user_id, account_id = entitlements.resolve_user(ident)
        if user_id is None:
            missing.append(ident)
            continue
        if account_id:
            key = f"{ACCT}{account_id}"
            if not user_id.startswith(ACCT):
                account_of[user_id] = account_id
        else:
            key = user_id
        by_key.setdefault(key, []).append(ident)
    return by_key, account_of, missing


def _read_idents(args) -> list[str]:
    """--user values then --users-file lines, stripped, first occurrence kept."""
    raw = [u.strip() for u in args.user]
    if args.users_file:
        raw += base._read_exclude_file(args.users_file)
    out = []
    for ident in raw:
        if ident and ident not in out:
            out.append(ident)
    return out


def _run(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], allow_abbrev=False)
    ap.add_argument("--user", action="append", default=[], metavar="ID",
                    help="person to grant (repeatable): Sleeper id or username, acct_*, "
                         "or account id")
    ap.add_argument("--users-file", metavar="PATH",
                    help="file of identifiers to grant, one per line (# comments ignored)")
    ap.add_argument("--apply", action="store_true",
                    help="send the grants (default is a dry run that writes nothing)")
    ap.add_argument("--base-url", help="with --apply: the API base, e.g. https://<render-host>")
    ap.add_argument("--note", help="with --apply (required): why, stored on every grant")
    ap.add_argument("--out", metavar="PATH",
                    help="file to write the would-grant (dry run) or sent (--apply) keys to")
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--allow-local", action="store_true",
                    help="allow a local SQLite database (local test runs only)")
    ap.add_argument("--verbose", action="store_true", help="also print identifiers and ids")
    args = ap.parse_args(argv)

    if args.batch_size < 1:
        ap.error("--batch-size must be at least 1")
    if not args.apply and args.base_url:
        ap.error("--base-url only goes with --apply")
    idents = _read_idents(args)
    if not idents:
        ap.error("name at least one person with --user or --users-file")
    note = (args.note or "").strip()
    secret = os.environ.get(base.SECRET_ENV, "").strip()
    if args.apply:
        if not args.base_url:
            raise Refused("--apply needs --base-url")
        if not note:
            raise Refused("--apply needs --note (why; stored on the grant for later audits)")
        if not secret:
            raise Refused(f"--apply needs {base.SECRET_ENV} in the environment "
                          "(set -a; . ./secrets.local.env; set +a)")

    print(base._identity(db.engine.url))
    if db.engine.url.get_backend_name() == "sqlite" and not args.allow_local:
        raise Refused("that is a local SQLite database. Set DATABASE_URL in this shell, "
                      "or pass --allow-local for a local test run")

    with base._read_only():
        by_key, account_of, missing = resolve(idents)
        held = base.perpetual_pro_holders(set(by_key), account_of)

    todo = set(by_key) - held
    if args.verbose:
        for key in sorted(by_key):
            what = "skip, already holds perpetual pro" if key in held else (
                "to grant" if args.apply else "would grant")
            print(f"  {', '.join(by_key[key])} -> {key}: {what}")
        for ident in missing:
            print(f"  {ident}: not found")
    print(f"identifiers given: {len(idents)}; people found: {len(by_key)}; "
          f"not found: {len(missing)}")
    print(f"already hold active perpetual pro (skipped): {len(held)}")
    print(f"{'to grant' if args.apply else 'would grant'}: {len(todo)}")

    if not args.apply:
        if args.out:
            base._write_out(args.out, todo)
            print(f"list written to {args.out}")
        if missing:
            print(f"WARNING: {len(missing)} identifier(s) match no user (--verbose lists "
                  "them); --apply will refuse until they are fixed or removed.")
        print("DRY RUN: nothing written. Re-run with --apply --base-url <url> --note <why> "
              "to grant.")
        return 0

    if missing:
        raise Refused(f"{len(missing)} identifier(s) match no user (--verbose lists them). "
                      "Nothing was granted")
    if args.out:
        base._write_out(args.out, todo)
        print(f"list written to {args.out}")
    if not todo:
        print("nothing to grant.")
        return 0

    failures = base.apply(todo, args.base_url, secret, args.batch_size, note=note)
    with base._read_only():
        now_held = base.perpetual_pro_holders(todo, account_of)
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
        print(f"grant_pro_to_users: REFUSED. {e}")
        return 2
    except Exception as e:  # never str(e): a DB error can carry ids
        print(f"grant_pro_to_users: ERROR ({type(e).__name__}). Details are withheld "
              "because they can name ids. Nothing more was sent; re-run the dry run.",
              file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
