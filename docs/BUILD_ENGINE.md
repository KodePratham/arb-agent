# Building the C++ Engine

The matching engine is written in C++14 and uses CMake as its build system. This guide covers installation and building on Windows and Linux.

---

## Dependencies

| Dependency | Purpose | Required? |
|---|---|---|
| **CMake** (≥ 3.5) | Build system | Yes |
| **GCC/MinGW** (≥ 6.3) or **MSVC** (≥ 2017) | C++14 compiler | Yes |
| **nlohmann/json** | JSON parsing | Auto-fetched by CMake |
| **spdlog** | Logging | Auto-fetched by CMake |
| **ZeroMQ** (`libzmq` + `cppzmq`) | IPC with Python ingestion nodes | Optional (compiles with stub if missing) |

> **nlohmann/json** and **spdlog** are downloaded automatically by CMake via `FetchContent`. You don't need to install them manually.

---

## Windows

### Option A — MinGW + CMake (recommended for this project)

#### 1. Install CMake

**Via winget (easiest):**
```powershell
winget install Kitware.CMake
```

**Via installer:**
1. Download from [cmake.org/download](https://cmake.org/download/) (Windows x64 Installer).
2. During install, select **"Add CMake to the system PATH"**.
3. Restart your terminal.

**Verify:**
```powershell
cmake --version
# cmake version 3.28.0 (or similar)
```

#### 2. Install MinGW (GCC)

If you already have GCC (`gcc --version` works), skip this.

**Via MSYS2 (recommended):**
1. Download MSYS2 from [msys2.org](https://www.msys2.org/).
2. Open MSYS2 UCRT64 terminal:
   ```bash
   pacman -Syu
   pacman -S mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-cmake
   ```
3. Add `C:\msys64\ucrt64\bin` to your system PATH.

**Via standalone MinGW:**
- Download from [winlibs.com](https://winlibs.com/) or [sourceforge](https://sourceforge.net/projects/mingw/).
- Add the `bin/` directory to PATH.

#### 3. Install ZeroMQ (optional)

**Via vcpkg:**
```powershell
git clone https://github.com/microsoft/vcpkg.git C:\vcpkg
C:\vcpkg\bootstrap-vcpkg.bat
C:\vcpkg\vcpkg install cppzmq:x64-windows
```

Then pass `-DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake` to CMake.

**Skip it:** If you don't install ZMQ, the engine will compile with `ARB_NO_ZMQ` defined — it will still load market snapshots and scan for arbs, just without live updates from the ingestion nodes.

#### 4. Build

```powershell
cd Engine
mkdir build
cd build

# MinGW:
cmake .. -G "MinGW Makefiles"
cmake --build .

# Or with vcpkg ZMQ:
cmake .. -G "MinGW Makefiles" -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake
cmake --build .
```

The output binary will be `arb-engine.exe` in the build directory.

### Option B — Visual Studio (MSVC)

```powershell
cd Engine
mkdir build
cd build
cmake .. -G "Visual Studio 17 2022"
cmake --build . --config Release
```

Binary: `Release\arb-engine.exe`

---

## Linux / macOS

### 1. Install dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install build-essential cmake libzmq3-dev
```

**Fedora:**
```bash
sudo dnf install gcc-c++ cmake zeromq-devel
```

**macOS (Homebrew):**
```bash
brew install cmake zeromq
```

### 2. Build

```bash
cd Engine
mkdir -p build && cd build
cmake ..
cmake --build .
```

Binary: `./arb-engine`

---

## Build Options

| CMake Flag | Effect |
|---|---|
| `-DCMAKE_BUILD_TYPE=Release` | Optimised build (recommended for production) |
| `-DCMAKE_BUILD_TYPE=Debug` | Debug symbols, no optimisation |
| `-DARB_NO_ZMQ=ON` | Force-disable ZMQ even if installed |

Example:
```bash
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build .
```

---

## Run

From the `Engine/build` directory (the engine uses relative path `..\Data\markets`):

```bash
cd Engine/build
./arb-engine --output arbs.json       # Linux/macOS
.\arb-engine.exe --output arbs.json   # Windows
```

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--output FILE` / `-o FILE` | `arbs.json` | Path to write discovered arb opportunities (consumed by `Execution/run_arb.py`) |

### Environment variables

The engine reads these from environment or `.env` in the working directory:

| Variable | Default | Description |
|---|---|---|
| `MIN_ARB_DELTA_BPS` | 50 | Minimum net spread (bps) to trigger a trade |
| `MAX_TRADE_SIZE_USDT` | 500 | Max USDT per trade |
| `GAS_PRICE_MULTIPLIER` | 1.1 | Gas price safety margin |
| `SLIPPAGE_TOLERANCE_BPS` | 30 | Maximum tolerated slippage |

---

## Common Build Errors

### `cmake` not recognized

CMake is not installed or not on your PATH. See installation steps above.

```
cmake : The term 'cmake' is not recognized as the name of a cmdlet...
```

**Fix:** Install CMake and restart your terminal.

### FetchContent download failures

If CMake can't download nlohmann/json or spdlog (firewall / no internet):

1. Download the headers manually:
   - [nlohmann/json v3.10.5](https://github.com/nlohmann/json/releases/tag/v3.10.5)  
   - [spdlog v1.9.2](https://github.com/gabime/spdlog/releases/tag/v1.9.2)
2. Place them under `Engine/third_party/` (the headers are already partially there).
3. Modify `CMakeLists.txt` to use `add_subdirectory()` instead of `FetchContent`.

### ZMQ not found warning

```
cppzmq not found. ZMQ features will use a stub.
```

This is OK — the engine will compile and run without live updates. Install ZMQ if you want the full pipeline (see above).

### MinGW `pthread` errors

MinGW builds with `win32` threading model don't have `pthreads`. The engine already handles this — it uses Win32 `CreateThread` + `CRITICAL_SECTION` instead of `std::thread` / `std::mutex` on Windows.

---

## About the Rust Engine

The Rust source files have been archived to `Engine/rust_archive/`. The C++ engine is the
active implementation. See `Engine/WHY_NOT_RUST.md` for background.
