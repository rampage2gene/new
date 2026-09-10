"""Stopping the app from its own page.

When the desktop app cannot open a window of its own it runs in a browser
tab, and a browser tab has no close box that stops a server. So the page
carries a "Stop the app" button, and this is what it calls. The launcher
registers a stop hook on the app when it starts the server; without one
(the development server, the tests) there is nothing to stop and the route
says so rather than pretending.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .lan import is_loopback

router = APIRouter(prefix="/api", tags=["system"])


@router.post("/quit", status_code=204)
def quit_app(request: Request) -> None:
    # A phone on the Wi-Fi must not be able to switch the computer's app off.
    if not is_loopback(request):
        raise HTTPException(403, "Only the computer running the app can stop it.")
    stop = getattr(request.app.state, "stop", None)
    if stop is None:
        raise HTTPException(404, "Nothing to stop: this server was not started by the desktop app.")
    stop()
