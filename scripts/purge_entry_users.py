#!/usr/bin/env python3
"""purge_entry_users.py — one-time purge of orphaned ESPN/MFL entry users (2026-11).

Legal R28.12 row 2 and R28.16; head-eng 2026-10-26. The old unverified
ESPN/MFL league-ID sign-in minted users keyed `entry:espn:<SWID>`,
`entry:espn:<league>.t<team>` and `entry:mfl:<league>.f<franchise>`. No one can
delete them (they belong to no account a person can prove), and an ESPN one
may carry a third person's identifier (the team owner's SWID). Each is removed
through the FULL deletion path, `accounts.delete_user_data`, one id per call.
In one transaction it locks the id's users and accounts rows (FOR UPDATE on
Postgres), deletes private rows and anonymizes shared ones per privacy §6.
Never a bare row delete. Its lifecycle "drain" (user_data_lifecycle.hold) is
process-local: it waits only for user work admitted in THIS process, which
for a one-off script is none, and afterwards fails that process's queued
stale work. It cannot see requests running in the web service; that is why
the runbook turns the entry flag off and restarts the service first.

It must finish BEFORE `landing.platform_options` goes back on: a credential
left on an entry id would make the proof-based sign-in's
`platform_identity_in_use` answer 409 to the real owner. Runbook:
docs/runbook.md § "Purge orphaned ESPN/MFL entry users (one-time, 2026-11)".

Usage, from the repo root (`--cutoff` is required in every mode):
    python3 scripts/purge_entry_users.py --cutoff 2026-10-26T00:00:00Z            # dry run
    python3 scripts/purge_entry_users.py --cutoff … --execute --expect N \
        [--delete-verified-credentials M]
    python3 scripts/purge_entry_users.py --cutoff … --verify
    (add --allow-local only for a local SQLite test run)

Targets (head-eng's filter): an `entry:` id with a users row whose
`verified_via` is NULL and `created_at` is before the cutoff, or an `entry:` id
with NO users row (an orphan; a proven sign-in always writes one with
`verified_via`). Verified ids, ids created at or after the cutoff, and ids
whose users row has no usable `created_at` are skipped, counted, and never
touched. But an UNVERIFIED entry id created at or after the cutoff means a
live entry session minted it after the flag went off (the flip or the
restart didn't take): the dry run says STOP and prints no execute command,
and --verify fails on it.

Verified entry users are never deleted, but legal R28.17 A1 removes their
ESPN/MFL credential rows: `--delete-verified-credentials M` (M = the dry run's
count, refused if stale) deletes those rows and nothing else of theirs, in the
same execute. --verify then checks R28.16's two parts: (g) zero entry users
without verified_via, and (b) zero credential rows on any entry user.

Output is COUNTS ONLY: never an id, SWID, team or league name (legal). The DB
is whatever `backend.database` points at (DATABASE_URL, default
data/trade_finder.db). Every mode prints that DB's identity first (dialect,
the host's first label, the database name; never credentials) and refuses a
local SQLite database unless `--allow-local` is passed. The prod run needs the
operator's own word in the acting session.

The work runs on engines built with `hide_parameters=True`, swapped into
`backend.database` for the run (`db.engine`, and `db.ro_engine`, which the
dry run and --verify read through), so `delete_user_data` uses them too and
no SQL error can print bound ids. Any unexpected error prints only its type.

Exit codes: 0 done / verified; 1 --verify failed or a target failed; 2
refused (local DB, stale --expect, a non-entry id in a deletion scope, bad
arguments); 3 an unexpected error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from sqlalchemy import create_engine, delete, func, inspect, select  # noqa: E402

from backend import accounts, database as db  # noqa: E402

ENTRY_PREFIX = "entry:"
CHUNK = 500

# User-id columns `_delete_user_data` filters on that neither
# accounts._EXPORT_TABLES nor accounts._ADDITIONAL_PRIVATE_TABLES names.
# tests/test_purge_entry_users.py captures delete_user_data's SQL and fails if
# it filters a user id on a column this module doesn't discover.
DELETION_ONLY_KEYS = (
    ("accounts_table", "sleeper_user_id"),
    ("sessions_table", "user_id"),
    ("entitlements_table", "user_id"),
    ("subscription_events_table", "user_id"),
    ("identity_links_table", "sleeper_user_id"),
    ("experiment_assignments_table", "unit_id"),
    ("trade_matches_table", "user_a_id"),
    ("trade_matches_table", "user_b_id"),
    ("trade_impressions_table", "target_user_id"),
    ("bad_trade_flags_table", "target_user_id"),
    ("trade_proposals_table", "target_user_id"),
    ("referrals_table", "referrer_user_id"),
    ("referrals_table", "referred_user_id"),
    ("users_table", "invited_by"),
    ("draft_picks_table", "owner_user_id"),
    ("draft_picks_table", "original_user_id"),
    ("recorded_picks_table", "picking_team_id"),
    ("prepared_trade_participants_table", "participant_user_id"),
    # Other users' overhaul offers naming the deleted user (overhauls'
    # account_user_id comes from the export manifest).
    ("overhaul_offers_table", "counterparty_user_id"),
)
# Reported as info counts, never a failure (onboarding-eng, 2026-10-26).
# user_events.props: OTHER users' events can name an entry id (e.g.
# pick_assignment_changed.new_owner). delete_user_data anonymizes those
# audit-trail ids and --verify (d) fails on any left; other event types are info.
JSON_MENTIONS = (("standing_offers_table", "team_user_ids"),
                 ("leagues_table", "opponent_data"),
                 ("user_events_table", "props"))
CREDENTIAL_TABLES = ("espn_credentials_table", "mfl_credentials_table")


def key_columns() -> list[tuple[str, str]]:
    """(table attr, column) pairs that can hold a user id: accounts' own
    deletion/export manifests plus the deletion-only list above."""
    pairs = {(attr, col) for _key, attr, col, _omit in accounts._EXPORT_TABLES}
    pairs |= {(name + "_table", "user_id") for name in accounts._ADDITIONAL_PRIVATE_TABLES}
    pairs |= set(DELETION_ONLY_KEYS)
    return sorted(pairs)


def _guard(uid: str) -> str:
    if not isinstance(uid, str) or not uid.startswith(ENTRY_PREFIX):
        raise ValueError("refusing a non-entry id")
    return uid


def _guard_scope(uid: str) -> str:
    """Guard every id delete_user_data(uid) would delete, not just `uid`: it
    also removes each alias accounts._user_data_scope resolves (an account
    bound to uid, that account's acct_ key, the working keys of its
    sessions). An orphaned entry id has none, so any alias refuses."""
    _guard(uid)
    with db.engine.connect() as conn:
        user_ids, _account_ids = accounts._user_data_scope(conn, uid)
    for alias in user_ids:
        _guard(alias)
    return uid


def _present(pairs, existing) -> list:
    out = []
    for attr, col in pairs:
        tbl = getattr(db, attr)
        if tbl.name in existing and col in tbl.c:
            out.append((tbl, col))
    return out


_CUTOFF = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})")


def _parse_cutoff(text) -> datetime | None:
    """The operator's --cutoff: a full datetime, seconds included, with an
    explicit timezone (Z or ±HH:MM). Date-only, ISO week forms and naive
    datetimes are refused: a cutoff hours off selects different targets."""
    if not isinstance(text, str) or not _CUTOFF.fullmatch(text):
        return None
    try:
        return datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError:
        return None


def _parse_iso(value) -> datetime | None:
    """A stored users.created_at (DB data, so lenient; naive reads as UTC)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _chunks(ids):
    ids = sorted(ids)
    for i in range(0, len(ids), CHUNK):
        yield ids[i:i + CHUNK]


