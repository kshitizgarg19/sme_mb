import { BulkDealsTable } from "@/components/BulkDealsTable";

export const dynamic = "force-static";

export default function BulkDealsPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-zinc-100">Bulk &amp; Block Deals</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Latest NSE session. ⭐ = marquee investor (Jhunjhunwala, Kedia, Kacholia, Mukul Agrawal, Dolly Khanna…);
          green <span className="text-emerald-300">SME</span> tag = in our scanned universe. Where the big money is moving.
        </p>
      </div>
      <BulkDealsTable />
    </div>
  );
}
