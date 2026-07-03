"""sleeper_write.py — adapter for Sleeper's undocumented authenticated write API
("Send in Sleeper").

⚠️ FLAGGED-BETA / ToS-adverse. See docs/plans/sleeper-write-capture-runbook.md §C4:
Sleeper publishes only a *read-only* public API and no sanctioned write API. This
module reproduces the private `propose_trade` GraphQL mutation captured from live
web traffic on 2026-07-02. It is gated everywhere by the `trade.send_in_sleeper`
feature flag (default OFF). The user's Sleeper token is a **full-account
credential** — it is encrypted at rest (Fernet) and must never be logged.

Captured facts (runbook §C1–C3):
  - endpoint : POST https://sleeper.com/graphql   (single endpoint, op per call)
  - headers  : content-type: application/json
               x-sleeper-graphql-op: <operationName>
               authorization: Bearer <JWT>        (365-day HS256, self-contained)
  - propose_trade encodes *every* traded player in BOTH k_adds and k_drops,
    paired positionally with roster_ids:
        v_adds[i]  = roster_id that RECEIVES  k_adds[i]
        v_drops[i] = roster_id that GIVES UP  k_drops[i]
    league_id + draft_picks are inlined into the query string; adds/drops ride
    as variables. FAAB rides in waiver_budget:[{sender,receiver,amount}].

This module has no Flask / DB imports on purpose — it is pure and unit-testable.
The HTTP call is injectable via `_opener` so tests never touch the network.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

SLEEPER_GRAPHQL_URL = "https://sleeper.com/graphql"
_HTTP_TIMEOUT = 15
_ENV_KEY = "SLEEPER_TOKEN_KEY"  # Fernet key (base64) — set in secrets.local.env / Render


# ---------------------------------------------------------------------------
# Errors — the caller maps these to an HTTP response + deep-link fallback.
# ---------------------------------------------------------------------------

class SleeperWriteError(Exception):
    """A write to Sleeper failed. `kind` steers the caller's handling:
      'auth'    → token missing/expired/rejected → prompt reconnect
      'network' → transport problem → retry / deep-link fallback
      'config'  → server misconfigured (no key / lib) → 503, feature dark
      'error'   → everything else → deep-link fallback
    """

    def __init__(self, message: str, *, kind: str = "error", detail: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.detail = detail


class SleeperAuthError(SleeperWriteError):
    """Token missing / expired / rejected. Caller should drop the stored token
    and prompt the user to reconnect Sleeper."""

    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message, kind="auth", detail=detail)


# ---------------------------------------------------------------------------
# Token encryption at rest (Fernet). Key comes from the environment; if it is
# missing we fail closed (config error) rather than store a plaintext token.
# ---------------------------------------------------------------------------

def _fernet():
    try:
        from cryptography.fernet import Fernet
    except Exception as e:  # pragma: no cover - import guard
        raise SleeperWriteError("cryptography package not installed", kind="config", detail=str(e))
    key = (os.environ.get(_ENV_KEY) or "").strip()
    if not key:
        raise SleeperWriteError(f"{_ENV_KEY} is not set — cannot store/read Sleeper tokens", kind="config")
    try:
        return Fernet(key.encode("ascii"))
    except Exception as e:
        raise SleeperWriteError(f"{_ENV_KEY} is not a valid Fernet key", kind="config", detail=str(e))


def token_encryption_available() -> bool:
    """True if a usable encryption key is configured (feature can operate)."""
    try:
        _fernet()
        return True
    except SleeperWriteError:
        return False


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except SleeperWriteError:
        raise
    except Exception as e:
        raise SleeperWriteError("could not decrypt stored Sleeper token", kind="config", detail=str(e))


# ---------------------------------------------------------------------------
# JWT introspection — read-only, NO signature verification. We only need the
# self-contained claims (sleeper user_id + exp) that C1 confirmed are present.
# ---------------------------------------------------------------------------

def token_claims(jwt: str) -> dict:
    """Return the decoded (unverified) JWT payload, or {} if unparseable."""
    try:
        payload_b64 = jwt.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}


def token_expiry(jwt: str) -> int | None:
    """The JWT `exp` (unix seconds), or None if absent/unparseable."""
    exp = token_claims(jwt).get("exp")
    try:
        return int(exp) if exp is not None else None
    except (TypeError, ValueError):
        return None


def token_sleeper_user_id(jwt: str) -> str | None:
    uid = token_claims(jwt).get("user_id")
    return str(uid) if uid is not None else None


def is_expired(jwt: str, *, skew: int = 0) -> bool:
    """True if the token is already past (or within `skew`s of) expiry."""
    exp = token_expiry(jwt)
    return exp is not None and exp <= (time.time() + skew)


# ---------------------------------------------------------------------------
# propose_trade — payload construction (verbatim structure from the capture).
# ---------------------------------------------------------------------------

# Placeholders are replaced (not .format()'d) to avoid brace-escaping bugs in
# the GraphQL body. league_id + draft_picks + waiver_budget are inlined exactly
# as Sleeper's own web client sends them.
_PROPOSE_TRADE_TEMPLATE = (
    'mutation propose_trade($k_adds: [String], $v_adds: [Int], $k_drops: [String], $v_drops: [Int]) {\n'
    '        propose_trade(league_id: "__LEAGUE_ID__",draft_picks: __DRAFT_PICKS__,'
    'k_adds: $k_adds,v_adds: $v_adds,k_drops: $k_drops,v_drops: $v_drops,waiver_budget: __WAIVER_BUDGET__){\n'
    '          adds\n          consenter_ids\n          created\n          creator\n          drops\n'
    '          league_id\n          leg\n          metadata\n          roster_ids\n          settings\n'
    '          status\n          status_updated\n          transaction_id\n          draft_picks\n'
    '          type\n          player_map\n          waiver_budget\n        }\n      }'
)


@dataclass
class ProposeTradeRequest:
    league_id: str
    my_roster_id: int          # the proposing user's roster
    their_roster_id: int       # the counterparty's roster
    give_player_ids: list      # players I send    (my_roster  -> their_roster)
    receive_player_ids: list   # players I receive (their_roster -> my_roster)
    draft_picks: list | None = None      # pre-encoded "orig,season,round,from,to" strings
    waiver_budget: list | None = None    # [{sender, receiver, amount}]


def _is_valid_pick_str(p) -> bool:
    parts = str(p).split(",")
    return len(parts) == 5 and all(x.strip().lstrip("-").isdigit() for x in parts)


def build_propose_trade_body(req: ProposeTradeRequest) -> dict:
    """Build the exact GraphQL request body for propose_trade.

    Every traded player appears in BOTH k_adds and k_drops; the paired
    v_adds / v_drops carry the receiving / giving roster_ids.
    """
    lid = str(req.league_id)
    if not lid.isdigit():
        raise SleeperWriteError("league_id must be a numeric string", kind="error")
    if req.my_roster_id == req.their_roster_id:
        raise SleeperWriteError("cannot trade with your own roster", kind="error")
    if not req.give_player_ids and not req.receive_player_ids and not (req.draft_picks or []):
        raise SleeperWriteError("trade has no assets on either side", kind="error")

    k_adds: list = []
    v_adds: list = []
    k_drops: list = []
    v_drops: list = []

    # players I receive → added to my roster, dropped from theirs
    for pid in req.receive_player_ids:
        k_adds.append(str(pid)); v_adds.append(int(req.my_roster_id))
        k_drops.append(str(pid)); v_drops.append(int(req.their_roster_id))
    # players I give → added to their roster, dropped from mine
    for pid in req.give_player_ids:
        k_adds.append(str(pid)); v_adds.append(int(req.their_roster_id))
        k_drops.append(str(pid)); v_drops.append(int(req.my_roster_id))

    picks = [str(p) for p in (req.draft_picks or [])]
    for p in picks:
        if not _is_valid_pick_str(p):
            raise SleeperWriteError(f"invalid draft-pick encoding: {p!r}", kind="error")

    query = (
        _PROPOSE_TRADE_TEMPLATE
        .replace("__LEAGUE_ID__", lid)
        .replace("__DRAFT_PICKS__", json.dumps(picks))
        .replace("__WAIVER_BUDGET__", json.dumps(req.waiver_budget or []))
    )
    return {
        "operationName": "propose_trade",
        "variables": {"k_adds": k_adds, "v_adds": v_adds, "k_drops": k_drops, "v_drops": v_drops},
        "query": query,
    }


# ---------------------------------------------------------------------------
# HTTP issue. `_opener` is injectable so unit tests never hit the network.
# ---------------------------------------------------------------------------

def _post_graphql(op: str, token: str, body: dict, *, _opener=None) -> dict:
    if not token:
        raise SleeperAuthError("no Sleeper token available")

    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(SLEEPER_GRAPHQL_URL, data=data, method="POST")
    request.add_header("content-type", "application/json")
    request.add_header("x-sleeper-graphql-op", op)
    request.add_header("authorization", f"Bearer {token}")

    opener = _opener or urllib.request.urlopen
    try:
        with opener(request, timeout=_HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8")
        except Exception:
            raw = ""
        if e.code in (401, 403):
            raise SleeperAuthError(f"Sleeper rejected the token (HTTP {e.code})", detail=raw[:500])
        raise SleeperWriteError(f"Sleeper returned HTTP {e.code}", detail=raw[:500])
    except urllib.error.URLError as e:
        raise SleeperWriteError("network error contacting Sleeper", kind="network", detail=str(e))

    try:
        parsed = json.loads(raw)
    except Exception:
        raise SleeperWriteError("non-JSON response from Sleeper", detail=raw[:500])

    # GraphQL surfaces errors as HTTP 200 with an "errors" array.
    errors = parsed.get("errors") if isinstance(parsed, dict) else None
    if errors:
        msg = json.dumps(errors)[:500]
        low = msg.lower()
        if any(w in low for w in ("auth", "unauth", "token", "forbidden", "login")):
            raise SleeperAuthError("Sleeper auth error", detail=msg)
        raise SleeperWriteError("Sleeper GraphQL error", detail=msg)

    node = ((parsed.get("data") or {}) if isinstance(parsed, dict) else {}).get(op) or {}
    return {"transaction_id": node.get("transaction_id"), "status": node.get("status"), "raw": node}


def propose_trade(token: str, req: ProposeTradeRequest, *, _opener=None) -> dict:
    """Issue the captured propose_trade mutation.

    Returns {transaction_id, status, raw}. `status` is "proposed" on success.
    Raises SleeperAuthError on auth failure, SleeperWriteError otherwise.
    """
    return _post_graphql("propose_trade", token, build_propose_trade_body(req), _opener=_opener)


def reject_trade(token: str, league_id, transaction_id, leg: int = 1, *, _opener=None) -> dict:
    """Reject a pending proposal (captured adjacent op). Same auth path."""
    lid, tid = str(league_id), str(transaction_id)
    if not lid.isdigit() or not tid.isdigit():
        raise SleeperWriteError("league_id and transaction_id must be numeric", kind="error")
    query = (
        "mutation reject_trade {\n"
        f'        reject_trade(league_id: "{lid}",transaction_id: "{tid}",leg: {int(leg)}){{\n'
        "          status\n          transaction_id\n          metadata\n        }\n      }"
    )
    body = {"operationName": "reject_trade", "variables": {}, "query": query}
    return _post_graphql("reject_trade", token, body, _opener=_opener)
