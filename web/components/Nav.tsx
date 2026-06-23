import Link from "next/link";

export function Nav() {
  return (
    <header className="sticky top-0 z-20 border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-6">
        <Link href="/" className="font-semibold tracking-tight">
          SME<span className="text-emerald-400">Scanner</span>
        </Link>
        <nav className="flex gap-5 text-sm text-zinc-400">
          <Link href="/" className="transition-colors hover:text-zinc-100">
            Rankings
          </Link>
          <Link href="/red-flags" className="transition-colors hover:text-zinc-100">
            Red Flags
          </Link>
          <Link href="/bulk-deals" className="transition-colors hover:text-zinc-100">
            Bulk Deals
          </Link>
        </nav>
        <span className="ml-auto hidden text-xs text-zinc-500 sm:block">
          NSE Emerge · BSE SME · fundamentals-first
        </span>
      </div>
    </header>
  );
}
