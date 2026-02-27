"""
Ingestion/ingest_predictfun.py
────────────────────────────────────────────────────────────────────
Predict.fun ingestion node — designed to be run by ANY teammate on
their own machine.

Workflow:
  1. Fetch all OPEN markets from the Predict.fun REST API.
  2. Normalise each market through the LLM-based ETL parser.
  3. Persist snapshots as JSON in Data/markets_init/.
  4. Open an asyncio WebSocket listener that publishes live odds
     updates to the Rust engine over ZMQ PUB.

Run:
    python -m Ingestion.ingest_predictfun
────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
import zmq
import zmq.asyncio
from dotenv import load_dotenv

# ── Ensure the project root is on sys.path ───────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Data.schemas import (
    CryptoUpDownVariantData,
    MarketStatus,
    MarketVariant,
    NormalizedMarket,
    OddsUpdate,
    OrderBook,
    OrderBookLevel,
    Outcome,
    Platform,
    ResolutionOracle,
    ResolutionStyle,
    TradingStatus,
)
from Ingestion.base_parser import parse_market_text

load_dotenv()

log = logging.getLogger("ingest.predictfun")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)

# ── Config ────────────────────────────────────────────────────────

API_BASE: str = os.getenv("PREDICTFUN_API_BASE", "https://api.predict.fun")
API_KEY: str = os.getenv("PREDICTFUN_API_KEY", "")
WS_URL: str = os.getenv("PREDICTFUN_WS_URL", "wss://ws.predict.fun")
ZMQ_ADDR: str = os.getenv("ZMQ_ENGINE_ADDR", "tcp://0.0.0.0:5555")
DATA_DIR: Path = ROOT / "Data" / "markets_init"
DATA_DIR.mkdir(parents=True, exist_ok=True)

NODE_ID: str = uuid.uuid4().hex[:8]  # unique per teammate instance


# ── REST helpers ──────────────────────────────────────────────────


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json"}
    if API_KEY:
        h["x-api-key"] = API_KEY
    return h


def fetch_all_markets() -> list[dict]:
    """
    Paginate through GET /v1/markets?status=OPEN and return the raw
    list of market dicts from the Predict.fun API.
    """
    markets: list[dict] = []
    cursor: str | None = None
    page_size = 50

    with httpx.Client(base_url=API_BASE, headers=_headers(), timeout=30) as client:
        while True:
            params: dict[str, str] = {
                "first": str(page_size),
                "status": "OPEN",
                "includeStats": "true",
            }
            if cursor:
                params["after"] = cursor

            resp = client.get("/v1/markets", params=params)
            resp.raise_for_status()
            body = resp.json()

            page = body.get("data", [])
            markets.extend(page)
            cursor = body.get("cursor")
            log.info("Fetched %d markets (total so far: %d)", len(page), len(markets))

            if not cursor or len(page) < page_size:
                break

    return markets


def fetch_orderbook(market_id: int) -> dict | None:
    """Fetch the order book for a single market."""
    with httpx.Client(base_url=API_BASE, headers=_headers(), timeout=15) as client:
        resp = client.get(f"/v1/markets/{market_id}/orderbook")
        if resp.status_code != 200:
            return None
        return resp.json().get("data")


# ── Normalisation ─────────────────────────────────────────────────


def _infer_oracle(market: dict) -> ResolutionOracle:
    """Infer oracle from variant data or resolver address."""
    vd = market.get("variantData")
    if vd and vd.get("type") == "CRYPTO_UP_DOWN" and vd.get("priceFeedId"):
        return ResolutionOracle.PYTH
    resolver = (market.get("resolverAddress") or "").lower()
    if "chainlink" in resolver:
        return ResolutionOracle.CHAINLINK
    if "uma" in resolver:
        return ResolutionOracle.UMA
    return ResolutionOracle.CUSTOM


def _extract_underlying(market: dict) -> tuple[str, float | None]:
    """
    Try to pull the underlying asset ticker and strike from variant
    data, falling back to an LLM parse of the question text.
    """
    vd = market.get("variantData")
    if vd and vd.get("type") == "CRYPTO_UP_DOWN":
        # Use the priceFeedId to guess the ticker
        feed = vd.get("priceFeedId", "")
        ticker = feed.split("/")[0].upper() if "/" in feed else ""
        start = vd.get("startPrice")
        return ticker, start

    # Fallback: try structured LLM extraction
    from pydantic import BaseModel as _BM

    class _Extracted(_BM):
        underlying_asset: str = ""
        strike_value: float | None = None

    try:
        parsed = parse_market_text(
            raw_text=market.get("question", "") + " " + market.get("description", ""),
            response_model=_Extracted,
        )
        return parsed.underlying_asset, parsed.strike_value
    except Exception:
        return "", None


def normalise_market(raw: dict) -> NormalizedMarket:
    """Convert a raw Predict.fun API market dict into NormalizedMarket."""
    outcomes_raw = raw.get("outcomes", [])
    outcomes = [
        Outcome(
            name=o["name"],
            indexSet=o["indexSet"],
            onChainId=o["onChainId"],
        )
        for o in outcomes_raw
    ]

    # Infer yes/no prices from outcomes ordering (Yes=index 0, No=index 1)
    yes_price = 0.0
    no_price = 0.0

    oracle = _infer_oracle(raw)
    underlying, strike = _extract_underlying(raw)

    # Variant data
    vd_raw = raw.get("variantData")
    variant_data = None
    if vd_raw and vd_raw.get("type") == "CRYPTO_UP_DOWN":
        variant_data = CryptoUpDownVariantData(
            startPrice=vd_raw["startPrice"],
            endPrice=vd_raw.get("endPrice"),
            priceFeedId=vd_raw["priceFeedId"],
        )

    return NormalizedMarket(
        platform=Platform.PREDICTFUN,
        market_id=str(raw["id"]),
        condition_id=raw.get("conditionId", ""),
        title=raw.get("title", ""),
        question=raw.get("question", ""),
        description=raw.get("description", ""),
        underlying_asset=underlying,
        strike_value=strike,
        resolution_oracle=oracle,
        resolution_style=ResolutionStyle.EXPIRY,
        oracle_price_feed_id=(
            variant_data.price_feed_id if variant_data else ""
        ),
        expiration_iso=raw.get("boostEndsAt") or raw.get("createdAt", ""),
        created_at_iso=raw.get("createdAt", ""),
        outcomes=outcomes,
        yes_price=yes_price,
        no_price=no_price,
        fee_rate_bps=raw.get("feeRateBps", 0),
        trading_status=TradingStatus(raw.get("tradingStatus", "OPEN")),
        market_status=MarketStatus(raw.get("status", "REGISTERED")),
        market_variant=MarketVariant(raw.get("marketVariant", "DEFAULT")),
        variant_data=variant_data,
        is_neg_risk=raw.get("isNegRisk", False),
        is_yield_bearing=raw.get("isYieldBearing", False),
        is_visible=raw.get("isVisible", True),
        raw=raw,
    )


# ── Persist to Data/markets_init/ ─────────────────────────────────


def persist_markets(markets: list[NormalizedMarket]) -> Path:
    """Write all normalised markets to a single JSON file."""
    filename = f"predictfun_{NODE_ID}.json"
    filepath = DATA_DIR / filename
    payload = [m.model_dump(mode="json") for m in markets]
    filepath.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Persisted %d markets → %s", len(payload), filepath)
    return filepath


# ── ZMQ live odds publisher ───────────────────────────────────────


async def live_odds_publisher(markets: list[NormalizedMarket]) -> None:
    """
    Long-running coroutine that:
      1. Polls the Predict.fun REST API for order-book updates
         (until a true WebSocket feed is available).
      2. Publishes OddsUpdate messages over ZMQ PUB so the Rust
         engine receives them in real-time.
    """
    ctx = zmq.asyncio.Context()
    pub = ctx.socket(zmq.PUB)

    # Connect to the Engine's SUB bind address
    connect_addr = ZMQ_ADDR.replace("0.0.0.0", "localhost")
    pub.connect(connect_addr)
    log.info("ZMQ PUB connected → %s", connect_addr)

    # Build a lookup so we can iterate quickly
    market_ids = [int(m.market_id) for m in markets if m.market_id.isdigit()]

    while True:
        for mid in market_ids:
            try:
                ob_data = await asyncio.to_thread(fetch_orderbook, mid)
                if ob_data is None:
                    continue

                bids = [
                    OrderBookLevel(price=lvl[0], size=lvl[1])
                    for lvl in ob_data.get("bids", [])
                ]
                asks = [
                    OrderBookLevel(price=lvl[0], size=lvl[1])
                    for lvl in ob_data.get("asks", [])
                ]

                best_bid = bids[0].price if bids else 0.0
                best_ask = asks[0].price if asks else 0.0

                update = OddsUpdate(
                    platform=Platform.PREDICTFUN,
                    market_id=str(mid),
                    yes_price=best_bid,
                    no_price=1.0 - best_ask if best_ask else 0.0,
                    order_book=OrderBook(
                        bids=bids,
                        asks=asks,
                        updateTimestampMs=ob_data.get("updateTimestampMs", 0),
                    ),
                    timestamp_ms=int(time.time() * 1000),
                )

                topic = f"odds.{Platform.PREDICTFUN.value}.{mid}"
                payload = update.model_dump_json()
                await pub.send_multipart(
                    [topic.encode(), payload.encode()]
                )

            except Exception:
                log.exception("Error polling orderbook for market %s", mid)

        # Throttle: poll every 2 seconds
        await asyncio.sleep(2.0)


# ── Main ──────────────────────────────────────────────────────────


async def main() -> None:
    log.info("═══  Predict.fun Ingestion Node [%s]  ═══", NODE_ID)

    # Step 1 — Fetch
    raw_markets = await asyncio.to_thread(fetch_all_markets)
    log.info("Received %d raw markets from API", len(raw_markets))

    # Step 2 — Normalise
    normalised: list[NormalizedMarket] = []
    for rm in raw_markets:
        try:
            nm = normalise_market(rm)
            normalised.append(nm)
        except Exception:
            log.exception("Failed to normalise market %s", rm.get("id"))

    log.info("Normalised %d / %d markets", len(normalised), len(raw_markets))

    # Step 3 — Persist
    persist_markets(normalised)

    # Step 4 — Live odds loop
    await live_odds_publisher(normalised)


if __name__ == "__main__":
    asyncio.run(main())
