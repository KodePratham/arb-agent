// Minimal spdlog stub for syntax-checking without CMake.
// The real spdlog header is fetched by CMake's FetchContent.

#pragma once

#include <cstdio>
#include <string>

namespace spdlog {

enum class level { trace, debug, info, warn, err, critical, off };

inline void set_level(level) {}
inline void set_pattern(const std::string&) {}

// Variadic template info/warn/error/debug stubs
template<typename... Args> void trace(const char*, Args&&...)    {}
template<typename... Args> void debug(const char*, Args&&...)    {}
template<typename... Args> void info(const char*, Args&&...)     {}
template<typename... Args> void warn(const char*, Args&&...)     {}
template<typename... Args> void error(const char*, Args&&...)    {}
template<typename... Args> void critical(const char*, Args&&...) {}

} // namespace spdlog
