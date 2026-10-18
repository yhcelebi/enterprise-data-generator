"""Reconcile trade between dataset companies: both sides of every link.

    python scripts/check_interco.py OUT_DIR
"""

import sys
from pathlib import Path

import duckdb

out = Path(sys.argv[1])
con = duckdb.connect()
links = con.sql(f"select seller, buyer from read_parquet('{out}/shared/interco_links.parquet')").fetchall()
present = {p.name for p in out.iterdir() if (p / "invoices").exists()}
print(f"{'link':26s} {'seller':>7s} {'buyer':>7s} {'matched':>8s} {'amount diff':>11s} {'late':>5s} {'missing':>7s} "
      f"{'same pay day':>12s}")
bad = 0
for s, b in links:
    if s not in present or b not in present:
        continue
    r = lambda t, c: f"read_parquet('{out}/{c}/{t}/*.parquet')"
    row = con.sql(f"""
    with sc as (select code from {r('counterparties', s)} where interco_company = '{b}'),
         bc as (select code from {r('counterparties', b)} where interco_company = '{s}'),
         si as (select number, issued_on, gross from {r('invoices', s)} where direction = 'sale'
                and counterparty_code in (select code from sc)),
         bi as (select number, issued_on, gross_fx from {r('invoices', b)} where direction = 'purchase'
                and counterparty_code in (select code from bc)),
         sp as (select invoice_number, paid_on from {r('invoice_payments', s)} where direction = 'sale'
                and counterparty_code in (select code from sc)),
         bp as (select invoice_number, paid_on from {r('invoice_payments', b)} where direction = 'purchase'
                and counterparty_code in (select code from bc))
    select (select count(*) from si), (select count(*) from bi), count(*), max(abs(si.gross - bi.gross_fx)),
           sum((si.issued_on <> bi.issued_on)::int),
           (select count(*) from si where number not in (select number from bi)),
           (select avg((sp.paid_on = bp.paid_on)::int) from sp join bp using (invoice_number))
    from si join bi using (number)""").fetchone()
    ok = (row[3] or 0) < 0.01 and (row[6] is None or row[6] > 0.999)
    bad += not ok
    print(f"{s + ' -> ' + b:26s} {row[0]:7d} {row[1]:7d} {row[2]:8d} {row[3] or 0:11.2f} {row[4]:5d} {row[5]:7d} "
          f"{(row[6] or 0):12.4f} {'OK' if ok else 'FAIL'}")
sys.exit(1 if bad else 0)
