"""Read-only access to the other services.

* ``InternalSources`` is what the monitoring loop uses: service-token calls to /internal snapshot
  endpoints that cover every organisation.
* ``UserApi`` is what the assistant uses: it forwards the signed-in user's own token to the public
  APIs, so the owning service enforces exactly what that user may see.
"""
import logging
from typing import Any, Protocol

import httpx

log = logging.getLogger("sources")


class SourceError(Exception):
    def __init__(self, source: str, message: str):
        super().__init__(f"{source}: {message}")
        self.source = source


class Sources(Protocol):
    def organizations(self) -> list[dict]: ...
    def inventory(self, expiry_days: int, demand_days: int) -> dict: ...
    def orders_snapshot(self, demand_days: int) -> dict: ...
    def health(self) -> dict[str, dict]: ...


def _get(client: httpx.Client, source: str, path: str, **params: Any) -> Any:
    last: Exception | None = None
    for _ in range(3):
        try:
            r = client.get(path, params=params or None)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            raise SourceError(source, f"HTTP {exc.response.status_code} on {path}") from exc
        except httpx.TransportError as exc:
            last = exc
    raise SourceError(source, f"unreachable ({last})")


class InternalSources:
    def __init__(self, urls: dict[str, str], service_token: str, transport: httpx.BaseTransport | None = None):
        self.urls = urls
        self._clients = {
            name: httpx.Client(base_url=url, headers={"X-Service-Token": service_token}, transport=transport,
                               timeout=httpx.Timeout(20.0, connect=3.0))
            for name, url in urls.items()
        }

    def organizations(self) -> list[dict]:
        return _get(self._clients["identity"], "identity", "/internal/organizations")

    def inventory(self, expiry_days: int, demand_days: int) -> dict:
        return _get(self._clients["catalog"], "catalog", "/internal/monitoring/inventory",
                    expiry_days=expiry_days, demand_days=demand_days)

    def orders_snapshot(self, demand_days: int) -> dict:
        return _get(self._clients["orders"], "orders", "/internal/monitoring/snapshot", demand_days=demand_days)

    def health(self) -> dict[str, dict]:
        out = {}
        for name, client in self._clients.items():
            try:
                r = client.get("/health", timeout=3.0)
                out[name] = {"up": r.status_code == 200, "latency_ms": round(r.elapsed.total_seconds() * 1000, 1),
                             "detail": None if r.status_code == 200 else f"HTTP {r.status_code}"}
            except httpx.HTTPError as exc:
                out[name] = {"up": False, "latency_ms": None, "detail": type(exc).__name__}
        return out


class UserApi:
    """The signed-in user's view of the platform (authorisation enforced by each service)."""

    def __init__(self, urls: dict[str, str], token: str, transport: httpx.BaseTransport | None = None):
        self._clients = {
            name: httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}, transport=transport,
                               timeout=httpx.Timeout(15.0, connect=3.0))
            for name, url in urls.items()
        }

    def get(self, service: str, path: str, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v not in (None, "", [])}
        return _get(self._clients[service], service, path, **clean)

    def close(self) -> None:
        for c in self._clients.values():
            c.close()
