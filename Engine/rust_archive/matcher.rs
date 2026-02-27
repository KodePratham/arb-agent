// Engine/src/matcher.rs
// ─────────────────────────────────────────────────────────────────
// The Math Engine.
//
// Detects identical markets across Predict.fun and Probable by
// comparing underlying asset, condition, strike value, oracle,
// and expiration.  Calculates BNB mainnet gas, order-book
// slippage, and net delta before signalling a trade.
// ─────────────────────────────────────────────────────────────────

use crate::types::{
    ArbOpportunity, NormalizedMarket, OddsUpdate, OrderBook, Platform,
};
use dashmap::DashMap;
use rust_decimal::prelude::*;
use rust_decimal_macros::dec;
use std::sync::Arc;
use tracing::{debug, info, warn};

// ── Configuration constants ──────────────────────────────────────

/// Minimum profitable delta in basis points (from .env at runtime).
const DEFAULT_MIN_DELTA_BPS: f64 = 50.0;

/// Maximum single-trade size in USDT.
const DEFAULT_MAX_TRADE_USDT: f64 = 500.0;

/// Multiplier applied to the estimated gas price.
const DEFAULT_GAS_MULTIPLIER: f64 = 1.1;

/// Slippage tolerance in basis points.
const DEFAULT_SLIPPAGE_TOLERANCE_BPS: f64 = 30.0;

/// Average BNB Mainnet gas price in Gwei.
const BASE_GAS_PRICE_GWEI: f64 = 3.0;

/// Gas units for a typical CTF exchange interaction.
const GAS_UNITS_PER_TRADE: u64 = 250_000;

/// BNB price in USD (updated by an external feed in production).
const BNB_PRICE_USD: f64 = 600.0;

// ── Runtime config pulled from env ───────────────────────────────

pub struct MatcherConfig {
    pub min_delta_bps: f64,
    pub max_trade_usdt: f64,
    pub gas_multiplier: f64,
    pub slippage_tolerance_bps: f64,
}

impl Default for MatcherConfig {
    fn default() -> Self {
        Self {
            min_delta_bps: DEFAULT_MIN_DELTA_BPS,
            max_trade_usdt: DEFAULT_MAX_TRADE_USDT,
            gas_multiplier: DEFAULT_GAS_MULTIPLIER,
            slippage_tolerance_bps: DEFAULT_SLIPPAGE_TOLERANCE_BPS,
        }
    }
}

impl MatcherConfig {
    /// Build config from environment variables, falling back to defaults.
    pub fn from_env() -> Self {
        let min_delta = std::env::var("MIN_ARB_DELTA_BPS")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(DEFAULT_MIN_DELTA_BPS);

        let max_trade = std::env::var("MAX_TRADE_SIZE_USDT")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(DEFAULT_MAX_TRADE_USDT);

        let gas_mult = std::env::var("GAS_PRICE_MULTIPLIER")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(DEFAULT_GAS_MULTIPLIER);

        let slippage = std::env::var("SLIPPAGE_TOLERANCE_BPS")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(DEFAULT_SLIPPAGE_TOLERANCE_BPS);

        Self {
            min_delta_bps: min_delta,
            max_trade_usdt: max_trade,
            gas_multiplier: gas_mult,
            slippage_tolerance_bps: slippage,
        }
    }
}

// ── Gas Estimation ───────────────────────────────────────────────

/// Estimate the gas cost of executing a single trade on BNB Mainnet.
///
/// Returns the cost in USD.
pub fn estimate_gas_cost_usd(gas_multiplier: f64) -> f64 {
    // gas_cost_bnb = gas_units * gas_price_gwei * 1e-9 * multiplier
    let gas_cost_bnb =
        GAS_UNITS_PER_TRADE as f64 * BASE_GAS_PRICE_GWEI * 1e-9 * gas_multiplier;
    gas_cost_bnb * BNB_PRICE_USD
}

/// Same as above but returns cost in BNB.
pub fn estimate_gas_cost_bnb(gas_multiplier: f64) -> f64 {
    GAS_UNITS_PER_TRADE as f64 * BASE_GAS_PRICE_GWEI * 1e-9 * gas_multiplier
}

// ── Slippage Estimation ──────────────────────────────────────────

