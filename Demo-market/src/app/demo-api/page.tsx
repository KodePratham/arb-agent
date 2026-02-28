"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type DemoApiRow = {
  timestamp: string;
  platform: string;
  market_id: string;
  url: string;
  event_name: string;
  last_price: string;
  volume_24h: string;
  liquidity: string;
  open_interest: string;
  spread: string;
};

type DemoApiResponse = {
  ok: boolean;
  rows: DemoApiRow[];
  error?: string;
};

const prettifyEventName = (value: string) => value.replaceAll("_", " ");

export default function DemoApiPage() {
  const [rows, setRows] = useState<DemoApiRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [apiKeyPopupOpen, setApiKeyPopupOpen] = useState(false);

  useEffect(() => {
    const loadRows = async () => {
      setLoading(true);
      setStatus("");

      try {
        const response = await fetch("/api/demo-api", { cache: "no-store" });
        const data = (await response.json()) as DemoApiResponse;

        if (!response.ok || !data.ok) {
          throw new Error(data.error || "Failed to load demo API data.");
        }

        setRows(data.rows || []);
      } catch (error) {
        setStatus((error as Error).message || "Failed to load demo API data.");
      } finally {
        setLoading(false);
      }
    };

    void loadRows();
  }, []);

  const filteredRows = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
      return rows;
    }

    return rows.filter((row) =>
      Object.values(row).some((value) => value.toLowerCase().includes(normalizedQuery))
    );
  }, [query, rows]);

  return (
    <main className="mx-auto min-h-screen max-w-7xl bg-orange-50 p-6 text-zinc-950 md:p-10">
      <section className="rounded-3xl border-2 border-zinc-950 bg-yellow-100 p-5 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-3xl font-black tracking-tight">Demo API</h1>
            <p className="mt-1 text-sm font-medium">Mock market feed from demo-market-app/mock.csv</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/" className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px">
              Back to Market
            </Link>
            <button
              onClick={() => setApiKeyPopupOpen(true)}
              className="rounded-xl border-2 border-zinc-950 bg-lime-300 px-4 py-2 text-sm font-black transition hover:-translate-y-px"
            >
              Get API Key
            </button>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2 rounded-xl border-2 border-zinc-950 bg-white px-3 py-2">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="h-4 w-4"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search markets by id, platform, event, URL, or any field"
            className="w-full bg-transparent text-sm font-semibold outline-none"
          />
        </div>

        <p className="mt-2 text-sm font-medium">Results: {filteredRows.length}</p>
        {status && <p className="mt-2 text-sm font-semibold text-red-800">{status}</p>}
      </section>

      <section className="mt-5 overflow-hidden rounded-3xl border-2 border-zinc-950 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-left text-sm">
            <thead className="bg-zinc-100">
              <tr>
                <th className="border-b border-zinc-300 px-3 py-2 font-black">Timestamp</th>
                <th className="border-b border-zinc-300 px-3 py-2 font-black">Platform</th>
                <th className="border-b border-zinc-300 px-3 py-2 font-black">Market ID</th>
                <th className="border-b border-zinc-300 px-3 py-2 font-black">Event</th>
                <th className="border-b border-zinc-300 px-3 py-2 font-black">Last Price</th>
                <th className="border-b border-zinc-300 px-3 py-2 font-black">Volume 24h</th>
                <th className="border-b border-zinc-300 px-3 py-2 font-black">Liquidity</th>
                <th className="border-b border-zinc-300 px-3 py-2 font-black">Open Interest</th>
                <th className="border-b border-zinc-300 px-3 py-2 font-black">Spread</th>
                <th className="border-b border-zinc-300 px-3 py-2 font-black">URL</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={10} className="px-3 py-4 text-center font-semibold">
                    Loading demo API data...
                  </td>
                </tr>
              )}
              {!loading && filteredRows.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-3 py-4 text-center font-semibold">
                    No markets found for your search.
                  </td>
                </tr>
              )}
              {!loading &&
                filteredRows.map((row, index) => (
                  <tr key={`${row.timestamp}-${row.market_id}-${index}`} className="odd:bg-white even:bg-zinc-50">
                    <td className="border-b border-zinc-200 px-3 py-2 font-medium">{row.timestamp}</td>
                    <td className="border-b border-zinc-200 px-3 py-2 font-medium">{row.platform}</td>
                    <td className="border-b border-zinc-200 px-3 py-2 font-medium">{row.market_id}</td>
                    <td className="border-b border-zinc-200 px-3 py-2 font-medium">{prettifyEventName(row.event_name)}</td>
                    <td className="border-b border-zinc-200 px-3 py-2 font-medium">{row.last_price}</td>
                    <td className="border-b border-zinc-200 px-3 py-2 font-medium">{row.volume_24h}</td>
                    <td className="border-b border-zinc-200 px-3 py-2 font-medium">{row.liquidity}</td>
                    <td className="border-b border-zinc-200 px-3 py-2 font-medium">{row.open_interest}</td>
                    <td className="border-b border-zinc-200 px-3 py-2 font-medium">{row.spread}</td>
                    <td className="border-b border-zinc-200 px-3 py-2 font-medium">
                      <a href={row.url} target="_blank" rel="noreferrer" className="underline">
                        Open
                      </a>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>

      {apiKeyPopupOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/45 p-4">
          <div className="w-full max-w-lg rounded-3xl border-2 border-zinc-950 bg-yellow-100 p-5 shadow-sm">
            <h2 className="text-2xl font-black">Get API Key</h2>
            <p className="mt-3 text-sm font-medium">
              Demo key request received. For this hackathon demo, use <span className="font-black">DEMO-CHAD-API-KEY</span> in your integration.
            </p>
            <p className="mt-2 text-sm font-medium">Base endpoint: /api/demo-api</p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setApiKeyPopupOpen(false)}
                className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
