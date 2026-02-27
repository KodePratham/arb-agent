# Setup & Run Guide

> **What does this project do?**
>
> Imagine two shops sell lottery tickets for the same event (e.g. "Will BTC hit $100k?").
> Shop A sells a YES ticket for $0.40, Shop B sells a YES ticket for $0.60.
> That means Shop B's NO ticket costs $0.40 (because YES + NO = $1).
>
> You buy YES at Shop A ($0.40) and NO at Shop B ($0.40) = $0.80 total.
> No matter what happens, one ticket pays $1 → you profit $0.20.
>
> **This bot finds those price gaps automatically and trades them.**
>
> The two "shops" are **Predict.fun** and **Probable** — prediction market platforms on BNB Chain.

---

## Architecture — Two-Person Workflow

```
 TEAMMATE (ingestion)                          YOU (matching + execution)
 ───────────────────                           ─────────────────────────
 1. Run ingestion scripts                      3. git pull → get latest Data/markets/*.json
 2. git push (JSON committed to Data/markets/) 4. Build + run C++ engine → arbs.json
                                               5. python -m Execution.run_arb → on-chain trades
```

Your **teammate** runs `Ingestion/ingest_predictfun.py` and `Ingestion/ingest_probable.py`.
These fetch market data, normalise it with a local Ollama LLM, and save JSON files to
`Data/markets/`. The JSONs are committed and pushed to Git.

**You** pull the latest data, run the C++ engine to find arbitrage opportunities
(written to `arbs.json`), and then optionally execute trades on opBNB using
`Execution/run_arb.py`.

---

## What You Need Installed

| Tool | Check Command | Purpose |
|---|---|---|
| **Python** | `python --version` | 3.10+ |
| **Node.js** | `node --version` | 22.x (for Hardhat / contracts) |
| **npm** | `npm --version` | 11.x |
| **CMake** | `cmake --version` | 4.2+ |
| **GCC (MinGW)** | `gcc --version` | 6.3+ (C++ engine) |
| **Ollama** | `ollama --version` | Local LLM for ingestion |

### Installing Ollama

```powershell
# Download from https://ollama.com/download
# Or via winget:
winget install Ollama.Ollama

# Pull a model (ingestion will also prompt you to pick one):
ollama pull llama3
```

---

## Step 0 — Environment Setup

Open `.env` in the project root. Key settings:

```dotenv
# LLM — Ollama is the default (runs locally, no API key needed)
LLM_PROVIDER=ollama
MODEL=                    # leave blank to get an interactive picker at startup

# Predict.fun API key (needed for ingestion)
PREDICTFUN_API_KEY=your_api_key_here

# Wallet (only needed if you want to execute real trades)
PRIVATE_KEY=0xYOUR_PRIVATE_KEY_HERE
ARB_EXECUTOR_ADDRESS=0xYOUR_DEPLOYED_CONTRACT
```

See [docs/API_KEYS.md](docs/API_KEYS.md) for details on every key.

---

## Step 1 — Install Python Dependencies

```powershell
cd D:\Hackathons\arb-agent
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Step 2 — Build the C++ Engine

```powershell
cd Engine
mkdir build -ErrorAction SilentlyContinue
cd build
cmake .. -G "MinGW Makefiles"
cmake --build .
cd ..\..
```

✅ Done when `Engine\build\arb-engine.exe` exists.

Without ZeroMQ installed the engine compiles with `ARB_NO_ZMQ` — it still loads snapshots
and scans for arbs, just without live price updates. See [docs/BUILD_ENGINE.md](docs/BUILD_ENGINE.md)
for ZMQ setup.

---

## Step 3 — Install Smart Contract Dependencies

```powershell
cd Contracts
npm install
cd ..
```

---

## How to Run — Ingestion (your teammate)

Your teammate runs these from the project root with the venv activated:

### Fetch & save market snapshots

```powershell
# Predict.fun — fetches markets, saves to Data/markets/
python -m Ingestion.ingest_predictfun

