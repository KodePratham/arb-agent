# arb-agent

Autonomous arbitrage infrastructure for prediction markets.

This repository ingests heterogeneous market data, normalizes it into a canonical schema, runs a low-latency C++ matching/scoring engine, and routes opportunities to a Python execution runner.

## Architecture

```text
                      +-----------------------------+
                      | Ingestion (Python)          |
                      | Probable / Opinion.trade    |
                      +-------------+---------------+
                                    |
                     LLM parse + canonical normalize
                                    |
                                    v
                      +-----------------------------+
                      | Data/markets/*.json         |
                      | Canonical snapshots         |
                      +-------------+---------------+
                                    |
                                    v
                      +-----------------------------+
                      | Engine (C++)                |
                      | Match + score spreads       |
                      | Emits arbs.json             |
                      +-------------+---------------+
                                    |
                                    v
                      +-----------------------------+
                      | Execution (Python)          |
                      | Dry-run / on-chain scaffold |
                      +-----------------------------+

                      +-----------------------------+
                      | Demo-market (Next.js + AMM) |
                      | End-to-end UI simulation    |
                      +-----------------------------+
```

## How It Works

1. Ingestion adapters fetch raw market payloads from external platforms.
2. Parsers normalize noisy schemas into the canonical types in `Data/schemas.py`.
3. The C++ engine loads all normalized snapshots into memory and detects cross-platform opportunities.
4. Opportunities are written to `arbs.json` with pricing/spread/size metadata.
5. The execution runner reads `arbs.json` and either:
   - prints a dry-run execution plan, or
   - submits transactions when `--execute` is enabled and execution inputs are configured.

## API Use-case

This repo exposes a single canonical data API surface (the normalized schema in `Data/schemas.py`) for multiple prediction markets.

- Source SDKs: `Ingestion/sdk/probable.py` and `Ingestion/sdk/opinion_trade.py`
- Unified output: `Data/markets/*.json` with one shared shape (`NormalizedMarket`)
- Consumer simplicity: downstream components (engine, execution, analytics) read one schema, not per-platform payload formats

## C++ Execution Engine

The execution core is in `Engine/` and is built with CMake.

### What the engine does

- Loads normalized markets from `Data/markets/*.json`.
- Deduplicates by platform + market id.
- Builds in-memory indexes for fast matching.
- Continuously scans for profitable cross-market opportunities.
- Writes ranked opportunities to JSON (`arbs.json`).

### Build

Windows (MinGW):

```powershell
cd Engine
cmake -S . -B build -G "MinGW Makefiles"
cmake --build build
```

Windows (MSVC):

```powershell
cd Engine
cmake -S . -B build -G "Visual Studio 17 2022"
cmake --build build --config Release
```

Linux/macOS:

```bash
cd Engine
cmake -S . -B build
cmake --build build
```

### Run

From repo root:

```powershell
.\Engine\build\arb-engine.exe --output Engine\build\arbs.json
```

or on Linux/macOS:

```bash
./Engine/build/arb-engine --output Engine/build/arbs.json
```

### Execution handoff

Run the Python executor against generated opportunities:

```powershell
python -m Execution.run_arb --arbs Engine\build\arbs.json
python -m Execution.run_arb --arbs Engine\build\arbs.json --execute
```

Note: live submission is scaffolded and requires exchange order construction + signing inputs.

## Demo Market

`Demo-market/` is an end-to-end demo environment to validate market mechanics and arbitrage behavior independently of external API instability.

### What it includes

- Next.js frontend dashboard (`Demo-market/src/app`).
- Solidity AMM contract (`Demo-market/contracts/BinaryPredictionAMM.sol`).
- Hardhat deploy flow (`Demo-market/scripts/deploy.js`).
- Admin resolution route (`Demo-market/src/app/api/admin/resolve/route.ts`).

### Demo capabilities

- Two binary markets shown side-by-side.
- Wallet connect + BSC testnet switching.
- Liquidity add/remove and YES/NO buy-sell flow.
- “Activate Chad” arbitrage action for spread scenarios.
- Admin market resolution and winner claiming.

### Run demo market

```powershell
cd Demo-market
npm install
npm run hardhat:compile
npm run hardhat:deploy:bsc
npm run dev
```

Then open `http://localhost:3067`.

## Repository Structure

```text
Ingestion/             Python source adapters + parser orchestration
Data/schemas.py        Canonical schema definitions
Data/markets/          Normalized market snapshots
Engine/                C++ matcher/scorer and output writer
Execution/             Python arb runner (dry-run + execute scaffold)
Contracts/             Solidity ArbExecutor + deployment scripts
Demo-market/           Next.js + Hardhat AMM demo app
docs/                  Build, API keys, troubleshooting guides
```

## Quick Start

```powershell
pip install -r requirements.txt
python -m Ingestion.ingest_probable
python -m Ingestion.ingest_opinion_trade
.\Engine\build\arb-engine.exe --output Engine\build\arbs.json
python -m Execution.run_arb --arbs Engine\build\arbs.json
```

For complete setup, see:

- `SETUP_AND_RUN.md`
- `docs/BUILD_ENGINE.md`
- `docs/API_KEYS.md`
- `docs/TROUBLESHOOTING.md`
- `Demo-market/README.md`

## License

MIT — see `LICENSE`.
