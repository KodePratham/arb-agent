import Link from "next/link";

export default function SixMonthsPlanPage() {
  return (
    <main className="mx-auto min-h-screen max-w-5xl bg-orange-50 p-6 text-zinc-950 md:p-10">
      <section className="rounded-3xl border-2 border-zinc-950 bg-yellow-100 p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-3xl font-black tracking-tight">Six Months Plan</h1>
          <div className="flex flex-wrap gap-2">
            <Link href="/" className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px">
              Back to Market
            </Link>
            <Link href="/demo-api" className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px">
              Demo API
            </Link>
          </div>
        </div>
        <p className="mt-3 text-sm font-medium">
          Detailed roadmap to transform BNB prediction markets through a Mega-API layer, autonomous arbitrage agents,
          and a low-latency C++ pricing-balance engine.
        </p>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">Month 1: Mega-API foundation</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
          <li>Unify all supported market providers into one normalized schema and stable endpoint contracts.</li>
          <li>Ship secure key management and one developer-facing API key for all integrated BNB prediction sources.</li>
          <li>Add quality scoring for each source feed: freshness, consistency, and event-resolution alignment.</li>
          <li>Publish reference SDKs for Python and TypeScript so builders integrate once and scale faster.</li>
        </ul>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">Month 2: Market intelligence and parity graph</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
          <li>Build a cross-platform event graph to map semantically similar markets to one canonical event ID.</li>
          <li>Add confidence-weighted similarity matching to reduce false positive arbitrage candidates.</li>
          <li>Track historical divergence and convergence windows to improve spread timing for agents.</li>
          <li>Launch a parity monitor dashboard for operators, market makers, and ecosystem partners.</li>
        </ul>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">Month 3: Arbitrage-agent toolkit</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
          <li>Expose strategy-ready streams: spread deltas, liquidity depth, slippage estimates, and execution risk.</li>
          <li>Release a plug-and-play arbitrage-agent template that can subscribe to Mega-API alerts.</li>
          <li>Add route simulation for best execution paths across market venues and contract rails.</li>
          <li>Introduce guardrails: max exposure, market halt rules, and volatility-aware position sizing.</li>
        </ul>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">Month 4: C++ engine optimization for price balance</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
          <li>Optimize matcher hot paths and memory layout for lower end-to-end signal latency.</li>
          <li>Add continuous fair-value estimation and imbalance scoring per market cluster.</li>
          <li>Emit balancing signals to agents so they can compress extreme spreads earlier.</li>
          <li>Benchmark stability under burst updates and maintain deterministic ranked outputs.</li>
        </ul>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">Month 5: BNB ecosystem rollout</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
          <li>Onboard ecosystem teams: wallets, analytics platforms, market makers, and trading bots.</li>
          <li>Publish ecosystem grants playbook for teams building on top of the Mega-API.</li>
          <li>Launch transparent reliability metrics and service-level reporting for production trust.</li>
          <li>Support partner-specific routing profiles for advanced arbitrage-agent orchestration.</li>
        </ul>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">Month 6: Production-grade market balancing network</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
          <li>Enable autonomous balancing loops: detect dislocations, execute hedged trades, verify convergence.</li>
          <li>Add settlement feedback into model tuning to keep long-run pricing quality high.</li>
          <li>Expand coverage to more prediction categories while preserving canonical compatibility.</li>
          <li>Publish ecosystem impact report focused on tighter spreads, deeper liquidity, and fairer market prices.</li>
        </ul>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">Expected transformation outcomes</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
          <li>Mega-API reduces integration overhead and unlocks broader BNB prediction market participation.</li>
          <li>Arbitrage agents become safer and more efficient through standardized, high-quality market signals.</li>
          <li>The C++ engine helps keep prices balanced by continuously surfacing actionable cross-market mispricing.</li>
        </ul>
      </section>
    </main>
  );
}
