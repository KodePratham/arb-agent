import dotenv from "dotenv";
import { readFileSync } from "node:fs";
import { existsSync, writeFileSync } from "node:fs";
import { ContractFactory, JsonRpcProvider, Wallet, parseEther } from "ethers";

dotenv.config();

async function main() {
  const rpcUrl =
    process.env.BSC_TESTNET_RPC_URL ||
    process.env.OPBNB_TESTNET_RPC_URL ||
    "https://data-seed-prebsc-1-s1.bnbchain.org:8545";
  const privateKey = process.env.DEPLOYER_PRIVATE_KEY;
  const seedTbnb = process.env.DEPLOY_SEED_TBNB || "0.01";

  if (!privateKey) {
    throw new Error("Set DEPLOYER_PRIVATE_KEY in .env before deployment.");
  }

  const provider = new JsonRpcProvider(rpcUrl);
  const deployer = new Wallet(privateKey, provider);
  console.log("Deploying with:", deployer.address);

  const artifactPath = new URL(
    "../artifacts/contracts/BinaryPredictionAMM.sol/BinaryPredictionAMM.json",
    import.meta.url
  );
  const artifact = JSON.parse(readFileSync(artifactPath, "utf8"));

  const factory = new ContractFactory(artifact.abi, artifact.bytecode, deployer);
  const market = await factory.deploy(100);
  await market.waitForDeployment();

  const address = await market.getAddress();
  console.log("BinaryPredictionAMM deployed at:", address);

  const seed = parseEther(seedTbnb);

  const tx1 = await market.createMarket(
    "Will humans land on mars by 2030",
    seed,
    { value: seed }
  );
  await tx1.wait();

  const tx2 = await market.createMarket(
    "Successful Human Mars mission by 2030?",
    seed,
    { value: seed }
  );
  await tx2.wait();

  const count = Number(await market.marketCount());
  if (count < 2) {
    throw new Error(`Expected 2 markets after deployment, got ${count}`);
  }

  const [m0, m1] = await Promise.all([market.getMarket(0), market.getMarket(1)]);
  const market0Active = m0[0].length > 0 && m0[1] > 0n && m0[2] > 0n;
  const market1Active = m1[0].length > 0 && m1[1] > 0n && m1[2] > 0n;

  if (!market0Active || !market1Active) {
    throw new Error("Market deployment finished but one or both markets are not active.");
  }

  const envLocalPath = new URL("../.env.local", import.meta.url);
  const existing = existsSync(envLocalPath) ? readFileSync(envLocalPath, "utf8") : "";
  const lines = existing.split(/\r?\n/).filter(Boolean);
  const withoutAddress = lines.filter((line) => !line.startsWith("NEXT_PUBLIC_CONTRACT_ADDRESS="));
  withoutAddress.push(`NEXT_PUBLIC_CONTRACT_ADDRESS=${address}`);
  if (!withoutAddress.some((line) => line.startsWith("NEXT_PUBLIC_CHAIN_ID="))) {
    withoutAddress.push("NEXT_PUBLIC_CHAIN_ID=97");
  }
  writeFileSync(envLocalPath, `${withoutAddress.join("\n")}\n`);

  console.log(`Created and verified market 0 + market 1 with active seed liquidity (${seedTbnb} tBNB each).`);
  console.log("Updated .env.local with NEXT_PUBLIC_CONTRACT_ADDRESS.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
