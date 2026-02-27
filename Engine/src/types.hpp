// Engine/src/types.hpp
// ─────────────────────────────────────────────────────────────────
// C++14-compatible structs mapping 1:1 with Data/schemas.py.
// No std::optional, std::filesystem, or designated initializers.
// ─────────────────────────────────────────────────────────────────

#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <functional>
#include <stdexcept>
#include <algorithm>
#include <cctype>

#include <nlohmann/json.hpp>

namespace arb {

// ── Simple Optional<T> (C++14 polyfill) ─────────────────────────

template <typename T>
struct Optional {
    bool  has;
    T     val;

    Optional()           : has(false), val()  {}
    Optional(const T& v) : has(true),  val(v) {}

    bool        has_value() const { return has; }
    const T&    value()     const { return val; }
    T&          value()           { return val; }
    const T&    value_or(const T& d) const { return has ? val : d; }

    static Optional none() { return Optional(); }
};

// ── Enums ────────────────────────────────────────────────────────

enum Platform { PLATFORM_PREDICTFUN = 0, PLATFORM_PROBABLE = 1 };

inline std::string platform_to_string(Platform p) {
    switch (p) {
        case PLATFORM_PREDICTFUN: return "PREDICTFUN";
        case PLATFORM_PROBABLE:   return "PROBABLE";
    }
    return "UNKNOWN";
}

inline Platform platform_from_string(const std::string& s) {
    if (s == "PREDICTFUN") return PLATFORM_PREDICTFUN;
    if (s == "PROBABLE")   return PLATFORM_PROBABLE;
    throw std::runtime_error("Unknown platform: " + s);
}

enum ResolutionOracle { ORACLE_PYTH = 0, ORACLE_CHAINLINK, ORACLE_UMA, ORACLE_CUSTOM };

inline std::string oracle_to_string(ResolutionOracle o) {
    switch (o) {
        case ORACLE_PYTH:      return "PYTH";
        case ORACLE_CHAINLINK: return "CHAINLINK";
        case ORACLE_UMA:       return "UMA";
        case ORACLE_CUSTOM:    return "CUSTOM";
    }
    return "CUSTOM";
}

inline ResolutionOracle oracle_from_string(const std::string& s) {
    if (s == "PYTH")      return ORACLE_PYTH;
    if (s == "CHAINLINK") return ORACLE_CHAINLINK;
    if (s == "UMA")       return ORACLE_UMA;
    return ORACLE_CUSTOM;
}

enum ResolutionStyle { STYLE_TOUCH = 0, STYLE_EXPIRY };

inline ResolutionStyle resolution_style_from_string(const std::string& s) {
    if (s == "TOUCH") return STYLE_TOUCH;
    return STYLE_EXPIRY;
}

enum MarketVariant {
    VARIANT_DEFAULT = 0, VARIANT_SPORTS_MATCH, VARIANT_CRYPTO_UP_DOWN,
    VARIANT_TWEET_COUNT, VARIANT_SPORTS_TEAM_MATCH
};

inline MarketVariant market_variant_from_string(const std::string& s) {
    if (s == "SPORTS_MATCH")      return VARIANT_SPORTS_MATCH;
    if (s == "CRYPTO_UP_DOWN")    return VARIANT_CRYPTO_UP_DOWN;
    if (s == "TWEET_COUNT")       return VARIANT_TWEET_COUNT;
    if (s == "SPORTS_TEAM_MATCH") return VARIANT_SPORTS_TEAM_MATCH;
    return VARIANT_DEFAULT;
}

enum TradingStatus { TS_OPEN = 0, TS_MATCHING_NOT_ENABLED, TS_CANCEL_ONLY, TS_CLOSED };

inline TradingStatus trading_status_from_string(const std::string& s) {
    if (s == "MATCHING_NOT_ENABLED") return TS_MATCHING_NOT_ENABLED;
    if (s == "CANCEL_ONLY")          return TS_CANCEL_ONLY;
    if (s == "CLOSED")               return TS_CLOSED;
    return TS_OPEN;
}

enum MarketStatus {
    MS_REGISTERED = 0, MS_PRICE_PROPOSED, MS_PRICE_DISPUTED,
    MS_PAUSED, MS_UNPAUSED, MS_RESOLVED, MS_REMOVED
};

inline MarketStatus market_status_from_string(const std::string& s) {
    if (s == "PRICE_PROPOSED") return MS_PRICE_PROPOSED;
    if (s == "PRICE_DISPUTED") return MS_PRICE_DISPUTED;
    if (s == "PAUSED")         return MS_PAUSED;
    if (s == "UNPAUSED")       return MS_UNPAUSED;
    if (s == "RESOLVED")       return MS_RESOLVED;
    if (s == "REMOVED")        return MS_REMOVED;
    return MS_REGISTERED;
}

// ── Sub-structs ──────────────────────────────────────────────────

struct Outcome {
    std::string name;
    int64_t     index_set;
    std::string on_chain_id;

