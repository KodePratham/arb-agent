// Engine/src/matcher.cpp
// ─────────────────────────────────────────────────────────────────
// The Math Engine — implementation.
// C++14 / GCC 6.3 / MinGW win32-threads compatible.
//
// Market Index:  Similar markets are bucketed by
//   (underlying_asset, oracle, expiration_bucket)
// so scan_for_arbs() only cross-compares within each bucket.
// ─────────────────────────────────────────────────────────────────

#include "matcher.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdlib>

#include <spdlog/spdlog.h>

namespace arb {

// ── Constants ────────────────────────────────────────────────────

static const double    BASE_GAS_PRICE_GWEI  = 3.0;
static const uint64_t  GAS_UNITS_PER_TRADE  = 250000;
static const double    BNB_PRICE_USD        = 600.0;
static const int64_t   EXPIRATION_BUCKET_SEC = 120;  // 2-minute windows

// ── Helpers ──────────────────────────────────────────────────────

static double env_double(const char* name, double def) {
    const char* v = std::getenv(name);
    if (!v) return def;
    try { return std::stod(v); }
    catch (...) { return def; }
}

static std::string to_upper(std::string s) {
    for (size_t i = 0; i < s.size(); ++i)
        s[i] = static_cast<char>(std::toupper(static_cast<unsigned char>(s[i])));
    return s;
}

// ── MatcherConfig ────────────────────────────────────────────────

MatcherConfig MatcherConfig::from_env() {
    MatcherConfig cfg;
    cfg.min_delta_bps          = env_double("MIN_ARB_DELTA_BPS",       50.0);
    cfg.max_trade_usdt         = env_double("MAX_TRADE_SIZE_USDT",    500.0);
    cfg.gas_multiplier         = env_double("GAS_PRICE_MULTIPLIER",     1.1);
    cfg.slippage_tolerance_bps = env_double("SLIPPAGE_TOLERANCE_BPS",  30.0);
    return cfg;
}

// ── Gas estimation ───────────────────────────────────────────────

double estimate_gas_cost_usd(double gas_multiplier) {
    double gas_bnb = static_cast<double>(GAS_UNITS_PER_TRADE)
                     * BASE_GAS_PRICE_GWEI * 1e-9 * gas_multiplier;
    return gas_bnb * BNB_PRICE_USD;
}

double estimate_gas_cost_bnb(double gas_multiplier) {
    return static_cast<double>(GAS_UNITS_PER_TRADE)
           * BASE_GAS_PRICE_GWEI * 1e-9 * gas_multiplier;
}

// ── Slippage estimation ──────────────────────────────────────────

double estimate_slippage_bps(const OrderBook& book, double trade_size_usdt, bool is_buy) {
    const std::vector<OrderBookLevel>& levels = is_buy ? book.asks : book.bids;
    if (levels.empty()) return 0.0;

    double best_price = levels[0].price;
    if (best_price == 0.0) return 0.0;

    double remaining      = trade_size_usdt;
    double weighted_price  = 0.0;
    double filled          = 0.0;

    for (size_t i = 0; i < levels.size(); ++i) {
        double available = levels[i].price * levels[i].size;
        double fill      = std::min(remaining, available);
        weighted_price  += levels[i].price * fill;
        filled          += fill;
        remaining       -= fill;
        if (remaining <= 0.0) break;
    }

    if (filled == 0.0) return 0.0;

    double avg_price = weighted_price / filled;
    double impact    = std::abs(avg_price - best_price) / best_price;
    return impact * 10000.0;
}

// ── Market matching ──────────────────────────────────────────────

bool markets_are_equivalent(const NormalizedMarket& a, const NormalizedMarket& b) {
    if (a.platform == b.platform) return false;

    if (a.underlying_asset.empty() || b.underlying_asset.empty()) return false;
    if (to_upper(a.underlying_asset) != to_upper(b.underlying_asset)) return false;

    if (a.strike_value.has_value() && b.strike_value.has_value()) {
        double sa   = a.strike_value.value();
        double sb   = b.strike_value.value();
        double diff = std::abs(sa - sb);
        double avg  = (sa + sb) / 2.0;
        if (avg > 0.0 && diff / avg > 0.0001) return false;
    } else if (a.strike_value.has_value() != b.strike_value.has_value()) {
        return false;
    }

    if (a.resolution_oracle != b.resolution_oracle) return false;

    if (a.expiration_unix != 0 && b.expiration_unix != 0) {
        int64_t diff = a.expiration_unix - b.expiration_unix;
        if (diff < 0) diff = -diff;
        if (static_cast<uint64_t>(diff) > 60) return false;
    }

    return true;
}

// ── Delta calculation ────────────────────────────────────────────

double gross_delta_bps(double yes_cheap, double yes_expensive) {
    return (yes_expensive - yes_cheap) * 10000.0;
}

double net_delta_bps(
    double yes_cheap, double yes_expensive,
    int fee_a_bps, int fee_b_bps,
    double gas_cost_bps, double slippage_a_bps, double slippage_b_bps
) {
    double gross          = gross_delta_bps(yes_cheap, yes_expensive);
    double total_fees     = static_cast<double>(fee_a_bps + fee_b_bps);
    double total_slippage = slippage_a_bps + slippage_b_bps;
    return gross - total_fees - gas_cost_bps - total_slippage;
}

// ── Market Index functions ───────────────────────────────────────

BucketKey make_bucket_key(const NormalizedMarket& m) {
    std::string upper = to_upper(m.underlying_asset);
    int oracle_int = static_cast<int>(m.resolution_oracle);
    int64_t exp_bucket = (m.expiration_unix > 0)
        ? (m.expiration_unix / EXPIRATION_BUCKET_SEC)
        : 0;
    return BucketKey(upper, oracle_int, exp_bucket);
}

void rebuild_index(SharedState& state) {
    // Note: caller must hold state.mtx
    state.index.clear();
    for (StateMap::const_iterator it = state.map.begin(); it != state.map.end(); ++it) {
        const NormalizedMarket& m = it->second;
        if (m.underlying_asset.empty()) continue;  // can't index without underlying

        BucketKey bk = make_bucket_key(m);
        state.index[bk].push_back(it->first);
    }
    spdlog::info("MarketIndex rebuilt: {} buckets from {} markets",
                 state.index.size(), state.map.size());
}

void index_insert(SharedState& state, const CompositeKey& ck, const NormalizedMarket& m) {
    // Note: caller must hold state.mtx
    if (m.underlying_asset.empty()) return;

    BucketKey bk = make_bucket_key(m);
    std::vector<CompositeKey>& bucket = state.index[bk];

    // Avoid duplicate entries in the bucket
    for (size_t i = 0; i < bucket.size(); ++i) {
        if (bucket[i] == ck) return;
    }
    bucket.push_back(ck);
}

// ── Core scan (bucket-based) ─────────────────────────────────────

std::vector<ArbOpportunity> scan_for_arbs(SharedState& state, const MatcherConfig& cfg) {
    std::vector<ArbOpportunity> opportunities;

    // Snapshot buckets and market data under lock
    MarketIndex index_snapshot;
    StateMap    map_snapshot;
    {
        LockGuard lock(state.mtx);
        index_snapshot = state.index;
        map_snapshot   = state.map;
    }

    size_t buckets_checked = 0;
    size_t pairs_checked   = 0;

    for (MarketIndex::const_iterator bit = index_snapshot.begin();
         bit != index_snapshot.end(); ++bit) {

        const std::vector<CompositeKey>& bucket = bit->second;
        if (bucket.size() < 2) continue;  // need at least 2 markets to compare
        ++buckets_checked;

        // Cross-compare all pairs within this bucket
        for (size_t i = 0; i < bucket.size(); ++i) {
            StateMap::const_iterator it_a = map_snapshot.find(bucket[i]);
            if (it_a == map_snapshot.end()) continue;
            const NormalizedMarket& a = it_a->second;

            for (size_t j = i + 1; j < bucket.size(); ++j) {
                StateMap::const_iterator it_b = map_snapshot.find(bucket[j]);
                if (it_b == map_snapshot.end()) continue;
                const NormalizedMarket& b = it_b->second;

                ++pairs_checked;

                // Final equivalence guard (bucket is an approximate filter)
                if (!markets_are_equivalent(a, b)) continue;

                const NormalizedMarket* cheap     = (a.yes_price < b.yes_price) ? &a : &b;
                const NormalizedMarket* expensive = (a.yes_price < b.yes_price) ? &b : &a;

                double gas_usd = estimate_gas_cost_usd(cfg.gas_multiplier);
                double gas_bps = (cfg.max_trade_usdt > 0.0)
                                 ? (gas_usd / cfg.max_trade_usdt) * 10000.0
                                 : 0.0;

                double slip_a = cheap->order_book.has_value()
                    ? estimate_slippage_bps(cheap->order_book.value(), cfg.max_trade_usdt, true)
                    : 0.0;
                double slip_b = expensive->order_book.has_value()
                    ? estimate_slippage_bps(expensive->order_book.value(), cfg.max_trade_usdt, false)
                    : 0.0;

                double delta = net_delta_bps(
                    cheap->yes_price, expensive->yes_price,
                    cheap->fee_rate_bps, expensive->fee_rate_bps,
                    gas_bps, slip_a, slip_b
                );

                bool profitable = delta >= cfg.min_delta_bps;

                if (delta > 0.0) {
                    spdlog::info("ARB {} | {}/{} vs {}/{} | net d={:.1f} bps | profitable={}",
                        cheap->underlying_asset,
                        platform_to_string(cheap->platform), cheap->market_id,
                        platform_to_string(expensive->platform), expensive->market_id,
                        delta, profitable);
                }

                if (profitable) {
                    ArbOpportunity opp;
                    opp.market_a_platform     = cheap->platform;
                    opp.market_a_id           = cheap->market_id;
                    opp.market_a_yes_price    = cheap->yes_price;
                    opp.market_b_platform     = expensive->platform;
                    opp.market_b_id           = expensive->market_id;
                    opp.market_b_yes_price    = expensive->yes_price;
                    opp.net_delta_bps         = delta;
                    opp.estimated_gas_bnb     = estimate_gas_cost_bnb(cfg.gas_multiplier);
                    opp.slippage_bps          = slip_a + slip_b;
                    opp.is_profitable         = true;
                    opp.recommended_size_usdt = cfg.max_trade_usdt;
                    opportunities.push_back(opp);
                }
            }
        }
    }

    spdlog::info("Scan: {} buckets, {} pairs checked, {} arbs found",
                 buckets_checked, pairs_checked, opportunities.size());

    return opportunities;
}

// ── Apply live odds update ───────────────────────────────────────

bool apply_odds_update(SharedState& state, const OddsUpdate& update) {
    CompositeKey key(update.platform, update.market_id);

    LockGuard lock(state.mtx);
    StateMap::iterator it = state.map.find(key);
    if (it == state.map.end()) {
        spdlog::warn("Odds update for unknown market: {}::{}",
                     platform_to_string(update.platform), update.market_id);
        return false;
    }

    NormalizedMarket& market = it->second;
    market.yes_price = update.yes_price;
    market.no_price  = update.no_price;
    if (update.order_book.has_value())
        market.order_book = update.order_book;

    return true;
}

// ── Execute trade (stub) ─────────────────────────────────────────

void execute_arb_trade(const ArbOpportunity& opp) {
    spdlog::info(
        "EXECUTING ARB: {}/{} (YES@{:.4f}) vs {}/{} (YES@{:.4f}) "
        "| d={:.1f}bps | size=${:.0f}",
        platform_to_string(opp.market_a_platform), opp.market_a_id, opp.market_a_yes_price,
        platform_to_string(opp.market_b_platform), opp.market_b_id, opp.market_b_yes_price,
        opp.net_delta_bps, opp.recommended_size_usdt
    );

    // Execution is handled off-engine by Execution/run_arb.py
    // which reads arbs.json and calls the ArbExecutor contract.
    spdlog::info("Arb written to output file → use 'python -m Execution.run_arb' to execute");
}

} // namespace arb
