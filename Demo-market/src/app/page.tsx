import WalletConnect from "@/components/WalletConnect";

export default function Home() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 px-6 py-16 font-sans dark:bg-black">
      <main className="flex w-full max-w-3xl flex-col items-center gap-10">
        <section className="text-center">
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 sm:text-4xl">
            Demo Market dApp
          </h1>
          <p className="mt-3 text-zinc-600 dark:text-zinc-400">
            Next.js app initialized with Bun and MetaMask wallet connection.
          </p>
        </section>
        <WalletConnect />
      </main>
    </div>
  );
}
