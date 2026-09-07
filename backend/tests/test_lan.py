"""Serving the app to a phone on the Wi-Fi, and the pairing key that guards it."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

KEY = "test-pairing-key"
PHONE = ("192.168.1.9", 51000)
HERE = ("127.0.0.1", 51000)
BASE = "http://testserver:8765"


@pytest.fixture()
def guarded(data_dir, monkeypatch):
    """An app configured the way the desktop launcher configures it for a phone."""
    from app.api import lan
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setattr(lan, "lan_addresses", lambda: ["192.168.1.23"])
    os.environ["MDI_ACCESS_KEY"] = KEY
    get_settings.cache_clear()
    try:
        yield create_app()
    finally:
        os.environ.pop("MDI_ACCESS_KEY", None)
        get_settings.cache_clear()
        get_settings()


def phone(app, **kw) -> TestClient:
    return TestClient(app, base_url=BASE, client=PHONE, **kw)


def computer(app) -> TestClient:
    return TestClient(app, base_url=BASE, client=HERE)


def test_this_computer_needs_no_key(guarded):
    with computer(guarded) as c:
        assert c.get("/api/status").status_code == 200


def test_the_network_needs_the_key(guarded):
    with phone(guarded) as c:
        denied = c.get("/api/status")
        assert denied.status_code == 401
        assert "scan the qr code" in denied.json()["detail"].lower()
        assert c.get("/api/status", headers={"X-MDI-Key": KEY}).status_code == 200
        assert c.get("/api/status", headers={"X-MDI-Key": "wrong"}).status_code == 401


def test_pairing_sets_a_cookie_so_downloads_work(guarded):
    with phone(guarded) as c:
        assert c.post("/api/pair", json={"key": "wrong"}).status_code == 401
        assert c.post("/api/pair", json={"key": KEY}).json() == {"paired": True, "protected": True}
        # The cookie the browser now holds is enough on its own (plain <a href> downloads).
        assert c.get("/api/status").status_code == 200


def test_the_page_itself_loads_before_pairing(guarded):
    """The phone must be able to load the app in order to pair; only /api/ is guarded."""
    with phone(guarded) as c:
        assert c.get("/").status_code in (200, 404)  # 404 only when the UI was never built


def test_the_key_is_not_readable_from_the_network(guarded):
    with phone(guarded) as c:
        assert c.get("/api/lan", headers={"X-MDI-Key": KEY}).status_code == 403
        assert c.get("/api/lan/qr.png", headers={"X-MDI-Key": KEY}).status_code == 403


def test_importing_by_path_is_refused_from_the_network(guarded):
    with phone(guarded) as c:
        r = c.post("/api/documents/import", json={"paths": ["/etc/hostname"]}, headers={"X-MDI-Key": KEY})
        assert r.status_code == 403


def test_the_computer_gets_the_address_and_the_qr_code(guarded):
    with computer(guarded) as c:
        info = c.get("/api/lan").json()
        assert info["enabled"] is True and info["protected"] is True
        assert info["urls"] == [f"http://192.168.1.23:8765/?key={KEY}"]
        qr = c.get("/api/lan/qr.png")
        assert qr.status_code == 200 and qr.headers["content-type"] == "image/png"
        assert qr.content[:4] == b"\x89PNG"


def test_finding_the_addresses_never_waits_on_a_name_lookup(monkeypatch):
    """Regression: resolving this machine's own hostname blocks for as long as
    the resolver takes when the name has no DNS entry, which timed out
    /api/lan on a build runner. Nothing here may look a name up."""
    import socket as socket_module
    import time

    from app.api import lan

    def refuse(*args, **kwargs):  # pragma: no cover - fails the test if reached
        raise AssertionError("lan_addresses must not resolve names")

    monkeypatch.setattr(lan.socket, "getaddrinfo", refuse)
    monkeypatch.setattr(lan.socket, "gethostbyname", refuse)
    started = time.monotonic()
    for addr in lan.lan_addresses():
        ip = socket_module.inet_aton(addr)  # a literal address, not a name
        assert ip and not addr.startswith("127.")
    assert time.monotonic() - started < 2


def test_without_a_key_the_api_is_open(client):
    """The dev server and the Docker image configure no key and behave as before."""
    with TestClient(client.app, base_url=BASE, client=PHONE) as c:
        assert c.get("/api/status").status_code == 200
        assert c.post("/api/pair", json={"key": "anything"}).json()["protected"] is False
