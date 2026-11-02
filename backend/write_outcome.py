"""write_outcome.py — when did a trade-send write fail: before or after it was sent?

Shared by the provider write adapters (`espn_write.py`, `mfl_write.py`). Pure:
no Flask, no DB, no network.

A failed write is one of two things (C10, head-eng pre-launch triage):

  * **Not sent.** The provider never got a complete request, so a retry
    cannot double-send. These keep the adapters' ordinary kinds (`network`,
    `error`, `input`).
  * **Outcome unknown** (`OUTCOME_UNKNOWN`). The request may have reached the
    provider but no definitive answer came back. The trade may exist, so the
    caller must tell the user to check the provider before sending again, and
    must never retry on its own.

How urllib tells them apart. `urllib.request.AbstractHTTPHandler.do_open`
wraps ONLY `h.request(...)` (DNS, connect, TLS handshake and writing the
request) in `URLError`. Everything after the request was written,
`h.getresponse()` and `resp.read()`, raises raw: `TimeoutError`
(`socket.timeout`), `ConnectionResetError`, `http.client.RemoteDisconnected`,
`BadStatusLine`, `IncompleteRead`. So:

  * a raw `OSError` / `http.client.HTTPException` from the call or the body
    read is after-send → outcome unknown;
  * an HTTP 5xx is after-send (the provider or a gateway answered, often a
    504 while the write was still running) → outcome unknown;
  * a `URLError` is before-send, but it is only treated as **not sent** when
    its reason is a definite connect-phase failure (`request_never_sent`). A
    timeout or reset inside `URLError` is still outcome unknown. `URLError`
    cannot say whether a timeout came from connect or from writing the
    request, and a redirect's follow-up request can fail after the first leg
    already reached the provider. The brief's rule applies: when it can't be
    told apart, a timeout during the write is unknown.

A 2xx body the adapter can't read as success or as a refusal is also outcome
unknown. Each adapter raises that itself.
"""
from __future__ import annotations

import errno
import socket
import urllib.error

#: The adapters' `kind` for "the provider may have the trade". The route
#: cores map it to `espn_outcome_unknown` / `mfl_outcome_unknown`.
OUTCOME_UNKNOWN = "outcome_unknown"

# Connect-phase failures: no connection was made, so no byte of the request
# reached the provider.
_NO_ROUTE_ERRNOS = frozenset(e for e in (getattr(errno, "ENETUNREACH", None),
                                         getattr(errno, "EHOSTUNREACH", None))
                             if e is not None)


def request_never_sent(err: urllib.error.URLError) -> bool:
    """True when a (non-HTTP) `URLError` proves nothing was sent: DNS failed,
    the connection was refused, there was no route to the host, or urllib
    refused the URL before connecting (a string reason such as "unknown url
    type"). Anything else (a timeout, a reset, a TLS error) is not proof."""
    reason = getattr(err, "reason", None)
    if not isinstance(reason, BaseException):
        return True                      # urllib's own pre-connect refusals
    if isinstance(reason, (socket.gaierror, ConnectionRefusedError)):
        return True
    return isinstance(reason, OSError) and reason.errno in _NO_ROUTE_ERRNOS
