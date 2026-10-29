"""Account deletion's model-artifact hook (legal R28.20 and R28.22;
models-lead E-b1, E-b3).

A fitted value model keeps `partner_rates` keyed "<viewer>|<partner>"
(value_model._partner_key), so a deleted user's platform id survives in its
keys, as the viewer or as the partner. The deletion scrub (trades-eng) calls
redact_model_store once per run with that run's {platform id: token} map.
Under legal R28.22 (f, c3 #14), every persisted record's keys whose viewer
is a deleted user (their own rates) are deleted, and its keys whose partner
is one take that user's token, the same token as the scrub's other stores.
Partner rates need only equality, never the id's value (E2), so a re-keyed
rate keeps its value. Dropping those keys instead would change replay
scores of the redacted cards, whose partner is the token (models-lead
addendum G's E-b3 wording).

Here, not in value_model.py: that module is in the engine code hash
(server._ENGINE_CODE_MODULES), and editing it would cold every stored page.
No id is logged or returned; the caller gets a count.

Not locked (head-eng's #529 check, (b)): value_model.append_model takes no
lock, and adding one would edit that hashed module. An append in flight
during the rewrite (written after the last signature check, or to the file
os.replace swapped out) is lost: that night's refit record, so serving keeps
the previous model until the next nightly_refit. The scrub closes the window
by calling this in the daily tick before nightly_refit, never beside it.
"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping

from backend import value_model

# A concurrent append (the nightly fit) between the read and the replace is
# retried this many times before giving up (the scrub's job then retries).
_ATTEMPTS = 3


def _signature(path: str) -> tuple[int, int]:
    """(mtime_ns, size): what a concurrent append changes."""
    st = os.stat(path)
    return st.st_mtime_ns, st.st_size


def _may_hold(line: str, tokens: Mapping[str, str]) -> bool:
    """Whether an unparseable line may hold a platform id in `tokens`: one
    appears in it, or it ends in the start of one (torn mid-id: its text
    after the last key delimiter, '"' or '|')."""
    tail = re.split(r'["|]', line)[-1]
    return any(pid and (pid in line or (tail and pid.startswith(tail))) for pid in tokens)


def redact_partner_rates(rates: Mapping, tokens: Mapping[str, str]) -> tuple[dict, int]:
    """(`rates` without the keys whose viewer `tokens` maps, and with the
    keys whose partner it maps re-keyed to that token, the number of keys
    deleted or re-keyed). Values are kept. A re-keyed pair already present
    under the token keeps the rate it has."""
    out, rekeyed, changed = {}, [], 0
    for key, rate in rates.items():
        viewer, sep, partner = str(key).partition("|")
        if sep and viewer in tokens:          # the deleted user's own rates (R28.22)
            changed += 1
        elif sep and partner in tokens:
            rekeyed.append((f"{viewer}|{tokens[partner]}", rate))
            changed += 1
        else:
            out[key] = rate
    for key, rate in rekeyed:
        out.setdefault(key, rate)
    return out, changed


def redact_model_store(tokens: Mapping[str, str], path: str | None = None) -> int:
    """Rewrite the value-model store (value_model.models_path() unless
    `path`) so no record's partner_rates key names a platform id in
    `tokens` (redact_partner_rates); returns the number of changes, keys
    deleted or re-keyed plus unparseable lines dropped (0 when there's
    nothing to do). The file is replaced atomically (a temp file in the same
    directory, with the store's mode, then os.replace), which changes its
    mtime, so the serve-time cache reloads. An unparseable line
    (a torn write) that may hold a mapped id is dropped (_may_hold): the
    loader skips such lines, so serving is unchanged (head-eng's #529 check,
    (a)); others are kept as they are. Idempotent: a re-run with the same map
    changes nothing. Raises when the store keeps changing under it, so the
    scrub retries."""
    path = path or value_model.models_path()
    if not tokens or not os.path.exists(path):
        return 0
    for _ in range(_ATTEMPTS):
        before = _signature(path)
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        changed, out = 0, []
        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                if _may_hold(line, tokens):
                    changed += 1
                else:
                    out.append(line)
                continue
            try:
                rates = record["model"]["partner_rates"]
            except (KeyError, TypeError):
                out.append(line)
                continue
            if not isinstance(rates, dict):
                out.append(line)
                continue
            record["model"]["partner_rates"], n = redact_partner_rates(rates, tokens)
            changed += n
            out.append(json.dumps(record, sort_keys=True) if n else line)
        if not changed:
            return 0
        if _signature(path) != before:
            continue                       # appended to meanwhile: read it again
        mode = stat.S_IMODE(os.stat(path).st_mode)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".redact")
        try:
            os.fchmod(fd, mode)                # mkstemp's is 0600
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("".join(f"{line}\n" for line in out))
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return changed
    raise RuntimeError("value-model store kept changing during redaction; retry")
