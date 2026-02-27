# API Keys & Accounts Guide

This document explains every API key and external account the arb-agent needs, where to obtain them, and how to configure them in your `.env` file.

---

## Quick Reference

| Variable | Required? | Free? | Purpose |
|---|---|---|---|
| `PREDICTFUN_API_KEY` | **Yes** (for Predict.fun ingestion) | Yes | Authenticate REST API calls to fetch markets & orderbooks |
| `PROBABLE_API_KEY` | No | Yes | Probable's read API is public; key only needed for write/order endpoints |
| `OLLAMA_BASE_URL` | Yes (default LLM provider) | Yes (local) | Local LLM; no API key needed |
| `GROQ_API_KEY` | Only if using Groq fallback | Free tier available | Cloud LLM inference for parsing market text |
| `TELEGRAM_BOT_TOKEN` | Only for alerts | Yes | Telegram bot that sends arb notifications |
| `TELEGRAM_CHAT_ID` | Only for alerts | Yes | Chat/channel to receive alerts |
| `PRIVATE_KEY` | Only for on-chain execution | N/A | Wallet private key for deploying/calling the smart contract |
| `OPBNB_SCAN_API_KEY` | Optional | Yes | For contract verification on opBNB block explorer |
| `BSCSCAN_API_KEY` | Optional | Yes | For contract verification on BscScan |

---

## 1. Predict.fun API Key

### Why you need it

The ingestion node (`Ingestion/ingest_predictfun.py`) calls the Predict.fun REST API at `https://api.predict.fun/v1/markets`. This endpoint returns **401 Unauthorized** without a valid API key.

### How to get it

