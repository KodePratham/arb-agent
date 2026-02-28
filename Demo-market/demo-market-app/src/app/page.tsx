"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BrowserProvider, Contract, formatEther, parseEther } from "ethers";
import { AMM_ABI, BSC_TESTNET, CONTRACT_ADDRESS } from "@/lib/contract";

declare global {
  interface Window {
    ethereum?: {
      request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
    };
  }
}

type MarketView = {
  id: number;
  question: string;
  yesPool: bigint;
  noPool: bigint;
  yesPriceBps: bigint;
  userYesShares: bigint;
  userNoShares: bigint;
};

const MARKET_IDS = [0, 1];

const formatShortAddress = (address: string) => `${address.slice(0, 6)}...${address.slice(-4)}`;

export default function Home() {
  const [account, setAccount] = useState<string>("");
  const [chainId, setChainId] = useState<number | null>(null);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);
  const [amountByMarket, setAmountByMarket] = useState<Record<number, string>>({ 0: "0.01", 1: "0.01" });
  const [markets, setMarkets] = useState<MarketView[]>([]);

  const ready = useMemo(() => Boolean(CONTRACT_ADDRESS), []);

  const getProvider = async () => {
    if (!window.ethereum) {
      throw new Error("MetaMask is not installed.");
    }
    return new BrowserProvider(window.ethereum);
  };

  const ensureBscNetwork = async () => {
    if (!window.ethereum) {
      throw new Error("MetaMask is not installed.");
    }

    try {
      await window.ethereum.request({
        method: "wallet_switchEthereumChain",
        params: [{ chainId: BSC_TESTNET.chainIdHex }],
      });
    } catch (error: unknown) {
      const switchError = error as { code?: number };
      if (switchError.code === 4902) {
        await window.ethereum.request({
          method: "wallet_addEthereumChain",
          params: [
            {
              chainId: BSC_TESTNET.chainIdHex,
              chainName: BSC_TESTNET.chainName,
              nativeCurrency: BSC_TESTNET.nativeCurrency,
              rpcUrls: BSC_TESTNET.rpcUrls,
              blockExplorerUrls: BSC_TESTNET.blockExplorerUrls,
            },
          ],
        });
      } else {
        throw error;
      }
    }
  };

  const connectWallet = async () => {
    setBusy(true);
    setStatus("");
    try {
      if (!ready) {
        throw new Error("Set NEXT_PUBLIC_CONTRACT_ADDRESS in .env.local first.");
      }

      const provider = await getProvider();
      await ensureBscNetwork();

      const accounts = (await provider.send("eth_requestAccounts", [])) as string[];
      const network = await provider.getNetwork();
      setAccount(accounts[0] || "");
      setChainId(Number(network.chainId));
      setStatus("Wallet connected.");
      await loadMarkets(accounts[0] || "");
    } catch (error) {
      setStatus((error as Error).message || "Failed to connect wallet.");
    } finally {
      setBusy(false);
    }
  };

  const loadMarkets = useCallback(async (walletAddress?: string) => {
    if (!ready || !window.ethereum) {
      return;
    }

    const provider = await getProvider();
    const contract = new Contract(CONTRACT_ADDRESS, AMM_ABI, provider);
    const target = walletAddress || account;

    const rows = await Promise.all(
      MARKET_IDS.map(async (marketId) => {
        const [question, yesPool, noPool, yesPriceBps] = await contract.getMarket(marketId);
        let userYesShares = 0n;
        let userNoShares = 0n;

        if (target) {
          [userYesShares, userNoShares] = await contract.getUserShares(marketId, target);
        }

        return {
          id: marketId,
          question,
          yesPool,
          noPool,
          yesPriceBps,
          userYesShares,
          userNoShares,
        } as MarketView;
      })
    );

    setMarkets(rows);
  }, [account, ready]);

  const runTrade = async (marketId: number, action: "add" | "yes" | "no") => {
    setBusy(true);
    setStatus("");

    try {
      const amountRaw = amountByMarket[marketId];
      if (!amountRaw) {
        throw new Error("Enter an amount in tBNB.");
      }

      const provider = await getProvider();
      const signer = await provider.getSigner();
      const contract = new Contract(CONTRACT_ADDRESS, AMM_ABI, signer);
      const amount = parseEther(amountRaw);

      let tx;
      if (action === "add") {
        tx = await contract.addLiquidity(marketId, { value: amount });
      } else if (action === "yes") {
        tx = await contract.buyYes(marketId, { value: amount });
      } else {
        tx = await contract.buyNo(marketId, { value: amount });
      }

      await tx.wait();
      setStatus(`Confirmed ${action.toUpperCase()} on market ${marketId}.`);
      await loadMarkets();
    } catch (error) {
      setStatus((error as Error).message || "Transaction failed.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    loadMarkets().catch(() => undefined);
  }, [loadMarkets]);

  return (
    <main className="mx-auto min-h-screen max-w-6xl p-6 md:p-10">
      <section className="mb-6 rounded-xl border border-black/10 p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Prediction Market Demo (AMM)</h1>
            <p className="text-sm opacity-80">Network: BNB Smart Chain Testnet ({BSC_TESTNET.chainIdDec})</p>
          </div>
          <button
            onClick={connectWallet}
            disabled={busy}
            className="rounded-lg border border-black/20 px-4 py-2 text-sm font-medium hover:bg-black/5 disabled:opacity-50"
          >
            {account ? `Connected: ${formatShortAddress(account)}` : "Connect MetaMask"}
          </button>
        </div>
        <p className="mt-2 text-sm opacity-75">
          AMM pricing uses pool ratio. Add liquidity or buy YES/NO using tBNB on testnet.
        </p>
        {!ready && (
          <p className="mt-2 text-sm text-red-600">Set NEXT_PUBLIC_CONTRACT_ADDRESS in .env.local to enable transactions.</p>
        )}
        {chainId !== null && chainId !== BSC_TESTNET.chainIdDec && (
          <p className="mt-2 text-sm text-red-600">Wrong chain selected in wallet. Switch to BNB Smart Chain Testnet.</p>
        )}
        {status && <p className="mt-2 text-sm">{status}</p>}
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {markets.map((market) => {
          const amount = amountByMarket[market.id] || "";
          const yesPercent = Number(market.yesPriceBps) / 100;
          const noPercent = 100 - yesPercent;

          return (
            <article key={market.id} className="rounded-xl border border-black/10 p-4">
              <h2 className="mb-2 text-lg font-semibold">Market {market.id + 1}</h2>
              <p className="mb-4 text-sm opacity-90">{market.question}</p>

              <div className="space-y-1 text-sm">
                <p>YES pool: {formatEther(market.yesPool)} tBNB</p>
                <p>NO pool: {formatEther(market.noPool)} tBNB</p>
                <p>YES price: {yesPercent.toFixed(2)}% | NO price: {noPercent.toFixed(2)}%</p>
                <p>Your YES shares: {formatEther(market.userYesShares)}</p>
                <p>Your NO shares: {formatEther(market.userNoShares)}</p>
              </div>

              <input
                className="mt-4 w-full rounded-lg border border-black/20 px-3 py-2 text-sm"
                value={amount}
                onChange={(event) =>
                  setAmountByMarket((prev) => ({
                    ...prev,
                    [market.id]: event.target.value,
                  }))
                }
                placeholder="Amount in tBNB"
              />

              <div className="mt-3 grid grid-cols-3 gap-2">
                <button
                  onClick={() => runTrade(market.id, "add")}
                  disabled={busy || !ready}
                  className="rounded-lg border border-black/20 px-2 py-2 text-xs font-medium hover:bg-black/5 disabled:opacity-50"
                >
                  Add Liquidity
                </button>
                <button
                  onClick={() => runTrade(market.id, "yes")}
                  disabled={busy || !ready}
                  className="rounded-lg border border-black/20 px-2 py-2 text-xs font-medium hover:bg-black/5 disabled:opacity-50"
                >
                  Buy YES
                </button>
                <button
                  onClick={() => runTrade(market.id, "no")}
                  disabled={busy || !ready}
                  className="rounded-lg border border-black/20 px-2 py-2 text-xs font-medium hover:bg-black/5 disabled:opacity-50"
                >
                  Buy NO
                </button>
              </div>
            </article>
          );
        })}
      </section>
    </main>
  );
}
