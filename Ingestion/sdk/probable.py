from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ProbableConfig:
    base_url: str
    api_key: str = ""
    timeout_seconds: int = 30


class ProbableSDK:
    """Thin SDK wrapper for Probable market and orderbook APIs."""

    def __init__(self, config: ProbableConfig):
        self._config = config

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        return headers

    @staticmethod
    def _extract_market_list(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [m for m in payload if isinstance(m, dict)]
        if not isinstance(payload, dict):
            return []

        for key in ("data", "markets", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [m for m in value if isinstance(m, dict)]
        return []

    def list_open_markets(self, max_markets: int | None = None) -> list[dict[str, Any]]:
        markets: list[dict[str, Any]] = []
        page = 1
        page_size = 50

        with httpx.Client(
            base_url=self._config.base_url,
            headers=self._headers(),
            timeout=self._config.timeout_seconds,
        ) as client:
            while True:
                params: dict[str, str | int] = {
                    "page": page,
                    "limit": page_size,
                    "status": "open",
                }
                response = client.get("/v1/markets", params=params)
                if response.status_code in (401, 403):
                    raise RuntimeError(
                        f"Probable API returned {response.status_code}: authentication required. "
                        "Set PROBABLE_API_KEY in your environment."
                    )
                response.raise_for_status()

                page_markets = self._extract_market_list(response.json())
                if max_markets is not None:
                    remaining = max_markets - len(markets)
                    if remaining <= 0:
                        break
                    markets.extend(page_markets[:remaining])
                else:
                    markets.extend(page_markets)

                if (
                    (max_markets is not None and len(markets) >= max_markets)
                    or len(page_markets) < page_size
                ):
                    break
                page += 1

        return markets

    def get_orderbook(self, market_id: str) -> dict[str, Any] | None:
        with httpx.Client(
            base_url=self._config.base_url,
            headers=self._headers(),
            timeout=min(self._config.timeout_seconds, 15),
        ) as client:
            response = client.get(f"/v1/markets/{market_id}/orderbook")
            if response.status_code != 200:
                return None

            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                return payload["data"]
            if isinstance(payload, dict):
                return payload
            return None
