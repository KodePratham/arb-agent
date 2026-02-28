from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class OpinionTradeConfig:
    api_base_url: str
    app_base_url: str = "https://app.opinion.trade"
    api_key: str = ""
    timeout_seconds: int = 30


class OpinionTradeSDK:
    """SDK-style client for Opinion.trade with resilient endpoint fallback logic."""

    MARKET_ENDPOINTS: tuple[str, ...] = (
        "/v1/markets",
        "/markets",
        "/api/v1/markets",
        "/v1/public/markets",
    )

    ORDERBOOK_ENDPOINTS: tuple[str, ...] = (
        "/v1/markets/{market_id}/orderbook",
        "/markets/{market_id}/orderbook",
        "/api/v1/markets/{market_id}/orderbook",
    )

    def __init__(self, config: OpinionTradeConfig):
        self._config = config

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
            headers["x-api-key"] = self._config.api_key
        return headers

    @staticmethod
    def _extract_items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []

        for key in ("data", "markets", "items", "results", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                for nested in ("items", "markets", "data", "results"):
                    nested_value = value.get(nested)
                    if isinstance(nested_value, list):
                        return [item for item in nested_value if isinstance(item, dict)]
        return []

    @staticmethod
    def _extract_next_cursor(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        for key in ("cursor", "nextCursor", "next_cursor", "next"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                token = value.get("cursor") or value.get("nextCursor")
                if isinstance(token, str) and token:
                    return token
        return None

    def _query_markets_from_base(
        self,
        base_url: str,
        max_markets: int | None,
    ) -> list[dict[str, Any]]:
        markets: list[dict[str, Any]] = []
        page = 1
        page_size = 50
        cursor: str | None = None

        with httpx.Client(
            base_url=base_url,
            headers=self._headers(),
            timeout=self._config.timeout_seconds,
        ) as client:
            while True:
                got_any_endpoint = False
                page_payload: Any = None

                for endpoint in self.MARKET_ENDPOINTS:
                    params: dict[str, str | int] = {
                        "status": "open",
                        "limit": page_size,
                        "page": page,
                    }
                    if cursor:
                        params["cursor"] = cursor
                        params["after"] = cursor

                    response = client.get(endpoint, params=params)
                    if response.status_code in (401, 403, 404, 405):
                        continue

                    response.raise_for_status()
                    page_payload = response.json()
                    got_any_endpoint = True
                    break

                if not got_any_endpoint:
                    break

                page_markets = self._extract_items(page_payload)
                if not page_markets:
                    break

                if max_markets is not None:
                    remaining = max_markets - len(markets)
                    if remaining <= 0:
                        break
                    markets.extend(page_markets[:remaining])
                else:
                    markets.extend(page_markets)

                if max_markets is not None and len(markets) >= max_markets:
                    break

                cursor = self._extract_next_cursor(page_payload)
                if cursor:
                    continue

                if len(page_markets) < page_size:
                    break
                page += 1

        return markets

    def list_open_markets(self, max_markets: int | None = None) -> list[dict[str, Any]]:
        from_api = self._query_markets_from_base(self._config.api_base_url, max_markets)
        if from_api:
            return from_api

        return self._query_markets_from_base(self._config.app_base_url, max_markets)

    def get_orderbook(self, market_id: str) -> dict[str, Any] | None:
        for base_url in (self._config.api_base_url, self._config.app_base_url):
            with httpx.Client(
                base_url=base_url,
                headers=self._headers(),
                timeout=min(self._config.timeout_seconds, 15),
            ) as client:
                for endpoint in self.ORDERBOOK_ENDPOINTS:
                    route = endpoint.format(market_id=market_id)
                    response = client.get(route)
                    if response.status_code in (401, 403, 404, 405):
                        continue
                    response.raise_for_status()

                    payload = response.json()
                    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                        return payload["data"]
                    if isinstance(payload, dict):
                        return payload
        return None
