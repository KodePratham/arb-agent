# ChadOnChain (Next.js + MetaMask + Hardhat)

Simple prediction market dashboard with:

- 2 Mars binary markets shown side by side
- MetaMask connect + chain switch
- AMM-based liquidity and trading (YES / NO)
- `Activate Chad` arbitrage agent button
- Hardhat deployment flow for BSC testnet

## Hackathon note (mock data + Ollama constraints)

- For hackathon purposes, we are using mock market data in the demo flows.
- Reason: end-to-end parsing against live external feeds could not be reliably completed within hackathon constraints due to Ollama runtime limitations in our environment.
- Ollama parsing is only required once to produce the normalized canonical snapshot; after that, the matcher and UI can run repeatedly on the generated snapshot/mock dataset.

## Stack

- Next.js (App Router, TypeScript)
- Ethers.js for wallet/contract calls
- Solidity contract: `contracts/BinaryPredictionAMM.sol`
- Hardhat for compile + deploy

## 1) Environment

Copy `.env.example` to `.env` for Hardhat and `.env.local` for Next.js.

Required values:

```dotenv
BSC_TESTNET_RPC_URL=https://data-seed-prebsc-1-s1.bnbchain.org:8545
DEPLOYER_PRIVATE_KEY=0x...

NEXT_PUBLIC_CONTRACT_ADDRESS=0x...
NEXT_PUBLIC_CHAIN_ID=97
ADMIN_USER=...
ADMIN_PASS=...
ADMIN_PRIVATE_KEY=0x... # optional, defaults to DEPLOYER_PRIVATE_KEY
DEPLOY_SEED_TBNB=0.005
```

## 2) Compile + deploy to BSC testnet

```bash
bun run hardhat:compile
bun run hardhat:deploy:bsc
```

After deployment, copy the deployed contract address into `NEXT_PUBLIC_CONTRACT_ADDRESS` in `.env.local`.

## 3) Run dashboard

```bash
bun run dev
```

Open `http://localhost:3067`, connect MetaMask, switch to BSC testnet, then interact with market 1 and market 2.

Use `Activate Chad` to run the arbitrage step when market prices diverge.

## 4) Admin finalization

- Open `http://localhost:3067/admin`
- Enter `ADMIN_USER` and `ADMIN_PASS`
- Select final outcome (YES or NO)
- Submit once to finalize both similar markets on-chain

After finalization, users can claim winnings from the main dashboard.

The UI now shows explicit ACTIVE/INACTIVE states for:

- Both required markets (market 1 and market 2)
- Chad status (Inactive / Active Monitoring / Active Trading / Active)

## Notes

- The deploy script seeds exactly 2 Mars markets and verifies both are active.
- Seed per market is controlled by `DEPLOY_SEED_TBNB` (default `0.005`).
- The deploy script automatically writes `NEXT_PUBLIC_CONTRACT_ADDRESS` into `.env.local`.
- Markets are viewable even before MetaMask connects (read-only mode via public RPC).
- Winners claim on-chain payouts after admin resolves each market.
- Users can sell YES/NO shares before market resolution.
- Share display is normalized: 1 share = 0.005 tBNB notional at launch.
- Arbitrage bot behavior: buy YES on the lower-priced market and hedge with NO on the higher-priced market.
- Hackathon demo uses mock data where needed because live parsing was constrained by Ollama environment limits during build time.
- Ollama parsing is a one-time preprocessing step, not required for each subsequent UI or matching run.
- Questions are:
	- Will humans land on mars by 2030
	- Successful Human Mars mission by 2030?
- Trades and liquidity operations use testnet `tBNB`.
- Pricing is AMM pool-ratio based with a fee configured in the contract constructor.
