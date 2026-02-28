"""
Compatibility shim.

Predict.fun ingestion has been replaced by Opinion.trade ingestion.
Use:
    python -m Ingestion.ingest_opinion_trade
"""

from __future__ import annotations

import asyncio
import logging

from Ingestion.ingest_opinion_trade import main as opinion_main


log = logging.getLogger("ingest.predictfun")


async def main() -> None:
    log.warning(
        "ingest_predictfun is deprecated and now routes to Opinion.trade ingestion. "
        "Use python -m Ingestion.ingest_opinion_trade instead."
    )
    await opinion_main()


if __name__ == "__main__":
    asyncio.run(main())
