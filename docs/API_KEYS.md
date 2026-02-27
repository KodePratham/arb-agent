# Environment and Keys

## Required

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | Must be `ollama` |
| `OLLAMA_BASE_URL` | Local Ollama endpoint (default `http://localhost:11434`) |
| `PREDICTFUN_API_KEY` | Predict.fun ingestion authentication |

## Optional

| Variable | Purpose |
|---|---|
| `MODEL` | Ollama model override; leave blank to pick interactively |
| `PROBABLE_API_KEY` | Optional bearer token if Probable endpoint requires auth |
| `PRIVATE_KEY` | Required only for `Execution.run_arb --execute` |
| `ARB_EXECUTOR_CONTRACT` | Required only for live contract calls |
| `OPBNB_RPC_URL` | RPC endpoint override |

## Minimal `.env`

```dotenv
LLM_PROVIDER=ollama
MODEL=
OLLAMA_BASE_URL=http://localhost:11434

PREDICTFUN_API_BASE=https://api.predict.fun
PREDICTFUN_API_KEY=your_predictfun_key
PREDICTFUN_WS_URL=wss://ws.predict.fun

PROBABLE_API_BASE=https://market-api.probable.markets
PROBABLE_API_KEY=
PROBABLE_WS_URL=wss://probable.markets/ws

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