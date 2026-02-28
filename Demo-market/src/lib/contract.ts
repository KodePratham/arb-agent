export const BSC_TESTNET = {
  chainIdHex: "0x61",
  chainIdDec: 97,
  chainName: "BNB Smart Chain Testnet",
  nativeCurrency: {
    name: "tBNB",
    symbol: "tBNB",
    decimals: 18,
  },
  rpcUrls: ["https://data-seed-prebsc-1-s1.bnbchain.org:8545"],
  blockExplorerUrls: ["https://testnet.bscscan.com"],
};

export const CONTRACT_ADDRESS = process.env.NEXT_PUBLIC_CONTRACT_ADDRESS || "";

export const AMM_ABI = [
  "function marketCount() view returns (uint256)",
  "function getMarket(uint256 marketId) view returns (string question, uint256 yesPool, uint256 noPool, uint256 yesPriceBps)",
  "function getMarketStatus(uint256 marketId) view returns (bool resolved, bool outcomeYes)",
  "function getUserShares(uint256 marketId, address user) view returns (uint256 yesShares, uint256 noShares)",
  "function getClaimable(uint256 marketId, address user) view returns (uint256)",
  "function addLiquidity(uint256 marketId) payable",
  "function buyYes(uint256 marketId) payable returns (uint256)",
  "function buyNo(uint256 marketId) payable returns (uint256)",
  "function resolveMarket(uint256 marketId, bool outcomeYes)",
  "function claimWinnings(uint256 marketId) returns (uint256)",
];
