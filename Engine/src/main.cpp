// Engine/src/main.cpp
// ─────────────────────────────────────────────────────────────────
// Arb-Engine entry point.
// C++14 / GCC 6.3 / MinGW win32-threads compatible.
//
// Uses Win32 CreateThread + Sleep instead of std::thread.
// Uses Win32 FindFirstFile instead of std::filesystem.
// Uses volatile bool instead of std::atomic<bool>.
//
// Data path:  ../Data/markets   (JSON committed by ingestion teammate)
// Output:     arbs.json         (consumed by Execution/run_arb.py)
// ─────────────────────────────────────────────────────────────────

#include "types.hpp"
#include "matcher.hpp"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>
#include <spdlog/spdlog.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <dirent.h>
#include <unistd.h>
#endif

#ifndef ARB_NO_ZMQ
#include <zmq.hpp>
#endif

// ── Constants ────────────────────────────────────────────────────

static const char* MARKETS_DIR      = "..\\Data\\markets";
static const char* ZMQ_BIND_ADDR    = "tcp://0.0.0.0:5555";
static const int   SCAN_INTERVAL_MS = 1000;

// Default output path (overrideable via --output)
static std::string g_output_path = "arbs.json";

// ── Global state ─────────────────────────────────────────────────

static volatile bool g_running = true;

// ── Cross-platform helpers ────────────────────────────────────────

static void sleep_ms(int ms) {
#ifdef _WIN32
    Sleep(static_cast<DWORD>(ms));
#else
    usleep(ms * 1000);
#endif
}

static bool ends_with(const std::string& s, const std::string& suffix) {
    if (suffix.size() > s.size()) return false;
    return s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

// ── Directory listing (Win32 / POSIX) ────────────────────────────

static std::vector<std::string> list_json_files(const std::string& dir) {
    std::vector<std::string> files;

#ifdef _WIN32
    std::string pattern = dir + "\\*.json";
    WIN32_FIND_DATAA fd;
    HANDLE hFind = FindFirstFileA(pattern.c_str(), &fd);
    if (hFind == INVALID_HANDLE_VALUE) return files;
    do {
        if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) {
            std::string name(fd.cFileName);
            // Skip sidecar manifest files (*_meta.json)
            if (ends_with(name, "_meta.json")) continue;
            files.push_back(dir + "\\" + name);
        }
    } while (FindNextFileA(hFind, &fd));
    FindClose(hFind);
#else
    DIR* d = opendir(dir.c_str());
    if (!d) return files;
    struct dirent* entry;
    while ((entry = readdir(d)) != NULL) {
        std::string name(entry->d_name);
        if (ends_with(name, ".json") && !ends_with(name, "_meta.json")) {
            files.push_back(dir + "/" + name);
        }
    }
    closedir(d);
#endif

    return files;
}

// ── Bootstrap: load + deduplicate JSON files ─────────────────────

static size_t load_initial_markets(arb::SharedState& state) {
    std::vector<std::string> json_files = list_json_files(MARKETS_DIR);

    if (json_files.empty()) {
        spdlog::warn("No JSON files found in {}", MARKETS_DIR);
        return 0;
    }

    size_t total = 0;
    size_t dupes = 0;

    for (size_t f = 0; f < json_files.size(); ++f) {
        const std::string& filepath = json_files[f];
        spdlog::info("Loading {}", filepath);

        std::ifstream ifs(filepath);
        if (!ifs) {
            spdlog::error("Failed to open {}", filepath);
            continue;
        }

        nlohmann::json j;
        try {
            ifs >> j;
        } catch (const std::exception& ex) {
            spdlog::error("JSON parse error in {}: {}", filepath, ex.what());
            continue;
        }

        if (!j.is_array()) {
            spdlog::error("Expected JSON array in {}", filepath);
            continue;
        }

        arb::LockGuard lock(state.mtx);
        for (size_t i = 0; i < j.size(); ++i) {
            try {
                arb::NormalizedMarket m;
                arb::from_json(j[i], m);
                arb::CompositeKey key(m.platform, m.market_id);

                if (state.map.count(key)) ++dupes;

                state.map[key] = m;
                ++total;
            } catch (const std::exception& ex) {
                spdlog::error("Failed to deserialize market: {}", ex.what());
            }
        }
    }

    // Build bucket index for fast matching
    {
        arb::LockGuard lock(state.mtx);
        arb::rebuild_index(state);
    }

    spdlog::info("Loaded {} market records ({} deduped overwrites). "
                 "Unique markets in state: {}",
                 total, dupes, state.map.size());

    return total;
}

