"""HTTP client for the catalog service's internal API."""
import logging

import httpx
from fastapi import HTTPException

from .config import settings

log = logging.getLogger("catalog_client")


class CatalogClient:
    def __init__(self, base_url: str, service_token: str, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(base_url=base_url, headers={"X-Service-Token": service_token},
                                  timeout=httpx.Timeout(10.0, connect=3.0), transport=transport)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        last_exc: Exception | None = None
        for _attempt in range(3):  # all internal calls are idempotent, so retrying is safe
            try:
                return self._http.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                last_exc = exc
                log.warning("catalog call %s %s failed: %s", method, path, exc)
        raise HTTPException(503, "Stock service is temporarily unavailable, please try again") from last_exc

    def products(self, ids: list[int]) -> list[dict]:
        r = self._request("GET", "/internal/products", params={"ids": ",".join(map(str, ids))})
        r.raise_for_status()
        return r.json()

    def reserve(self, order_ref: str, lines: list[dict]) -> list[dict]:
        r = self._request("POST", "/internal/reservations", json={"order_ref": order_ref, "lines": lines})
        if r.status_code == 409:
            raise HTTPException(409, r.json()["detail"])
        r.raise_for_status()
        return r.json()["lines"]

    def release(self, order_ref: str) -> None:
        self._request("POST", f"/internal/reservations/{order_ref}/release").raise_for_status()

    def commit(self, order_ref: str) -> None:
        self._request("POST", f"/internal/reservations/{order_ref}/commit").raise_for_status()


_client: CatalogClient | None = None


def get_catalog() -> CatalogClient:
    global _client
    if _client is None:
        _client = CatalogClient(settings.catalog_url, settings.service_token)
    return _client
