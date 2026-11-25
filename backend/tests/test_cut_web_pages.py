"""`_CUT_WEB_PAGES` — the signed-in web pages cut for launch (2026-11-25).

Web sign-in and every page behind it were cut (keep/cut list section 13). The
landing page no longer loads the web app, and the standalone signed-in pages
redirect to it in every environment, so a bookmark or a typed URL lands on the
landing page instead of a half-working app. The files stay in web/.
"""
import pytest

import backend.server as server


CUT = ["/calculator.html", "/league-rankings.html", "/player.html"]


@pytest.fixture()
def client():
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


def test_cut_list_is_exactly_these():
    assert set(server._CUT_WEB_PAGES) == set(CUT)


@pytest.mark.parametrize("prod", [True, False])
@pytest.mark.parametrize("path", CUT)
def test_cut_page_redirects_to_landing(client, monkeypatch, path, prod):
    monkeypatch.setattr(server, "_IS_PROD_ENV", prod)
    r = client.get(path + "?id=123")
    assert r.status_code == 302
    assert r.headers["Location"] in ("/", "http://localhost/")


@pytest.mark.parametrize("path", [
    "/", "/index.html", "/faq.html", "/contact.html", "/privacy", "/terms",
    "/positional-tiers.html", "/ranking-method.html",
])
def test_public_pages_still_served(client, monkeypatch, path):
    monkeypatch.setattr(server, "_IS_PROD_ENV", True)
    assert client.get(path).status_code == 200