1. Go to [predict.fun](https://predict.fun) and create an account (Google, X, or email sign-up).
2. Navigate to your account settings / developer section.
3. Generate an API key.
4. Copy the key into your `.env`:

```dotenv
PREDICTFUN_API_KEY=your_api_key_here
```

### How it's used

The key is sent as the `x-api-key` header on every REST request:

```python
# From Ingestion/ingest_predictfun.py
def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json"}
    if API_KEY:
        h["x-api-key"] = API_KEY
    return h
```

### Without it

You will see:
```
httpx.HTTPStatusError: Client error '401 Unauthorized' for url
'https://api.predict.fun/v1/markets?first=50&status=OPEN&includeStats=true'
```

---

## 2. Probable API Key

### Why it's optional

Probable's public read API (`https://probable.markets/v1/markets`) does **not** require authentication for fetching market data and orderbooks. The API key is only needed if you want to place orders programmatically.

### How to get it (if needed)

1. Go to [probable.markets](https://probable.markets) and create an account.
2. Check the developer/API section for a Bearer token.
3. Add to `.env`:

```dotenv
PROBABLE_API_KEY=your_bearer_token_here
```

### How it's used

Sent as a `Bearer` token in the `Authorization` header (only if set):

```python
# From Ingestion/ingest_probable.py
def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h
```

---

## 3. LLM Provider (Groq or Ollama)

The ingestion layer uses an LLM to extract structured data from unstructured market descriptions. **You must configure exactly one provider.**

### Option A — Ollama (local, default — no API key needed)

1. Install Ollama from [ollama.com](https://ollama.com) (or `winget install Ollama.Ollama`).
2. Pull a model: `ollama pull llama3`
3. Ensure the Ollama server is running (default: `http://localhost:11434`).
4. Configure `.env`:

```dotenv
LLM_PROVIDER=ollama
MODEL=              # leave blank → interactive model picker at startup
OLLAMA_BASE_URL=http://localhost:11434
```

**Interactive picker:** When `MODEL` is empty, the ingestion script queries `ollama.list()` and shows a numbered menu of your installed models.

**Pros:** No API key, no rate limits, data stays local.  
**Cons:** Requires decent hardware (8GB+ RAM for 8B models).

### Option B — Groq (cloud fallback)

1. Go to [console.groq.com](https://console.groq.com) and sign up.
2. Create an API key from the dashboard.
3. Configure `.env`:

```dotenv
LLM_PROVIDER=groq
MODEL=llama-3.1-8b-instant
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx
```

**Free tier:** Groq offers a generous free tier with rate limits suitable for this bot.

**Available models:** `llama-3.1-8b-instant`, `llama3-70b-8192`, `mixtral-8x7b-32768`, etc.

---

## 4. Telegram Bot (Alerts)

### How to create a bot

1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts to name your bot.
3. BotFather will give you a token like `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`.

### How to get your Chat ID

1. Add your bot to a group/channel (or message it directly).
2. Send a message in the chat.
3. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser.
4. Find the `"chat": {"id": ...}` field — that's your Chat ID.

Alternatively, search for `@userinfobot` on Telegram and message it to get your personal chat ID.

### Configure `.env`

```dotenv
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=-1001234567890
```

> **Tip:** Channel IDs start with `-100`. Group IDs are negative numbers. Personal chat IDs are positive.

---

## 5. Wallet Private Key (Smart Contract)

### When you need it

Only if you want to:
- Deploy the `ArbExecutor` contract to opBNB
- Execute on-chain arb trades

### How to get it

Export the private key from your wallet (MetaMask, Trust Wallet, etc.):

- **MetaMask:** Account Details → Export Private Key
- **Trust Wallet:** Settings → Wallets → (i) icon → Show Private Key

### Configure `.env`

```dotenv
PRIVATE_KEY=0xabc123...your_64_hex_char_private_key
```

### Fund the wallet

The wallet needs:
- **BNB on opBNB** for gas (very cheap — ~0.001 Gwei per tx)
- **USDT on opBNB** for executing arb trades

Bridge assets from BNB Chain to opBNB via the [official bridge](https://opbnb-bridge.bnbchain.org).

> **Security:** Never commit your `.env` file. The `.gitignore` should already exclude it, but double-check.

---

## 6. Block Explorer API Keys (Optional)

These are only needed for verifying the smart contract on block explorers after deployment.

### opBNB Scan

1. Go to [opbnb.bscscan.com](https://opbnb.bscscan.com), create an account.
2. Go to API Keys → Create.
3. Add to `.env`:

```dotenv
OPBNB_SCAN_API_KEY=your_key_here
```

### BscScan

1. Go to [bscscan.com](https://bscscan.com), create an account.
2. Go to API Keys → Create.
3. Add to `.env`:

```dotenv
BSCSCAN_API_KEY=your_key_here
```

---

## Complete `.env` Template

```dotenv
# ── LLM Provider (Ollama is default) ─────────────────────
LLM_PROVIDER=ollama
MODEL=                    # blank = interactive picker; or 'llama3', etc.
OLLAMA_BASE_URL=http://localhost:11434

# Uncomment below for Groq cloud fallback:
# LLM_PROVIDER=groq
# MODEL=llama-3.1-8b-instant
# GROQ_API_KEY=gsk_...

# ── Platform APIs ─────────────────────────────────────────
PREDICTFUN_API_BASE=https://api.predict.fun
PREDICTFUN_API_KEY=your_predictfun_api_key_here
PREDICTFUN_WS_URL=wss://ws.predict.fun

PROBABLE_API_BASE=https://probable.markets
PROBABLE_API_KEY=
PROBABLE_WS_URL=wss://probable.markets/ws

# ── ZMQ IPC ──────────────────────────────────────────────
ZMQ_ENGINE_ADDR=tcp://0.0.0.0:5555

# ── Engine Tuning ─────────────────────────────────────────
MIN_ARB_DELTA_BPS=50
MAX_TRADE_SIZE_USDT=500
GAS_PRICE_MULTIPLIER=1.1
SLIPPAGE_TOLERANCE_BPS=30

# ── Telegram Alerts ──────────────────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# ── Smart Contract / opBNB ────────────────────────────────
PRIVATE_KEY=0x0000000000000000000000000000000000000000000000000000000000000000
OPBNB_RPC_URL=https://opbnb-mainnet-rpc.bnbchain.org
BNB_RPC_URL=https://bsc-dataseed1.binance.org
OPBNB_USDT=0x9e5AAC1Ba1a2e6aEd6b32689DFcF62A509Ca96f3
ARB_EXECUTOR_ADDRESS=

# ── Block Explorer Verification (optional) ────────────────
OPBNB_SCAN_API_KEY=
BSCSCAN_API_KEY=
```
