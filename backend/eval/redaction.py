"""Account deletion's model-artifact hook (legal R28.20; models-lead E-b1,
E-b3).

A fitted value model keeps `partner_rates` keyed "<viewer>|<partner>"
(value_model._partner_key), so a deleted user's platform id survives in its
keys, as the viewer or as the partner. The deletion scrub (trades-eng) calls
redact_model_store once per run with that run's {platform id: token} map,
and every persisted record's keys take the same token as the scrub's other
stores. Fit and score stay consistent: partner rates need only equality,
never the id's value (E2), so the rates keep their values under the token.
Dropping the keys would change live scores, since those pairs would fall
back to the global rate.

Here, not in value_model.py: that module is in the engine code hash
(server._ENGINE_CODE_MODULES), and editing it would cold every stored page.
No id is logged or returned; the caller gets a count.
"""

from __future__ import annotations

import json
import os
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


def redact_partner_rates(rates: Mapping, tokens: Mapping[str, str]) -> tuple[dict, int]:
    """(`rates` with every key's viewer and partner that `tokens` maps
    replaced by its token, the number of keys changed). Values are kept."""
    out, changed = {}, 0
    for key, rate in rates.items():
        viewer, sep, partner = str(key).partition("|")
        new = f"{tokens.get(viewer, viewer)}|{tokens.get(partner, partner)}" if sep else key
        changed += new != key
        out[new] = rate
    return out, changed


def redact_model_store(tokens: Mapping[str, str], path: str | None = None) -> int:
    """Rewrite the value-model store (value_model.models_path() unless
    `path`) so no record's partner_rates key names a platform id in
    `tokens`; returns the number of keys changed (0 when there's nothing to
    do). The file is replaced atomically (a temp file in the same directory,
    then os.replace), which changes its mtime, so the serve-time cache
    reloads. Unparseable lines (torn writes) are kept as they are.
    Idempotent: a re-run with the same map changes nothing. Raises when the
    store keeps changing under it, so the scrub retries."""
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
                rates = record["model"]["partner_rates"]
            except (json.JSONDecodeError, KeyError, TypeError):
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
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".redact")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("\n".join(out) + "\n")
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return changed
    raise RuntimeError("value-model store kept changing during redaction; retry")
