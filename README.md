# Arb-Agent

> Cross-platform prediction-market arbitrage bot on **opBNB / BNB Chain**.

Arb-Agent detects price discrepancies between [Predict.fun](https://predict.fun) and [Probable](https://probable.markets) prediction markets and executes atomic two-leg arbitrage trades via an on-chain smart contract.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        Ingestion Layer (Python)                  │
│                                                                  │
│   ingest_predictfun.py ──┐                                       │
│                          ├──► JSON snapshots ──► Data/markets/
│   ingest_probable.py  ───┘                                       │
│              │                                                   │
│              └──► Live odds polling + ZMQ PUB (topic: "odds.*")   │
└──────────────────────────┬───────────────────────────────────────┘
                           │  ZMQ (tcp://0.0.0.0:5555)
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Matching Engine (C++14)                         │
│                                                                  │
│   1. Loads initial market snapshots from Data/markets/           │
│   2. Subscribes to live odds updates via ZMQ SUB                 │
│   3. Scans for cross-platform arb opportunities every 1s         │
│   4. Writes opportunities to arbs.json (execution via Python)    │
└──────────────────────────┬───────────────────────────────────────┘
                           │  ZMQ
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│               Alert System (Python / Telegram)                   │
│                                                                  │
│   telegram_bot.py subscribes to "arb.*" topics and forwards      │
│   profitable opportunities to a Telegram chat / channel.         │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│              Smart Contract (Solidity / opBNB)                   │
│                                                                  │
│   ArbExecutor.sol — Atomically buys YES on the cheap platform    │
│   and NO on the expensive platform. Reverts if either leg fails. │
└──────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

| Path | Language | Purpose |
|---|---|---|
| `Ingestion/` | Python | Fetches & normalises markets from Predict.fun and Probable APIs; streams live odds over ZMQ |
| `Data/` | Python | Pydantic schemas (`NormalizedMarket`, `OddsUpdate`, etc.) shared across all Python code |
| `Data/markets/` | JSON | Persisted market snapshots consumed by the C++ engine at startup |
| `Engine/` | C++14 | High-frequency matching engine — loads markets, receives live odds, scans for arbs |
| `Contracts/` | Solidity | `ArbExecutor.sol` smart contract for atomic on-chain arb execution on opBNB |
| `Alert-system/` | Python | Telegram bot that relays arb alerts |

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| **Python** | 3.11+ | For ingestion nodes and Telegram bot |
| **GCC / MinGW** | 6.3+ | For building the C++ engine (C++14) |
| **CMake** | 3.5+ | Build system for the engine |
| **Node.js** | 18+ | For Hardhat / smart contract deployment |
| **ZeroMQ** (`libzmq`) | 4.x | IPC between ingestion → engine → alerts. Install via `vcpkg install cppzmq` (Windows) or `apt install libzmq3-dev` (Linux) |

### Optional

| Tool | Notes |
|---|---|
| **Ollama** | Run LLM locally for market text extraction (alternative to Groq cloud) |
| **Groq API key** | Cloud LLM for market text extraction |

---

## Setup

### 1. Clone & create `.env`

```bash
git clone <repo-url> arb-agent
cd arb-agent
cp .env.example .env   # or create manually — see below
```

Create a `.env` file in the project root with the following variables:

```dotenv
# ── LLM (pick one provider) ──────────────────────────────
LLM_PROVIDER=groq              # "groq" or "ollama"
MODEL=llama3-8b-8192           # model name
GROQ_API_KEY=gsk_...           # required if LLM_PROVIDER=groq
OLLAMA_BASE_URL=http://localhost:11434  # required if LLM_PROVIDER=ollama

# ── Platform APIs ─────────────────────────────────────────
PREDICTFUN_API_BASE=https://api.predict.fun
PREDICTFUN_API_KEY=             # optional
PREDICTFUN_WS_URL=wss://ws.predict.fun

PROBABLE_API_BASE=https://probable.markets
PROBABLE_API_KEY=               # optional (public read)
PROBABLE_WS_URL=wss://probable.markets/ws

# ── ZMQ ───────────────────────────────────────────────────
ZMQ_ENGINE_ADDR=tcp://0.0.0.0:5555

# ── Engine Tuning ─────────────────────────────────────────
MIN_ARB_DELTA_BPS=50           # minimum net spread (basis points) to trade
MAX_TRADE_SIZE_USDT=500        # max USDT per arb trade
GAS_PRICE_MULTIPLIER=1.1       # safety margin on gas estimate
SLIPPAGE_TOLERANCE_BPS=30      # max tolerated slippage

# ── Telegram Alerts ──────────────────────────────────────
TELEGRAM_BOT_TOKEN=            # from @BotFather
TELEGRAM_CHAT_ID=              # target chat / channel ID

# ── Smart Contract / opBNB ────────────────────────────────
PRIVATE_KEY=0x...              # deployer wallet private key
OPBNB_RPC_URL=https://opbnb-mainnet-rpc.bnbchain.org
BNB_RPC_URL=https://bsc-dataseed1.binance.org
OPBNB_USDT=0x9e5AAC1Ba1a2e6aEd6b32689DFcF62A509Ca96f3
ARB_EXECUTOR_CONTRACT=         # filled after deployment
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Build the C++ Engine

> **Don't have CMake?** See [docs/BUILD_ENGINE.md](docs/BUILD_ENGINE.md) for detailed installation instructions per platform.

```bash
cd Engine
mkdir build && cd build
cmake ..
cmake --build .
```

> **Note:** If ZeroMQ is not found, the engine compiles with a stub (`ARB_NO_ZMQ`) — it will load market snapshots and scan for arbs but won't receive live updates.

### 4. Install smart contract dependencies

```bash
cd Contracts
npm install
```

### 5. Configure API keys

You need accounts on at least one platform. See [docs/API_KEYS.md](docs/API_KEYS.md) for step-by-step instructions.

| Key | Required? | Where to get it |
|---|---|---|
| `PREDICTFUN_API_KEY` | **Yes** (for Predict.fun ingestion) | [predict.fun](https://predict.fun) — create account → API settings |
| `PROBABLE_API_KEY` | No (public read API) | [probable.markets](https://probable.markets) — only needed for order placement |
| `GROQ_API_KEY` | Yes (if `LLM_PROVIDER=groq`) | [console.groq.com](https://console.groq.com) |
| `TELEGRAM_BOT_TOKEN` | Only for alerts | [@BotFather](https://t.me/BotFather) on Telegram |
| `PRIVATE_KEY` | Only for on-chain execution | Your BNB/opBNB wallet private key |

---

## Running the Bot

The system has **four independent processes**. Run them in separate terminals:

### Step 1 — Ingest market data

Fetch markets from both platforms, persist JSON snapshots, and start streaming live odds:

```bash
# Terminal 1: Predict.fun ingestion
python -m Ingestion.ingest_predictfun

# Terminal 2: Probable ingestion
python -m Ingestion.ingest_probable
```

Each ingestion node will:
1. Paginate through the platform's REST API to fetch OPEN markets (optionally capped via `--max-markets`).
2. Normalise each market into the shared `NormalizedMarket` schema (using LLM for unstructured text fields).
3. Save JSON snapshots to `Data/markets/`.
4. In `--live` mode, poll order books and publish live odds updates over ZMQ (`topic: odds.*`).

### Step 1b — Selective Groq ingestion (API-safe)

Use this mode to fetch only a capped candidate set, then let Groq auto-pick ~5 strict overlap pairs between Predict.fun and Probable:

```bash
python -m Ingestion.ingest_groq_selective --cap-per-platform 20 --pick-count 5
```

This writes only the selected overlap markets (about 5 per platform) to `Data/markets/`.

### Step 2 — Start the matching engine

```bash
# Terminal 3
cd Engine/build
./arb-engine          # Linux/macOS
arb-engine.exe        # Windows
```

The engine will:
1. Load all JSON snapshots from `Data/markets/`.
2. Subscribe to ZMQ for live odds updates on `tcp://0.0.0.0:5555`.
3. Every 1 second, scan bucketed Predict.fun × Probable equivalents for arbitrage.
4. Write opportunities to `arbs.json` for `Execution/run_arb.py`.

### Step 3 — Start Telegram alerts (optional)

```bash
# Terminal 4
python -m Alert-system.telegram_bot
```

Subscribes to `arb.*` ZMQ topics and forwards arb alerts to your Telegram chat.

---

## Deploy the Smart Contract

The `ArbExecutor` contract enables **atomic** two-leg arb trades on opBNB.

```bash
cd Contracts

# Compile
npx hardhat compile

# Deploy to opBNB mainnet
npx hardhat run scripts/deploy.js --network opbnb

# Deploy to opBNB testnet (for testing)
npx hardhat run scripts/deploy.js --network opbnbTestnet
```

After deployment, copy the contract address into `.env`:

```dotenv
ARB_EXECUTOR_CONTRACT=0x...
```

> **Important:** Update the placeholder exchange & CTF addresses in `.env` (or `deploy.js`) with the actual Predict.fun and Probable contract addresses on opBNB before deploying to mainnet.

---

## How the Arbitrage Works

1. **Same event, two platforms.** Both Predict.fun and Probable list markets on the same underlying event (e.g., "Will BTC hit $100k by Friday?").

2. **Price discrepancy.** If `YES` on Platform A costs $0.45 and `YES` on Platform B costs $0.55, there's a 10% (1000 bps) gross spread.

3. **Two-leg trade:**
   - **Buy YES** on the cheap platform (A @ $0.45)
   - **Buy NO** on the expensive platform (B @ $0.45, since NO = 1 − YES)

4. **Guaranteed profit.** Regardless of the outcome:
   - If the event happens → YES pays $1 on A. You spent $0.45 + $0.45 = $0.90 → profit = $0.10
   - If the event doesn't happen → NO pays $1 on B. Same math.

5. **Net profit** = gross spread − platform fees − gas costs − slippage.

The engine only executes when `net_delta_bps ≥ MIN_ARB_DELTA_BPS` (default: 50 bps).

---

## Engine Configuration

All tunable parameters are read from environment variables (or `.env`):

| Variable | Default | Description |
|---|---|---|
| `MIN_ARB_DELTA_BPS` | `50` | Minimum net spread in basis points to trigger a trade |
| `MAX_TRADE_SIZE_USDT` | `500` | Maximum USDT deployed per arb opportunity |
| `GAS_PRICE_MULTIPLIER` | `1.1` | Safety multiplier on gas price estimates |
| `SLIPPAGE_TOLERANCE_BPS` | `30` | Maximum acceptable slippage before skipping a trade |

---

## Data Flow & Schemas

All components share the `NormalizedMarket` schema defined in [Data/schemas.py](Data/schemas.py):

- **`NormalizedMarket`** — Platform-agnostic market representation (identity, outcomes, prices, order book, fees, oracle info).
- **`OddsUpdate`** — Lightweight ZMQ message for live price changes.
- **`OrderBook`** / **`OrderBookLevel`** — Bid/ask snapshots used for slippage estimation.

The C++ engine mirrors these schemas 1:1 in [Engine/src/types.hpp](Engine/src/types.hpp) and deserializes from the same JSON format.

---

## LLM Routing

The ingestion layer uses an LLM to extract structured data from unstructured market text (e.g., parsing "Will BTC reach $100k?" into `underlying_asset=BTC, strike_value=100000`).

Two providers are supported, configured via `LLM_PROVIDER` in `.env`:

| Provider | Env Vars Required | Notes |
|---|---|---|
| **Groq** (cloud) | `GROQ_API_KEY`, `MODEL` | Fast, hosted inference. Default model: `llama3-8b-8192` |
| **Ollama** (local) | `OLLAMA_BASE_URL`, `MODEL` | Run locally. Requires Ollama running at the configured URL |

The LLM is **only** used during initial ETL parsing. It does not participate in live trading decisions.

---

## Known Limitations

- **Trade execution is stubbed.** The C++ engine detects opportunities and logs them, but the on-chain `ArbExecutor.executeArb()` call is not yet wired up. See the `TODO` in [Engine/src/matcher.cpp](Engine/src/matcher.cpp#L247).
- **Rust engine blocked.** A Rust implementation exists in `Engine/src/*.rs` but cannot compile because the installed Rust toolchain (1.83) is too old for the `getrandom` crate (needs Rust 1.85+). See [Engine/WHY_NOT_RUST.md](Engine/WHY_NOT_RUST.md) for details.
- **Placeholder contract addresses.** The deploy script uses dummy addresses for the platform exchange and CTF contracts — these must be replaced with real opBNB addresses before mainnet use.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Ingestion | Python 3.11+, httpx, websockets, pyzmq, Pydantic v2 |
| LLM ETL | Groq cloud / Ollama local (Llama 3) |
| Engine | C++14, nlohmann/json, spdlog, ZeroMQ |
| Smart Contract | Solidity 0.8.24, Hardhat, opBNB (Chain ID 204) |
| Alerts | python-telegram-bot, pyzmq |
| IPC | ZeroMQ PUB/SUB over TCP |

---

## Further Documentation

| Document | Description |
|---|---|
| [docs/API_KEYS.md](docs/API_KEYS.md) | Detailed guide on every API key & account you need, where to get them, and how to configure them |
| [docs/BUILD_ENGINE.md](docs/BUILD_ENGINE.md) | Step-by-step guide for building the C++ engine on Windows (MinGW / MSVC) and Linux |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common errors and how to fix them (401 Unauthorized, cmake not found, ZMQ issues, etc.) |

---

## License

Hackathon project — see individual file headers for details.
