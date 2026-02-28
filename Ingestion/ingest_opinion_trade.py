"""
Ingestion/ingest_opinion_trade.py
────────────────────────────────────────────────────────────────────
Opinion.trade ingestion node.

Workflow:
  1. Fetch all OPEN markets from the Opinion.trade SDK.
  2. Normalise each market through the LLM-based ETL parser.
  3. Persist snapshots as JSON in Data/markets/.
  4. (Optional, --live) Poll orderbook updates and publish over ZMQ.

Run:
    python -m Ingestion.ingest_opinion_trade
    python -m Ingestion.ingest_opinion_trade --model llama3
    python -m Ingestion.ingest_opinion_trade --live
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

from dotenv import load_dotenv

# ── Ensure the project root is on sys.path ───────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Data.schemas import (
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
from Ingestion.sdk.opinion_trade import OpinionTradeConfig, OpinionTradeSDK

load_dotenv()

log = logging.getLogger("ingest.opinion_trade")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)

# ── Config ────────────────────────────────────────────────────────

API_KEY: str = os.getenv("OPINION_TRADE_API_KEY", "")
ZMQ_ADDR: str = os.getenv("ZMQ_ENGINE_ADDR", "tcp://0.0.0.0:5555")
DATA_DIR: Path = ROOT / "Data" / "markets"
DATA_DIR.mkdir(parents=True, exist_ok=True)

NODE_ID: str = uuid.uuid4().hex[:8]
OPINION_SDK = OpinionTradeSDK(
    OpinionTradeConfig(
        api_base_url=os.getenv("OPINION_TRADE_API_BASE", "https://api.opinion.trade"),
        app_base_url=os.getenv("OPINION_TRADE_APP_BASE", "https://app.opinion.trade"),
        api_key=API_KEY,
        timeout_seconds=int(os.getenv("OPINION_TRADE_API_TIMEOUT_SECONDS", "30")),
    )
)


# ── SDK helpers ───────────────────────────────────────────────────


def fetch_all_markets(max_markets: int | None = None) -> list[dict]:
    """Fetch open markets through the Opinion.trade SDK client."""
    markets = OPINION_SDK.list_open_markets(max_markets=max_markets)
    log.info("Fetched %d markets from Opinion.trade SDK", len(markets))
    return markets


def fetch_orderbook(market_id: str) -> dict | None:
    """Fetch the order book for a single market via SDK."""
    return OPINION_SDK.get_orderbook(market_id)


# ── Normalisation ─────────────────────────────────────────────────


def _parse_status(raw_value: str, enum_cls: type[TradingStatus] | type[MarketStatus], default: str):
    value = (raw_value or default).upper()
    try:
        return enum_cls(value)
    except ValueError:
        return enum_cls(default)


def _infer_oracle(market: dict) -> ResolutionOracle:
    """Infer resolution oracle from market metadata when available."""
    oracle_str = (
        market.get("oracle")
        or market.get("resolutionOracle")
        or market.get("oracleType")
        or ""
    ).upper()
    if "PYTH" in oracle_str:
        return ResolutionOracle.PYTH
    if "CHAINLINK" in oracle_str or "CHAIN_LINK" in oracle_str:
        return ResolutionOracle.CHAINLINK
    if "UMA" in oracle_str:
        return ResolutionOracle.UMA
    return ResolutionOracle.CUSTOM


def _extract_underlying(market: dict) -> tuple[str, float | None]:
    """
    Pull underlying and strike from structured fields when possible,
    then use simple ticker heuristics, then LLM fallback.
    """
    underlying = (
        market.get("underlying_asset")
        or market.get("underlyingAsset")
        or market.get("asset")
        or market.get("ticker")
        or ""
    )
    strike = market.get("strike_value") or market.get("strikeValue") or market.get("strike")

    if underlying:
        try:
            return str(underlying), float(strike) if strike is not None else None
        except (TypeError, ValueError):
            return str(underlying), None

    question = (market.get("question", "") + " " + market.get("title", "")).upper()
    known_assets = [
        "BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA",
        "AVAX", "DOT", "MATIC", "LINK", "UNI", "SHIB", "ARB",
        "OP", "APT", "SUI", "TIA", "SEI", "INJ", "PEPE",
        "BITCOIN", "ETHEREUM", "SOLANA", "DOGECOIN", "RIPPLE",
    ]
    ticker_map = {
        "BITCOIN": "BTC",
        "ETHEREUM": "ETH",
        "SOLANA": "SOL",
        "DOGECOIN": "DOGE",
        "RIPPLE": "XRP",
    }
    for asset in known_assets:
        if asset in question:
            return ticker_map.get(asset, asset), None

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
            market.get("id", market.get("marketId", "?")),
            exc,
        )
        return "", None


def _coerce_price(v: object) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _extract_yes_no_prices(raw: dict, outcomes_raw: list[dict]) -> tuple[float, float]:
    yes_price = (
        _coerce_price(raw.get("yesPrice"))
        or _coerce_price(raw.get("yes_price"))
        or _coerce_price(raw.get("yes"))
        or _coerce_price(raw.get("probabilityYes"))
    )
    no_price = (
        _coerce_price(raw.get("noPrice"))
        or _coerce_price(raw.get("no_price"))
        or _coerce_price(raw.get("no"))
        or _coerce_price(raw.get("probabilityNo"))
    )

    if yes_price is None or no_price is None:
        for outcome in outcomes_raw:
            name = str(outcome.get("name", "")).strip().lower()
            price = (
                _coerce_price(outcome.get("price"))
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

    return yes_price if yes_price is not None else 0.0, no_price if no_price is not None else 0.0


def normalise_market(raw: dict) -> NormalizedMarket:
    """Convert a raw Opinion.trade market dict into NormalizedMarket."""
    outcomes_raw = raw.get("outcomes", [])
    if not outcomes_raw:
        outcomes_raw = [
            {"name": "YES", "indexSet": 0, "onChainId": "0"},
            {"name": "NO", "indexSet": 1, "onChainId": "1"},
        ]

    outcomes = [
        Outcome(
            name=o.get("name", f"Outcome_{idx}"),
            indexSet=o.get("indexSet", idx),
            onChainId=str(o.get("onChainId", o.get("id", idx))),
        )
        for idx, o in enumerate(outcomes_raw)
    ]

    oracle = _infer_oracle(raw)
    underlying, strike = _extract_underlying(raw)
    yes_price, no_price = _extract_yes_no_prices(raw, outcomes_raw)

    expiration_iso = (
        raw.get("expiration")
        or raw.get("expiresAt")
        or raw.get("endAt")
        or raw.get("endTime")
        or ""
    )
    created_at_iso = raw.get("createdAt") or raw.get("created_at") or ""

    trading_status = _parse_status(
        raw.get("tradingStatus", raw.get("trading_status", "OPEN")),
        TradingStatus,
        "OPEN",
    )
    market_status = _parse_status(
        raw.get("status", "REGISTERED"),
        MarketStatus,
        "REGISTERED",
    )

    return NormalizedMarket(
        platform=Platform.OPINION_TRADE,
        market_id=str(raw.get("id", raw.get("marketId", raw.get("slug", "")))),
        condition_id=str(raw.get("conditionId", raw.get("condition_id", ""))),
        title=raw.get("title", raw.get("name", raw.get("question", ""))),
        question=raw.get("question", raw.get("title", raw.get("name", ""))),
        description=raw.get("description", ""),
        underlying_asset=underlying,
        strike_value=strike,
        resolution_oracle=oracle,
        resolution_style=ResolutionStyle.EXPIRY,
        oracle_price_feed_id=raw.get("oracleFeedId", raw.get("oracle_feed_id", "")),
        expiration_iso=expiration_iso,
        created_at_iso=created_at_iso,
        outcomes=outcomes,
        yes_price=yes_price,
        no_price=no_price,
        fee_rate_bps=int(raw.get("feeRateBps", raw.get("fee_bps", 0)) or 0),
        trading_status=trading_status,
        market_status=market_status,
        market_variant=MarketVariant.DEFAULT,
        is_neg_risk=bool(raw.get("isNegRisk", raw.get("is_neg_risk", False))),
        is_yield_bearing=bool(raw.get("isYieldBearing", raw.get("is_yield_bearing", False))),
        is_visible=bool(raw.get("isVisible", raw.get("is_visible", True))),
        raw=raw,
    )


# ── Persist to Data/markets/ ───────────────────────────────────────


def persist_markets(markets: list[NormalizedMarket], model_used: str = "") -> Path:
    """Write all normalised markets to a timestamped JSON file."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"opinion_trade_{ts}.json"
    filepath = DATA_DIR / filename
    payload = [m.model_dump(mode="json") for m in markets]
    filepath.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    manifest = SnapshotManifest(
        created_by=f"ingest_opinion_trade:{NODE_ID}",
        created_at=datetime.now(timezone.utc).isoformat(),
        model_used=model_used,
        platform="OPINION_TRADE",
        market_count=len(markets),
    )
    meta_path = DATA_DIR / f"opinion_trade_{ts}_meta.json"
    meta_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

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

    preview_count = min(5, len(markets))
    for i, market in enumerate(markets[:preview_count], 1):
        title = (market.title or market.question or "(no title)")[:50]
        print(f"  {i:>3}. [{market.platform.value}] id={market.market_id}  \"{title}\"")
    if len(markets) > preview_count:
        print(f"  ... and {len(markets) - preview_count} more")
    print("═" * 64 + "\n")

    log.info("Persisted %d markets → %s", len(payload), abs_data)
    log.info("Manifest → %s", abs_meta)
    return filepath


