# Setup and Run

This guide covers the single supported workflow:

Ollama ingestion -> C++ market matching -> execution runner.

## 1. Environment

From repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Install and start Ollama, then pull a model:

```powershell
ollama pull llama3
```

Create `.env` from template:

```powershell
Copy-Item .env.example .env
```

Set at least:

```dotenv
LLM_PROVIDER=ollama
MODEL=
OLLAMA_BASE_URL=http://localhost:11434
PROBABLE_API_KEY=your_key_here
OPINION_TRADE_API_KEY=your_key_here
```

## 2. Build C++ Engine

```powershell
cd Engine
cmake -S . -B build -G "MinGW Makefiles"
cmake --build build
cd ..
```

If you use MSVC, switch generator accordingly.

## 3. Ingest Markets

```powershell
python -m Ingestion.ingest_probable
python -m Ingestion.ingest_opinion_trade
```

Optional flags:

- `--model llama3.1`
- `--max-markets 200`
- `--live`

## 4. Run Matching Engine

```powershell
cd Engine\build
.\arb-engine.exe --output arbs.json
cd ..\..
```

Engine behavior:

- loads `Data/markets/*.json` into RAM
- deduplicates by platform + market id
- scans cross-platform overlap opportunities
- writes opportunities to `Engine/build/arbs.json`

## 5. Review / Execute

Dry run:

```powershell
python -m Execution.run_arb --arbs Engine\build\arbs.json
```

Live mode:

```powershell
python -m Execution.run_arb --arbs Engine\build\arbs.json --execute
```

`--execute` requires wallet and contract fields in `.env`.

## 6. Contract (Optional)

```powershell
cd Contracts
npm install
npx hardhat compile
npx hardhat run scripts/deploy.js --network opbnb
cd ..
```

Put deployed address in `.env`:

```dotenv
ARB_EXECUTOR_CONTRACT=0x...
```