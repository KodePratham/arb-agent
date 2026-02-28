"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

export default function AdminPage() {
  const [adminUser, setAdminUser] = useState("");
  const [adminPass, setAdminPass] = useState("");
  const [outcomeYes, setOutcomeYes] = useState(true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  const submitResolution = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setStatus("");

    try {
      const response = await fetch("/api/admin/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          outcomeYes,
          adminUser,
          adminPass,
        }),
      });

      const data = (await response.json()) as { ok?: boolean; message?: string; txHashes?: string[]; error?: string };
      if (!response.ok || !data.ok) {
        throw new Error(data.error || "Resolution failed.");
      }

      const hashText = data.txHashes?.length ? ` Txs: ${data.txHashes.join(", ")}` : "";
      setStatus(`${data.message || "Resolved successfully."}${hashText}`);
    } catch (error) {
      setStatus((error as Error).message || "Resolution failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto min-h-screen max-w-2xl bg-orange-50 p-6 text-zinc-950 md:p-10">
      <section className="rounded-3xl border-2 border-zinc-950 bg-yellow-100 p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-2xl font-black">Admin Console</h1>
          <div className="flex flex-wrap gap-2">
            <Link href="/" className="rounded-xl border-2 border-zinc-950 bg-white px-3 py-2 text-sm font-bold">
              Back
            </Link>
            <Link href="/demo-api" className="rounded-xl border-2 border-zinc-950 bg-white px-3 py-2 text-sm font-bold">
              Demo API
            </Link>
          </div>
        </div>

        <p className="mb-4 text-sm font-medium">Set one final result for both similar markets.</p>

        <form onSubmit={submitResolution} className="space-y-3">
          <input
            value={adminUser}
            onChange={(event) => setAdminUser(event.target.value)}
            placeholder="Admin user"
            className="w-full rounded-xl border-2 border-zinc-950 px-3 py-2 text-sm font-semibold"
            required
          />

          <input
            type="password"
            value={adminPass}
            onChange={(event) => setAdminPass(event.target.value)}
            placeholder="Admin password"
            className="w-full rounded-xl border-2 border-zinc-950 px-3 py-2 text-sm font-semibold"
            required
          />

          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setOutcomeYes(true)}
              className={`rounded-xl border-2 border-zinc-950 px-3 py-2 text-sm font-black ${outcomeYes ? "bg-fuchsia-200" : "bg-white"}`}
            >
              YES Wins
            </button>
            <button
              type="button"
              onClick={() => setOutcomeYes(false)}
              className={`rounded-xl border-2 border-zinc-950 px-3 py-2 text-sm font-black ${!outcomeYes ? "bg-cyan-200" : "bg-white"}`}
            >
              NO Wins
            </button>
          </div>

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-xl border-2 border-zinc-950 bg-lime-300 px-3 py-2 text-sm font-black disabled:opacity-50"
          >
            {busy ? "Resolving..." : "Set Final Result (Both Markets)"}
          </button>
        </form>

        {status && <p className="mt-3 text-sm font-semibold">{status}</p>}
      </section>
    </main>
  );
}
