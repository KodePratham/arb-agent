# Build Engine (C++)

## Dependencies

- CMake >= 3.5
- C++14 compiler (MinGW/GCC/MSVC)
- Optional: ZeroMQ (`libzmq` + `cppzmq`) for live ingestion updates

`nlohmann/json` and `spdlog` are resolved by CMake.

## Windows (MinGW)

```powershell
cd Engine
cmake -S . -B build -G "MinGW Makefiles"
cmake --build build
```

Binary:

- `Engine/build/arb-engine.exe`

## Windows (MSVC)

```powershell
cd Engine
cmake -S . -B build -G "Visual Studio 17 2022"
cmake --build build --config Release
```

## Linux/macOS

```bash
cd Engine
cmake -S . -B build
cmake --build build
```

Binary:

- `Engine/build/arb-engine`

## Run

```bash
# from repo root
./Engine/build/arb-engine --output Engine/build/arbs.json
# or on Windows
./Engine/build/arb-engine.exe --output Engine/build/arbs.json
```

## Notes

- Without ZeroMQ, build may define `ARB_NO_ZMQ`; snapshot matching still works.
- Runtime parameters are read from environment variables in `.env`.