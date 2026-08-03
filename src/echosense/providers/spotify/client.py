from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import httpx

from echosense.repositories.provider_connections import ProviderConnection
from echosense.spotify_resilience import SpotifyRequestDeferred, SpotifyRequestGovernor


class SpotifyRateLimited(RuntimeError):
    def __init__(
        self,
        retry_after: int,
        *,
        reason: str = "RATE_LIMIT_EXCEEDED",
        endpoint: str = "unknown",
        locally_deferred: bool = False,
    ) -> None:
        super().__init__("Spotify rate limit reached")
        self.retry_after = retry_after
        self.reason = reason
        self.endpoint = endpoint
        self.locally_deferred = locally_deferred


class SpotifyClient:
    """Authenticated Spotify transport with bounded pagination and one refresh retry."""

    def __init__(
        self,
        connection: ProviderConnection,
        refresh_connection: Callable[..., None],
        *,
        base_url: str = "https://api.spotify.com/v1",
        timeout_seconds: float = 15.0,
        governor: SpotifyRequestGovernor | None = None,
    ) -> None:
        self.connection = connection
        self.refresh_connection = refresh_connection
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.governor = governor

    def _begin(self, method: str, path: str) -> str | None:
        if self.governor is None:
            return None
        try:
            return self.governor.begin(method, path)
        except SpotifyRequestDeferred as exc:
            raise SpotifyRateLimited(
                exc.retry_after,
                reason=exc.reason,
                endpoint=exc.endpoint,
                locally_deferred=exc.locally_deferred,
            ) from exc

    def _observe(self, ticket: str | None, response: httpx.Response, path: str) -> None:
        if self.governor is None or ticket is None:
            return
        deferred = self.governor.observe_response(ticket, response, path)
        if deferred:
            raise SpotifyRateLimited(
                deferred.retry_after,
                reason=deferred.reason,
                endpoint=deferred.endpoint,
                locally_deferred=deferred.locally_deferred,
            )

    def _get(self, path: str, params: dict[str, object] | None = None) -> dict[str, Any]:
        self.refresh_connection(self.connection)
        response = self._safe_get(path, params)
        if response.status_code == 401:
            self.refresh_connection(self.connection, force=True)
            response = self._safe_get(path, params)
        elif response.status_code in {502, 503, 504}:
            response = self._safe_get(path, params)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "1")
            raise SpotifyRateLimited(int(retry_after) if retry_after.isdigit() else 1)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Spotify returned a non-object response")
        return payload

    def _safe_get(self, path: str, params: dict[str, object] | None = None) -> httpx.Response:
        """Retry one transport-level failure for an idempotent Spotify GET."""
        for attempt in range(2):
            ticket = self._begin("GET", path)
            try:
                response = httpx.get(
                    f"{self.base_url}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {self.connection.access_token}"},
                    timeout=self.timeout_seconds,
                )
                self._observe(ticket, response, path)
                return response
            except httpx.TransportError:
                if self.governor is not None and ticket is not None:
                    self.governor.observe_transport_error(ticket)
                if attempt == 1:
                    raise
        raise RuntimeError("unreachable Spotify GET retry state")

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
    ) -> Any:
        """Send a Spotify request that may return an object, array, or empty body."""
        self.refresh_connection(self.connection)
        response = self._request_once(method, path, params)
        if response.status_code == 401:
            self.refresh_connection(self.connection, force=True)
            response = self._request_once(method, path, params)
        elif response.status_code in {502, 503, 504}:
            response = self._request_once(method, path, params)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "1")
            raise SpotifyRateLimited(int(retry_after) if retry_after.isdigit() else 1)
        response.raise_for_status()
        return response.json() if response.content else None

    def _request_once(
        self, method: str, path: str, params: dict[str, object] | None
    ) -> httpx.Response:
        ticket = self._begin(method, path)
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self.connection.access_token}"},
                timeout=self.timeout_seconds,
            )
        except httpx.TransportError:
            if self.governor is not None and ticket is not None:
                self.governor.observe_transport_error(ticket)
            raise
        self._observe(ticket, response, path)
        return response

    def items(
        self, path: str, params: dict[str, object], *, limit: int
    ) -> Iterator[dict[str, Any]]:
        remaining = limit
        payload = self._get(path, params)
        while remaining > 0:
            items = payload.get("items")
            if not isinstance(items, list):
                return
            for item in items:
                if remaining <= 0:
                    return
                if isinstance(item, dict):
                    yield item
                    remaining -= 1
            next_url = payload.get("next")
            if not isinstance(next_url, str) or not next_url:
                return
            next_path = next_url.removeprefix(self.base_url)
            payload = self._get(next_path)
