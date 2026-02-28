"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { BrowserProvider, Contract, JsonRpcProvider, formatEther, parseEther } from "ethers";
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
  claimable: bigint;
  active: boolean;
  resolved: boolean;
  outcomeYes: boolean;
};

const REQUIRED_MARKETS = [0, 1];
const CHAD_TRADE_SIZE_TBNB = "0.01";

const formatShortAddress = (address: string) => `${address.slice(0, 6)}...${address.slice(-4)}`;

export default function Home() {
  const [account, setAccount] = useState<string>("");
  const [chainId, setChainId] = useState<number | null>(null);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [amountByMarket, setAmountByMarket] = useState<Record<number, string>>({ 0: "0.01", 1: "0.01" });
  const [markets, setMarkets] = useState<MarketView[]>([]);
  const [chadStatus, setChadStatus] = useState<string>("Inactive");
  const [spreadBps, setSpreadBps] = useState<number | null>(null);
  const [marketCount, setMarketCount] = useState<number>(0);

  const ready = useMemo(() => Boolean(CONTRACT_ADDRESS), []);
  const hasWallet = useMemo(() => (typeof window !== "undefined" ? Boolean(window.ethereum) : false), []);
  const bothMarketsActive = useMemo(() => markets.length === 2 && markets.every((market) => market.active), [markets]);
  const chadActive = useMemo(() => bothMarketsActive && chadStatus !== "Inactive" && chadStatus !== "Failed", [bothMarketsActive, chadStatus]);

  const getReadProvider = useCallback(() => new JsonRpcProvider(BSC_TESTNET.rpcUrls[0]), []);

  const getBrowserProvider = async () => {
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

  const loadMarkets = useCallback(async (walletAddress?: string) => {
    if (!ready) {
      return;
    }

    const provider = window.ethereum ? await getBrowserProvider() : getReadProvider();
    const contract = new Contract(CONTRACT_ADDRESS, AMM_ABI, provider);
    const target = walletAddress || account;

    const count = Number(await contract.marketCount());
    setMarketCount(count);

    const rows = await Promise.all(
      REQUIRED_MARKETS.map(async (marketId) => {
        if (count <= marketId) {
          return {
            id: marketId,
            question: "Market not deployed",
            yesPool: 0n,
            noPool: 0n,
            yesPriceBps: 5000n,
            userYesShares: 0n,
            userNoShares: 0n,
            claimable: 0n,
            active: false,
            resolved: false,
            outcomeYes: false,
          } as MarketView;
        }

        const [question, yesPool, noPool, yesPriceBps] = await contract.getMarket(marketId);
        const [resolved, outcomeYes] = await contract.getMarketStatus(marketId);

        let userYesShares = 0n;
        let userNoShares = 0n;
        let claimable = 0n;

        if (target) {
          [userYesShares, userNoShares] = await contract.getUserShares(marketId, target);
          claimable = await contract.getClaimable(marketId, target);
        }

        const active = question.length > 0 && yesPool > 0n && noPool > 0n && !resolved;

        return {
          id: marketId,
          question,
          yesPool,
          noPool,
          yesPriceBps,
          userYesShares,
          userNoShares,
          claimable,
          active,
          resolved,
          outcomeYes,
        } as MarketView;
      })
    );

    setMarkets(rows);
    const loadedSpread = Math.abs(Number(rows[0]?.yesPriceBps ?? 0n) - Number(rows[1]?.yesPriceBps ?? 0n));
    if (rows.length === 2) {
      setSpreadBps(loadedSpread);
    }
  }, [account, getReadProvider, ready]);

  const connectWallet = async () => {
    setBusy(true);
    setStatus("");

    try {
      if (!ready) {
        throw new Error("Set NEXT_PUBLIC_CONTRACT_ADDRESS in .env.local first.");
      }

      const provider = await getBrowserProvider();
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

  const refreshData = async () => {
    setIsRefreshing(true);
    setStatus("");
    try {
      await loadMarkets();
      setStatus("Market data refreshed.");
    } catch (error) {
      setStatus((error as Error).message || "Refresh failed.");
    } finally {
      setIsRefreshing(false);
    }
  };

  const runTrade = async (marketId: number, action: "add" | "yes" | "no") => {
    setBusy(true);
    setStatus("");

    try {
      const amountRaw = amountByMarket[marketId];
      if (!amountRaw) {
        throw new Error("Enter an amount in tBNB.");
      }

      const provider = await getBrowserProvider();
      await ensureBscNetwork();
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
      setStatus(`Confirmed ${action.toUpperCase()} on market ${marketId + 1}.`);
      await loadMarkets();
    } catch (error) {
      setStatus((error as Error).message || "Transaction failed.");
    } finally {
      setBusy(false);
    }
  };

  const claimWinnings = async (marketId: number) => {
    setBusy(true);
    setStatus("");

    try {
      if (!account) {
        throw new Error("Connect wallet first.");
      }

      const provider = await getBrowserProvider();
      await ensureBscNetwork();
      const signer = await provider.getSigner();
      const contract = new Contract(CONTRACT_ADDRESS, AMM_ABI, signer);

      const tx = await contract.claimWinnings(marketId);
      await tx.wait();
      setStatus(`Claimed winnings from market ${marketId + 1}.`);
      await loadMarkets();
    } catch (error) {
      setStatus((error as Error).message || "Claim failed.");
    } finally {
      setBusy(false);
    }
  };

  const activateChad = async () => {
    setBusy(true);
    setStatus("");

    try {
      if (!ready) {
        throw new Error("Set NEXT_PUBLIC_CONTRACT_ADDRESS in .env.local first.");
      }
      if (!account) {
        throw new Error("Connect wallet before activating Chad.");
      }
      if (!bothMarketsActive) {
        throw new Error("Both markets must be active before Chad can run.");
      }

      const provider = await getBrowserProvider();
      await ensureBscNetwork();
      const signer = await provider.getSigner();
      const contract = new Contract(CONTRACT_ADDRESS, AMM_ABI, signer);

      const [market0, market1] = await Promise.all([contract.getMarket(0), contract.getMarket(1)]);
      const yes0 = Number(market0[3]);
      const yes1 = Number(market1[3]);
      const currentSpread = Math.abs(yes0 - yes1);
      setSpreadBps(currentSpread);

      if (currentSpread < 50) {
        setChadStatus("Active (Monitoring)");
        setStatus("Chad is active and monitoring. Spread already tight.");
        return;
      }

      const tradeValue = parseEther(CHAD_TRADE_SIZE_TBNB);

      if (yes0 < yes1) {
        setChadStatus("Active (Trading)");
        const tx1 = await contract.buyYes(0, { value: tradeValue });
        await tx1.wait();
        const tx2 = await contract.buyNo(1, { value: tradeValue });
        await tx2.wait();
      } else {
        setChadStatus("Active (Trading)");
        const tx1 = await contract.buyYes(1, { value: tradeValue });
        await tx1.wait();
        const tx2 = await contract.buyNo(0, { value: tradeValue });
        await tx2.wait();
      }

      await loadMarkets();
      setChadStatus("Active");
      setStatus("Chad arbitrage completed successfully.");
    } catch (error) {
      setChadStatus("Failed");
      setStatus((error as Error).message || "Activate Chad failed.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    loadMarkets().catch(() => undefined);
  }, [loadMarkets]);

  useEffect(() => {
    if (bothMarketsActive && chadStatus === "Inactive") {
      setChadStatus("Active (Ready)");
    }
  }, [bothMarketsActive, chadStatus]);

  return (
    <main className="mx-auto min-h-screen max-w-6xl bg-orange-50 p-6 text-zinc-950 md:p-10">
      <section className="rounded-3xl border-2 border-zinc-950 bg-yellow-100 p-5 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-3xl font-black tracking-tight">ChadOnChain</h1>
            <p className="text-sm font-medium">BNB Smart Chain Testnet ({BSC_TESTNET.chainIdDec})</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/admin" className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px">
              Admin
            </Link>
            <button
              onClick={connectWallet}
              disabled={busy}
              className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px disabled:opacity-50"
            >
              {account ? `Connected: ${formatShortAddress(account)}` : "Connect MetaMask"}
            </button>
            <button
              onClick={refreshData}
              disabled={isRefreshing || busy || !ready}
              className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px disabled:opacity-50"
            >
              {isRefreshing ? "Refreshing..." : "Refresh"}
            </button>
            <button
              onClick={activateChad}
              disabled={busy || !ready || !bothMarketsActive}
              className="rounded-xl border-2 border-zinc-950 bg-lime-300 px-4 py-2 text-sm font-black transition hover:-translate-y-px disabled:opacity-50"
            >
              Activate Chad
            </button>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-2 text-sm md:grid-cols-3">
          <p className="rounded-xl border border-zinc-950 bg-white px-3 py-2 font-semibold">
            Both Markets: {bothMarketsActive ? "ACTIVE" : "INACTIVE"}
          </p>
          <p className="rounded-xl border border-zinc-950 bg-white px-3 py-2 font-semibold">
            Chad: {chadActive ? "ACTIVE" : chadStatus}
          </p>
          <p className="rounded-xl border border-zinc-950 bg-white px-3 py-2 font-semibold">
            Spread: {spreadBps === null ? "N/A" : `${(spreadBps / 100).toFixed(2)}%`}
          </p>
        </div>

        <p className="mt-3 text-sm font-medium">Chad trade size: {CHAD_TRADE_SIZE_TBNB} tBNB per leg.</p>
        <p className="mt-1 text-sm font-medium">Detected markets onchain: {marketCount}</p>

        {!hasWallet && <p className="mt-2 text-sm font-semibold">Showing markets in read-only mode. Install MetaMask to trade.</p>}
        {!ready && (
          <p className="mt-2 rounded-lg border border-red-700 bg-red-100 px-3 py-2 text-sm font-semibold text-red-800">
            Set NEXT_PUBLIC_CONTRACT_ADDRESS in .env.local to enable transactions.
          </p>
        )}
        {chainId !== null && chainId !== BSC_TESTNET.chainIdDec && (
          <p className="mt-2 rounded-lg border border-red-700 bg-red-100 px-3 py-2 text-sm font-semibold text-red-800">
            Wrong chain selected in wallet. Switch to BNB Smart Chain Testnet.
          </p>
        )}
        {status && <p className="mt-2 text-sm font-semibold">{status}</p>}
      </section>

      <section className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
        {markets.map((market) => {
          const amount = amountByMarket[market.id] || "";
          const yesPercent = Number(market.yesPriceBps) / 100;
          const noPercent = 100 - yesPercent;

          return (
            <article key={market.id} className="rounded-3xl border-2 border-zinc-950 bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-xl font-black">Market {market.id + 1}</h2>
                  <p className="mt-1 text-sm font-medium">{market.question}</p>
                </div>
                <span
                  className={`rounded-lg border px-2 py-1 text-xs font-black ${
                    market.resolved
                      ? "border-purple-700 bg-purple-100 text-purple-900"
                      : market.active
                        ? "border-emerald-700 bg-emerald-100 text-emerald-900"
                        : "border-red-700 bg-red-100 text-red-900"
                  }`}
                >
                  {market.resolved ? "RESOLVED" : market.active ? "ACTIVE" : "INACTIVE"}
                </span>
              </div>

              <div className="grid grid-cols-1 gap-2 text-sm font-medium">
                <p className="rounded-lg border border-zinc-950/30 bg-zinc-50 px-3 py-2">YES pool: {formatEther(market.yesPool)} tBNB</p>
                <p className="rounded-lg border border-zinc-950/30 bg-zinc-50 px-3 py-2">NO pool: {formatEther(market.noPool)} tBNB</p>
                <p className="rounded-lg border border-zinc-950/30 bg-zinc-50 px-3 py-2">
                  YES: {yesPercent.toFixed(2)}% | NO: {noPercent.toFixed(2)}%
                </p>

                <div className="rounded-lg border border-zinc-950/30 bg-zinc-50 p-3">
                  <div className="mb-2 flex justify-between text-xs font-bold">
                    <span>YES {yesPercent.toFixed(2)}%</span>
                    <span>NO {noPercent.toFixed(2)}%</span>
                  </div>
                  <div className="h-3 w-full overflow-hidden rounded-full border border-zinc-950/30 bg-white">
                    <div className="h-full bg-fuchsia-300" style={{ width: `${yesPercent}%` }} />
                  </div>
                </div>

                <p className="rounded-lg border border-zinc-950/30 bg-zinc-50 px-3 py-2">Your YES shares: {formatEther(market.userYesShares)}</p>
                <p className="rounded-lg border border-zinc-950/30 bg-zinc-50 px-3 py-2">Your NO shares: {formatEther(market.userNoShares)}</p>
                {market.resolved && (
                  <p className="rounded-lg border border-zinc-950/30 bg-zinc-50 px-3 py-2">
                    Final result: {market.outcomeYes ? "YES won" : "NO won"}
                  </p>
                )}
                {account && (
                  <p className="rounded-lg border border-zinc-950/30 bg-zinc-50 px-3 py-2">
                    Claimable: {formatEther(market.claimable)} tBNB
                  </p>
                )}
              </div>

              <input
                className="mt-4 w-full rounded-xl border-2 border-zinc-950 px-3 py-2 text-sm font-semibold"
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
                  disabled={busy || !ready || !market.active || !account}
                  className="rounded-xl border-2 border-zinc-950 bg-white px-2 py-2 text-xs font-black transition hover:-translate-y-px disabled:opacity-50"
                >
                  Add
                </button>
                <button
                  onClick={() => runTrade(market.id, "yes")}
                  disabled={busy || !ready || !market.active || !account}
                  className="rounded-xl border-2 border-zinc-950 bg-fuchsia-200 px-2 py-2 text-xs font-black transition hover:-translate-y-px disabled:opacity-50"
                >
                  Buy YES
                </button>
                <button
                  onClick={() => runTrade(market.id, "no")}
                  disabled={busy || !ready || !market.active || !account}
                  className="rounded-xl border-2 border-zinc-950 bg-cyan-200 px-2 py-2 text-xs font-black transition hover:-translate-y-px disabled:opacity-50"
                >
                  Buy NO
                </button>
              </div>

              {market.resolved && account && (
                <button
                  onClick={() => claimWinnings(market.id)}
                  disabled={busy || market.claimable === 0n}
                  className="mt-3 w-full rounded-xl border-2 border-zinc-950 bg-lime-200 px-3 py-2 text-sm font-black transition hover:-translate-y-px disabled:opacity-50"
                >
                  Claim Winnings
                </button>
              )}
            </article>
          );
        })}
      </section>
    </main>
  );
}
