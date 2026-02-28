# Environment and Keys

## Required

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | Must be `ollama` |
| `OLLAMA_BASE_URL` | Local Ollama endpoint (default `http://localhost:11434`) |
| `PROBABLE_API_KEY` | Probable ingestion authentication |
| `OPINION_TRADE_API_KEY` | Opinion.trade ingestion authentication (if required by endpoint) |

## Optional

| Variable | Purpose |
|---|---|
| `MODEL` | Ollama model override; leave blank to pick interactively |
| `PROBABLE_API_BASE` | Probable API base URL override |
| `OPINION_TRADE_API_BASE` | Opinion.trade API base URL override |
| `OPINION_TRADE_APP_BASE` | Opinion.trade app base fallback override |
| `PRIVATE_KEY` | Required only for `Execution.run_arb --execute` |
| `ARB_EXECUTOR_CONTRACT` | Required only for live contract calls |
| `OPBNB_RPC_URL` | RPC endpoint override |

## Minimal `.env`

```dotenv
LLM_PROVIDER=ollama
MODEL=
OLLAMA_BASE_URL=http://localhost:11434

PROBABLE_API_BASE=https://market-api.probable.markets
PROBABLE_API_KEY=your_probable_key
PROBABLE_WS_URL=wss://probable.markets/ws

OPINION_TRADE_API_BASE=https://api.opinion.trade
OPINION_TRADE_APP_BASE=https://app.opinion.trade
OPINION_TRADE_API_KEY=

ZMQ_ENGINE_ADDR=tcp://0.0.0.0:5555

MIN_ARB_DELTA_BPS=50
MAX_TRADE_SIZE_USDT=500
GAS_PRICE_MULTIPLIER=1.1
SLIPPAGE_TOLERANCE_BPS=30

OPBNB_RPC_URL=https://opbnb-mainnet-rpc.bnbchain.org
ARB_EXECUTOR_CONTRACT=
PRIVATE_KEY=
```

## Notes

- Groq keys are no longer used.
- Keep `.env` private and never commit it.
- Validate Ollama is reachable before ingestion: `ollama list`.