// ── Thread argument bundle ───────────────────────────────────────

struct ThreadArgs {
    arb::SharedState*  state;
    arb::MatcherConfig cfg;
};

// ── ZMQ subscriber thread ────────────────────────────────────────

#ifdef _WIN32
static DWORD WINAPI zmq_subscriber_thread_fn(LPVOID arg)
#else
static void* zmq_subscriber_thread_fn(void* arg)
#endif
{
    arb::SharedState& state = *static_cast<ThreadArgs*>(arg)->state;

#ifdef ARB_NO_ZMQ
    spdlog::warn("ZMQ disabled at compile time. Live odds updates will not be received.");
    while (g_running) {
        sleep_ms(1000);
    }
#else
    try {
        zmq::context_t ctx(1);
        zmq::socket_t sub(ctx, ZMQ_SUB);

        sub.setsockopt(ZMQ_SUBSCRIBE, "odds.", 5);
        sub.bind(ZMQ_BIND_ADDR);
        spdlog::info("ZMQ SUB bound on {}", ZMQ_BIND_ADDR);

        while (g_running) {
            zmq::pollitem_t items[] = { { static_cast<void*>(sub), 0, ZMQ_POLLIN, 0 } };
            zmq::poll(items, 1, 500);

            if (!(items[0].revents & ZMQ_POLLIN)) continue;

            zmq::message_t topic_msg, payload_msg;
            sub.recv(&topic_msg);
            sub.recv(&payload_msg);

            try {
                std::string payload_str(
                    static_cast<const char*>(payload_msg.data()),
                    payload_msg.size()
                );
                nlohmann::json j = nlohmann::json::parse(payload_str);
                arb::OddsUpdate update;
                arb::from_json(j, update);
                arb::apply_odds_update(state, update);
            } catch (const std::exception& ex) {
                spdlog::warn("Failed to parse OddsUpdate: {}", ex.what());
            }
        }
    } catch (const std::exception& ex) {
        spdlog::error("ZMQ subscriber crashed: {}", ex.what());
    }
#endif

#ifdef _WIN32
    return 0;
#else
    return NULL;
#endif
}

// ── Write arbs to JSON output ────────────────────────────────────

static void write_arbs_json(const std::vector<arb::ArbOpportunity>& opps) {
    if (g_output_path.empty()) return;

    nlohmann::json jarr = nlohmann::json::array();
    for (size_t i = 0; i < opps.size(); ++i) {
        const arb::ArbOpportunity& o = opps[i];
        nlohmann::json jo;
        jo["market_a_platform"]     = arb::platform_to_string(o.market_a_platform);
        jo["market_a_id"]           = o.market_a_id;
        jo["market_a_yes_price"]    = o.market_a_yes_price;
        jo["market_b_platform"]     = arb::platform_to_string(o.market_b_platform);
        jo["market_b_id"]           = o.market_b_id;
        jo["market_b_yes_price"]    = o.market_b_yes_price;
        jo["net_delta_bps"]         = o.net_delta_bps;
        jo["estimated_gas_bnb"]     = o.estimated_gas_bnb;
        jo["slippage_bps"]          = o.slippage_bps;
        jo["is_profitable"]         = o.is_profitable;
        jo["recommended_size_usdt"] = o.recommended_size_usdt;
        jarr.push_back(jo);
    }

    std::ofstream ofs(g_output_path);
    if (!ofs) {
        spdlog::error("Failed to open output file: {}", g_output_path);
        return;
    }
    ofs << jarr.dump(2) << std::endl;
    spdlog::info("Wrote {} arb opportunities to {}", opps.size(), g_output_path);
}

