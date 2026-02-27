"""
Data/schemas.py
────────────────────────────────────────────────────────────────────
Strict Pydantic v2 models shared between ALL Python ingestion nodes.
Enums enforce a closed set of oracles and resolution styles.
All dates are ISO-8601 strings; a deterministic helper converts to
Unix-epoch integers.
────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums ─────────────────────────────────────────────────────────


class Platform(str, enum.Enum):
    """Prediction-market platforms we ingest from."""
    PREDICTFUN = "PREDICTFUN"
    PROBABLE   = "PROBABLE"


class ResolutionOracle(str, enum.Enum):
    """On-chain price-feed oracle that resolves the market."""
    PYTH      = "PYTH"
    CHAINLINK = "CHAINLINK"
    UMA       = "UMA"
    CUSTOM    = "CUSTOM"


class ResolutionStyle(str, enum.Enum):
    """How the market resolves once expiration is reached."""
    TOUCH  = "TOUCH"    # resolves the instant the strike is touched
    EXPIRY = "EXPIRY"   # resolves only at the expiration timestamp


class MarketVariant(str, enum.Enum):
    """Sub-type of market (mirrors Predict.fun API)."""
    DEFAULT          = "DEFAULT"
    SPORTS_MATCH     = "SPORTS_MATCH"
    CRYPTO_UP_DOWN   = "CRYPTO_UP_DOWN"
    TWEET_COUNT      = "TWEET_COUNT"
    SPORTS_TEAM_MATCH = "SPORTS_TEAM_MATCH"


class TradingStatus(str, enum.Enum):
    OPEN                = "OPEN"
    MATCHING_NOT_ENABLED = "MATCHING_NOT_ENABLED"
    CANCEL_ONLY         = "CANCEL_ONLY"
    CLOSED              = "CLOSED"


class MarketStatus(str, enum.Enum):
    REGISTERED      = "REGISTERED"
    PRICE_PROPOSED  = "PRICE_PROPOSED"
    PRICE_DISPUTED  = "PRICE_DISPUTED"
    PAUSED          = "PAUSED"
    UNPAUSED        = "UNPAUSED"
    RESOLVED        = "RESOLVED"
    REMOVED         = "REMOVED"


# ── Deterministic ISO → Unix converter ────────────────────────────


def iso8601_to_unix(iso_str: str) -> int:
    """
    Convert an ISO-8601 date/time string to a Unix-epoch integer (seconds).

    Deterministic: if no timezone info is present, UTC is assumed.
    """
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


# ── Sub-models ────────────────────────────────────────────────────


class Outcome(BaseModel):
    """A single outcome of a binary or multi-outcome market."""
    name: str
    index_set: int = Field(..., alias="indexSet")
    on_chain_id: str = Field(..., alias="onChainId")

    model_config = {"populate_by_name": True}


class CryptoUpDownVariantData(BaseModel):
    """Variant metadata for CRYPTO_UP_DOWN markets (Pyth oracle)."""
    start_price: float = Field(..., alias="startPrice")
    end_price: Optional[float] = Field(None, alias="endPrice")
    price_feed_id: str = Field(..., alias="priceFeedId")

    model_config = {"populate_by_name": True}


class OrderBookLevel(BaseModel):
    """Single price/size level in the order book."""
    price: float
    size: float


class OrderBook(BaseModel):
    """Snapshot of bids and asks."""
    bids: list[OrderBookLevel] = Field(default_factory=list)
    asks: list[OrderBookLevel] = Field(default_factory=list)
    update_timestamp_ms: int = Field(0, alias="updateTimestampMs")

    model_config = {"populate_by_name": True}


# ── Core Market Model ─────────────────────────────────────────────


class NormalizedMarket(BaseModel):
    """
    Platform-agnostic market representation.

    This is the canonical shape that every ingestion node must produce.
    The Rust engine deserializes these from JSON files in Data/markets_init/.
    """

    # ── Identity ──────────────────────────────────────────────────
    platform: Platform
    market_id: str = Field(
        ...,
        description="Platform-native unique ID (int-as-string for Predict.fun)",
    )
    condition_id: str = Field(
        "",
        description="Conditional-token conditionId (hex string)",
    )

    # ── Descriptive ───────────────────────────────────────────────
    title: str
    question: str
    description: str = ""

    # ── Underlying asset / condition ──────────────────────────────
    underlying_asset: str = Field(
        "",
        description="Ticker or slug of the underlying (e.g. 'BTC', 'ETH')",
    )
    strike_value: Optional[float] = Field(
        None,
        description="Strike price for UP/DOWN markets",
    )

    # ── Oracle / Resolution ───────────────────────────────────────
    resolution_oracle: ResolutionOracle = ResolutionOracle.CUSTOM
    resolution_style: ResolutionStyle = ResolutionStyle.EXPIRY
    oracle_price_feed_id: str = Field(
        "",
        description="Pyth / Chainlink feed identifier",
    )

    # ── Timestamps (ISO-8601 strings) ─────────────────────────────
    expiration_iso: str = Field(
        "",
        description="Market expiration as ISO-8601",
    )
    created_at_iso: str = Field(
        "",
        description="Market creation timestamp as ISO-8601",
    )

    # ── Computed Unix epochs ──────────────────────────────────────
    expiration_unix: int = 0
    created_at_unix: int = 0

    # ── Outcomes & Odds ───────────────────────────────────────────
    outcomes: list[Outcome] = Field(default_factory=list)
    yes_price: float = Field(0.0, ge=0.0, le=1.0)
    no_price: float = Field(0.0, ge=0.0, le=1.0)

    # ── Order Book (populated by live WS feed) ────────────────────
    order_book: Optional[OrderBook] = None

    # ── Fees / Trading ────────────────────────────────────────────
    fee_rate_bps: int = Field(0, description="Platform fee in basis points")
    trading_status: TradingStatus = TradingStatus.OPEN
    market_status: MarketStatus = MarketStatus.REGISTERED

    # ── Variant ───────────────────────────────────────────────────
    market_variant: MarketVariant = MarketVariant.DEFAULT
    variant_data: Optional[CryptoUpDownVariantData] = None

    # ── Flags ─────────────────────────────────────────────────────
    is_neg_risk: bool = False
    is_yield_bearing: bool = False
    is_visible: bool = True

    # ── Raw blob (for debugging) ──────────────────────────────────
    raw: Optional[dict[str, Any]] = Field(
        None,
        description="Original API payload for debugging",
        exclude=True,
    )

    # ── Validators ────────────────────────────────────────────────

    @field_validator("expiration_unix", mode="before")
    @classmethod
    def _compute_expiration_unix(cls, v: int, info: Any) -> int:
        iso = info.data.get("expiration_iso", "")
        if iso and v == 0:
            return iso8601_to_unix(iso)
        return v

    @field_validator("created_at_unix", mode="before")
    @classmethod
    def _compute_created_at_unix(cls, v: int, info: Any) -> int:
        iso = info.data.get("created_at_iso", "")
        if iso and v == 0:
            return iso8601_to_unix(iso)
        return v

    # ── Helpers ───────────────────────────────────────────────────

    @property
    def composite_key(self) -> str:
        """Key used by the Rust DashMap: (Platform, MarketID)."""
        return f"{self.platform.value}::{self.market_id}"


# ── ZMQ Live-Odds Update ─────────────────────────────────────────


class OddsUpdate(BaseModel):
    """
    Lightweight message published over ZMQ by each ingestion node
    whenever odds change.  The Rust engine subscribes and applies
    the update to its DashMap.
    """
    platform: Platform
    market_id: str
    yes_price: float
    no_price: float
    order_book: Optional[OrderBook] = None
    timestamp_ms: int = 0
