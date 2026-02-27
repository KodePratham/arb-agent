# Troubleshooting

Common issues and their fixes when running arb-agent.

---

## Ingestion: 401 Unauthorized (Predict.fun)

**Error:**
```
httpx.HTTPStatusError: Client error '401 Unauthorized' for url
'https://api.predict.fun/v1/markets?first=50&status=OPEN&includeStats=true'
```

**Cause:** The `PREDICTFUN_API_KEY` is missing or invalid in your `.env` file.

**Fix:**
1. Create an account at [predict.fun](https://predict.fun).
2. Get your API key from the developer / account settings page.
3. Add it to `.env`:
   ```dotenv
   PREDICTFUN_API_KEY=your_key_here
   ```
4. Re-run the ingestion node.

> **Tip:** You can test the ingestion for Probable first (`python -m Ingestion.ingest_probable`) — Probable's read API is public and doesn't require a key.

---

## Ingestion: Connection Error / Timeout

**Error:**
```
httpx.ConnectError: ... [Errno 11001] getaddrinfo failed
httpx.ReadTimeout: timed out
```

**Cause:** Network issue — DNS resolution failed or the API is unreachable.

**Fix:**
- Check your internet connection.
- Verify the API base URL in `.env` is correct (`PREDICTFUN_API_BASE`, `PROBABLE_API_BASE`).
- Try opening the URL in a browser: `https://api.predict.fun/v1/markets?first=1&status=OPEN`
- If behind a proxy, configure `HTTP_PROXY` / `HTTPS_PROXY` env variables.

---

## CMake: 'cmake' Not Recognized

**Error:**
```
cmake : The term 'cmake' is not recognized as the name of a cmdlet,
function, script file, or operable program.
```

**Cause:** CMake is not installed or not on your system PATH.

**Fix (Windows):**
```powershell
winget install Kitware.CMake
```
Then **restart your terminal** (or open a new one). See [docs/BUILD_ENGINE.md](BUILD_ENGINE.md) for detailed instructions.

**Fix (Linux):**
```bash
sudo apt install cmake   # Debian/Ubuntu
sudo dnf install cmake   # Fedora
```

---

## Engine: No JSON Files Found

**Warning:**
```
[warn] No JSON files found in ..\Data\markets_init
```

**Cause:** The ingestion nodes haven't run yet — there are no market snapshots for the engine to load.

**Fix:**
1. Run at least one ingestion node first:
   ```bash
   python -m Ingestion.ingest_probable
   ```
2. Verify that JSON files exist in `Data/markets_init/`.
3. Then start the engine.

---

## Engine: ZMQ Disabled Warning

**Warning:**
```
[warn] ZMQ disabled at compile time. Live odds updates will not be received.
```

**Cause:** The engine was compiled without ZeroMQ (`ARB_NO_ZMQ` was defined).

**Impact:** The engine will still load initial snapshots and scan for arbs, but it won't receive live price updates from the ingestion nodes. It works in "static mode" only.

**Fix:** Install ZeroMQ and recompile:

- **Windows (vcpkg):**
  ```powershell
  vcpkg install cppzmq:x64-windows
  cd Engine/build
  cmake .. -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake
  cmake --build .
  ```

- **Linux:**
  ```bash
  sudo apt install libzmq3-dev
  cd Engine/build
  cmake ..
  cmake --build .
  ```

---

## Telegram Bot: BOT_TOKEN / CHAT_ID Not Set

**Error:**
```
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env
```

**Fix:** See the [API Keys guide](API_KEYS.md#4-telegram-bot-alerts) for how to create a bot and get your chat ID.

```dotenv
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=-1001234567890
```

---

## LLM: GROQ_API_KEY Not Set

**Error:**
```
RuntimeError: GROQ_API_KEY is not set in .env
```

**Cause:** You have `LLM_PROVIDER=groq` but no API key.

**Fix (Option A — use Groq):**
1. Sign up at [console.groq.com](https://console.groq.com).
2. Create an API key.
3. Add to `.env`:
   ```dotenv
   GROQ_API_KEY=gsk_xxxxxxxx
   ```

**Fix (Option B — use Ollama instead):**
1. Install [Ollama](https://ollama.com) and pull a model: `ollama pull llama3`
2. Change `.env`:
   ```dotenv
   LLM_PROVIDER=ollama
   MODEL=llama3
   OLLAMA_BASE_URL=http://localhost:11434
   ```

---

## LLM: Unknown LLM_PROVIDER

**Error:**
```
ValueError: Unknown LLM_PROVIDER='xxx'. Use 'groq' or 'ollama'.
```

**Fix:** Set `LLM_PROVIDER` to exactly `groq` or `ollama` (lowercase) in `.env`.

---

## Python: ModuleNotFoundError

**Error:**
```
ModuleNotFoundError: No module named 'httpx'
ModuleNotFoundError: No module named 'pydantic'
```

**Fix:**
```bash
pip install -r requirements.txt
```

If using a virtual environment, make sure it's activated first:
```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

---

## Python Version: 3.10 Compatibility

The codebase uses `type[X] | type[Y]` union syntax not available before Python 3.10. If you see:

```
TypeError: unsupported operand type(s) for |: 'type' and 'type'
```

**Fix:** Use Python 3.10+ (3.11+ recommended). Check with:
```bash
python --version
```

---

## Smart Contract: Deployment Fails

### Insufficient funds
```
ProviderError: insufficient funds for gas * price + value
```

**Fix:** Fund your wallet with BNB on the target network:
- opBNB mainnet: bridge BNB from BNB Chain via [opbnb-bridge.bnbchain.org](https://opbnb-bridge.bnbchain.org)
- opBNB testnet: use the [opBNB faucet](https://opbnb-testnet-bridge.bnbchain.org/deposit)

### Invalid private key
```
Error: invalid private key
```

**Fix:** Ensure `PRIVATE_KEY` in `.env` is a valid 64-character hex string prefixed with `0x`.

### Contract verification fails
```
⚠ Verification failed (can retry later)
```

This is non-critical — the contract is deployed and functional. You can retry verification later:
```bash
npx hardhat verify --network opbnb <CONTRACT_ADDRESS> <USDT> <PF_EXCHANGE> <PR_EXCHANGE> <PF_CTF> <PR_CTF>
```

---

## ZMQ: Address Already in Use

**Error:**
```
zmq.error.ZMQError: Address already in use (addr 'tcp://0.0.0.0:5555')
```

**Cause:** Another instance of the engine or a previous crashed process is still bound to port 5555.

**Fix (Windows):**
```powershell
netstat -ano | Select-String "5555"
# Find the PID and kill it:
Stop-Process -Id <PID> -Force
```

**Fix (Linux):**
```bash
lsof -i :5555
kill <PID>
```

Or change the port in `.env`:
```dotenv
ZMQ_ENGINE_ADDR=tcp://0.0.0.0:5556
```

---

## Rust Engine: edition2024 Error

**Error:**
```
error: failed to parse manifest at .../getrandom-0.4.1/Cargo.toml
  the cargo feature `edition2024` requires a nightly version of Cargo
```

**Cause:** Installed Rust toolchain (1.83) is too old. The `getrandom` crate needs Rust 1.85+.

**Fix:**
```bash
rustup update stable
rustc --version   # should be 1.85+
cd Engine
cargo build
```

If you can't update Rust, use the C++ engine instead (it's the primary build target).

See `Engine/WHY_NOT_RUST.md` for the full story.

---

## Still stuck?

1. Check that your `.env` file is in the **project root** (`arb-agent/.env`).
2. Make sure you're running commands from the **project root** (not a subdirectory).
3. Re-read [docs/API_KEYS.md](API_KEYS.md) to verify all required keys are set.
4. Open an issue on the repo with the full error output.
