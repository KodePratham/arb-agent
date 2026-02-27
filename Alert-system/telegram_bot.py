"""
Alert-system/telegram_bot.py
────────────────────────────────────────────────────────────────────
Lightweight Telegram bot that forwards arbitrage alerts from the
Rust engine (or directly from Python orchestration) to a Telegram
chat / channel.

Usage:
    python -m Alert-system.telegram_bot
────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import zmq
import zmq.asyncio
from dotenv import load_dotenv
from telegram import Bot

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv()

log = logging.getLogger("alert.telegram")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)

# ── Config ────────────────────────────────────────────────────────

BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
ZMQ_ADDR: str = os.getenv("ZMQ_ENGINE_ADDR", "tcp://0.0.0.0:5555")


# ── Alert formatter ───────────────────────────────────────────────


def format_arb_alert(data: dict) -> str:
    """Format an ArbOpportunity dict into a readable Telegram message."""
    return (
        f"🚨 <b>Arbitrage Detected</b>\n\n"
        f"<b>Buy YES</b>: {data.get('market_a_platform', '?')} / {data.get('market_a_id', '?')}\n"
        f"  Price: {data.get('market_a_yes_price', 0):.4f}\n\n"
        f"<b>Sell YES</b>: {data.get('market_b_platform', '?')} / {data.get('market_b_id', '?')}\n"
        f"  Price: {data.get('market_b_yes_price', 0):.4f}\n\n"
        f"📊 Net Δ: <b>{data.get('net_delta_bps', 0):.1f} bps</b>\n"
        f"⛽ Gas: {data.get('estimated_gas_bnb', 0):.6f} BNB\n"
        f"📉 Slippage: {data.get('slippage_bps', 0):.1f} bps\n"
        f"💰 Size: ${data.get('recommended_size_usdt', 0):.0f} USDT\n"
        f"✅ Profitable: {data.get('is_profitable', False)}"
    )


# ── Main listener ─────────────────────────────────────────────────


async def main() -> None:
    if not BOT_TOKEN or not CHAT_ID:
        log.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env")
        sys.exit(1)

    bot = Bot(token=BOT_TOKEN)

    # Subscribe to arb alert topics on the same ZMQ bus
    ctx = zmq.asyncio.Context()
    sub = ctx.socket(zmq.SUB)
    connect_addr = ZMQ_ADDR.replace("0.0.0.0", "localhost")
    sub.connect(connect_addr)
    sub.setsockopt_string(zmq.SUBSCRIBE, "arb.")
    log.info("ZMQ SUB connected → %s  (topic: arb.*)", connect_addr)

    await bot.send_message(
        chat_id=CHAT_ID,
        text="🤖 Arb-Agent alert bot is online.",
        parse_mode="HTML",
    )

    while True:
        frames = await sub.recv_multipart()
        if len(frames) < 2:
            continue

        topic = frames[0].decode()
        payload = frames[1].decode()

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            log.warning("Invalid JSON on topic %s", topic)
            continue

        msg = format_arb_alert(data)
        log.info("Sending alert → %s", CHAT_ID)
        await bot.send_message(
            chat_id=CHAT_ID,
            text=msg,
            parse_mode="HTML",
        )


if __name__ == "__main__":
    asyncio.run(main())
