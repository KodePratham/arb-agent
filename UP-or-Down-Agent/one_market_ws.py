"""
predict.fun — BTC/USD Daily Up-or-Down Live Odds (continuous)

Flow:
  1) Check current date (ET)
  2) Build today's market URL slug
  3) Resolve market ID using Predict.fun API key
  4) Subscribe to Predict.fun WebSocket orderbook updates
  5) Continuously print live odds in terminal

Run:
  python one_market_ws.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import websockets
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

API_BASE = os.getenv("PREDICTFUN_API_BASE", "https://api.predict.fun")
API_KEY = os.getenv("PREDICTFUN_API_KEY", "")
WS_URL = os.getenv("PREDICTFUN_WS_URL", "wss://ws.predict.fun").rstrip("/")
WS_ENDPOINT = WS_URL if WS_URL.endswith("/ws") else f"{WS_URL}/ws"
ET_TZ_NAME = "America/New_York"


def now_et() -> datetime:
    try:
        return datetime.now(tz=ZoneInfo(ET_TZ_NAME))
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone()


def build_daily_slug(dt_et: datetime) -> str:
    return f"btc-usd-up-down-{dt_et.strftime('%Y-%m-%d')}-12-00-daily"


def headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json"}
    if API_KEY:
        h["x-api-key"] = API_KEY
    return h


def resolve_market_by_slug(client: httpx.Client, slug: str) -> dict[str, Any]:
    cursor: str | None = None

    for _ in range(12):
        params: dict[str, str] = {
            "first": "50",
            "status": "OPEN",
            "marketVariant": "CRYPTO_UP_DOWN",
        }
        if cursor:
            params["after"] = cursor

        resp = client.get("/v1/markets", params=params)
        resp.raise_for_status()
        payload = resp.json()

        for market in payload.get("data", []):
            if market.get("categorySlug") == slug:
                return market

        cursor = payload.get("cursor")
        if not cursor:
            break

    raise RuntimeError(f"Market not found for slug: {slug}")


def best_prices(orderbook: dict[str, Any]) -> tuple[float | None, float | None]:
    bids = orderbook.get("bids") or []
    asks = orderbook.get("asks") or []
    best_bid = max((float(b[0]) for b in bids if b), default=None)
    best_ask = min((float(a[0]) for a in asks if a), default=None)
    return best_bid, best_ask


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def print_snapshot(
    market_id: int,
    title: str,
    market_url: str,
    up_name: str,
    down_name: str,
    best_bid: float | None,
    best_ask: float | None,
    btc_price: float | None,
) -> None:
    ts = now_et().strftime("%Y-%m-%d %H:%M:%S")
    mid_yes = None
    if best_bid is not None and best_ask is not None:
        mid_yes = (best_bid + best_ask) / 2

    print("-" * 68)
    print(f"[{ts} ET] Market ID: {market_id}")
    print(f"Title: {title}")
    print(f"URL: {market_url}")
    print(f"{up_name} best bid: {fmt_pct(best_bid)}")
    print(f"{up_name} best ask: {fmt_pct(best_ask)}")
    print(f"{up_name} mid odds: {fmt_pct(mid_yes)}")
    if mid_yes is not None:
        print(f"{down_name} mid odds: {fmt_pct(1.0 - mid_yes)}")
    else:
        print(f"{down_name} mid odds: N/A")
    if btc_price is not None:
        print(f"BTC/USD live price: ${btc_price:,.2f}")
    else:
        print("BTC/USD live price: N/A")


async def stream_live_odds(market: dict[str, Any], slug: str) -> None:
    market_id = int(market["id"])
    title = market.get("title", "BTC/USD Up or Down")
    outcomes = market.get("outcomes") or []
    up_name = outcomes[0].get("name", "Up") if len(outcomes) > 0 else "Up"
    down_name = outcomes[1].get("name", "Down") if len(outcomes) > 1 else "Down"
    market_url = f"https://predict.fun/market/{slug}"
    price_feed_id = (
        (market.get("variantData") or {}).get("priceFeedId")
        or "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"
    )

    ws_url = WS_ENDPOINT
    if API_KEY:
        ws_url = f"{ws_url}?apiKey={API_KEY}"

    print("=" * 68)
    print("predict.fun BTC/USD Up-or-Down — Live Odds (WebSocket)")
    print("=" * 68)
    print(f"Market URL: {market_url}")
    print(f"Market ID : {market_id}")
    print("Listening for live updates... Press Ctrl+C to stop.\n")

    last_bid: float | None = None
    last_ask: float | None = None
    last_btc_price: float | None = None
    backoff_seconds = 1

    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=None, open_timeout=20) as ws:
                request_id = 1
                await ws.send(
                    json.dumps(
                        {
                            "method": "subscribe",
                            "requestId": request_id,
                            "params": [f"predictOrderbook/{market_id}"],
                        }
                    )
                )
                await ws.send(
                    json.dumps(
                        {
                            "method": "subscribe",
                            "requestId": request_id + 1,
                            "params": [f"assetPriceUpdate/{price_feed_id}"],
                        }
                    )
                )

                async for raw in ws:
                    msg = json.loads(raw)
                    msg_type = msg.get("type")

                    if msg_type == "M" and msg.get("topic") == "heartbeat":
                        await ws.send(
                            json.dumps(
                                {
                                    "method": "heartbeat",
                                    "data": msg.get("data"),
                                }
                            )
                        )
                        continue

                    if msg_type != "M":
                        continue

                    topic = msg.get("topic", "")

                    if topic.startswith("assetPriceUpdate/"):
                        price = (msg.get("data") or {}).get("price")
                        if price is not None:
                            try:
                                new_price = float(price)
                                if new_price != last_btc_price and (
                                    last_bid is not None or last_ask is not None
                                ):
                                    last_btc_price = new_price
                                    print_snapshot(
                                        market_id,
                                        title,
                                        market_url,
                                        up_name,
                                        down_name,
                                        last_bid,
                                        last_ask,
                                        last_btc_price,
                                    )
                                else:
                                    last_btc_price = new_price
                            except (TypeError, ValueError):
                                pass
                        continue

                    if not topic.startswith("predictOrderbook/"):
                        continue

                    orderbook = msg.get("data") or {}
                    best_bid, best_ask = best_prices(orderbook)

                    if best_bid == last_bid and best_ask == last_ask:
                        continue

                    last_bid = best_bid
                    last_ask = best_ask
                    print_snapshot(
                        market_id,
                        title,
                        market_url,
                        up_name,
                        down_name,
                        best_bid,
                        best_ask,
                        last_btc_price,
                    )

            backoff_seconds = 1
        except (websockets.ConnectionClosed, OSError, ConnectionError) as exc:
            print(f"WebSocket disconnected: {exc}. Reconnecting in {backoff_seconds}s...")
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, 30)


async def main() -> None:
    if not API_KEY:
        print("ERROR: Missing PREDICTFUN_API_KEY in .env")
        sys.exit(1)

    dt = now_et()
    slug = build_daily_slug(dt)

    with httpx.Client(base_url=API_BASE, headers=headers(), timeout=20) as client:
        market = resolve_market_by_slug(client, slug)

    await stream_live_odds(market, slug)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
    except httpx.HTTPStatusError as exc:
        print(f"\nHTTP error: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\nError: {exc}")
        sys.exit(1)