/// Estimate slippage in basis points from an order book for a given
/// trade size in USDT.
///
/// Walks the book from best price outward, accumulating fill until
/// the desired size is consumed, and returns the effective price
/// impact as basis points.
pub fn estimate_slippage_bps(book: &OrderBook, trade_size_usdt: f64, is_buy: bool) -> f64 {
    let levels = if is_buy { &book.asks } else { &book.bids };
    if levels.is_empty() {
        return 0.0;
    }

    let best_price = levels[0].price;
    if best_price == 0.0 {
        return 0.0;
    }

    let mut remaining = trade_size_usdt;
    let mut weighted_price = 0.0;
    let mut filled = 0.0;

    for level in levels {
        let available_usdt = level.price * level.size;
        let fill = remaining.min(available_usdt);
        weighted_price += level.price * fill;
        filled += fill;
        remaining -= fill;

        if remaining <= 0.0 {
            break;
        }
    }

    if filled == 0.0 {
        return 0.0;
    }

    let avg_price = weighted_price / filled;
    let impact = ((avg_price - best_price) / best_price).abs();
    impact * 10_000.0 // convert to basis points
}

// ── Market Matching ──────────────────────────────────────────────

/// Determine whether two markets from different platforms represent
/// the SAME underlying event and can be arbitraged.
///
/// Matches on:
///   1. Same underlying asset (case-insensitive)
///   2. Same (or very close) strike value
///   3. Same oracle type
///   4. Expiration within 60 seconds of each other
pub fn markets_are_equivalent(a: &NormalizedMarket, b: &NormalizedMarket) -> bool {
    // Must be from different platforms
    if a.platform == b.platform {
        return false;
    }

    // 1. Underlying asset must match
    if a.underlying_asset.is_empty() || b.underlying_asset.is_empty() {
        return false;
    }
    if a.underlying_asset.to_uppercase() != b.underlying_asset.to_uppercase() {
        return false;
    }

    // 2. Strike values must be within 0.01% of each other
    match (a.strike_value, b.strike_value) {
        (Some(sa), Some(sb)) => {
            let diff = (sa - sb).abs();
            let avg = (sa + sb) / 2.0;
            if avg > 0.0 && diff / avg > 0.0001 {
                return false;
            }
        }
        (None, None) => {} // both have no strike — OK for non-numeric markets
        _ => return false, // one has strike, other doesn't
    }

    // 3. Oracle must match
    if a.resolution_oracle != b.resolution_oracle {
        return false;
    }

    // 4. Expiration within 60s
    if a.expiration_unix != 0 && b.expiration_unix != 0 {
        if (a.expiration_unix - b.expiration_unix).unsigned_abs() > 60 {
            return false;
        }
    }

    true
}

// ── Delta Calculation ────────────────────────────────────────────

/// Calculate the gross arbitrage delta in basis points between two
/// binary markets.
///
/// For a delta-neutral arb on binary markets:
///   Buy YES on the cheap platform, buy NO on the expensive platform
///   (or equivalently sell YES on the expensive side).
///
///   gross_profit = 1.0 - (yes_cheap + no_expensive)
///   where no_expensive = 1.0 - yes_expensive
///
///   gross_profit = yes_expensive - yes_cheap
///   gross_delta_bps = gross_profit * 10_000
pub fn gross_delta_bps(yes_cheap: f64, yes_expensive: f64) -> f64 {
    (yes_expensive - yes_cheap) * 10_000.0
}

/// Calculate the NET delta after fees, gas, and slippage.
pub fn net_delta_bps(
    yes_cheap: f64,
    yes_expensive: f64,
    fee_a_bps: i32,
    fee_b_bps: i32,
    gas_cost_bps: f64,
    slippage_a_bps: f64,
    slippage_b_bps: f64,
) -> f64 {
    let gross = gross_delta_bps(yes_cheap, yes_expensive);
    let total_fees = fee_a_bps as f64 + fee_b_bps as f64;
    let total_slippage = slippage_a_bps + slippage_b_bps;
    gross - total_fees - gas_cost_bps - total_slippage
}

// ── The Core Scan ────────────────────────────────────────────────

