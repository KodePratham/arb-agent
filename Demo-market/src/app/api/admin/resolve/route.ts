import { NextRequest, NextResponse } from "next/server";
import { Contract, JsonRpcProvider, Wallet } from "ethers";
import { AMM_ABI } from "@/lib/contract";

const MARKET_IDS = [0, 1];

export async function POST(request: NextRequest) {
  try {
    const { outcomeYes, adminUser, adminPass } = (await request.json()) as {
      outcomeYes?: boolean;
      adminUser?: string;
      adminPass?: string;
    };

    const expectedUser = process.env.ADMIN_USER;
    const expectedPass = process.env.ADMIN_PASS;

    if (!expectedUser || !expectedPass) {
      return NextResponse.json({ error: "Missing ADMIN_USER / ADMIN_PASS in env." }, { status: 500 });
    }

    if (!adminUser || !adminPass || adminUser !== expectedUser || adminPass !== expectedPass) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    if (typeof outcomeYes !== "boolean") {
      return NextResponse.json({ error: "outcomeYes must be boolean." }, { status: 400 });
    }

    const rpcUrl =
      process.env.BSC_TESTNET_RPC_URL ||
      process.env.OPBNB_TESTNET_RPC_URL ||
      "https://data-seed-prebsc-1-s1.bnbchain.org:8545";

    const privateKey = process.env.ADMIN_PRIVATE_KEY || process.env.DEPLOYER_PRIVATE_KEY;
    if (!privateKey) {
      return NextResponse.json({ error: "Missing ADMIN_PRIVATE_KEY or DEPLOYER_PRIVATE_KEY." }, { status: 500 });
    }

    const contractAddress = process.env.NEXT_PUBLIC_CONTRACT_ADDRESS;
    if (!contractAddress) {
      return NextResponse.json({ error: "Missing NEXT_PUBLIC_CONTRACT_ADDRESS." }, { status: 500 });
    }

    const provider = new JsonRpcProvider(rpcUrl);
    const signer = new Wallet(privateKey, provider);
    const contract = new Contract(contractAddress, AMM_ABI, signer);

    const txHashes: string[] = [];

    for (const marketId of MARKET_IDS) {
      const [resolved] = (await contract.getMarketStatus(marketId)) as [boolean, boolean];
      if (resolved) {
        continue;
      }
      const tx = await contract.resolveMarket(marketId, outcomeYes);
      const receipt = await tx.wait();
      txHashes.push(receipt?.hash || tx.hash);
    }

    return NextResponse.json({
      ok: true,
      outcomeYes,
      txHashes,
      message: txHashes.length ? "Markets resolved." : "All markets already resolved.",
    });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message || "Resolve failed." }, { status: 500 });
  }
}
