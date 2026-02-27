// Engine/src/matcher.hpp
// ─────────────────────────────────────────────────────────────────
// The Math Engine — header.
// C++14 / GCC 6.3 / MinGW win32-threads compatible.
//
// Uses Win32 CRITICAL_SECTION instead of std::mutex (which is
// unavailable in MinGW.org builds with win32 threading model).
// ─────────────────────────────────────────────────────────────────

#pragma once

#include "types.hpp"

#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif

#include <unordered_map>
#include <vector>
#include <string>

namespace arb {

// ── Cross-platform mutex wrapper (C++14 / win32 threads) ─────────

class Mutex {
public:
    Mutex() {
#ifdef _WIN32
        InitializeCriticalSection(&cs_);
#else
        pthread_mutex_init(&mtx_, NULL);
#endif
    }
    ~Mutex() {
#ifdef _WIN32
        DeleteCriticalSection(&cs_);
#else
        pthread_mutex_destroy(&mtx_);
#endif
    }

    void lock() {
#ifdef _WIN32
        EnterCriticalSection(&cs_);
#else
        pthread_mutex_lock(&mtx_);
#endif
    }

    void unlock() {
#ifdef _WIN32
        LeaveCriticalSection(&cs_);
#else
        pthread_mutex_unlock(&mtx_);
#endif
    }

private:
    Mutex(const Mutex&);
    Mutex& operator=(const Mutex&);

#ifdef _WIN32
    CRITICAL_SECTION cs_;
#else
    pthread_mutex_t mtx_;
#endif
};

/// RAII lock guard.
class LockGuard {
public:
    explicit LockGuard(Mutex& m) : mtx_(m) { mtx_.lock(); }
    ~LockGuard() { mtx_.unlock(); }
private:
    Mutex& mtx_;
    LockGuard(const LockGuard&);
    LockGuard& operator=(const LockGuard&);
};

// ── Shared state type ────────────────────────────────────────────

typedef std::unordered_map<CompositeKey, NormalizedMarket, CompositeKeyHash> StateMap;

// ── Market Index — bucket similar markets for fast matching ──────
//
// BucketKey = hash of (lowercase(underlying_asset), oracle, expiration_bucket)
// where expiration_bucket = expiration_unix / 120  (2-minute windows).
//
// Only markets within the same bucket are cross-compared, reducing
// complexity from O(N×M) to O(B × k²) where k ≈ 2 per bucket.

struct BucketKey {
    std::string underlying_upper;   // uppercased underlying_asset
    int         oracle;             // ResolutionOracle as int
    int64_t     exp_bucket;         // expiration_unix / 120

    BucketKey() : oracle(0), exp_bucket(0) {}
    BucketKey(const std::string& u, int o, int64_t e)
        : underlying_upper(u), oracle(o), exp_bucket(e) {}

    bool operator==(const BucketKey& o2) const {
        return underlying_upper == o2.underlying_upper
            && oracle == o2.oracle
            && exp_bucket == o2.exp_bucket;
    }
};

struct BucketKeyHash {
    size_t operator()(const BucketKey& k) const {
        size_t h1 = std::hash<std::string>()(k.underlying_upper);
        size_t h2 = std::hash<int>()(k.oracle);
        size_t h3 = std::hash<int64_t>()(k.exp_bucket);
        return h1 ^ (h2 << 1) ^ (h3 << 2);
    }
};

typedef std::unordered_map<BucketKey, std::vector<CompositeKey>, BucketKeyHash> MarketIndex;

struct SharedState {
    mutable Mutex mtx;
    StateMap      map;
    MarketIndex   index;
};

// ── Index helpers ────────────────────────────────────────────────

/// Compute the bucket key for a given market.
BucketKey make_bucket_key(const NormalizedMarket& m);

/// Rebuild the entire index from the current state map (call after bulk load).
void rebuild_index(SharedState& state);

/// Insert/update a single market in the index.
void index_insert(SharedState& state, const CompositeKey& ck, const NormalizedMarket& m);

// ── Runtime config ───────────────────────────────────────────────

struct MatcherConfig {
    double min_delta_bps;
    double max_trade_usdt;
    double gas_multiplier;
    double slippage_tolerance_bps;

    MatcherConfig()
        : min_delta_bps(50.0)
        , max_trade_usdt(500.0)
        , gas_multiplier(1.1)
        , slippage_tolerance_bps(30.0)
    {}

    static MatcherConfig from_env();
};

// ── Functions ────────────────────────────────────────────────────

double estimate_gas_cost_usd(double gas_multiplier);
double estimate_gas_cost_bnb(double gas_multiplier);
double estimate_slippage_bps(const OrderBook& book, double trade_size_usdt, bool is_buy);
bool   markets_are_equivalent(const NormalizedMarket& a, const NormalizedMarket& b);
double gross_delta_bps(double yes_cheap, double yes_expensive);

double net_delta_bps(
    double yes_cheap, double yes_expensive,
    int fee_a_bps, int fee_b_bps,
    double gas_cost_bps, double slippage_a_bps, double slippage_b_bps
);

std::vector<ArbOpportunity> scan_for_arbs(SharedState& state, const MatcherConfig& cfg);
bool apply_odds_update(SharedState& state, const OddsUpdate& update);
void execute_arb_trade(const ArbOpportunity& opp);

} // namespace arb
