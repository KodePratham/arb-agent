import "@nomicfoundation/hardhat-ethers";
import dotenv from "dotenv";

dotenv.config();

const BSC_TESTNET_RPC_URL =
  process.env.BSC_TESTNET_RPC_URL ||
  process.env.OPBNB_TESTNET_RPC_URL ||
  "https://data-seed-prebsc-1-s1.bnbchain.org:8545";
const DEPLOYER_PRIVATE_KEY = process.env.DEPLOYER_PRIVATE_KEY || "";

const config = {
  solidity: "0.8.24",
  networks: {
    localhost: {
      type: "http",
      url: "http://127.0.0.1:8545",
      chainId: 31337,
    },
    bscTestnet: {
      type: "http",
      url: BSC_TESTNET_RPC_URL,
      chainId: 97,
      accounts: DEPLOYER_PRIVATE_KEY ? [DEPLOYER_PRIVATE_KEY] : [],
    },
  },
};

export default config;
