from __future__ import annotations

import os
import webbrowser
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

API_BASE = os.getenv("PREDICTFUN_API_BASE", "https://api.predict.fun")
API_KEY = os.getenv("PREDICTFUN_API_KEY", "")
HOST = "127.0.0.1"
PORT = 8765
DEFAULT_PRICE_FEED = "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"


def now_et() -> datetime:
    try:
        return datetime.now(tz=ZoneInfo("America/New_York"))
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone()


def slug_for_today() -> str:
    return f"btc-usd-up-down-{now_et().strftime('%Y-%m-%d')}-12-00-daily"


def headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json"}
    if API_KEY:
        h["x-api-key"] = API_KEY
    return h


def resolve_market(slug: str) -> dict:
    cursor: str | None = None
    with httpx.Client(base_url=API_BASE, headers=headers(), timeout=20) as client:
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

    raise RuntimeError(f"Market not found for slug={slug}")


def main() -> None:
    if not API_KEY:
        raise RuntimeError("Missing PREDICTFUN_API_KEY in .env")

    slug = slug_for_today()
    market = resolve_market(slug)

    market_id = str(market["id"])
    title = market.get("title", "BTC/USD Up or Down")
    price_feed_id = (market.get("variantData") or {}).get("priceFeedId") or DEFAULT_PRICE_FEED

    query = urlencode(
        {
            "apiKey": API_KEY,
            "marketId": market_id,
            "title": title,
            "slug": slug,
            "priceFeedId": price_feed_id,
        }
    )
    url = f"http://{HOST}:{PORT}/live_odds.html?{query}"

    handler = partial(SimpleHTTPRequestHandler, directory=str(APP_DIR))
    server = ThreadingHTTPServer((HOST, PORT), handler)

    print(f"Serving on http://{HOST}:{PORT}")
    print(f"Opening {url}")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()