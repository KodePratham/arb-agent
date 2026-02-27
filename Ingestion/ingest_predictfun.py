"""
Ingestion/ingest_predictfun.py
────────────────────────────────────────────────────────────────────
Predict.fun ingestion node — designed to be run by ANY teammate on
their own machine.

Workflow:
  1. Fetch all OPEN markets from the Predict.fun REST API.
  2. Normalise each market through the LLM-based ETL parser.
  3. Persist snapshots as JSON in Data/markets/.
  4. (Optional, --live) Open an asyncio listener that publishes
     live odds updates to the Engine over ZMQ PUB.

Run:
    python -m Ingestion.ingest_predictfun
    python -m Ingestion.ingest_predictfun --model llama3
    python -m Ingestion.ingest_predictfun --live
────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
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
    SnapshotManifest,
    TradingStatus,
)
from Ingestion.base_parser import parse_market_text, set_model

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
DATA_DIR: Path = ROOT / "Data" / "markets"
DATA_DIR.mkdir(parents=True, exist_ok=True)

NODE_ID: str = uuid.uuid4().hex[:8]  # unique per teammate instance


# ── REST helpers ──────────────────────────────────────────────────


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json"}
    if API_KEY:
        h["x-api-key"] = API_KEY
    return h


def fetch_all_markets(max_markets: int | None = None) -> list[dict]:
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
            if max_markets is not None:
                remaining = max_markets - len(markets)
                if remaining <= 0:
                    break
                markets.extend(page[:remaining])
            else:
                markets.extend(page)
            cursor = body.get("cursor")
            log.info("Fetched %d markets (total so far: %d)", len(page), len(markets))

            if (max_markets is not None and len(markets) >= max_markets) or not cursor or len(page) < page_size:
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
    data, falling back to simple heuristics and then LLM only
    as a last resort.
    """
    vd = market.get("variantData")
    if vd and vd.get("type") == "CRYPTO_UP_DOWN":
        feed = vd.get("priceFeedId", "")
        ticker = feed.split("/")[0].upper() if "/" in feed else ""
        start = vd.get("startPrice")
        return ticker, start

    # ── Heuristic: scan question for common crypto tickers ────────
    question = (market.get("question", "") + " " + market.get("title", "")).upper()
    _KNOWN_ASSETS = [
        "BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA",
        "AVAX", "DOT", "MATIC", "LINK", "UNI", "SHIB", "ARB",
        "OP", "APT", "SUI", "TIA", "SEI", "INJ", "PEPE",
        "BITCOIN", "ETHEREUM", "SOLANA", "DOGECOIN", "RIPPLE",
    ]
    _TICKER_MAP = {
        "BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL",
        "DOGECOIN": "DOGE", "RIPPLE": "XRP",
    }
    for asset in _KNOWN_ASSETS:
        if asset in question:
            ticker = _TICKER_MAP.get(asset, asset)
            return ticker, None

    # ── LLM fallback (may fail — that's OK, we degrade gracefully) ─
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
    except Exception as exc:
        log.warning(
            "LLM extraction failed for market %s — using empty underlying. Error: %s",
            market.get("id", "?"), exc,
        )
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

    def _coerce_price(v: object) -> float | None:
        try:
            if v is None:
                return None
            return float(v)
        except (TypeError, ValueError):
            return None

    yes_price = _coerce_price(raw.get("yesPrice"))
    no_price = _coerce_price(raw.get("noPrice"))

    if yes_price is None or no_price is None:
        for outcome in outcomes_raw:
            name = str(outcome.get("name", "")).strip().lower()
            price = (
                _coerce_price(outcome.get("price"))
                or _coerce_price(outcome.get("yesPrice"))
                or _coerce_price(outcome.get("noPrice"))
                or _coerce_price(outcome.get("probability"))
                or _coerce_price(outcome.get("lastPrice"))
            )
            if price is None:
                continue
            if name in {"yes", "up", "true"} and yes_price is None:
                yes_price = price
            elif name in {"no", "down", "false"} and no_price is None:
                no_price = price

    if yes_price is None and no_price is not None:
        yes_price = max(0.0, min(1.0, 1.0 - no_price))
    if no_price is None and yes_price is not None:
        no_price = max(0.0, min(1.0, 1.0 - yes_price))

    yes_price = yes_price if yes_price is not None else 0.0
    no_price = no_price if no_price is not None else 0.0

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