def discover(cutoff: datetime) -> dict:
    """Every entry: id in a key column, classified against the cutoff."""
    existing = set(inspect(db.engine).get_table_names())
    keys = _present(key_columns(), existing)
    ids: set[str] = set()
    with db.engine.connect() as conn:
        for tbl, col in keys:
            ids.update(v for v in conn.execute(
                select(tbl.c[col]).where(tbl.c[col].like(ENTRY_PREFIX + "%")).distinct()).scalars()
                if isinstance(v, str) and v.startswith(ENTRY_PREFIX))
        users = db.users_table
        rows = {}
        for chunk in _chunks(ids):
            for r in conn.execute(select(users.c.sleeper_user_id, users.c.verified_via,
                                         users.c.created_at).where(users.c.sleeper_user_id.in_(chunk))):
                rows[r.sleeper_user_id] = r
    out = {"targets": set(), "orphans": 0, "unverified_before": 0, "skipped_verified": set(),
           "skipped_after_cutoff": set(), "skipped_no_created_at": set(), "keys": keys,
           "existing": existing}
    for uid in ids:
        r = rows.get(uid)
        if r is None:
            out["targets"].add(uid)
            out["orphans"] += 1
        elif (r.verified_via or "").strip():   # a blank value isn't a verification
            out["skipped_verified"].add(uid)
        else:
            created = _parse_iso(r.created_at)
            if created is None:
                out["skipped_no_created_at"].add(uid)
            elif created >= cutoff:
                out["skipped_after_cutoff"].add(uid)
            else:
                out["targets"].add(uid)
                out["unverified_before"] += 1
    return out