    Outcome() : index_set(0) {}
};

struct CryptoUpDownVariantData {
    double               start_price;
    Optional<double>     end_price;
    std::string          price_feed_id;

    CryptoUpDownVariantData() : start_price(0.0) {}
};

struct OrderBookLevel {
    double price;
    double size;

    OrderBookLevel() : price(0.0), size(0.0) {}
    OrderBookLevel(double p, double s) : price(p), size(s) {}
};

struct OrderBook {
    std::vector<OrderBookLevel> bids;
    std::vector<OrderBookLevel> asks;
    int64_t update_timestamp_ms;

    OrderBook() : update_timestamp_ms(0) {}
};

// ── Core Market ──────────────────────────────────────────────────

struct NormalizedMarket {
    Platform    platform;
    std::string market_id;
    std::string condition_id;

    std::string title;
    std::string question;
    std::string description;

    std::string          underlying_asset;
    Optional<double>     strike_value;

    ResolutionOracle resolution_oracle;
    ResolutionStyle  resolution_style;
    std::string      oracle_price_feed_id;

    std::string expiration_iso;
    std::string created_at_iso;
    int64_t     expiration_unix;
    int64_t     created_at_unix;

    std::vector<Outcome> outcomes;
    double yes_price;
    double no_price;

    Optional<OrderBook> order_book;

    int32_t       fee_rate_bps;
    TradingStatus trading_status;
    MarketStatus  market_status;

    MarketVariant                        market_variant;
    Optional<CryptoUpDownVariantData>    variant_data;

    bool is_neg_risk;
    bool is_yield_bearing;
    bool is_visible;

    NormalizedMarket()
        : platform(PLATFORM_PREDICTFUN)
        , resolution_oracle(ORACLE_CUSTOM)
        , resolution_style(STYLE_EXPIRY)
        , expiration_unix(0)
        , created_at_unix(0)
        , yes_price(0.0)
        , no_price(0.0)
        , fee_rate_bps(0)
        , trading_status(TS_OPEN)
        , market_status(MS_REGISTERED)
        , market_variant(VARIANT_DEFAULT)
        , is_neg_risk(false)
        , is_yield_bearing(false)
        , is_visible(true)
    {}

    std::string composite_key() const {
        return platform_to_string(platform) + "::" + market_id;
    }
};

// ── ZMQ Live-Odds Update ─────────────────────────────────────────

struct OddsUpdate {
    Platform    platform;
    std::string market_id;
    double      yes_price;
    double      no_price;
    Optional<OrderBook> order_book;
    int64_t     timestamp_ms;

    OddsUpdate()
        : platform(PLATFORM_PREDICTFUN)
        , yes_price(0.0)
        , no_price(0.0)
        , timestamp_ms(0)
    {}
};

// ── Arb Opportunity (output of the math engine) ──────────────────

struct ArbOpportunity {
    Platform    market_a_platform;
    std::string market_a_id;
    double      market_a_yes_price;