# Probable — same
python -m Ingestion.ingest_probable
```

Each run creates a timestamped file like `Data/markets/predictfun_20260301_143000.json`
plus a sidecar `_meta.json` with ingestion metadata.

**CLI options:**

| Flag | Description |
|---|---|
| `--model llama3` | Override the Ollama model (skips interactive picker) |
| `--live` | After snapshot, keep running and stream live odds via ZMQ |

Then commit and push:

```powershell
git add Data/markets/
git commit -m "ingest: snapshot 2026-03-01"
git push
```

---

## How to Run — Engine + Execution (you)

### 1. Pull latest data

```powershell
git pull
```

### 2. Run the C++ engine

```powershell
cd Engine\build
.\arb-engine.exe --output arbs.json
```

The engine:
1. Loads all `Data/markets/*.json` files (skips `*_meta.json`)
2. Indexes similar markets into buckets by (asset, oracle, expiration)
3. Scans within each bucket for cross-platform price gaps
4. Writes profitable opportunities to `arbs.json`

If `--live` mode ingestion nodes are running, the engine also listens on ZMQ for real-time
price updates and re-scans every second.

### 3. Review & execute arbs

```powershell
cd D:\Hackathons\arb-agent
& .\.venv\Scripts\Activate.ps1

# Dry-run — print opportunities without touching the chain
python -m Execution.run_arb --arbs Engine\build\arbs.json

# Live — submit transactions on opBNB (requires PRIVATE_KEY in .env)
python -m Execution.run_arb --arbs Engine\build\arbs.json --execute
```

---

## Quick Test (No API Keys Needed)

Create a fake market file to verify the engine works:

```powershell
New-Item -ItemType Directory -Force -Path Data\markets

@'
[
  {
    "platform": "PREDICTFUN",
    "market_id": "test-001",
    "question": "Will BTC hit 100k?",
    "underlying_asset": "BTC",
    "outcomes": [
      {"name": "Yes", "indexSet": 1, "onChainId": "0xabc"},
      {"name": "No",  "indexSet": 2, "onChainId": "0xdef"}
    ],
    "yes_price": 0.45,
    "no_price": 0.55,
    "market_variant": "CRYPTO_UP_DOWN",
    "trading_status": "OPEN",
    "market_status": "REGISTERED",
    "resolution_oracle": "PYTH",
    "resolution_style": "EXPIRY",
    "platform_fee_bps": 200,
    "expiration_utc": "2026-03-15T00:00:00Z",
    "expiration_unix": 1773763200,
    "volume_usdt_24h": 50000.0,
    "order_book": {"bids": [], "asks": []}
  },
  {
    "platform": "PROBABLE",
    "market_id": "test-002",
    "question": "Will BTC hit 100k?",
    "underlying_asset": "BTC",
    "outcomes": [
      {"name": "Yes", "indexSet": 1, "onChainId": "0x123"},
      {"name": "No",  "indexSet": 2, "onChainId": "0x456"}
    ],
    "yes_price": 0.55,
    "no_price": 0.45,
    "market_variant": "CRYPTO_UP_DOWN",
    "trading_status": "OPEN",
    "market_status": "REGISTERED",
    "resolution_oracle": "PYTH",
    "resolution_style": "EXPIRY",
    "platform_fee_bps": 0,
    "expiration_utc": "2026-03-15T00:00:00Z",
    "expiration_unix": 1773763200,
    "volume_usdt_24h": 30000.0,
    "order_book": {"bids": [], "asks": []}
  }
]
'@ | Out-File -Encoding utf8 Data\markets\test_snapshot.json
```

Run the engine:

```powershell
cd Engine\build
.\arb-engine.exe --output arbs.json
```

You should see it load 2 markets, bucket them together, and detect the 1000 bps arb.

Then review:

```powershell
cd D:\Hackathons\arb-agent
python -m Execution.run_arb --arbs Engine\build\arbs.json
```

---

## Deploying the Smart Contract (Advanced)

```powershell
cd Contracts
npx hardhat compile
npx hardhat run scripts/deploy.js --network opbnb
```

Copy the printed contract address into `.env`:
```dotenv
ARB_EXECUTOR_ADDRESS=0xYourNewContractAddressHere
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `cmake` can't find `CMakeLists.txt` | `cd Engine\build` first, then `cmake ..` |
| Engine says "No JSON files found" | Run ingestion first, or `git pull` for teammate's data, or use the Quick Test above |
| `ollama` not found | Install from [ollama.com/download](https://ollama.com/download) |
| `ollama.list()` returns empty | Pull a model first: `ollama pull llama3` |
| `pip install` fails | Activate venv: `& .\.venv\Scripts\Activate.ps1` |
| Execution says "PRIVATE_KEY not set" | Fill it in `.env` — only needed for real on-chain trades |

For more: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
