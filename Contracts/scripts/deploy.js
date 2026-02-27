// Contracts/scripts/deploy.js
// ─────────────────────────────────────────────────────────────────
// Deploy ArbExecutor to opBNB.
//
// Usage:
//   cd Contracts
//   npx hardhat run scripts/deploy.js --network opbnb
// ─────────────────────────────────────────────────────────────────

const hre = require("hardhat");

async function main() {
    const [deployer] = await hre.ethers.getSigners();
    console.log("Deploying ArbExecutor with account:", deployer.address);

    const balance = await hre.ethers.provider.getBalance(deployer.address);
    console.log("Account balance:", hre.ethers.formatEther(balance), "BNB");

    // ── Contract addresses on opBNB ──────────────────────────────
    // IMPORTANT: Replace these with the actual deployed addresses
    // for Predict.fun and Probable on opBNB / BNB Chain.

    // USDT on opBNB (Bridged from BNB Chain)
    const USDT = process.env.OPBNB_USDT || "0x9e5AAC1Ba1a2e6aEd6b32689DFcF62A509Ca96f3";

    // Predict.fun exchange & CTF (placeholder — update when known)
    const PF_EXCHANGE = process.env.PF_EXCHANGE || "0x0000000000000000000000000000000000000001";
    const PF_CTF      = process.env.PF_CTF      || "0x0000000000000000000000000000000000000002";

    // Probable exchange & CTF (placeholder — update when known)
    const PR_EXCHANGE = process.env.PR_EXCHANGE || "0x0000000000000000000000000000000000000003";
    const PR_CTF      = process.env.PR_CTF      || "0x0000000000000000000000000000000000000004";

    console.log("\nDeployment parameters:");
    console.log("  USDT:           ", USDT);
    console.log("  PF Exchange:    ", PF_EXCHANGE);
    console.log("  PR Exchange:    ", PR_EXCHANGE);
    console.log("  PF CTF:         ", PF_CTF);
    console.log("  PR CTF:         ", PR_CTF);

    // ── Deploy ───────────────────────────────────────────────────
    const ArbExecutor = await hre.ethers.getContractFactory("ArbExecutor");
    const executor = await ArbExecutor.deploy(
        USDT,
        PF_EXCHANGE,
        PR_EXCHANGE,
        PF_CTF,
        PR_CTF
    );

    await executor.waitForDeployment();
    const address = await executor.getAddress();

    console.log("\n✓ ArbExecutor deployed to:", address);
    console.log("\nAdd this to your .env file:");
    console.log(`  ARB_EXECUTOR_CONTRACT=${address}`);

    // ── Verify (optional) ────────────────────────────────────────
    if (hre.network.name !== "hardhat" && hre.network.name !== "localhost") {
        console.log("\nWaiting 30s for block confirmations before verification...");
        await new Promise(r => setTimeout(r, 30000));

        try {
            await hre.run("verify:verify", {
                address: address,
                constructorArguments: [USDT, PF_EXCHANGE, PR_EXCHANGE, PF_CTF, PR_CTF],
            });
            console.log("✓ Contract verified on block explorer");
        } catch (e) {
            console.log("⚠ Verification failed (can retry later):", e.message);
        }
    }
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
