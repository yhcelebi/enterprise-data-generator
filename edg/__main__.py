"""Command line entry point: python -m edg --help"""

import argparse
import time
import zlib
from pathlib import Path

from . import detail
from .companies import BY_ID, COMPANIES
from .engine import CompanySim
from .output import iter_tables, shared_tables, write_tables
from .timeline import make_calendar


def main():
    ap = argparse.ArgumentParser(description="Generate synthetic enterprise data as Parquet.")
    ap.add_argument("--companies", default="all", help="comma-separated company ids, or 'all'")
    ap.add_argument("--scale", type=float, default=1.0, help="size multiplier (1.0 is the full ~60 GB set)")
    ap.add_argument("--first-year", type=int, default=1995)
    ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--out", default="out")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--detail", type=float, default=1.0, help="industry detail volume multiplier (0 = finance only)")
    ap.add_argument("--shared", action="store_true", help="also write shared tables (companies, macro, chart)")
    args = ap.parse_args()

    out = Path(args.out)
    if args.companies == "all":
        ids = [c.id for c in COMPANIES]
    elif args.companies == "none":
        ids = []
    else:
        ids = args.companies.split(",")
    if args.shared:
        write_tables(shared_tables(args.first_year, args.end), out)
    cal = make_calendar(args.first_year, args.end)
    for cid in ids:
        company = BY_ID[cid]
        if company.is_bank:
            print(f"{cid}: bank (its data is the other companies' bank_transactions, loans and cheques)")
            continue
        t0 = time.time()
        seed = args.seed * 1_000_003 + zlib.crc32(cid.encode())
        sim = CompanySim(company, cal, args.scale, seed, args.seed)
        sim.run()
        sizes = write_tables(iter_tables(sim), out, cid)
        sizes.update(detail.generate(sim, out, args.detail))
        rows = sum(r for r, _ in sizes.values())
        mb = sum(s for _, s in sizes.values()) / 1e6
        print(f"{cid}: {rows:,} rows, {mb:,.1f} MB in {time.time() - t0:,.0f}s", flush=True)


if __name__ == "__main__":
    main()
