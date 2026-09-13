"""Anthropic client wrapper. The rest of the AI layer never touches the SDK directly."""
from __future__ import annotations

import logging
import os
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)
_client: Any = None
_checked = False


def get_client():
    """Return an `anthropic.Anthropic` client, or None when no credentials are configured."""
    global _client, _checked
    if _checked:
        return _client
    _checked = True
    s = get_settings()
    if not s.ai_enabled:
        return None
    api_key = s.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    try:
        import anthropic

        _client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        if not api_key and not _has_profile():
            _client = None
    except Exception as exc:  # noqa: BLE001
        log.warning("Anthropic client unavailable: %s", exc)
        _client = None
    return _client


def _has_profile() -> bool:
    cfg = os.path.expanduser("~/.config/anthropic")
    return os.path.isdir(cfg) and any(os.scandir(cfg))


def reset_client() -> None:
    global _client, _checked
    _client, _checked = None, False


def ai_available() -> bool:
    return get_client() is not None


def structured_call(system: str, user_content: Any, schema: type, max_tokens: int | None = None):
    """Run a structured-output request and return the parsed pydantic object.

    Raises the SDK exception on failure so callers can fall back gracefully.
    """
    import anthropic  # noqa: F401  (import error surfaces here if the SDK is missing)

    client = get_client()
    if client is None:
        raise RuntimeError("AI not configured")
    s = get_settings()
    response = client.messages.parse(
        model=s.ai_model,
        max_tokens=max_tokens or s.ai_max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        output_format=schema,
    )
    if getattr(response, "stop_reason", None) == "refusal":
        raise RuntimeError("The model declined to answer this request")
    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        raise RuntimeError("No structured output returned")
    return parsed
