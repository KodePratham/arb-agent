"""
Ingestion/ingest_groq_selective.py
────────────────────────────────────────────────────────────────────
Selective cross-platform ingestion using Groq ranking.

Workflow:
  1. Fetch capped OPEN markets from Predict.fun and Probable.
  2. Normalise into shared NormalizedMarket schema.
  3. Build strict overlap pairs (same asset/oracle/near-expiry/strike).
  4. Ask Groq to pick ~N best overlap pairs.
  5. Persist only selected markets into Data/markets/.

Run:
    python -m Ingestion.ingest_groq_selective
    python -m Ingestion.ingest_groq_selective --cap-per-platform 20 --pick-count 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field

from Data.schemas import NormalizedMarket
from Ingestion.base_parser import LLM_PROVIDER, get_active_model, parse_market_text, set_model
from Ingestion.ingest_predictfun import fetch_all_markets as fetch_predictfun_markets
from Ingestion.ingest_predictfun import normalise_market as normalize_predictfun_market
from Ingestion.ingest_predictfun import persist_markets as persist_predictfun_markets
from Ingestion.ingest_probable import fetch_all_markets as fetch_probable_markets
from Ingestion.ingest_probable import normalise_market as normalize_probable_market
from Ingestion.ingest_probable import persist_markets as persist_probable_markets

log = logging.getLogger("ingest.groq.selective")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)


@dataclass(frozen=True)
class OverlapPair:
    predictfun: NormalizedMarket
    probable: NormalizedMarket
    score: float


class PairSelection(BaseModel):
    picks: list[int] = Field(default_factory=list, description="Candidate indices to select")
    rationale: str = ""


def _strike_key(v: float | None) -> str:
    if v is None:
        return "none"
    return f"{v:.4f}"


def _key_for_market(market: NormalizedMarket) -> tuple[str, str, str, int]:
    asset = (market.underlying_asset or "").strip().upper()
    oracle = market.resolution_oracle.value
    strike = _strike_key(market.strike_value)
    exp_bucket = market.expiration_unix // 60 if market.expiration_unix > 0 else 0
    return asset, oracle, strike, exp_bucket


def _build_overlap_pairs(
    predictfun_markets: list[NormalizedMarket],
    probable_markets: list[NormalizedMarket],
) -> list[OverlapPair]:
    probable_by_key: dict[tuple[str, str, str, int], list[NormalizedMarket]] = {}
    for pm in probable_markets:
        key = _key_for_market(pm)
        if not key[0]:
            continue
        probable_by_key.setdefault(key, []).append(pm)

    pairs: list[OverlapPair] = []
    for pf in predictfun_markets:
        key = _key_for_market(pf)
        if not key[0]:
            continue

        for candidate in probable_by_key.get(key, []):
            if pf.expiration_unix and candidate.expiration_unix:
                if abs(pf.expiration_unix - candidate.expiration_unix) > 60:
                    continue

            spread = abs(pf.yes_price - candidate.yes_price)
            liquidity_bonus = 0.0
            if pf.order_book and pf.order_book.bids:
                liquidity_bonus += min(0.01, pf.order_book.bids[0].size / 100000.0)
            if candidate.order_book and candidate.order_book.bids:
                liquidity_bonus += min(0.01, candidate.order_book.bids[0].size / 100000.0)

            pairs.append(OverlapPair(predictfun=pf, probable=candidate, score=spread + liquidity_bonus))

    pairs.sort(key=lambda p: p.score, reverse=True)
    return pairs


def _pick_with_groq(pairs: list[OverlapPair], pick_count: int) -> list[OverlapPair]:
    if not pairs:
        return []

    max_candidates = min(len(pairs), 30)
    candidates = pairs[:max_candidates]

    payload = []
    for idx, pair in enumerate(candidates):
        payload.append(
            {
                "idx": idx,
                "asset": pair.predictfun.underlying_asset,
                "oracle": pair.predictfun.resolution_oracle.value,
                "strike": pair.predictfun.strike_value,
                "expiration_unix": pair.predictfun.expiration_unix,
                "predictfun": {
                    "id": pair.predictfun.market_id,
                    "title": pair.predictfun.title,
                    "yes_price": pair.predictfun.yes_price,
                },
                "probable": {
                    "id": pair.probable.market_id,
                    "title": pair.probable.title,
                    "yes_price": pair.probable.yes_price,
                },
                "spread": abs(pair.predictfun.yes_price - pair.probable.yes_price),
            }
        )

    system_prompt = (
        "You are selecting cross-platform prediction-market overlap pairs for ingestion. "
        "Pick pairs that are clearly the same market and likely useful for arbitrage checks. "
        "Return up to the requested count, with unique indices."
    )
    user_text = (
        f"Pick up to {pick_count} overlap pairs from this JSON array. "
        "Prefer clear same-market matches and meaningful spread.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    try:
        parsed = parse_market_text(
            raw_text=user_text,
            response_model=PairSelection,
            system_prompt=system_prompt,
        )
        selected_indices: list[int] = []
        for idx in parsed.picks:
            if isinstance(idx, int) and 0 <= idx < len(candidates) and idx not in selected_indices:
                selected_indices.append(idx)
            if len(selected_indices) >= pick_count:
                break
        if selected_indices:
            return [candidates[i] for i in selected_indices]
    except Exception as exc:
        log.warning("Groq selection failed, falling back to top-scored pairs: %s", exc)

    return candidates[:pick_count]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Groq-driven selective cross-platform ingestion")
    parser.add_argument(
        "--cap-per-platform",
        type=int,
        default=20,
        help="Maximum OPEN markets fetched per platform before overlap matching.",
    )
    parser.add_argument(
        "--pick-count",
        type=int,
        default=5,
        help="How many overlap pairs to select for ingestion.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="",
        help="Override LLM model name for Groq selection.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.model:
        set_model(args.model)

    if LLM_PROVIDER != "groq":
        raise RuntimeError(
            "This selective flow requires Groq. Set LLM_PROVIDER=groq in .env before running."
        )

    cap = max(1, args.cap_per_platform)
    pick_count = max(1, args.pick_count)

    log.info("═══  Groq Selective Ingestion  ═══")
    log.info("Fetch cap/platform: %d | pick-count: %d | model: %s", cap, pick_count, get_active_model())

    raw_predictfun, raw_probable = await asyncio.gather(
        asyncio.to_thread(fetch_predictfun_markets, cap),
        asyncio.to_thread(fetch_probable_markets, cap),
    )

    predictfun_markets: list[NormalizedMarket] = []
    for raw in raw_predictfun:
        try:
            predictfun_markets.append(normalize_predictfun_market(raw))
        except Exception:
            log.exception("Failed to normalize Predict.fun market %s", raw.get("id"))

    probable_markets: list[NormalizedMarket] = []
    for raw in raw_probable:
        try:
            probable_markets.append(normalize_probable_market(raw))
        except Exception:
            log.exception("Failed to normalize Probable market %s", raw.get("id"))

    pairs = _build_overlap_pairs(predictfun_markets, probable_markets)
    if not pairs:
        log.warning("No strict overlap pairs found under current cap. Try increasing --cap-per-platform.")
        return

    selected_pairs = _pick_with_groq(pairs, pick_count)
    if not selected_pairs:
        log.warning("No pairs selected.")
        return

    selected_predictfun = [pair.predictfun for pair in selected_pairs]
    selected_probable = [pair.probable for pair in selected_pairs]

    persist_predictfun_markets(selected_predictfun, model_used=get_active_model())
    persist_probable_markets(selected_probable, model_used=get_active_model())

    log.info(
        "Saved selective ingestion: %d Predict.fun + %d Probable markets (%d overlap pairs)",
        len(selected_predictfun),
        len(selected_probable),
        len(selected_pairs),
    )


if __name__ == "__main__":
    asyncio.run(main())
