"""`_PROD_BLOCKED_STATIC` — which `web/` files 404 in a deployed environment.

`web/` is served at the site root (`static_url_path=""`), so every file in it
is reachable by guessing its path. This pins the block list and the fact that
it is prod-only, because the failure mode is silent: a page drops off the
block list and nothing breaks until someone finds it in production.

`/admin/analytics.html` joined the list on 2026-08-26 by operator decision.
Its *data* was already `X-Cron-Secret`-gated — the block removes a public page
shell, not an access control — and the operator reaches it by running the
server locally, which is the `_IS_PROD_ENV is False` path asserted below.
"""
import pytest

import backend.server as server


BLOCKED = [
    "/style-guide.html",
    "/color-lab.html",
    "/color-lab-2.html",
    "/admin/analytics.html",
]


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


@pytest.mark.parametrize("path", BLOCKED)
def test_blocked_in_prod(client, path, monkeypatch):
    monkeypatch.setattr(server, "_IS_PROD_ENV", True)
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", BLOCKED)
def test_served_in_dev(client, path, monkeypatch):
    """The same paths stay reachable locally — that is how the operator gets in."""
    monkeypatch.setattr(server, "_IS_PROD_ENV", False)
    assert client.get(path).status_code == 200


def test_block_list_is_exactly_these(monkeypatch):
    """A page added to web/ is public unless it is named here on purpose."""
    assert set(server._PROD_BLOCKED_STATIC) == set(BLOCKED)


def test_shipping_page_is_not_blocked(client, monkeypatch):
    """Guard against an over-broad block: real pages must survive prod."""
    monkeypatch.setattr(server, "_IS_PROD_ENV", True)
    assert client.get("/index.html").status_code == 200