def _count_naming(keys, ids) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not ids:
        return counts
    with db.engine.connect() as conn:
        for tbl, col in keys:
            n = sum(conn.execute(select(func.count()).select_from(tbl)
                                 .where(tbl.c[col].in_(chunk))).scalar() or 0
                    for chunk in _chunks(ids))
            if n:
                counts[f"{tbl.name}.{col}"] = n
    return counts


def _count_like(pairs, existing, pattern) -> dict[str, int]:
    counts = {}
    with db.engine.connect() as conn:
        for tbl, col in _present(pairs, existing):
            counts[f"{tbl.name}.{col}"] = conn.execute(
                select(func.count()).select_from(tbl).where(tbl.c[col].like(pattern))).scalar() or 0
    return counts


def _count_entry_prefixed(pairs, existing) -> dict[str, int]:
    """Rows whose column starts with `entry:`, case-sensitively on every
    dialect: SQLite's LIKE ignores ASCII case, so an "ENTRY:" row would count."""
    counts = {}
    with db.engine.connect() as conn:
        for tbl, col in _present(pairs, existing):
            c = tbl.c[col]
            counts[f"{tbl.name}.{col}"] = conn.execute(
                select(func.count()).select_from(tbl).where(
                    c.like(ENTRY_PREFIX + "%"),
                    func.substr(c, 1, len(ENTRY_PREFIX)) == ENTRY_PREFIX)).scalar() or 0
    return counts


