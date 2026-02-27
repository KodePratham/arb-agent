"""
Ingestion/ingest_probable.py
────────────────────────────────────────────────────────────────────
Probable ingestion node — designed to be run by ANY teammate on
their own machine.

Workflow:
  1. Fetch all OPEN markets from the Probable REST API.
  2. Normalise each market through the LLM-based ETL parser.
  3. Persist snapshots as JSON in Data/markets/.
  4. (Optional, --live) Open an asyncio listener that publishes
     live odds updates to the Engine over ZMQ PUB.

Run:
    python -m Ingestion.ingest_probable
    python -m Ingestion.ingest_probable --model llama3
    python -m Ingestion.ingest_probable --live
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

log = logging.getLogger("ingest.probable")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)

# ── Config ────────────────────────────────────────────────────────

API_BASE: str = os.getenv("PROBABLE_API_BASE", "https://market-api.probable.markets")
API_KEY: str = os.getenv("PROBABLE_API_KEY", "")  # required — Probable enforces auth even on read endpoints
WS_URL: str = os.getenv("PROBABLE_WS_URL", "wss://probable.markets/ws")
ZMQ_ADDR: str = os.getenv("ZMQ_ENGINE_ADDR", "tcp://0.0.0.0:5555")
DATA_DIR: Path = ROOT / "Data" / "markets"
DATA_DIR.mkdir(parents=True, exist_ok=True)

NODE_ID: str = uuid.uuid4().hex[:8]


# ── REST helpers ──────────────────────────────────────────────────


def _headers() -> dict[str, str]:
    """Probable requires a Bearer token even for read endpoints."""
    h: dict[str, str] = {"Accept": "application/json"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    else:
        log.warning(
            "PROBABLE_API_KEY is not set — requests will likely be rejected "
            "with 401/403. Set it in your .env file: PROBABLE_API_KEY=<your_key>"
        )
    return h


def fetch_all_markets(max_markets: int | None = None) -> list[dict]:
    """
    Paginate through the Probable markets API.

    NOTE: Probable's exact API shape may differ; adapt the endpoint
    and pagination logic when their documentation is finalised.
    """
    markets: list[dict] = []
    page = 1
    page_size = 50

    with httpx.Client(base_url=API_BASE, headers=_headers(), timeout=30) as client:
        while True:
            params: dict[str, str | int] = {
                "page": page,
                "limit": page_size,
                "status": "open",
            }
            resp = client.get("/v1/markets", params=params)
            if resp.status_code in (401, 403):
                raise RuntimeError(
                    f"Probable API returned {resp.status_code}: authentication required. "
                    "Set PROBABLE_API_KEY=<your_key> in your .env file and re-run."
                )
            resp.raise_for_status()
            body = resp.json()

            data = body.get("data", body.get("markets", []))
            if max_markets is not None:
                remaining = max_markets - len(markets)
                if remaining <= 0:
                    break
                markets.extend(data[:remaining])
            else:
                markets.extend(data)
            log.info(
                "Fetched page %d  (%d markets, total %d)",
                page,
                len(data),
                len(markets),
            )

            if (max_markets is not None and len(markets) >= max_markets) or len(data) < page_size:
                break
            page += 1

    return markets


def fetch_orderbook(market_id: str) -> dict | None:
    """Fetch the order book for a single Probable market."""
    with httpx.Client(base_url=API_BASE, headers=_headers(), timeout=15) as client:
        resp = client.get(f"/v1/markets/{market_id}/orderbook")
        if resp.status_code != 200:
            return None
        return resp.json().get("data", resp.json())


# ── Normalisation ─────────────────────────────────────────────────


def _infer_oracle(market: dict) -> ResolutionOracle:
    """Infer oracle from market metadata.

    Probable uses UMA Optimistic Oracle for all market resolution.
    """
    oracle_str = (market.get("oracle") or "").upper()
    if "PYTH" in oracle_str:
        return ResolutionOracle.PYTH
    if "CHAINLINK" in oracle_str or "CHAIN_LINK" in oracle_str:
        return ResolutionOracle.CHAINLINK
    if "UMA" in oracle_str:
        return ResolutionOracle.UMA
    # Probable defaults to UMA Optimistic Oracle
    return ResolutionOracle.UMA


def _extract_underlying(market: dict) -> tuple[str, float | None]:
    """
    Pull underlying asset and strike from structured fields when
    possible, falling back to heuristics, then LLM as last resort.
    """
    underlying = market.get("underlying_asset") or market.get("asset", "")
    strike = market.get("strike_value") or market.get("strike")

    if underlying:
        return underlying, float(strike) if strike else None

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
            raw_text=(
                market.get("question", "")
                + " "
                + market.get("description", "")
            ),
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
    """Convert a raw Probable API market dict into NormalizedMarket."""
    outcomes_raw = raw.get("outcomes", [])
    outcomes: list[Outcome] = []
    for idx, o in enumerate(outcomes_raw):
        outcomes.append(
            Outcome(
                name=o.get("name", f"Outcome_{idx}"),
                indexSet=o.get("indexSet", idx),
                onChainId=str(o.get("onChainId", o.get("id", idx))),
            )
        )

    oracle = _infer_oracle(raw)
    underlying, strike = _extract_underlying(raw)

    yes_price = float(raw.get("yes_price", raw.get("yesPrice", 0.0)))
    no_price = float(raw.get("no_price", raw.get("noPrice", 0.0)))

    return NormalizedMarket(
        platform=Platform.PROBABLE,
        market_id=str(raw.get("id", raw.get("marketId", ""))),
        condition_id=raw.get("conditionId", ""),
        title=raw.get("title", ""),
        question=raw.get("question", raw.get("title", "")),
        description=raw.get("description", ""),
        underlying_asset=underlying,
        strike_value=strike,
        resolution_oracle=oracle,
        resolution_style=ResolutionStyle(
            raw.get("resolution_style", "EXPIRY").upper()
        ),
        oracle_price_feed_id=raw.get("oracle_feed_id", ""),
        expiration_iso=raw.get("expiration", raw.get("endsAt", "")),
        created_at_iso=raw.get("createdAt", ""),
        outcomes=outcomes,
        yes_price=yes_price,
        no_price=no_price,
        # Probable is a ZERO-FEE platform (launch promotion)
        fee_rate_bps=int(raw.get("feeRateBps", raw.get("fee_bps", 0))),
        trading_status=TradingStatus.OPEN,
        market_status=MarketStatus.REGISTERED,
        market_variant=MarketVariant.DEFAULT,
        is_neg_risk=raw.get("isNegRisk", False),
        is_yield_bearing=raw.get("isYieldBearing", False),
        is_visible=True,
        raw=raw,
    )


# ── Persist to Data/markets/ ───────────────────────────────────────


def persist_markets(markets: list[NormalizedMarket], model_used: str = "") -> Path:
    """Write all normalised markets to a timestamped JSON file."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"probable_{ts}.json"
    filepath = DATA_DIR / filename
    payload = [m.model_dump(mode="json") for m in markets]
    filepath.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Write sidecar manifest
    manifest = SnapshotManifest(
        created_by=f"ingest_probable:{NODE_ID}",
        created_at=datetime.now(timezone.utc).isoformat(),
        model_used=model_used,
        platform="PROBABLE",
        market_count=len(markets),
    )
    meta_path = DATA_DIR / f"probable_{ts}_meta.json"
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
    Long-running coroutine that polls the Probable REST API for
    order-book updates and publishes OddsUpdate messages over ZMQ PUB.
    """
    import zmq
    import zmq.asyncio

    ctx = zmq.asyncio.Context()
    pub = ctx.socket(zmq.PUB)

    connect_addr = ZMQ_ADDR.replace("0.0.0.0", "localhost")
    pub.connect(connect_addr)
    log.info("ZMQ PUB connected → %s", connect_addr)

    market_ids = [m.market_id for m in markets]

    while True:
        for mid in market_ids:
            try:
                ob_data = await asyncio.to_thread(fetch_orderbook, mid)
                if ob_data is None:
                    continue

                bids_raw = ob_data.get("bids", [])
                asks_raw = ob_data.get("asks", [])

                bids = [
                    OrderBookLevel(
                        price=float(b[0]) if isinstance(b, list) else float(b.get("price", 0)),
                        size=float(b[1]) if isinstance(b, list) else float(b.get("size", 0)),
                    )
                    for b in bids_raw
                ]
                asks = [
                    OrderBookLevel(
                        price=float(a[0]) if isinstance(a, list) else float(a.get("price", 0)),
                        size=float(a[1]) if isinstance(a, list) else float(a.get("size", 0)),
                    )
                    for a in asks_raw
                ]

                best_bid = bids[0].price if bids else 0.0
                best_ask = asks[0].price if asks else 0.0

                update = OddsUpdate(
                    platform=Platform.PROBABLE,
                    market_id=mid,
                    yes_price=best_bid,
                    no_price=1.0 - best_ask if best_ask else 0.0,
                    order_book=OrderBook(
                        bids=bids,
                        asks=asks,
                        updateTimestampMs=int(time.time() * 1000),
                    ),
                    timestamp_ms=int(time.time() * 1000),
                )

                topic = f"odds.{Platform.PROBABLE.value}.{mid}"
                payload = update.model_dump_json()
                await pub.send_multipart(
                    [topic.encode(), payload.encode()]
                )

            except Exception:
                log.exception("Error polling orderbook for market %s", mid)

        await asyncio.sleep(2.0)


# ── CLI ───────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probable market ingestion node",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="",
        help="Override the LLM model name (e.g. llama3, mistral). "
             "If omitted and LLM_PROVIDER=ollama, shows interactive picker.",
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

    log.info("═══  Probable Ingestion Node [%s]  ═══", NODE_ID)

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
