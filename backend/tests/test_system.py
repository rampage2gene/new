"""Stopping the app from its page: only this computer, only when there is a launcher."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.test_lan import KEY, computer, guarded, phone  # noqa: F401 - fixtures


def test_nothing_to_stop_without_a_launcher(client):
    r = client.post("/api/quit")
    assert r.status_code == 404
    assert "desktop app" in r.json()["detail"]


def test_a_phone_cannot_stop_the_computer(guarded):
    guarded.state.stop = lambda: (_ for _ in ()).throw(AssertionError("the phone stopped the app"))
    with phone(guarded) as c:
        assert c.post("/api/quit", headers={"X-MDI-Key": KEY}).status_code == 403


def test_this_computer_stops_the_app(guarded):
    stopped: list[bool] = []
    guarded.state.stop = lambda: stopped.append(True)
    with computer(guarded) as c:
        assert c.post("/api/quit").status_code == 204
    assert stopped == [True]
