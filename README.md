# arb-agent

Ollama-first prediction-market arbitrage pipeline for Predict.fun and Probable.

The project is intentionally focused on one production path:

1. Ingest markets with Python (`Ingestion/`) using local Ollama parsing.
2. Normalize and persist snapshots to `Data/markets/`.
3. Load markets in RAM and match opportunities with the C++ engine (`Engine/`).
4. Review/execute opportunities through `Execution/run_arb.py`.

## Scope

- **LLM provider:** Ollama only
- **Matching engine:** C++14
- **Execution path:** `arbs.json` output from engine -> execution runner
- **No alternate ingestion stacks:** Groq and string-ingestion removed

## Repository Layout

- `Ingestion/` - Predict.fun + Probable ingestion scripts and shared parser
- `Data/schemas.py` - shared normalized data contracts
- `Data/markets/` - local snapshot storage (git keeps `.gitkeep` only)
- `Engine/` - C++ matcher, arb scoring, and output writer
- `Execution/` - execution runner for opportunities emitted by engine
- `Contracts/` - `ArbExecutor.sol` and Hardhat deployment tooling
- `docs/` - build/setup/troubleshooting references

## Quick Start

### 1) Prerequisites

- Python 3.11+
- CMake 3.5+
- C++ compiler (MinGW/GCC/MSVC)
- Ollama running locally (`http://localhost:11434`)
- Node.js 18+ (only if deploying contracts)

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Configure environment

```bash
cp .env.example .env
```

Required minimum values in `.env`:

```dotenv
LLM_PROVIDER=ollama
MODEL=
OLLAMA_BASE_URL=http://localhost:11434
PREDICTFUN_API_KEY=your_key_here
```

`MODEL` can be left empty to use the interactive Ollama model picker.

### 4) Ingest snapshots

```bash
python -m Ingestion.ingest_predictfun
python -m Ingestion.ingest_probable
```

Snapshots are written to `Data/markets/`.

### 5) Build and run matcher

```bash
cd Engine
cmake -S . -B build
cmake --build build

# Windows
./build/arb-engine.exe --output arbs.json

# Linux/macOS
./build/arb-engine --output arbs.json
```

The engine loads all snapshots in RAM and writes opportunities to `arbs.json`.

### 6) Execute opportunities

```bash
python -m Execution.run_arb --arbs Engine/build/arbs.json
```

Use `--execute` only after setting wallet + contract variables in `.env`.

## Command Reference

### Ingestion

```bash
python -m Ingestion.ingest_predictfun [--model llama3] [--max-markets 200] [--live]
python -m Ingestion.ingest_probable   [--model llama3] [--max-markets 200] [--live]
```

### Engine

```bash
# From Engine/build
./arb-engine[.exe] --output arbs.json
```

### Execution

```bash
python -m Execution.run_arb --arbs Engine/build/arbs.json
python -m Execution.run_arb --arbs Engine/build/arbs.json --execute
```

## Notes

- ZMQ is optional at compile time. Without it, the engine still runs in snapshot mode.
- This repository does not track generated snapshots or build outputs.
- Execution remains dry-run safe by default unless `--execute` is provided.

## Documentation

- `SETUP_AND_RUN.md` - end-to-end setup walkthrough
- `docs/BUILD_ENGINE.md` - platform-specific C++ build instructions
- `docs/API_KEYS.md` - environment variable and credential reference
- `docs/TROUBLESHOOTING.md` - common failures and fixes