// ── Matcher scan loop thread ─────────────────────────────────────

#ifdef _WIN32
static DWORD WINAPI matcher_loop_thread_fn(LPVOID arg)
#else
static void* matcher_loop_thread_fn(void* arg)
#endif
{
    ThreadArgs* ta = static_cast<ThreadArgs*>(arg);
    arb::SharedState& state = *ta->state;
    arb::MatcherConfig cfg  = ta->cfg;

    while (g_running) {
        std::vector<arb::ArbOpportunity> opportunities = arb::scan_for_arbs(state, cfg);

        if (!opportunities.empty()) {
            spdlog::info("Found {} arbitrage opportunities", opportunities.size());
            write_arbs_json(opportunities);
        }

        for (size_t i = 0; i < opportunities.size(); ++i) {
            if (opportunities[i].is_profitable) {
                arb::execute_arb_trade(opportunities[i]);
            }
        }

        sleep_ms(SCAN_INTERVAL_MS);
    }

#ifdef _WIN32
    return 0;
#else
    return NULL;
#endif
}

// ── Main ─────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    // ── CLI args ─────────────────────────────────────────────────
    for (int i = 1; i < argc; ++i) {
        if ((std::strcmp(argv[i], "--output") == 0 || std::strcmp(argv[i], "-o") == 0)
            && i + 1 < argc) {
            g_output_path = argv[++i];
        }
    }

    // ── Logging ──────────────────────────────────────────────────
    spdlog::set_level(spdlog::level::info);
    spdlog::set_pattern("%Y-%m-%d %H:%M:%S.%e  [%l]  %v");

    spdlog::info("======================================================");
    spdlog::info("  Arb-Engine (C++)  --  BNB / opBNB Prediction-Market Arb");
    spdlog::info("======================================================");
    spdlog::info("Data dir:    {}", MARKETS_DIR);
    spdlog::info("Output file: {}", g_output_path);

    // ── Shared state ─────────────────────────────────────────────
    arb::SharedState state;

    // ── Step 1: Load initial market snapshots ────────────────────
    load_initial_markets(state);

    // ── Matcher config ───────────────────────────────────────────
    arb::MatcherConfig cfg = arb::MatcherConfig::from_env();
    spdlog::info("Matcher config: min_delta={}bps  max_trade=${}  "
                 "gas_mult={}  slippage_tol={}bps",
                 cfg.min_delta_bps, cfg.max_trade_usdt,
                 cfg.gas_multiplier, cfg.slippage_tolerance_bps);

    // ── Thread args ──────────────────────────────────────────────
    ThreadArgs args;
    args.state = &state;
    args.cfg   = cfg;

    // ── Step 2 + 3: Spawn threads ────────────────────────────────
#ifdef _WIN32
    HANDLE hZmq     = CreateThread(NULL, 0, zmq_subscriber_thread_fn, &args, 0, NULL);
    HANDLE hMatcher  = CreateThread(NULL, 0, matcher_loop_thread_fn,   &args, 0, NULL);

    if (!hZmq || !hMatcher) {
        spdlog::error("Failed to create threads");
        return 1;
    }

    {
        arb::LockGuard lock(state.mtx);
        spdlog::info("Engine running. {} unique markets in state. Listening on {}",
                     state.map.size(), ZMQ_BIND_ADDR);
    }

    // Wait for threads
    HANDLE handles[] = { hZmq, hMatcher };
    WaitForMultipleObjects(2, handles, TRUE, INFINITE);

    CloseHandle(hZmq);
    CloseHandle(hMatcher);
#else
    pthread_t t_zmq, t_matcher;
    pthread_create(&t_zmq,     NULL, zmq_subscriber_thread_fn, &args);
    pthread_create(&t_matcher,  NULL, matcher_loop_thread_fn,   &args);

    {
        arb::LockGuard lock(state.mtx);
        spdlog::info("Engine running. {} unique markets in state. Listening on {}",
                     state.map.size(), ZMQ_BIND_ADDR);
    }

    pthread_join(t_zmq,    NULL);
    pthread_join(t_matcher, NULL);
#endif

    return 0;
}
