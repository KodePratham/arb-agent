cmake_minimum_required(VERSION 3.5)
project(arb-engine VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ── Dependencies (fetched automatically) ──────────────────────────
include(FetchContent)

# nlohmann/json — header-only JSON library (v3.10.5 supports C++11/14)
FetchContent_Declare(
    json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG        v3.10.5
)
FetchContent_MakeAvailable(json)

# spdlog — fast logging (v1.9.x supports C++11)
FetchContent_Declare(
    spdlog
    GIT_REPOSITORY https://github.com/gabime/spdlog.git
    GIT_TAG        v1.9.2
)
FetchContent_MakeAvailable(spdlog)

# ── ZeroMQ (system install required: libzmq + cppzmq) ────────────
# Install:  vcpkg install cppzmq   or   apt install libzmq3-dev  
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
    pkg_check_modules(ZMQ IMPORTED_TARGET libzmq)
endif()

# Fallback: try find_package for vcpkg / manual installs
if(NOT ZMQ_FOUND)
    find_package(cppzmq QUIET)
    if(NOT cppzmq_FOUND)
        message(WARNING
            "cppzmq not found. ZMQ features will use a stub. "
            "Install via: vcpkg install cppzmq  OR  apt install libzmq3-dev"
        )
        add_compile_definitions(ARB_NO_ZMQ)
    endif()
endif()

# ── Sources ───────────────────────────────────────────────────────
add_executable(arb-engine
    src/main.cpp
    src/matcher.cpp
)

target_include_directories(arb-engine PRIVATE src)

target_link_libraries(arb-engine PRIVATE
    nlohmann_json::nlohmann_json
    spdlog::spdlog
)

# Link ZMQ if available
if(ZMQ_FOUND)
    target_link_libraries(arb-engine PRIVATE PkgConfig::ZMQ)
elseif(cppzmq_FOUND)
    target_link_libraries(arb-engine PRIVATE cppzmq)
endif()

# ── Platform-specific threading ───────────────────────────────────
if(UNIX)
    target_link_libraries(arb-engine PRIVATE pthread)
endif()

# ── MinGW: link ws2_32 for networking (Windows) ──────────────────
if(WIN32 AND MINGW)
    target_link_libraries(arb-engine PRIVATE ws2_32)
endif()
