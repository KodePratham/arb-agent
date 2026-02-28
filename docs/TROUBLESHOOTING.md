# Troubleshooting

## Probable returns 401/403

Cause: `PROBABLE_API_KEY` is missing or invalid.

Fix:

1. Set `PROBABLE_API_KEY` in `.env`
2. Re-run `python -m Ingestion.ingest_probable`

## Opinion.trade returns no markets

Cause: endpoint path differs from defaults or API requires auth.

Fix:

1. Set `OPINION_TRADE_API_BASE` and/or `OPINION_TRADE_APP_BASE` in `.env`
2. Set `OPINION_TRADE_API_KEY` if required by your endpoint
3. Re-run `python -m Ingestion.ingest_opinion_trade`

## Ollama connection failure

Typical symptoms:

- model picker is empty
- request retries fail in parser

Fix:

1. Start Ollama service
2. Run `ollama list`
3. Pull model if needed: `ollama pull llama3`
4. Verify `OLLAMA_BASE_URL`

## Unsupported LLM provider error

Error indicates non-ollama provider.

Fix:

```dotenv
LLM_PROVIDER=ollama
```

## Engine finds no markets

Cause: no snapshots in `Data/markets/`.

Fix:

1. Run both ingestion commands
2. Confirm JSON files exist in `Data/markets/`
3. Re-run engine

## ZMQ disabled warning

If ZeroMQ is missing at build time, engine still works in snapshot mode.

Fix for live mode:

- install ZeroMQ/cppzmq
- rebuild engine

## Execution cannot submit transactions

Typical causes:

- `PRIVATE_KEY` not set
- `ARB_EXECUTOR_CONTRACT` not set
- RPC not reachable

Fix:

1. Fill required execution env vars
2. Validate RPC URL
3. Test without `--execute` first

## CMake not found

Fix:

```powershell
winget install Kitware.CMake
```

Restart terminal and rebuild.