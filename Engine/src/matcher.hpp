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

struct SharedState {
    mutable Mutex mtx;
    StateMap      map;
};

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