/// Scan all markets in the DashMap to find cross-platform arb
/// opportunities.
///
/// Separates markets by platform, then does an O(N*M) comparison
/// across platforms to identify equivalent markets with a profitable
/// delta.
pub fn scan_for_arbs(
    state: &Arc<DashMap<(Platform, String), NormalizedMarket>>,
    config: &MatcherConfig,
) -> Vec<ArbOpportunity> {
    let mut opportunities: Vec<ArbOpportunity> = Vec::new();

    // Partition into per-platform vecs
    let mut predictfun_markets: Vec<NormalizedMarket> = Vec::new();
    let mut probable_markets: Vec<NormalizedMarket> = Vec::new();

    for entry in state.iter() {
        let m = entry.value();
        match m.platform {
            Platform::Predictfun => predictfun_markets.push(m.clone()),
            Platform::Probable => probable_markets.push(m.clone()),
        }
    }

    info!(
        "Scanning: {} Predict.fun × {} Probable markets",
        predictfun_markets.len(),
        probable_markets.len()
    );

    // Cross-compare
    for pf in &predictfun_markets {
        for pr in &probable_markets {
            if !markets_are_equivalent(pf, pr) {
                continue;
            }

            debug!(
                "Equivalent pair: PF:{} <-> PR:{}  ({})",
                pf.market_id, pr.market_id, pf.underlying_asset
            );

            // Determine the cheap/expensive side
            let (cheap, expensive) = if pf.yes_price < pr.yes_price {
                (pf, pr)
            } else {
                (pr, pf)
            };

            // Gas cost as basis points of trade size
            let gas_usd = estimate_gas_cost_usd(config.gas_multiplier);
            let gas_bps = if config.max_trade_usdt > 0.0 {
                (gas_usd / config.max_trade_usdt) * 10_000.0
            } else {
                0.0
            };

            // Slippage estimates
            let slippage_a = cheap
                .order_book
                .as_ref()
                .map(|ob| estimate_slippage_bps(ob, config.max_trade_usdt, true))
                .unwrap_or(0.0);

            let slippage_b = expensive
                .order_book
                .as_ref()
                .map(|ob| estimate_slippage_bps(ob, config.max_trade_usdt, false))
                .unwrap_or(0.0);

            let delta = net_delta_bps(
                cheap.yes_price,
                expensive.yes_price,
                cheap.fee_rate_bps,
                expensive.fee_rate_bps,
                gas_bps,
                slippage_a,
                slippage_b,
            );

            let is_profitable = delta >= config.min_delta_bps;

            if delta > 0.0 {
                info!(
                    "ARB {} | {}/{} vs {}/{} | net Δ={:.1} bps | profitable={}",
                    cheap.underlying_asset,
                    cheap.platform,
                    cheap.market_id,
                    expensive.platform,
                    expensive.market_id,
                    delta,
                    is_profitable
                );
            }

            if is_profitable {
                opportunities.push(ArbOpportunity {
                    market_a_platform: cheap.platform,
                    market_a_id: cheap.market_id.clone(),
                    market_a_yes_price: cheap.yes_price,
                    market_b_platform: expensive.platform,
                    market_b_id: expensive.market_id.clone(),
                    market_b_yes_price: expensive.yes_price,
                    net_delta_bps: delta,
                    estimated_gas_bnb: estimate_gas_cost_bnb(config.gas_multiplier),
                    slippage_bps: slippage_a + slippage_b,
                    is_profitable,
                    recommended_size_usdt: config.max_trade_usdt,
                });
            }
        }
    }

    opportunities
}

// ── Apply live odds update ───────────────────────────────────────

/// Apply an incoming ZMQ odds update to the shared state map.
///
/// Returns `true` if the market was found and updated.
pub fn apply_odds_update(
    state: &Arc<DashMap<(Platform, String), NormalizedMarket>>,
    update: &OddsUpdate,
) -> bool {
    let key = (update.platform, update.market_id.clone());
    if let Some(mut entry) = state.get_mut(&key) {
        let market = entry.value_mut();
        market.yes_price = update.yes_price;
        market.no_price = update.no_price;
        if let Some(ref ob) = update.order_book {
            market.order_book = Some(ob.clone());
        }
        true
    } else {
        warn!(
            "Odds update for unknown market: {}::{}",
            update.platform, update.market_id
        );
        false
    }
}

// ── Execute trade (stub) ─────────────────────────────────────────

