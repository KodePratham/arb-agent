// Contracts/hardhat.config.js
// ─────────────────────────────────────────────────────────────────
// Hardhat configuration for opBNB deployment.
//
// Usage:
//   npx hardhat compile
//   npx hardhat run scripts/deploy.js --network opbnb
// ─────────────────────────────────────────────────────────────────

require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config({ path: "../.env" });

const PRIVATE_KEY = process.env.PRIVATE_KEY || "0x" + "0".repeat(64);
const OPBNB_RPC   = process.env.OPBNB_RPC_URL || "https://opbnb-mainnet-rpc.bnbchain.org";
const BNB_RPC     = process.env.BNB_RPC_URL   || "https://bsc-dataseed1.binance.org";

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
    solidity: {
        version: "0.8.24",
        settings: {
            optimizer: {
                enabled: true,
                runs: 200,
            },
            viaIR: true,
        },
    },

    networks: {
        // opBNB Mainnet (L2) — primary deployment target
        opbnb: {
            url: OPBNB_RPC,
            chainId: 204,
            accounts: [PRIVATE_KEY],
            gasPrice: 1000000,         // 0.001 Gwei (opBNB ultra-low gas)
        },

        // opBNB Testnet
        opbnbTestnet: {
            url: "https://opbnb-testnet-rpc.bnbchain.org",
            chainId: 5611,
            accounts: [PRIVATE_KEY],
        },

        // BNB Mainnet (L1) — fallback if needed
        bnb: {
            url: BNB_RPC,
            chainId: 56,
            accounts: [PRIVATE_KEY],
        },

        // BNB Testnet
        bnbTestnet: {
            url: "https://data-seed-prebsc-1-s1.binance.org:8545",
            chainId: 97,
            accounts: [PRIVATE_KEY],
        },
    },

    etherscan: {
        apiKey: {
            opbnb:        process.env.OPBNB_SCAN_API_KEY || "",
            opbnbTestnet: process.env.OPBNB_SCAN_API_KEY || "",
            bsc:          process.env.BSCSCAN_API_KEY    || "",
            bscTestnet:   process.env.BSCSCAN_API_KEY    || "",
        },
        customChains: [
            {
                network: "opbnb",
                chainId: 204,
                urls: {
                    apiURL:     "https://api-opbnb.bscscan.com/api",
                    browserURL: "https://opbnb.bscscan.com",
                },
            },
            {
                network: "opbnbTestnet",
                chainId: 5611,
                urls: {
                    apiURL:     "https://api-opbnb-testnet.bscscan.com/api",
                    browserURL: "https://opbnb-testnet.bscscan.com",
                },
            },
        ],
    },

    paths: {
        sources:  "./",
        tests:    "./test",
        cache:    "./cache",
        artifacts: "./artifacts",
    },
};
