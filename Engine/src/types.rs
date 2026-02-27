// Engine/src/types.rs
// ─────────────────────────────────────────────────────────────────
// Rust structs mapping 1:1 with the Python Pydantic schemas in
// Data/schemas.py.  Every field uses `serde` for strict JSON
// deserialization from the files produced by ingestion nodes.
// ─────────────────────────────────────────────────────────────────

use serde::{Deserialize, Serialize};
use std::fmt;

// ── Enums ────────────────────────────────────────────────────────

/// Prediction-market platform identifier.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Platform {
    Predictfun,
    Probable,
}

impl fmt::Display for Platform {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Predictfun => write!(f, "PREDICTFUN"),
            Self::Probable => write!(f, "PROBABLE"),
        }
    }
}

/// On-chain oracle used to resolve the market.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ResolutionOracle {
    Pyth,
    Chainlink,
    Uma,
    Custom,
}

/// How the market resolves once the expiration is reached.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ResolutionStyle {
    Touch,
    Expiry,
}

/// Sub-type of market (mirrors Predict.fun variants).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum MarketVariant {
    Default,
    SportsMatch,
    CryptoUpDown,
    TweetCount,
    SportsTeamMatch,
}

/// Current trading status.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum TradingStatus {
    Open,
    MatchingNotEnabled,
    CancelOnly,
    Closed,
}

/// Market lifecycle status.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum MarketStatus {
    Registered,
    PriceProposed,
    PriceDisputed,
    Paused,
    Unpaused,
    Resolved,
    Removed,
}

// ── Sub-structs ──────────────────────────────────────────────────

/// A single outcome (Yes / No / named) in a market.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Outcome {
    pub name: String,
    #[serde(alias = "index_set")]
    pub index_set: i64,
    #[serde(alias = "on_chain_id")]
    pub on_chain_id: String,
}

/// Variant metadata for CRYPTO_UP_DOWN markets.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CryptoUpDownVariantData {
    #[serde(alias = "start_price")]
    pub start_price: f64,
    #[serde(alias = "end_price")]
    pub end_price: Option<f64>,
    #[serde(alias = "price_feed_id")]
    pub price_feed_id: String,
}

/// Single price/size level in an order book.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderBookLevel {
    pub price: f64,
    pub size: f64,
}

/// Snapshot of bids and asks.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderBook {
    pub bids: Vec<OrderBookLevel>,
    pub asks: Vec<OrderBookLevel>,
    #[serde(alias = "update_timestamp_ms", default)]
    pub update_timestamp_ms: i64,
}

// ── Core Market ──────────────────────────────────────────────────

/// Canonical, platform-agnostic market representation.
///
/// Deserialized directly from the JSON files that Python ingestion
/// nodes write into `Data/markets_init/`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NormalizedMarket {
    // ── Identity ─────────────────────────────────────────────────
    pub platform: Platform,
    pub market_id: String,
    #[serde(default)]
    pub condition_id: String,

    // ── Descriptive ──────────────────────────────────────────────
    pub title: String,
    pub question: String,
    #[serde(default)]
    pub description: String,

    // ── Underlying asset / condition ─────────────────────────────
    #[serde(default)]
    pub underlying_asset: String,
    #[serde(default)]
    pub strike_value: Option<f64>,

    // ── Oracle / Resolution ──────────────────────────────────────
    #[serde(default = "default_oracle")]
    pub resolution_oracle: ResolutionOracle,
    #[serde(default = "default_resolution_style")]
    pub resolution_style: ResolutionStyle,
    #[serde(default)]
    pub oracle_price_feed_id: String,

    // ── Timestamps ───────────────────────────────────────────────
    #[serde(default)]
    pub expiration_iso: String,
    #[serde(default)]
    pub created_at_iso: String,
    #[serde(default)]
    pub expiration_unix: i64,
    #[serde(default)]
    pub created_at_unix: i64,

    // ── Outcomes & Odds ──────────────────────────────────────────
    #[serde(default)]
    pub outcomes: Vec<Outcome>,
    #[serde(default)]
    pub yes_price: f64,
    #[serde(default)]
    pub no_price: f64,

    // ── Order Book ───────────────────────────────────────────────
    #[serde(default)]
    pub order_book: Option<OrderBook>,

    // ── Fees / Trading ───────────────────────────────────────────
    #[serde(default)]
    pub fee_rate_bps: i32,
    #[serde(default = "default_trading_status")]
    pub trading_status: TradingStatus,
    #[serde(default = "default_market_status")]
    pub market_status: MarketStatus,

    // ── Variant ──────────────────────────────────────────────────
    #[serde(default = "default_market_variant")]
    pub market_variant: MarketVariant,
    #[serde(default)]
    pub variant_data: Option<CryptoUpDownVariantData>,

    // ── Flags ────────────────────────────────────────────────────
    #[serde(default)]
    pub is_neg_risk: bool,
    #[serde(default)]
    pub is_yield_bearing: bool,
    #[serde(default = "default_true")]
    pub is_visible: bool,
}

// Default value helpers for serde
fn default_oracle() -> ResolutionOracle {
    ResolutionOracle::Custom
}
fn default_resolution_style() -> ResolutionStyle {
    ResolutionStyle::Expiry
}
fn default_trading_status() -> TradingStatus {
    TradingStatus::Open
}
fn default_market_status() -> MarketStatus {
    MarketStatus::Registered
}
fn default_market_variant() -> MarketVariant {
    MarketVariant::Default
}
fn default_true() -> bool {
    true
}

impl NormalizedMarket {
    /// Composite key used by the DashMap: `(Platform, MarketID)`.
    ///
    /// Guarantees that the same market from the same platform is
    /// never duplicated, even when N teammates ingest the same data.
    pub fn composite_key(&self) -> (Platform, String) {
        (self.platform, self.market_id.clone())
    }
}

// ── ZMQ Live-Odds Update ─────────────────────────────────────────

/// Lightweight odds update received over ZMQ from Python nodes.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OddsUpdate {
    pub platform: Platform,
    pub market_id: String,
    pub yes_price: f64,
    pub no_price: f64,
    #[serde(default)]
    pub order_book: Option<OrderBook>,
    #[serde(default)]
    pub timestamp_ms: i64,
}

// ── Arb Opportunity (output of the math engine) ──────────────────

/// Represents a detected cross-platform arbitrage opportunity.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArbOpportunity {
    /// Market on platform A
    pub market_a_platform: Platform,
    pub market_a_id: String,
    pub market_a_yes_price: f64,

    /// Market on platform B
    pub market_b_platform: Platform,
    pub market_b_id: String,
    pub market_b_yes_price: f64,

    /// Net delta after fees, gas, and slippage (basis points)
    pub net_delta_bps: f64,

    /// Estimated gas cost in BNB
    pub estimated_gas_bnb: f64,

    /// Estimated slippage (basis points)
    pub slippage_bps: f64,

    /// Whether this opportunity is profitable after all costs
    pub is_profitable: bool,

    /// Recommended trade size in USDT
    pub recommended_size_usdt: f64,
}