/// Execute a delta-neutral arbitrage trade on BNB Mainnet.
///
/// **TODO**: Integrate with web3 transaction builder:
///   1. Build + sign TX for Buy YES on cheap platform
///   2. Build + sign TX for Buy NO on expensive platform
///   3. Submit both atomically (or via flashbots-style bundling)
pub async fn execute_arb_trade(opp: &ArbOpportunity) -> anyhow::Result<()> {
    info!(
        "🚀 EXECUTING ARB: {:?}/{} (YES@{:.4}) vs {:?}/{} (YES@{:.4}) | Δ={:.1}bps | size=${:.0}",
        opp.market_a_platform,
        opp.market_a_id,
        opp.market_a_yes_price,
        opp.market_b_platform,
        opp.market_b_id,
        opp.market_b_yes_price,
        opp.net_delta_bps,
        opp.recommended_size_usdt,
    );

    // ── Step 1: Build transaction for platform A (buy YES) ──────
    // let tx_a = build_ctf_buy_tx(
    //     platform: opp.market_a_platform,
    //     market_id: &opp.market_a_id,
    //     side: Side::Yes,
    //     amount_usdt: opp.recommended_size_usdt,
    // )?;

    // ── Step 2: Build transaction for platform B (buy NO) ───────
    // let tx_b = build_ctf_buy_tx(
    //     platform: opp.market_b_platform,
    //     market_id: &opp.market_b_id,
    //     side: Side::No,
    //     amount_usdt: opp.recommended_size_usdt,
    // )?;

    // ── Step 3: Submit ──────────────────────────────────────────
    // submit_bundle(vec![tx_a, tx_b]).await?;

    warn!("Trade execution is stubbed — integrate web3 TX builder");
    Ok(())
}

// ── Tests ────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gross_delta() {
        // Buy YES at 0.40, sell YES at 0.45 → 500 bps gross
        let d = gross_delta_bps(0.40, 0.45);
        assert!((d - 500.0).abs() < 0.01);
    }

    #[test]
    fn test_net_delta_with_fees() {
        let d = net_delta_bps(
            0.40,  // yes_cheap
            0.45,  // yes_expensive
            100,   // fee_a_bps (1%)
            100,   // fee_b_bps (1%)
            10.0,  // gas_cost_bps
            5.0,   // slippage_a
            5.0,   // slippage_b
        );
        // 500 - 200 - 10 - 10 = 280 bps
        assert!((d - 280.0).abs() < 0.01);
    }

    #[test]
    fn test_gas_estimation() {
        let cost = estimate_gas_cost_usd(1.0);
        // 250_000 * 3.0 * 1e-9 * 600 = 0.45 USD
        assert!((cost - 0.45).abs() < 0.01);
    }

    #[test]
    fn test_slippage_empty_book() {
        let book = OrderBook {
            bids: vec![],
            asks: vec![],
            update_timestamp_ms: 0,
        };
        assert_eq!(estimate_slippage_bps(&book, 100.0, true), 0.0);
    }

    #[test]
    fn test_market_equivalence() {
        let a = NormalizedMarket {
            platform: Platform::Predictfun,
            market_id: "1".into(),
            condition_id: String::new(),
            title: String::new(),
            question: String::new(),
            description: String::new(),
            underlying_asset: "BTC".into(),
            strike_value: Some(100_000.0),
            resolution_oracle: crate::types::ResolutionOracle::Pyth,
            resolution_style: crate::types::ResolutionStyle::Expiry,
            oracle_price_feed_id: String::new(),
            expiration_iso: String::new(),
            created_at_iso: String::new(),
            expiration_unix: 1700000000,
            created_at_unix: 0,
            outcomes: vec![],
            yes_price: 0.4,
            no_price: 0.6,
            order_book: None,
            fee_rate_bps: 100,
            trading_status: crate::types::TradingStatus::Open,
            market_status: crate::types::MarketStatus::Registered,
            market_variant: crate::types::MarketVariant::CryptoUpDown,
            variant_data: None,
            is_neg_risk: false,
            is_yield_bearing: false,
            is_visible: true,
        };

        let mut b = a.clone();
        b.platform = Platform::Probable;
        b.market_id = "99".into();
        b.yes_price = 0.45;
        b.no_price = 0.55;

        assert!(markets_are_equivalent(&a, &b));

        // Same platform → not equivalent
        b.platform = Platform::Predictfun;
        assert!(!markets_are_equivalent(&a, &b));
    }
}
