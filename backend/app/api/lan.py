"""Using the app from a phone on the same Wi-Fi.

The desktop app binds its built-in server to every network interface, so a
phone on the same network can open the UI. Everything still happens on the
PC - the phone is only a screen and a camera - but a server on the network
needs a door: every API request that does not come from the computer itself
must carry the **pairing key** the launcher generated
(`<data dir>/phone-key.txt`), as an ``X-MDI-Key`` header or the cookie
``POST /api/pair`` sets.

The endpoints here hand that key to the PC's own window as a QR code, so they
are answered for loopback clients only: the key must never be readable from
the network it protects.
"""
from __future__ import annotations

import io
import ipaddress
import logging
import secrets
import socket

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..config import get_settings

router = APIRouter(prefix="/api", tags=["phone"])
log = logging.getLogger(__name__)

KEY_HEADER = "X-MDI-Key"
PAIR_COOKIE = "mdi_key"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days
PAIR_MESSAGE = "Pair this device first: open “Use on your phone” on the computer and scan the QR code."
ONLY_HERE = "This is only available on the computer running the app."

# UDP "connect" targets used to find which interface this machine would send
# from. No packet is sent and nothing is looked up: the kernel just answers
# "which of my addresses would I use to reach that", so this is instant and
# works with no Internet connection. One target per private range, so a
# machine on several networks offers each of them.
_ROUTE_PROBES = ("192.168.1.1", "10.0.0.1", "172.16.0.1", "8.8.8.8")


def client_host(request: Request) -> str:
    return (request.client.host if request.client else "") or ""


def is_loopback(request: Request) -> bool:
    """True when the request comes from this computer (the desktop window, tests)."""
    host = client_host(request)
    if host in ("", "localhost", "testclient"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def lan_addresses() -> list[str]:
    """This machine's private IPv4 addresses, the one facing the router first.

    Deliberately no name lookup: resolving this machine's own hostname is the
    obvious way to enumerate addresses and the wrong one, because on a machine
    whose hostname has no DNS entry it blocks for as long as the resolver
    takes - which is how this endpoint first timed out on a build runner.
    Asking the routing table costs nothing and sends nothing.
    """
    found: list[str] = []

    def add(addr: str) -> None:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:  # pragma: no cover - the kernel returns an address
            return
        if ip.version != 4 or ip.is_loopback or ip.is_link_local or not ip.is_private:
            return
        if addr not in found:
            found.append(addr)

    for probe in _ROUTE_PROBES:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.connect((probe, 9))
            except OSError:
                continue  # no route that way; try the next network
            add(s.getsockname()[0])
    return found


def phone_urls(port: int, key: str | None) -> list[str]:
    """The addresses to type (or scan) on the phone, key included so one scan pairs it."""
    suffix = f"/?key={key}" if key else "/"
    return [f"http://{addr}:{port}{suffix}" for addr in lan_addresses()]


def _port_of(request: Request) -> int:
    return request.url.port or (443 if request.url.scheme == "https" else 80)


@router.get("/lan")
def lan_info(request: Request) -> dict:
    """What the phone needs to connect - shown by the “Use on your phone” page."""
    if not is_loopback(request):
        raise HTTPException(403, ONLY_HERE)
    settings = get_settings()
    port = _port_of(request)
    urls = phone_urls(port, settings.access_key) if settings.lan else []
    return {
        "enabled": bool(settings.lan),
        "protected": bool(settings.access_key),
        "computer": socket.gethostname(),
        "port": port,
        "urls": urls,
    }


@router.get("/lan/qr.png")
def lan_qr(request: Request) -> Response:
    """The first phone URL as a QR code, for the phone camera to scan."""
    if not is_loopback(request):
        raise HTTPException(403, ONLY_HERE)
    settings = get_settings()
    urls = phone_urls(_port_of(request), settings.access_key) if settings.lan else []
    if not urls:
        raise HTTPException(404, "This computer is not on a local network the phone could reach.")
    try:
        import qrcode
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise HTTPException(503, f"The QR code library is not installed ({exc}). Type the address instead.") from exc
    buf = io.BytesIO()
    qrcode.make(urls[0], box_size=8, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


class PairRequest(BaseModel):
    key: str


@router.post("/pair")
def pair(req: PairRequest, response: Response) -> dict:
    """Exchange the key from the QR code for a cookie, so downloads work too."""
    settings = get_settings()
    if not settings.access_key:
        return {"paired": True, "protected": False}
    if not secrets.compare_digest(req.key, settings.access_key):
        log.warning("pair: wrong key offered")
        raise HTTPException(401, "That is not the code this computer is showing. Scan the QR code again.")
    response.set_cookie(PAIR_COOKIE, settings.access_key, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/")
    log.info("pair: a device paired")
    return {"paired": True, "protected": True}
