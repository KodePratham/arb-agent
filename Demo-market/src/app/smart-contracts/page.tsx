import Link from "next/link";

export default function SmartContractsPage() {
  return (
    <main className="mx-auto min-h-screen max-w-4xl bg-orange-50 p-6 text-zinc-950 md:p-10">
      <section className="rounded-3xl border-2 border-zinc-950 bg-yellow-100 p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-3xl font-black tracking-tight">Smart Contracts</h1>
          <div className="flex flex-wrap gap-2">
            <Link href="/" className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px">
              Back to Market
            </Link>
            <Link href="/docs" className="rounded-xl border-2 border-zinc-950 bg-white px-4 py-2 text-sm font-bold transition hover:-translate-y-px">
              Docs
            </Link>
          </div>
        </div>
        <p className="mt-3 text-sm font-medium">
          For hackathon delivery, we use smart contracts in both the core trading surface and demo flows to prove that market pricing,
          position accounting, and settlement logic can run on BNB Smart Chain testnet end-to-end.
        </p>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">How contracts are used in this project</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
          <li>
            <span className="font-black">Demo-market execution layer:</span> the BinaryPredictionAMM contract handles market creation,
            YES/NO position trading, resolution, and winner claims.
          </li>
          <li>
            <span className="font-black">Main engine integration path:</span> the C++ matcher finds spread opportunities, then execution
            tooling can route selected opportunities into on-chain transaction flow when live execution is enabled.
          </li>
          <li>
            <span className="font-black">Hackathon validation:</span> this setup validates arbitrage behavior, market-state transitions,
            and payout correctness before scaling to broader production integrations.
          </li>
        </ul>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">Pseudocode: BinaryPredictionAMM</h2>
        <p className="mt-3 text-sm font-medium">
          High-level flow used by the demo contract at <code>contracts/BinaryPredictionAMM.sol</code>.
        </p>
        <pre className="mt-3 overflow-x-auto rounded-2xl border-2 border-zinc-950 bg-zinc-950 p-4 text-xs font-medium text-zinc-100 md:text-sm">
{`STATE
  Market { question, yesPool, noPool, resolved, outcomeYes, totalYesShares, totalNoShares, finalPool, winningShares }
  markets[marketId]
  userYesShares[marketId][user]
  userNoShares[marketId][user]

INIT(feeBps)
  require feeBps < 10000
  save feeBps

createMarket(question, seed)
  onlyOwner
  require non-empty question
  require msg.value == seed
  split seed into yesPool and noPool
  mark market exists

addLiquidity(marketId)
  require market exists and not resolved
  split msg.value equally into yesPool/noPool

buyYes(marketId)
  require market active and has liquidity
  netIn = msg.value - fee
  sharesOut = cpmmOut(netIn, yesPool+virtual, noPool+virtual)
  update pools: yesPool += netIn, noPool -= sharesOut
  credit userYesShares

buyNo(marketId)
  mirror of buyYes
  update pools: noPool += netIn, yesPool -= sharesOut
  credit userNoShares

sellYes(marketId, sharesIn)
  require user has enough yes shares and market active
  amountOut = cpmmOut(sharesIn, noPool+virtual, yesPool+virtual)
  payout = amountOut - fee
  debit userYesShares
  update pools opposite of buyYes
  transfer payout to seller

sellNo(marketId, sharesIn)
  mirror of sellYes

resolveMarket(marketId, outcomeYes)
  onlyOwner
  mark resolved
  finalPool = yesPool + noPool
  winningShares = totalYesShares or totalNoShares (by outcome)

claimWinnings(marketId)
  require resolved and user has winning shares
  payout = finalPool * userWinningShares / winningShares
  zero-out user winning balance
  transfer payout

cpmmOut(amountIn, reserveIn, reserveOut)
  k = reserveIn * reserveOut
  newReserveIn = reserveIn + amountIn
  newReserveOut = k / newReserveIn
  return reserveOut - newReserveOut`}
        </pre>
      </section>

      <section className="mt-5 rounded-3xl border-2 border-zinc-950 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-black">Why this matters for BNB ecosystem builders</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm font-medium">
          <li>Deterministic on-chain settlement for prediction positions.</li>
          <li>Composable interfaces that downstream arbitrage agents can automate against.</li>
          <li>Faster iteration with testnet-first market simulations during hackathons.</li>
        </ul>
      </section>
    </main>
  );
}
