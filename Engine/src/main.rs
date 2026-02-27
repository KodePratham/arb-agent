// Engine/src/main.rs
// ─────────────────────────────────────────────────────────────────
// Arb-Engine entry point.
//
// 1. Sweeps all JSON files in Data/markets_init/, deserializes
//    them, and deduplicates into a DashMap keyed by
//    (Platform, MarketID).
// 2. Binds a ZeroMQ SUB socket on tcp://0.0.0.0:5555 to receive
//    live odds updates from N distributed Python ingestion nodes.
// 3. Continuously scans for cross-platform arbitrage opportunities
//    and triggers the execution pipeline.
// ─────────────────────────────────────────────────────────────────

mod matcher;
mod types;

use anyhow::{Context, Result};
use dashmap::DashMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;
use tokio::time;
use tracing::{error, info, warn};
use tracing_subscriber::EnvFilter;
use zeromq::{Socket, SocketRecv, SubSocket};

use crate::matcher::{apply_odds_update, execute_arb_trade, scan_for_arbs, MatcherConfig};
use crate::types::{NormalizedMarket, OddsUpdate, Platform};

// ── Constants ────────────────────────────────────────────────────

/// Directory scanned for initial market JSON files produced by
/// Python ingestion nodes.
const MARKETS_INIT_DIR: &str = "../Data/markets_init";

/// ZeroMQ bind address — accepts connections from all LAN nodes.
const ZMQ_BIND_ADDR: &str = "tcp://0.0.0.0:5555";

/// How often the matcher scans for arbitrage (milliseconds).
const SCAN_INTERVAL_MS: u64 = 1_000;

// ── Bootstrap: load + deduplicate JSON files ─────────────────────

/// Read every `*.json` file in `Data/markets_init/` and insert the
/// markets into the shared DashMap.
///
/// Because multiple teammates may produce overlapping snapshots,
/// the DashMap composite key `(Platform, MarketID)` ensures strict
/// deduplication: later inserts simply overwrite older states.
fn load_initial_markets(
    state: &DashMap<(Platform, String), NormalizedMarket>,
) -> Result<usize> {
    let dir = PathBuf::from(MARKETS_INIT_DIR);
    if !dir.exists() {
        warn!("Markets directory does not exist: {}", dir.display());
        return Ok(0);
    }

    let pattern = dir.join("*.json");
    let pattern_str = pattern
        .to_str()
        .context("Non-UTF-8 path")?;

    let mut total = 0usize;
    let mut dupes = 0usize;

    for entry in glob::glob(pattern_str)? {
        let path = entry?;
        info!("Loading {}", path.display());

        let data = std::fs::read_to_string(&path)
            .with_context(|| format!("Reading {}", path.display()))?;

        // Each file is a JSON array of NormalizedMarket objects
        let markets: Vec<NormalizedMarket> = serde_json::from_str(&data)
            .with_context(|| format!("Parsing {}", path.display()))?;

        for m in markets {
            let key = m.composite_key();
            if state.contains_key(&key) {
                dupes += 1;
            }
            // Insert (or overwrite stale data)
            state.insert(key, m);
            total += 1;
        }
    }

    info!(
        "Loaded {} market records ({} deduped overwrites). Unique markets in state: {}",
        total,
        dupes,
        state.len()
    );

    Ok(total)
}

// ── ZMQ subscriber task ──────────────────────────────────────────

/// Long-running task that listens on the ZMQ SUB socket for live
/// `OddsUpdate` messages from all Python ingestion nodes.
async fn zmq_subscriber(
    state: Arc<DashMap<(Platform, String), NormalizedMarket>>,
) -> Result<()> {
    let mut sub = SubSocket::new();

    // Subscribe to all topics starting with "odds."
    sub.subscribe("odds.")
        .await
        .context("ZMQ subscribe failed")?;

    sub.bind(ZMQ_BIND_ADDR)
        .await
        .with_context(|| format!("ZMQ bind on {ZMQ_BIND_ADDR}"))?;

    info!("ZMQ SUB bound on {}", ZMQ_BIND_ADDR);

    loop {
        match sub.recv().await {
            Ok(msg) => {
                // Multi-part: [topic, payload]
                let frames: Vec<_> = msg.into_vecdeque().into_iter().collect();
                if frames.len() < 2 {
                    warn!("Malformed ZMQ message (expected 2 frames, got {})", frames.len());
                    continue;
                }

                let payload = &frames[1];
                match serde_json::from_slice::<OddsUpdate>(payload.as_ref()) {
                    Ok(update) => {
                        apply_odds_update(&state, &update);
                    }
                    Err(e) => {
                        warn!("Failed to parse OddsUpdate: {}", e);
                    }
                }
            }
            Err(e) => {
                error!("ZMQ recv error: {}", e);
                time::sleep(Duration::from_millis(100)).await;
            }
        }
    }
}

// ── Matcher scan loop ────────────────────────────────────────────

/// Periodically scans the shared state for arbitrage opportunities.
async fn matcher_loop(
    state: Arc<DashMap<(Platform, String), NormalizedMarket>>,
    config: MatcherConfig,
) {
    let mut interval = time::interval(Duration::from_millis(SCAN_INTERVAL_MS));

    loop {
        interval.tick().await;

        let opportunities = scan_for_arbs(&state, &config);

        if !opportunities.is_empty() {
            info!("Found {} arbitrage opportunities", opportunities.len());
        }

        for opp in &opportunities {
            if opp.is_profitable {
                if let Err(e) = execute_arb_trade(opp).await {
                    error!("Trade execution failed: {}", e);
                }
            }
        }
    }
}

// ── Main ─────────────────────────────────────────────────────────

#[tokio::main]
async fn main() -> Result<()> {
    // ── Logging ──────────────────────────────────────────────────
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    // ── Load .env ────────────────────────────────────────────────
    dotenvy::dotenv().ok();

    info!("══════════════════════════════════════════════════════");
    info!("  Arb-Engine  —  BNB Mainnet Prediction-Market Arb  ");
    info!("══════════════════════════════════════════════════════");

    // ── Shared state ─────────────────────────────────────────────
    let state: Arc<DashMap<(Platform, String), NormalizedMarket>> =
        Arc::new(DashMap::new());

    // ── Step 1: Load initial market snapshots ────────────────────
    load_initial_markets(&state)?;

    // ── Matcher config ───────────────────────────────────────────
    let config = MatcherConfig::from_env();
    info!(
        "Matcher config: min_delta={}bps  max_trade=${}  gas_mult={}  slippage_tol={}bps",
        config.min_delta_bps,
        config.max_trade_usdt,
        config.gas_multiplier,
        config.slippage_tolerance_bps
    );

    // ── Step 2: Spawn ZMQ subscriber ─────────────────────────────
    let zmq_state = Arc::clone(&state);
    let zmq_handle = tokio::spawn(async move {
        if let Err(e) = zmq_subscriber(zmq_state).await {
            error!("ZMQ subscriber crashed: {}", e);
        }
    });

    // ── Step 3: Spawn matcher loop ───────────────────────────────
    let match_state = Arc::clone(&state);
    let match_handle = tokio::spawn(matcher_loop(match_state, config));

    info!(
        "Engine running. {} unique markets in state. Listening on {}",
        state.len(),
        ZMQ_BIND_ADDR
    );

    // ── Wait for tasks (run forever) ─────────────────────────────
    tokio::select! {
        _ = zmq_handle => error!("ZMQ task exited unexpectedly"),
        _ = match_handle => error!("Matcher task exited unexpectedly"),
    }

    Ok(())
}