def _assignment_event_entry_ids(found) -> set[str]:
    """entry: ids still named in pick_assignment_changed events (old_owner /
    new_owner / actor). delete_user_data anonymizes a deleted Fleeced-minted id
    there, so after --execute only skipped (kept) entry users may remain."""
    if "user_events" not in found["existing"]:
        return set()
    ev = db.user_events_table
    named: set[str] = set()
    with db.engine.connect() as conn:
        for raw in conn.execute(select(ev.c.props).where(
                ev.c.event_type == "pick_assignment_changed",
                ev.c.props.like("%" + ENTRY_PREFIX + "%"))).scalars():
            try:
                props = json.loads(raw or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(props, dict):
                continue
            named.update(v for k in ("old_owner", "new_owner", "actor")
                         if isinstance(v := props.get(k), str) and v.startswith(ENTRY_PREFIX))
    return named


def _assignment_order_entry_ids(found) -> set[str]:
    """entry: ids still listed in any league's pick_assignment_settings.order
    (other importers' rows included). delete_user_data anonymizes a deleted
    Fleeced-minted id there, so after --execute only skipped entry users may
    remain."""
    if "leagues" not in found["existing"]:
        return set()
    lg = db.leagues_table
    named: set[str] = set()
    with db.engine.connect() as conn:
        for raw in conn.execute(select(lg.c.pick_assignment_settings).where(
                lg.c.pick_assignment_settings.like("%" + ENTRY_PREFIX + "%"))).scalars():
            try:
                settings = json.loads(raw or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            order = settings.get("order") if isinstance(settings, dict) else None
            if isinstance(order, list):
                named.update(o for o in order if isinstance(o, str) and o.startswith(ENTRY_PREFIX))
    return named


def _users_count(found) -> int | None:
    """Rows in users, or None when the table is missing (wrong or empty DB)."""
    if "users" not in found["existing"]:
        return None
    with db.engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(db.users_table)).scalar() or 0


def _info(found) -> list[str]:
    json_counts = _count_like(JSON_MENTIONS, found["existing"], "%" + ENTRY_PREFIX + "%")
    return [
        "info (never a failure):",
        "  rows whose JSON mentions an entry: id: "
        + ", ".join(f"{k} {v}" for k, v in json_counts.items()),
    ]


def _credentials_on(found, ids) -> dict[str, int]:
    """ESPN/MFL credential rows held by `ids`, per table.column (non-zero only)."""
    return _count_naming(_present([(a, "user_id") for a in CREDENTIAL_TABLES], found["existing"]),
                         ids)


def _credential_lines(found) -> tuple[list[str], int]:
    """Legal R28.17 A1: VERIFIED entry users keep their accounts, but their
    ESPN/MFL credential rows go (--delete-verified-credentials). Credentials on
    other skipped entry users are never deleted here; --verify (b) fails on
    them. Counts only."""
    on_verified = _credentials_on(found, found["skipped_verified"])
    on_other = _credentials_on(found, found["skipped_after_cutoff"] | found["skipped_no_created_at"])
    fmt = lambda c: " (" + ", ".join(f"{k} {v}" for k, v in c.items()) + ")" if c else ""  # noqa: E731
    n = sum(on_verified.values())
    return [
        f"credential rows on verified entry users (--delete-verified-credentials removes them; "
        f"legal R28.17 A1): {n}{fmt(on_verified)}",
        f"credential rows on other skipped entry users (never deleted here; --verify (b) fails "
        f"on any): {sum(on_other.values())}{fmt(on_other)}",
    ], n


def _summary(found) -> list[str]:
    skipped = len(found["skipped_verified"]) + len(found["skipped_after_cutoff"])
    return [
        f"entry ids found: {len(found['targets']) + skipped + len(found['skipped_no_created_at'])}",
        f"  targets: {len(found['targets'])} (unverified, created before the cutoff: "
        f"{found['unverified_before']}; orphans with no users row: {found['orphans']})",
        f"  skipped (verified or after cutoff): {skipped} (verified: {len(found['skipped_verified'])}; "
        f"created at or after the cutoff: {len(found['skipped_after_cutoff'])})",
        f"  skipped (no usable created_at): {len(found['skipped_no_created_at'])}",
    ]


def dry_run(cutoff) -> int:
    found = discover(cutoff)
    counts = _count_naming(found["keys"], found["targets"])
    lines = ["purge_entry_users: DRY RUN, nothing changed", *(_summary(found)),
             "rows naming a target, by table.column:"]
    lines += [f"  {k}: {v}" for k, v in sorted(counts.items())] or ["  (none)"]
    lines.append(f"  total: {sum(counts.values())}")
    lines += _info(found)
    cred_lines, n_creds = _credential_lines(found)
    lines += cred_lines
    late = len(found["skipped_after_cutoff"])
    lines.append(f"unverified created after cutoff: {late}")
    if late:
        # The flag flip or the restart didn't take: live entry sessions are
        # still minting users. No execute command is printed.
        lines.append("  STOP: unverified entry users were created at or after the cutoff, so the "
                     "flag flip or the restart didn't take. Don't run --execute; ask head-eng.")
    elif found["targets"] or n_creds:
        # The exact execute command, pre-filled, for the OPERATOR to run after
        # a DB snapshot (runbook). The cutoff is printed in UTC so the copied
        # command selects exactly the targets this dry run counted.
        stamp = cutoff.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        lines.append("next (the operator runs this exact command, after a DB snapshot):")
        # --expect-db pins the copied command to the database this dry run read.
        lines.append(f"  python3 scripts/purge_entry_users.py --cutoff {stamp} "
                     f"--execute --expect {len(found['targets'])} "
                     f"--expect-db {_db_name(db.engine.url)}"
                     + (f" --delete-verified-credentials {n_creds}" if n_creds else ""))
    print("\n".join(lines))
    return 0


def execute(cutoff, expect: int, expect_creds: int = 0) -> int:
    found = discover(cutoff)
    targets = sorted(found["targets"])
    if expect != len(targets):
        print(f"purge_entry_users: REFUSED. --expect {expect} but {len(targets)} targets were "
              "discovered now. Dry-run again and pass the fresh count.")
        return 2
    # Legal R28.17 A1: the ESPN/MFL credential rows of VERIFIED entry users go
    # in the same run (their accounts stay), so one execute + verify passes
    # both parts of R28.16's post-check. The count is pinned like --expect.
    verified = sorted(found["skipped_verified"])
    n_creds = sum(_credentials_on(found, verified).values())
    if expect_creds != n_creds:
        print(f"purge_entry_users: REFUSED. --delete-verified-credentials {expect_creds} but "
              f"verified entry users hold {n_creds} ESPN/MFL credential row(s) now. Dry-run "
              "again and copy the command it prints.")
        return 2
    try:
        for uid in targets:
            _guard_scope(uid)
        for uid in verified:
            _guard(uid)
    except ValueError:
        print("purge_entry_users: REFUSED. A target, or an alias its deletion would also remove "
              "(a bound account, its acct_ key, a session's working key), is not an entry: id. "
              "Nothing was deleted; escalate to head-eng.")
        return 2
    totals: Counter = Counter()
    failed = 0
    for uid in targets:
        try:  # re-checked per id, right before its deletion
            totals.update(accounts.delete_user_data(_guard_scope(uid)))
        except Exception as e:  # the id is never printed; only the error type
            failed += 1
            print(f"  a target failed ({type(e).__name__}); continuing")
    # The purge's own summary first, so it's on record whatever the credential
    # step does next.
    print("\n".join([f"purge_entry_users: EXECUTE. targets: {len(targets)}; "
                     f"deleted: {len(targets) - failed}; failed: {failed}",
                     "summed delete_user_data counts:",
                     json.dumps({k: v for k, v in sorted(totals.items()) if v}, indent=2)]))
    if not n_creds:
        return 1 if failed else 0
    # The credential step fails closed (release-lead #452 round 5, P1-1): it
    # runs only after a clean purge, in one transaction that deletes exactly
    # the M rows the operator confirmed or nothing, and an error prints its
    # type only.
    label = "verified entry users' credential rows"
    if failed:
        print(f"{label}: SKIPPED, {n_creds} kept, because a target failed. Fix that, dry-run "
              "again and run the command it prints.")
        return 1
    try:
        removed = _delete_verified_credentials(found, verified, n_creds)
    except _CountChanged as e:
        print(f"{label}: ROLLED BACK, nothing deleted: {e.count} matched at the write, not "
              f"{n_creds}. Dry-run again and run the command it prints.")
        return 1
    except Exception as e:  # the type only: no id, no SQL parameters
        print(f"{label}: FAILED ({type(e).__name__}), rolled back, nothing deleted. Dry-run "
              "again and run the command it prints.")
        return 1
    print(f"{label} deleted (accounts kept): {sum(removed.values())}"
          + "".join(f"; {k} {v}" for k, v in sorted(removed.items()) if v))
    return 0


class _CountChanged(Exception):
    def __init__(self, count: int):
        super().__init__("credential count changed")
        self.count = count


def _delete_verified_credentials(found, verified, expect: int) -> Counter:
    """Delete ONLY the ESPN/MFL credential rows of `verified` (legal R28.17
    A1): users, accounts, sessions, entitlements and everything else of
    theirs stays. One transaction: unless exactly `expect` rows go (a row
    added or removed since the count), it rolls back and raises."""
    removed: Counter = Counter()
    with db.engine.begin() as conn:
        for tbl, col in _present([(a, "user_id") for a in CREDENTIAL_TABLES], found["existing"]):
            for chunk in _chunks(verified):
                res = conn.execute(delete(tbl).where(tbl.c[col].in_([_guard(u) for u in chunk])))
                removed[tbl.name] += res.rowcount or 0
        if sum(removed.values()) != expect:
            raise _CountChanged(sum(removed.values()))
    return removed


def verify(cutoff) -> int:
    found = discover(cutoff)
    remaining = _count_naming(found["keys"], found["targets"])
    cred_pairs = [(attr, "user_id") for attr in CREDENTIAL_TABLES]
    creds = _count_entry_prefixed(cred_pairs, found["existing"])
    skipped = set().union(found["skipped_verified"], found["skipped_after_cutoff"],
                          found["skipped_no_created_at"])
    on_skipped = _count_naming(_present(cred_pairs, found["existing"]), skipped)
    ok_a = not found["targets"]
    ok_b = not any(creds.values())
    # Re-created ids: an UNVERIFIED entry user created at or after the cutoff
    # means a live entry session minted it after the flag went off. Verified
    # entry users stay skipped and only (b) applies to them.
    late = len(found["skipped_after_cutoff"])
    ok_c = not late
    # (d) the pick grid's audit trail names no deleted entry user (a skipped,
    # kept entry user may still appear: they still exist).
    leftover_events = _assignment_event_entry_ids(found) - skipped
    ok_d = not leftover_events
    # (f) no league's pick-assignment order still lists a removed entry id.
    leftover_orders = _assignment_order_entry_ids(found) - skipped
    ok_f = not leftover_orders
    # (e) a machine identity check: an empty or wrong database must not pass.
    n_users = _users_count(found)
    ok_e = bool(n_users)
    # (g) legal R28.16 part 1: zero entry users without verified_via. (a) and
    # (c) cover targets and late mints; an undated unverified user, which the
    # purge skips, only fails here.
    unverified = (found["unverified_before"] + len(found["skipped_after_cutoff"])
                  + len(found["skipped_no_created_at"]))
    ok_g = not unverified
    lines = ["purge_entry_users: VERIFY", *(_summary(found)),
             f"(a) target ids remaining in key columns: {len(found['targets'])} "
             f"-> {'OK' if ok_a else 'FAIL'}"]
    lines += [f"    {k}: {v}" for k, v in sorted(remaining.items())]
    lines.append("(b) credential rows on any entry: id: "
                 + ", ".join(f"{k} {v}" for k, v in creds.items())
                 + f" -> {'OK' if ok_b else 'FAIL'}")
    if any(on_skipped.values()):
        lines.append("    of those, on a SKIPPED entry user (verified, after the cutoff or no "
                     f"created_at): {sum(on_skipped.values())}. A human must look; the real "
                     "owner's sign-in would get 409.")
        on_verified = sum(_credentials_on(found, found["skipped_verified"]).values())
        if on_verified:
            lines.append(f"    on a verified entry user: {on_verified}. Dry-run again; its command "
                         "deletes them with --delete-verified-credentials (legal R28.17 A1).")
    if ok_c:
        lines.append("(c) unverified entry users created after the cutoff: 0 -> OK")
    else:
        lines.append(f"(c) unverified entry users created after the cutoff: {late}. The flag or "
                     "restart wasn't done; investigate before re-running. -> FAIL")
    lines.append(f"(d) pick_assignment_changed events naming a removed entry id: "
                 f"{len(leftover_events)} -> {'OK' if ok_d else 'FAIL'}")
    lines.append(f"(e) users rows in this database: "
                 f"{'table missing' if n_users is None else n_users} -> "
                 f"{'OK' if ok_e else 'FAIL (empty or wrong database)'}")
    lines.append(f"(f) league pick-assignment orders naming a removed entry id: "
                 f"{len(leftover_orders)} -> {'OK' if ok_f else 'FAIL'}")
    lines.append(f"(g) entry users without verified_via (legal R28.16 part 1): {unverified} -> "
                 f"{'OK' if ok_g else 'FAIL'}")
    lines += _info(found)
    print("\n".join(lines))
    return 0 if ok_a and ok_b and ok_c and ok_d and ok_e and ok_f and ok_g else 1


def _db_name(url) -> str:
    name = url.database or ""
    return Path(name).name if url.get_backend_name() == "sqlite" else name


def _identity(url) -> str:
    """Which database this is, without credentials: dialect, the host's first
    label (`***` when there is no name to show) and the database name."""
    host = url.host or ""
    label = "***" if not host or host.replace(".", "").isdigit() else host.split(".")[0]
    name = url.database or "***"
    if url.get_backend_name() == "sqlite":
        name = Path(name).name
    return f"database: {url.get_backend_name()}; host: {label}; name: {name}"


def _hidden_engine(source, *, read_only: bool):
    """A fresh engine on `source`'s URL that never renders bound parameters
    (ids) into an error message. Read-only on Postgres like db.ro_engine, but
    without its 5 s report timeout: a one-time full scan may need longer.
    SQLite's read-only mode rides in db.ro_engine's URL (`mode=ro`)."""
    url = source.url
    if url.get_backend_name() == "sqlite":
        args = {"check_same_thread": False}
    elif read_only:
        args = {"options": "-c default_transaction_read_only=on"}
    else:
        args = {}
    return create_engine(url, future=True, hide_parameters=True, connect_args=args)


@contextmanager
def _engines(read_only: bool):
    """Swap db.engine (and db.ro_engine) for hide_parameters engines for the
    run. Read modes run on the db.ro_engine database; --execute writes through
    db.engine, which accounts.delete_user_data reads at call time."""
    saved = {"engine": db.engine, "ro_engine": getattr(db, "ro_engine", None)}
    read = _hidden_engine(saved["ro_engine"] or saved["engine"], read_only=True)
    write = None if read_only else _hidden_engine(saved["engine"], read_only=False)
    try:
        db.engine = read if read_only else write
        if saved["ro_engine"] is not None:
            db.ro_engine = read
        yield
    finally:
        db.engine = saved["engine"]
        if saved["ro_engine"] is not None:
            db.ro_engine = saved["ro_engine"]
        for engine in (read, write):
            if engine is not None:
                engine.dispose()


def _run(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], allow_abbrev=False)
    ap.add_argument("--cutoff", required=True,
                    help="when the runbook's step-2 restart completed (after "
                         "landing.platform_options reads false): a full datetime with seconds "
                         "and an explicit timezone, e.g. 2026-10-26T14:00:00Z. An entry user "
                         "created before it is a target; at or after it, it is not")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true",
                      help="delete every target through accounts.delete_user_data")
    mode.add_argument("--verify", action="store_true",
                      help="exit 0 only if no target, no entry: credential row, no unverified entry "
                           "user (created after the cutoff or at all) and no removed entry id in the "
                           "pick audit trail or league pick-assignment order remains, on a non-empty "
                           "users table")
    ap.add_argument("--expect", type=int, help="with --execute: the dry run's target count")
    ap.add_argument("--delete-verified-credentials", type=int, metavar="M",
                    help="with --execute: also delete the ESPN/MFL credential rows held by "
                         "VERIFIED entry users, and nothing else of theirs (legal R28.17 A1); M is "
                         "the dry run's count of those rows")
    ap.add_argument("--allow-local", action="store_true",
                    help="allow a local SQLite database (local test runs only)")
    ap.add_argument("--expect-db", metavar="NAME",
                    help="refuse unless the database name matches NAME (the runbook passes "
                         "the prod database's name in every mode)")
    args = ap.parse_args(argv)
    cutoff = _parse_cutoff(args.cutoff)
    if cutoff is None:
        ap.error("--cutoff must be a full datetime with seconds and an explicit timezone "
                 "(Z or +HH:MM), e.g. 2026-10-26T14:00:00Z")
    if cutoff > datetime.now(timezone.utc):
        ap.error("--cutoff is in the future; use the UTC time the step-2 restart completed")
    if args.execute and args.expect is None:
        ap.error("--execute needs --expect N (the dry run's target count)")
    if not args.execute and args.expect is not None:
        ap.error("--expect only goes with --execute")
    if not args.execute and args.delete_verified_credentials is not None:
        ap.error("--delete-verified-credentials only goes with --execute")
    if args.execute and args.expect_db is None:
        ap.error("--execute needs --expect-db NAME (copy the command the dry run printed)")
    print(_identity(db.engine.url))
    if db.engine.url.get_backend_name() == "sqlite" and not args.allow_local:
        print("purge_entry_users: REFUSED. That is a local SQLite database, not the target. "
              "Set DATABASE_URL in this shell (runbook), or pass --allow-local for a local "
              "test run.")
        return 2
    if args.expect_db is not None and _db_name(db.engine.url) != args.expect_db:
        print("purge_entry_users: REFUSED. The database name doesn't match --expect-db; "
              "check DATABASE_URL in this shell.")
        return 2
    with _engines(read_only=not args.execute):
        if args.execute:
            return execute(cutoff, args.expect, args.delete_verified_credentials or 0)
        return verify(cutoff) if args.verify else dry_run(cutoff)


def main(argv=None) -> int:
    try:
        return _run(argv)
    except Exception as e:  # never str(e): a DB error can carry the statement's ids
        print(f"purge_entry_users: ERROR ({type(e).__name__}). Details are withheld because "
              "they can name ids. Re-run the dry run to see the current state.", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