# ── ZMQ live odds publisher (opt-in via --live) ───────────────────


def _book_levels(raw_levels: list) -> list[OrderBookLevel]:
    levels: list[OrderBookLevel] = []
    for level in raw_levels:
        if isinstance(level, list) and len(level) >= 2:
            price = _coerce_price(level[0]) or 0.0
            size = _coerce_price(level[1]) or 0.0
            levels.append(OrderBookLevel(price=price, size=size))
            continue
        if isinstance(level, dict):
            price = _coerce_price(level.get("price")) or 0.0
            size = _coerce_price(level.get("size")) or 0.0
            levels.append(OrderBookLevel(price=price, size=size))
    return levels


async def live_odds_publisher(markets: list[NormalizedMarket]) -> None:
    import zmq
    import zmq.asyncio

    ctx = zmq.asyncio.Context()
    pub = ctx.socket(zmq.PUB)

    connect_addr = ZMQ_ADDR.replace("0.0.0.0", "localhost")
    pub.connect(connect_addr)
    log.info("ZMQ PUB connected → %s", connect_addr)

    market_ids = [m.market_id for m in markets if m.market_id]

    while True:
        for market_id in market_ids:
            try:
                ob_data = await asyncio.to_thread(fetch_orderbook, market_id)
                if ob_data is None:
                    continue

                bids = _book_levels(ob_data.get("bids", []))
                asks = _book_levels(ob_data.get("asks", []))

                best_bid = bids[0].price if bids else 0.0
                best_ask = asks[0].price if asks else 0.0

                update = OddsUpdate(
                    platform=Platform.OPINION_TRADE,
                    market_id=market_id,
                    yes_price=best_bid,
                    no_price=1.0 - best_ask if best_ask else 0.0,
                    order_book=OrderBook(
                        bids=bids,
                        asks=asks,
                        updateTimestampMs=int(time.time() * 1000),
                    ),
                    timestamp_ms=int(time.time() * 1000),
                )

                topic = f"odds.{Platform.OPINION_TRADE.value}.{market_id}"
                payload = update.model_dump_json()
                await pub.send_multipart([topic.encode(), payload.encode()])
            except Exception:
                log.exception("Error polling orderbook for market %s", market_id)

        await asyncio.sleep(2.0)


# ── CLI ───────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Opinion.trade market ingestion node")
    parser.add_argument(
        "--model",
        type=str,
        default="",
        help="Override the LLM model name (e.g. llama3, mistral).",
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

    if args.model:
        set_model(args.model)

    log.info("═══  Opinion.trade Ingestion Node [%s]  ═══", NODE_ID)

    max_markets = args.max_markets if args.max_markets > 0 else None
    raw_markets = await asyncio.to_thread(fetch_all_markets, max_markets)
    log.info("Received %d raw markets from SDK", len(raw_markets))

    normalised: list[NormalizedMarket] = []
    for raw_market in raw_markets:
        try:
            normalised.append(normalise_market(raw_market))
        except Exception:
            log.exception("Failed to normalise market %s", raw_market.get("id", raw_market.get("marketId")))

    log.info("Normalised %d / %d markets", len(normalised), len(raw_markets))

    from Ingestion.base_parser import get_active_model

    persist_markets(normalised, model_used=get_active_model())

    if args.live:
        log.info("--live mode: starting ZMQ odds publisher…")
        await live_odds_publisher(normalised)
    else:
        log.info("Exiting. Use --live to start the ZMQ odds publisher.")


if __name__ == "__main__":
    asyncio.run(main())