    Platform    market_b_platform;
    std::string market_b_id;
    double      market_b_yes_price;

    double net_delta_bps;
    double estimated_gas_bnb;
    double slippage_bps;
    bool   is_profitable;
    double recommended_size_usdt;

    ArbOpportunity()
        : market_a_platform(PLATFORM_PREDICTFUN)
        , market_a_yes_price(0.0)
        , market_b_platform(PLATFORM_PROBABLE)
        , market_b_yes_price(0.0)
        , net_delta_bps(0.0)
        , estimated_gas_bnb(0.0)
        , slippage_bps(0.0)
        , is_profitable(false)
        , recommended_size_usdt(0.0)
    {}
};

// ── Composite key for unordered_map ──────────────────────────────

struct CompositeKey {
    Platform    platform;
    std::string market_id;

    CompositeKey() : platform(PLATFORM_PREDICTFUN) {}
    CompositeKey(Platform p, const std::string& id)
        : platform(p), market_id(id) {}

    bool operator==(const CompositeKey& o) const {
        return platform == o.platform && market_id == o.market_id;
    }
};

struct CompositeKeyHash {
    size_t operator()(const CompositeKey& k) const {
        size_t h1 = std::hash<int>()(static_cast<int>(k.platform));
        size_t h2 = std::hash<std::string>()(k.market_id);
        return h1 ^ (h2 << 1);
    }
};

// ── JSON helpers ─────────────────────────────────────────────────

inline std::string json_str(const nlohmann::json& j, const char* key,
                            const std::string& def = "") {
    if (j.count(key) && !j[key].is_null()) return j[key].get<std::string>();
    return def;
}

inline double json_dbl(const nlohmann::json& j, const char* key, double def = 0.0) {
    if (j.count(key) && !j[key].is_null()) return j[key].get<double>();
    return def;
}

inline int64_t json_i64(const nlohmann::json& j, const char* key, int64_t def = 0) {
    if (j.count(key) && !j[key].is_null()) return j[key].get<int64_t>();
    return def;
}

inline int32_t json_i32(const nlohmann::json& j, const char* key, int32_t def = 0) {
    if (j.count(key) && !j[key].is_null()) return j[key].get<int32_t>();
    return def;
}

inline bool json_bool(const nlohmann::json& j, const char* key, bool def = false) {
    if (j.count(key) && !j[key].is_null()) return j[key].get<bool>();
    return def;
}

// ── JSON (de)serialization ───────────────────────────────────────

inline void from_json(const nlohmann::json& j, Outcome& o) {
    o.name        = json_str(j, "name");
    o.index_set   = j.count("index_set") ? json_i64(j, "index_set") : json_i64(j, "indexSet");
    o.on_chain_id = j.count("on_chain_id") ? json_str(j, "on_chain_id") : json_str(j, "onChainId");
}

inline void from_json(const nlohmann::json& j, OrderBookLevel& l) {
    l.price = json_dbl(j, "price");
    l.size  = json_dbl(j, "size");
}

inline void from_json(const nlohmann::json& j, OrderBook& ob) {
    if (j.count("bids")) ob.bids = j["bids"].get<std::vector<OrderBookLevel> >();
    if (j.count("asks")) ob.asks = j["asks"].get<std::vector<OrderBookLevel> >();
    ob.update_timestamp_ms = j.count("update_timestamp_ms")
        ? json_i64(j, "update_timestamp_ms")
        : json_i64(j, "updateTimestampMs");
}

inline void from_json(const nlohmann::json& j, CryptoUpDownVariantData& v) {
    v.start_price   = j.count("start_price") ? json_dbl(j, "start_price") : json_dbl(j, "startPrice");
    v.price_feed_id = j.count("price_feed_id") ? json_str(j, "price_feed_id") : json_str(j, "priceFeedId");
    if (j.count("end_price") && !j["end_price"].is_null())
        v.end_price = j["end_price"].get<double>();
    else if (j.count("endPrice") && !j["endPrice"].is_null())
        v.end_price = j["endPrice"].get<double>();
}

inline void from_json(const nlohmann::json& j, NormalizedMarket& m) {
    m.platform     = platform_from_string(json_str(j, "platform", "PREDICTFUN"));
    m.market_id    = json_str(j, "market_id");
    m.condition_id = json_str(j, "condition_id");

    m.title       = json_str(j, "title");
    m.question    = json_str(j, "question");
    m.description = json_str(j, "description");

    m.underlying_asset     = json_str(j, "underlying_asset");
    if (j.count("strike_value") && !j["strike_value"].is_null())
        m.strike_value = j["strike_value"].get<double>();

    m.resolution_oracle    = oracle_from_string(json_str(j, "resolution_oracle", "CUSTOM"));
    m.resolution_style     = resolution_style_from_string(json_str(j, "resolution_style", "EXPIRY"));
    m.oracle_price_feed_id = json_str(j, "oracle_price_feed_id");

    m.expiration_iso  = json_str(j, "expiration_iso");
    m.created_at_iso  = json_str(j, "created_at_iso");
    m.expiration_unix = json_i64(j, "expiration_unix");
    m.created_at_unix = json_i64(j, "created_at_unix");

    if (j.count("outcomes"))
        m.outcomes = j["outcomes"].get<std::vector<Outcome> >();

    m.yes_price = json_dbl(j, "yes_price");
    m.no_price  = json_dbl(j, "no_price");

    if (j.count("order_book") && !j["order_book"].is_null()) {
        OrderBook ob;
        from_json(j["order_book"], ob);
        m.order_book = ob;
    }

    m.fee_rate_bps   = json_i32(j, "fee_rate_bps");
    m.trading_status = trading_status_from_string(json_str(j, "trading_status", "OPEN"));
    m.market_status  = market_status_from_string(json_str(j, "market_status", "REGISTERED"));
    m.market_variant = market_variant_from_string(json_str(j, "market_variant", "DEFAULT"));

    if (j.count("variant_data") && !j["variant_data"].is_null()) {
        CryptoUpDownVariantData vd;
        from_json(j["variant_data"], vd);
        m.variant_data = vd;
    }

    m.is_neg_risk      = json_bool(j, "is_neg_risk");
    m.is_yield_bearing = json_bool(j, "is_yield_bearing");
    m.is_visible       = json_bool(j, "is_visible", true);
}

inline void from_json(const nlohmann::json& j, OddsUpdate& u) {
    u.platform     = platform_from_string(json_str(j, "platform", "PREDICTFUN"));
    u.market_id    = json_str(j, "market_id");
    u.yes_price    = json_dbl(j, "yes_price");
    u.no_price     = json_dbl(j, "no_price");
    u.timestamp_ms = json_i64(j, "timestamp_ms");

    if (j.count("order_book") && !j["order_book"].is_null()) {
        OrderBook ob;
        from_json(j["order_book"], ob);
        u.order_book = ob;
    }
}

inline nlohmann::json to_json_obj(const ArbOpportunity& a) {
    nlohmann::json j;
    j["market_a_platform"]     = platform_to_string(a.market_a_platform);
    j["market_a_id"]           = a.market_a_id;
    j["market_a_yes_price"]    = a.market_a_yes_price;
    j["market_b_platform"]     = platform_to_string(a.market_b_platform);
    j["market_b_id"]           = a.market_b_id;
    j["market_b_yes_price"]    = a.market_b_yes_price;
    j["net_delta_bps"]         = a.net_delta_bps;
    j["estimated_gas_bnb"]     = a.estimated_gas_bnb;
    j["slippage_bps"]          = a.slippage_bps;
    j["is_profitable"]         = a.is_profitable;
    j["recommended_size_usdt"] = a.recommended_size_usdt;
    return j;
}

} // namespace arb
