"""The opt-in `no_real_network` guard itself (conftest.py), #479 QA P3-2.

Each blocked path must raise AND record the attempt; loopback and AF_UNIX must
pass through untouched. Every test clears the attempts it provoked on purpose,
so the fixture's teardown check stays meaningful for everything else.
"""
import os
import socket
import tempfile

import pytest


@pytest.mark.parametrize("call", [
    lambda: socket.getaddrinfo("api.sleeper.app", 443),
    lambda: socket.gethostbyname("api.sleeper.app"),
    lambda: socket.gethostbyname_ex("api.sleeper.app"),
    # A hostname that merely starts with "127." is not loopback.
    lambda: socket.getaddrinfo("127.evil.example", 443),
])
def test_lookups_are_blocked_and_recorded(no_real_network, call):
    with pytest.raises(OSError, match="no_real_network"):
        call()
    assert len(no_real_network) == 1
    no_real_network.clear()


def test_connect_connect_ex_and_udp_sendto_are_blocked_and_recorded(no_real_network):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(OSError, match="no_real_network"):
            s.connect(("203.0.113.7", 80))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(OSError, match="no_real_network"):
            s.connect_ex(("203.0.113.7", 80))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        with pytest.raises(OSError, match="no_real_network"):
            s.sendto(b"x", ("203.0.113.7", 53))
    assert [a.split(" ")[0] for a in no_real_network] == ["connect", "connect", "sendto"]
    no_real_network.clear()


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "127.0.0.2", "::1"])
def test_loopback_lookups_pass_through(no_real_network, host):
    try:
        socket.getaddrinfo(host, 80)
    except OSError as exc:  # e.g. no IPv6 loopback configured here
        assert "no_real_network" not in str(exc)
    assert no_real_network == []


def test_unix_socket_connect_passes_through(no_real_network):
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("no AF_UNIX on this platform")
    path = os.path.join(tempfile.mkdtemp(), "absent.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        with pytest.raises(OSError) as exc:
            s.connect(path)
    assert "no_real_network" not in str(exc.value)
    assert no_real_network == []
