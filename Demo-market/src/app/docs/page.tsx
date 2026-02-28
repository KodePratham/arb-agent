import Link from "next/link";

export default function DocsPage() {
  return (
    <main className="mx-auto min-h-screen max-w-4xl bg-orange-50 p-6 text-zinc-950 md:p-10">
      <section className="rounded-3xl border-2 border-zinc-950 bg-yellow-100 p-6 shadow-sm">
        <h1 className="text-3xl font-black tracking-tight">ChadOnChain Docs</h1>
        <p className="mt-3 text-sm font-medium">
          This demo app is the UI companion to our real arbitrage engine. We built it during the hackathon because external
          APIs and stable parsing signals were limited, and we still needed to validate end-to-end arbitrage behavior fast.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link
            href="/"
            className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px"
          >
            Back to Market
          </Link>
          <Link
            href="/demo-api"
            className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px"
          >
            Demo API
          </Link>
          <Link
            href="/admin"
            className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px"
          >
            Admin
          </Link>
          <Link
            href="/smart-contracts"
            className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px"
          >
            Smart Contracts
          </Link>
          <Link
            href="/six-months-plan"
            className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px"
          >
            Six Months Plan
          </Link>
        </div>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">How the real engine works</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm font-medium">
          <li>
            <span className="font-black">Ingest from multiple market sources:</span> Python adapters fetch raw payloads from
            different APIs with inconsistent shapes.
          </li>
          <li>
            <span className="font-black">Parse and normalize with LLM assistance:</span> local Ollama parsing maps noisy text,
            rules, and metadata into one canonical schema.
          </li>
          <li>
            <span className="font-black">Persist canonical snapshots:</span> normalized data is written into JSON snapshots that
            the matcher can load deterministically.
          </li>
          <li>
            <span className="font-black">Run low-latency C++ matching:</span> the engine scans for cross-platform overlaps,
            computes spreads, and scores opportunities in memory.
          </li>
          <li>
            <span className="font-black">Emit executable opportunities:</span> results are exported to <code>arbs.json</code>
            for dry run evaluation or controlled execution.
          </li>
          <li>
            <span className="font-black">Optional on-chain execution:</span> execution tooling can route opportunities through
            contracts when explicit live mode is enabled.
          </li>
        </ol>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">What this demo validates</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
          <li>Two similar markets can diverge in price and create measurable spread.</li>
          <li>An arbitrage loop can hedge exposure by buying YES on one market and NO on the other.</li>
          <li>Lifecycle states (active, resolved, claimable) can be observed clearly in one UI.</li>
          <li>Traders and judges can inspect behavior without waiting on full third-party API reliability.</li>
        </ul>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">Why we use only this smart contract set</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
          <li>
            <span className="font-black">Single-contract scope:</span> the demo uses only <code>BinaryPredictionAMM.sol</code> so all
            core actions (create market, buy/sell, resolve, claim) are transparent in one place.
          </li>
          <li>
            <span className="font-black">Lower integration risk:</span> fewer contract dependencies means fewer failure points during
            hackathon deployment and wallet interaction testing.
          </li>
          <li>
            <span className="font-black">Faster auditability:</span> judges and contributors can verify pricing and settlement rules without
            tracing cross-contract call graphs.
          </li>
          <li>
            <span className="font-black">MVP fit:</span> advanced modules (oracle adapters, upgrade proxies, LP share tokens) are intentionally
            excluded because they are not required to validate arbitrage behavior in this demo.
          </li>
          <li>
            <span className="font-black">Planned extensibility:</span> once core behavior is stable, additional contracts can be added behind
            clear interfaces instead of shipping unnecessary complexity now.
          </li>
        </ul>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">Engine and repo references</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
          <li>
            Root architecture and setup: <code>README.md</code>
          </li>
          <li>
            Ingestion and parser flow: <code>Ingestion/</code>
          </li>
          <li>
            Canonical schema: <code>Data/schemas.py</code>
          </li>
          <li>
            Matching core: <code>Engine/src/</code>
          </li>
          <li>
            Execution path: <code>Execution/run_arb.py</code>
          </li>
        </ul>
      </section>
    </main>
  );
}
