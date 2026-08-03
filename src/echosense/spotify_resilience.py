from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any
from uuid import uuid4

import httpx

from echosense.storage import Storage

_SPOTIFY_ID = re.compile(r"(?<=/)[A-Za-z0-9]{16,}(?=/|$)")


def endpoint_group(path: str) -> str:
    """Remove provider identifiers before retaining endpoint telemetry."""
    clean = path.split("?", 1)[0]
    return _SPOTIFY_ID.sub(":id", clean)


def _response_reason(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
    except ValueError:
        return "RATE_LIMIT_EXCEEDED"
    candidates = [payload]
    while candidates:
        value = candidates.pop()
        if isinstance(value, dict):
            reason = value.get("reason")
            if isinstance(reason, str) and reason:
                return reason.upper()
            candidates.extend(value.values())
        elif isinstance(value, list):
            candidates.extend(value)
    return "RATE_LIMIT_EXCEEDED"


class SpotifyRequestDeferred(RuntimeError):
    def __init__(
        self,
        retry_after: int,
        *,
        reason: str,
        endpoint: str,
        locally_deferred: bool,
    ) -> None:
        super().__init__("Spotify request deferred")
        self.retry_after = max(1, retry_after)
        self.reason = reason
        self.endpoint = endpoint
        self.locally_deferred = locally_deferred


class SpotifyRequestGovernor:
    """Persistent, cross-tab request budget and Spotify cooldown controller."""

    WINDOW_SECONDS = 30
    APP_SCOPE = "__spotify_app__"

    def __init__(self, storage: Storage, user_id: str) -> None:
        self.storage = storage
        self.user_id = user_id
        self.budget = max(5, int(os.getenv("ECHOSENSE_SPOTIFY_REQUEST_BUDGET", "20")))

    def begin(self, method: str, path: str, request_class: str = "web_api") -> str:
        group = endpoint_group(path)
        state = self.storage.get_provider_cooldown("spotify", self.APP_SCOPE)
        if state is None:
            state = self.storage.get_provider_cooldown("spotify", self.user_id)
        if state and state.get("cooldown_until"):
            remaining = (
                datetime.fromisoformat(state["cooldown_until"]) - datetime.now(UTC)
            ).total_seconds()
            if remaining > 0:
                raise SpotifyRequestDeferred(
                    ceil(remaining),
                    reason=str(state.get("error_code") or "SPOTIFY_COOLDOWN").upper(),
                    endpoint=group,
                    locally_deferred=True,
                )
        recent = self.storage.count_provider_requests(
            "spotify",
            None,
            since=datetime.now(UTC) - timedelta(seconds=self.WINDOW_SECONDS),
        )
        if recent >= self.budget:
            retry_after = self.WINDOW_SECONDS
            self.storage.set_provider_cooldown(
                provider="spotify",
                user_id=self.APP_SCOPE,
                cooldown_until=datetime.now(UTC) + timedelta(seconds=retry_after),
                error_code="local_request_budget",
                error_message="EchoSense paused Spotify calls before the provider limit.",
            )
            raise SpotifyRequestDeferred(
                retry_after,
                reason="LOCAL_REQUEST_BUDGET",
                endpoint=group,
                locally_deferred=True,
            )
        request_id = uuid4().hex
        self.storage.start_provider_request(
            request_id=request_id,
            provider="spotify",
            user_id=self.user_id,
            endpoint_group=group,
            method=method.upper(),
            request_class=request_class,
        )
        return request_id

    def observe_response(
        self, request_id: str, response: httpx.Response, path: str
    ) -> SpotifyRequestDeferred | None:
        reason = None
        retry_after = None
        outcome = "success" if response.status_code < 400 else "provider_error"
        deferred = None
        if response.status_code == 429:
            header = response.headers.get("Retry-After", "1")
            retry_after = int(header) if header.isdigit() else 1
            reason = _response_reason(response)
            outcome = "quota_exceeded" if reason == "QUOTA_EXCEEDED" else "rate_limited"
            self.storage.set_provider_cooldown(
                provider="spotify",
                user_id=self.APP_SCOPE,
                cooldown_until=datetime.now(UTC) + timedelta(seconds=retry_after),
                error_code=reason.lower(),
                error_message=f"Spotify limited {endpoint_group(path)}.",
            )
            deferred = SpotifyRequestDeferred(
                retry_after,
                reason=reason,
                endpoint=endpoint_group(path),
                locally_deferred=False,
            )
        self.storage.finish_provider_request(
            request_id,
            status_code=response.status_code,
            outcome=outcome,
            reason=reason,
            retry_after_seconds=retry_after,
        )
        return deferred

    def observe_transport_error(self, request_id: str) -> None:
        self.storage.finish_provider_request(
            request_id,
            status_code=None,
            outcome="transport_error",
            reason="TRANSPORT_ERROR",
            retry_after_seconds=None,
        )
        summary = self.storage.provider_request_summary(
            "spotify", None, since=datetime.now(UTC) - timedelta(minutes=1)
        )
        if int(summary["transport_errors"]) >= 2:
            self.storage.set_provider_cooldown(
                provider="spotify",
                user_id=self.APP_SCOPE,
                cooldown_until=datetime.now(UTC) + timedelta(seconds=30),
                error_code="transport_circuit_open",
                error_message="EchoSense opened the Spotify transport circuit after repeated failures.",
            )

    def status(self) -> dict[str, object]:
        state = self.storage.get_provider_cooldown("spotify", self.APP_SCOPE)
        if state is None:
            state = self.storage.get_provider_cooldown("spotify", self.user_id)
        retry_after = 0
        reason = None
        if state and state.get("cooldown_until"):
            retry_after = max(
                0,
                ceil(
                    (
                        datetime.fromisoformat(state["cooldown_until"]) - datetime.now(UTC)
                    ).total_seconds()
                ),
            )
            reason = state.get("error_code")
        summary = self.storage.provider_request_summary(
            "spotify", None, since=datetime.now(UTC) - timedelta(minutes=15)
        )
        return {
            "mode": "cooldown" if retry_after else "live",
            "reason": reason,
            "retry_after_seconds": retry_after,
            "budget": {
                "limit": self.budget,
                "window_seconds": self.WINDOW_SECONDS,
                "requests_in_window": self.storage.count_provider_requests(
                    "spotify",
                    None,
                    since=datetime.now(UTC) - timedelta(seconds=self.WINDOW_SECONDS),
                ),
            },
            "telemetry": summary,
        }
