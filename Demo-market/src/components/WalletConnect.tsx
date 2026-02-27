"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Eip1193Provider = {
  request: (args: { method: string; params?: unknown[] | object }) => Promise<unknown>;
  on: (event: string, listener: (...args: unknown[]) => void) => void;
  removeListener: (event: string, listener: (...args: unknown[]) => void) => void;
};

type EthereumWindow = Window & {
  ethereum?: Eip1193Provider;
};

function shortAddress(address: string) {
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

export default function WalletConnect() {
  const [address, setAddress] = useState<string | null>(null);
  const [chainId, setChainId] = useState<string | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const provider = useMemo(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    return (window as EthereumWindow).ethereum;
  }, []);

  const refreshConnection = useCallback(async () => {
    if (!provider) {
      return;
    }

    const accounts = (await provider.request({ method: "eth_accounts" })) as string[];
    setAddress(accounts[0] ?? null);

    const currentChain = (await provider.request({ method: "eth_chainId" })) as string;
    setChainId(currentChain);
  }, [provider]);

  const connectWallet = useCallback(async () => {
    if (!provider) {
      setError("MetaMask is not installed. Please install the extension and refresh.");
      return;
    }

    setError(null);
    setIsConnecting(true);

    try {
      const accounts = (await provider.request({ method: "eth_requestAccounts" })) as string[];
      setAddress(accounts[0] ?? null);
      const currentChain = (await provider.request({ method: "eth_chainId" })) as string;
      setChainId(currentChain);
    } catch (requestError) {
      if (
        typeof requestError === "object" &&
        requestError !== null &&
        "code" in requestError &&
        (requestError as { code?: number }).code === 4001
      ) {
        setError("Connection request was rejected in MetaMask.");
      } else {
        setError("Failed to connect wallet. Please try again.");
      }
    } finally {
      setIsConnecting(false);
    }
  }, [provider]);

  useEffect(() => {
    if (!provider) {
      return;
    }

    void refreshConnection();

    const onAccountsChanged = (accounts: unknown) => {
      if (Array.isArray(accounts) && typeof accounts[0] === "string") {
        setAddress(accounts[0] ?? null);
        return;
      }

      setAddress(null);
    };

    const onChainChanged = (nextChainId: unknown) => {
      if (typeof nextChainId === "string") {
        setChainId(nextChainId);
      }
    };

    provider.on("accountsChanged", onAccountsChanged);
    provider.on("chainChanged", onChainChanged);

    return () => {
      provider.removeListener("accountsChanged", onAccountsChanged);
      provider.removeListener("chainChanged", onChainChanged);
    };
  }, [provider, refreshConnection]);

  const isConnected = Boolean(address);

  return (
    <div className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="text-xl font-semibold">Wallet Connection</h2>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        Connect MetaMask to use on-chain features.
      </p>

      <button
        type="button"
        onClick={connectWallet}
        disabled={isConnecting}
        className="mt-6 w-full rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
      >
        {isConnecting ? "Connecting..." : isConnected ? "Reconnect MetaMask" : "Connect MetaMask"}
      </button>

      <div className="mt-4 rounded-lg border border-zinc-200 p-4 text-sm dark:border-zinc-800">
        <p>
          <span className="font-medium">Status:</span> {isConnected ? "Connected" : "Not connected"}
        </p>
        <p className="mt-1">
          <span className="font-medium">Account:</span> {address ? shortAddress(address) : "-"}
        </p>
        <p className="mt-1">
          <span className="font-medium">Chain ID:</span> {chainId ?? "-"}
        </p>
      </div>

      {error ? <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p> : null}
    </div>
  );
}
