# arb-agent

Open-source arbitrage infrastructure for prediction markets.

This repo combines resilient data ingestion, LLM-assisted normalization, and a low-latency C++ matcher to detect cross-platform pricing inefficiencies and route opportunities to execution.

## TL;DR

- **Problem:** real-world market APIs are inconsistent, under-documented, and prone to schema drift.
- **Approach:** normalize messy payloads into one canonical schema using local LLM parsing.
- **Core edge:** keep matching/scoring hot in C++ memory for speed.
- **Outcome:** a practical arbitrage pipeline from ingestion to execution.

## Why this matters

Prediction market arbitrage is not blocked by one hard algorithm — it is blocked by data quality.

Different platforms describe similar outcomes in different formats, with inconsistent field names, ambiguous market wording, and irregular metadata. This project is designed to survive that reality:

1. absorb heterogeneous payloads,
2. normalize semantics,
3. match equivalent outcomes quickly,
4. emit executable opportunities.

## Why we built the Demo Market

During the hackathon, external API coverage and stable parsing signals were limited. Instead of waiting for ideal upstream data, we built **`Demo-market/`** to validate the core mechanics end-to-end:

- AMM pricing behavior
- spread divergence and convergence
- arbitrage loop logic
- on-chain settlement flow

The demo lets judges and contributors test the engine ideas immediately while we continue hardening real-world ingestion quality.

## Architecture

```text
Predict.fun / Probable / Other Sources
                |
                v
        Ingestion Adapters (Python)
                |
                v
      LLM Parse + Canonical Normalize
                |
                v
      Data/schemas.py + snapshots (JSON)
                |
                v
      C++ Matching + Spread Scoring
                |
                v
         opportunities (arbs.json)
                |
                v
      Execution Runner / On-chain path
```

## Repository map

- `Ingestion/` — platform adapters and parser orchestration
- `Data/schemas.py` — canonical schema contracts
- `Data/markets/` — normalized snapshots consumed by engine
- `Engine/` — C++ matcher/scorer (`cmake` build)
- `Execution/` — dry-run/live execution entrypoint
- `Contracts/` — optional Solidity executor + deployment scripts
- `Demo-market/` — UX + on-chain simulation of market + arb behavior
- `docs/` — setup, API key, build, and troubleshooting guides

## Quick start

### 1) Prerequisites

- Python 3.11+
- CMake 3.5+
- C++ compiler (MSVC/MinGW/GCC/Clang)
- Ollama running locally (`http://localhost:11434`)
- Node.js 18+ (optional, contract/deploy paths)

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Configure environment

Create `.env` and set at minimum:

```dotenv
LLM_PROVIDER=ollama
MODEL=
OLLAMA_BASE_URL=http://localhost:11434
PREDICTFUN_API_KEY=your_key_here
```

### 4) Run ingestion

```bash
python -m Ingestion.ingest_predictfun
python -m Ingestion.ingest_probable
```

### 5) Build and run engine

```bash
cd Engine
cmake -S . -B build
cmake --build build
./build/arb-engine.exe --output arbs.json   # Windows
./build/arb-engine --output arbs.json       # Linux/macOS
```

### 6) Review or execute opportunities

```bash
python -m Execution.run_arb --arbs Engine/build/arbs.json
python -m Execution.run_arb --arbs Engine/build/arbs.json --execute
```

## Open-source goals

We want this to be a reference stack for market-neutral prediction market infra.

Near-term contribution areas:

- new source adapters and schema mappers
- stronger semantic market equivalence scoring
- risk model calibration and execution safeguards
- benchmarking datasets and reproducible evals

## Engineering principles

- **Schema first:** all downstream systems rely on a strict canonical contract.
- **Deterministic core:** scoring and matching remain deterministic and explainable.
- **Local-first parsing:** LLM parsing can run with local Ollama models.
- **Execution safety:** live mode is explicit and opt-in.

## Additional docs

- `SETUP_AND_RUN.md`
- `docs/BUILD_ENGINE.md`
- `docs/API_KEYS.md`
- `docs/TROUBLESHOOTING.md`
- `Demo-market/README.md`

## License

MIT — see `LICENSE`.
