import { NextRequest, NextResponse } from "next/server";
import { Contract, JsonRpcProvider, Wallet } from "ethers";
import { AMM_ABI } from "@/lib/contract";

export async function POST(request: NextRequest) {
  try {
    const { marketId, outcomeYes, adminKey } = (await request.json()) as {
      marketId?: number;
      outcomeYes?: boolean;
      adminKey?: string;
    };

    const expectedAdminKey = process.env.ADMIN_API_KEY;
    if (!expectedAdminKey) {
      return NextResponse.json({ error: "Missing ADMIN_API_KEY in env." }, { status: 500 });
    }

    if (!adminKey || adminKey !== expectedAdminKey) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    if (!Number.isInteger(marketId) || (marketId ?? -1) < 0) {
      return NextResponse.json({ error: "marketId must be a non-negative integer." }, { status: 400 });
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

    const tx = await contract.resolveMarket(marketId, outcomeYes);
    const receipt = await tx.wait();

    return NextResponse.json({
      ok: true,
      txHash: receipt?.hash || tx.hash,
      marketId,
      outcomeYes,
    });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message || "Resolve failed." }, { status: 500 });
  }
}