# ── Persist to Data/markets/ ───────────────────────────────────────


def persist_markets(markets: list[NormalizedMarket], model_used: str = "") -> Path:
    """Write all normalised markets to a timestamped JSON file."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"predictfun_{ts}.json"
    filepath = DATA_DIR / filename
    payload = [m.model_dump(mode="json") for m in markets]
    filepath.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Write sidecar manifest
    manifest = SnapshotManifest(
        created_by=f"ingest_predictfun:{NODE_ID}",
        created_at=datetime.now(timezone.utc).isoformat(),
        model_used=model_used,
        platform="PREDICTFUN",
        market_count=len(markets),
    )
    meta_path = DATA_DIR / f"predictfun_{ts}_meta.json"
    meta_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    # ── Print clear storage summary ───────────────────────────────
    abs_data = filepath.resolve()
    abs_meta = meta_path.resolve()
    print("\n" + "═" * 64)
    print("  DATA STORAGE SUMMARY")
    print("═" * 64)
    print(f"  Markets file : {abs_data}")
    print(f"  Manifest file: {abs_meta}")
    print(f"  Directory    : {DATA_DIR.resolve()}")
    print(f"  Market count : {len(markets)}")
    print(f"  Model used   : {model_used or '(none)'}")
    print("─" * 64)
    # Show first few markets with human-readable title + ID
    preview_count = min(5, len(markets))
    for i, m in enumerate(markets[:preview_count], 1):
        title = (m.title or m.question or "(no title)")[:50]
        print(f"  {i:>3}. [{m.platform.value}] id={m.market_id}  \"{title}\"")
    if len(markets) > preview_count:
        print(f"  ... and {len(markets) - preview_count} more")
    print("═" * 64 + "\n")

    log.info("Persisted %d markets → %s", len(payload), abs_data)
    log.info("Manifest → %s", abs_meta)

    return filepath


# ── ZMQ live odds publisher (opt-in via --live) ───────────────────


async def live_odds_publisher(markets: list[NormalizedMarket]) -> None:
    """
    Long-running coroutine that:
      1. Polls the Predict.fun REST API for order-book updates
         (until a true WebSocket feed is available).
      2. Publishes OddsUpdate messages over ZMQ PUB so the
         engine receives them in real-time.
    """
    import zmq
    import zmq.asyncio

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


# ── CLI ───────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Predict.fun market ingestion node",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="",
        help="Override the LLM model name (e.g. llama3, mistral). "
             "If omitted, shows interactive Ollama model picker.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="After ingestion, keep running and publish live odds over ZMQ.",
    )
    parser.add_argument(
        "--max-markets",
        type=int,
        default=0,
        help="Optional cap on number of open markets fetched (0 = no cap).",
    )
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────────


async def main() -> None:
    args = parse_args()

    # Apply --model override before parser initializes
    if args.model:
        set_model(args.model)

    log.info("═══  Predict.fun Ingestion Node [%s]  ═══", NODE_ID)

    # Step 1 — Fetch
    max_markets = args.max_markets if args.max_markets > 0 else None
    raw_markets = await asyncio.to_thread(fetch_all_markets, max_markets)
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
    from Ingestion.base_parser import get_active_model
    persist_markets(normalised, model_used=get_active_model())

    log.info("✓ Ingestion complete. JSON files written to Data/markets/")

    # Step 4 — (optional) Live odds loop
    if args.live:
        log.info("--live mode: starting ZMQ odds publisher…")
        await live_odds_publisher(normalised)
    else:
        log.info("Exiting. Use --live to start the ZMQ odds publisher.")


if __name__ == "__main__":
    asyncio.run(main())
