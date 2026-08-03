from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import httpx

from echosense.repositories.provider_connections import ProviderConnection


class SpotifyRateLimited(RuntimeError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Spotify rate limit reached")
        self.retry_after = retry_after


class SpotifyClient:
    """Authenticated Spotify transport with bounded pagination and one refresh retry."""

    def __init__(
        self,
        connection: ProviderConnection,
        refresh_connection: Callable[..., None],
        *,
        base_url: str = "https://api.spotify.com/v1",
        timeout_seconds: float = 15.0,
    ) -> None:
        self.connection = connection
        self.refresh_connection = refresh_connection
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

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
            try:
                return httpx.get(
                    f"{self.base_url}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {self.connection.access_token}"},
                    timeout=self.timeout_seconds,
                )
            except httpx.TransportError:
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
        response = httpx.request(
            method,
            f"{self.base_url}{path}",
            params=params,
            headers={"Authorization": f"Bearer {self.connection.access_token}"},
            timeout=self.timeout_seconds,
        )
        if response.status_code == 401:
            self.refresh_connection(self.connection, force=True)
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self.connection.access_token}"},
                timeout=self.timeout_seconds,
            )
        elif response.status_code in {502, 503, 504}:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self.connection.access_token}"},
                timeout=self.timeout_seconds,
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "1")
            raise SpotifyRateLimited(int(retry_after) if retry_after.isdigit() else 1)
        response.raise_for_status()
        return response.json() if response.content else None

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
