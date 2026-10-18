"""Consistency checks and yearly KPIs for generated companies.

    python scripts/validate.py OUT_DIR [company ...]
"""

import sys
from pathlib import Path

import duckdb

out = Path(sys.argv[1])
con = duckdb.connect()


def table(name, company):
    return f"read_parquet('{out}/{company}/{name}/*.parquet')"


TABLES = ["consumer_sales", "store_daily_sales", "pos_receipts", "pos_receipt_lines", "flights", "tickets", "claims",
          "encounters", "invoices", "shipments", "stock_monthly", "invoice_lines", "production_orders"]
SALES = "(select * from {invoices} where direction = 'sale')"
# Each check returns the largest absolute difference; anything above one cent fails.
DETAIL_CHECKS = [
    ("duplicate sales invoice numbers", "select count(*) - count(distinct number) from " + SALES),
    ("store days vs ledger consumer sales", """select max(abs(coalesce(a.g, 0) - b.gross)) from {consumer_sales} b
        left join (select date, sum(gross) g from {store_daily_sales} group by 1) a using (date)"""),
    ("receipts vs store days", """select max(abs(a.g - b.gross)) from (select store_id, date, sum(gross) g
        from {pos_receipts} group by all) a join {store_daily_sales} b using (store_id, date)"""),
    ("receipt lines vs receipts", """select max(abs(a.g - b.gross)) from (select receipt_id, sum(amount) g
        from {pos_receipt_lines} group by 1) a join {pos_receipts} b using (receipt_id)"""),
    ("flights vs ledger ticket sales", """select max(abs(coalesce(a.r, 0) - b.gross)) from {consumer_sales} b
        left join (select date, sum(ticket_revenue) r from {flights} group by 1) a using (date)"""),
    ("tickets vs flights", """select max(abs(a.f - b.ticket_revenue)) from (select flight_id, sum(fare) f
        from {tickets} group by 1) a join {flights} b using (flight_id)"""),
    ("claims vs insurer invoices", """select max(abs(a.s - b.net)) from (select invoice_number, sum(approved_amount) s
        from {claims} group by 1) a join """ + SALES + """ b on a.invoice_number = b.number"""),
    ("self-pay encounters vs ledger", """select max(abs(coalesce(a.s, 0) - b.gross)) from {consumer_sales} b
        left join (select admit_date date, sum(charge) s from {encounters} where payer = 'self-pay' group by 1) a
        using (date)"""),
    ("shipments vs invoices", """select max(abs(a.s - b.net)) from (select invoice_number, sum(revenue) s
        from {shipments} group by 1) a join """ + SALES + """ b on a.invoice_number = b.number"""),
    ("stock identity", "select max(abs(opening_qty + produced_qty - sold_qty - closing_qty)) from {stock_monthly}"),
    ("stock sold vs invoice lines", """select max(abs(s.q - l.q)) from (select period, sum(sold_qty) q
        from {stock_monthly} group by 1) s join (select strftime(issued_on, '%Y-%m') period, sum(quantity) q
        from {invoice_lines} group by 1) l using (period)"""),
    ("production orders vs plan", """select max(abs(o.q - s.q)) from (select strftime(start_time, '%Y-%m') period,
        product_id, sum(good_qty) q from {production_orders} group by all) o join (select period, product_id,
        produced_qty q from {stock_monthly}) s using (period, product_id)"""),
]

companies = sys.argv[2:] or sorted(p.name for p in out.iterdir() if (p / "trial_balance").exists())
failures = 0
for c in companies:
    print(f"\n=== {c}")
    gl, tb, bank = table("gl_journal_lines", c), table("trial_balance", c), table("bank_transactions", c)

    unbalanced = con.sql(f"""select count(*) from (select entry_id, sum(debit) - sum(credit) d from {gl}
                             group by entry_id having abs(d) > 0.02)""").fetchone()[0]
    tb_diff = con.sql(f"""select max(abs(d)) from (select period, sum(debit_balance) - sum(credit_balance) d
                          from {tb} where level = 'main' group by period)""").fetchone()[0]
    bank_diff = con.sql(f"""
        with b as (select strftime(booked_on, '%Y-%m') period, last(balance_after order by booked_on, reference) bal
                   from {bank} group by 1),
             t as (select period, debit_balance - credit_balance bal from {tb}
                   where level = 'main' and tdhp_code = '102')
        select max(abs(b.bal - t.bal)) from b join t using (period)""").fetchone()[0]
    ok = unbalanced == 0 and tb_diff < 1 and bank_diff < 1
    failures += not ok
    print(f"unbalanced entries: {unbalanced} | trial balance max diff: {tb_diff:,.2f} | "
          f"bank vs ledger max diff: {bank_diff:,.2f} -> {'OK' if ok else 'FAIL'}")
    detail_fail = []
    for name, sql in DETAIL_CHECKS:
        needed = [t for t in TABLES if "{" + t + "}" in sql]
        if not all((out / c / t).exists() for t in needed):
            continue
        value = con.sql(sql.format(**{t: table(t, c) for t in needed})).fetchone()[0] or 0
        if abs(value) > 0.01:
            detail_fail.append(f"{name}={value:,.2f}")
        print(f"  detail: {name}: {value:,.4f}")
    if detail_fail:
        failures += 1
        print("  detail checks FAIL:", ", ".join(detail_fail))

    kpi = con.sql(f"""
        with dec as (select * from {tb} where level = 'main' and period like '%-12'
                     or (level = 'main' and period = (select max(period) from {tb}))),
             y as (select left(period, 4)::int yr, tdhp_code a,
                          sum(ytd_credit - ytd_debit) cr, sum(ytd_debit - ytd_credit) dr from dec group by 1, 2)
        select yr,
               sum(case when a in ('600','601') then cr else 0 end) - sum(case when a in ('610','611') then dr else 0 end) net_sales,
               sum(case when left(a,2) = '62' then dr else 0 end) cogs,
               sum(case when left(a,2) = '63' then dr else 0 end) opex,
               sum(case when a = '660' then dr else 0 end) interest,
               sum(case when left(a,2) = '10' then dr else 0 end) cash,
               sum(case when a in ('120','128') then dr else 0 end) receivables,
               sum(case when left(a,2) = '15' then dr else 0 end) inventory,
               sum(case when a = '300' then cr else 0 end) debt,
               sum(case when left(a,1) = '5' then cr else 0 end) equity_ex_result
        from y group by yr order by yr""").df()
    kpi["gm%"] = (100 * (1 - kpi.cogs / kpi.net_sales)).round(1)
    kpi["opex%"] = (100 * kpi.opex / kpi.net_sales).round(1)
    kpi["dso"] = (kpi.receivables / kpi.net_sales * 365).round(0)
    heads = con.sql(f"""select left(period,4)::int yr, count(distinct employee_id) employees
                        from {table('payroll_lines', c)} where period like '%-12' group by 1""").df()
    kpi = kpi.merge(heads, on="yr", how="left")
    show = kpi[["yr", "net_sales", "gm%", "opex%", "interest", "cash", "receivables", "inventory", "debt", "dso",
                "employees"]].copy()
    for col in ["net_sales", "interest", "cash", "receivables", "inventory", "debt"]:
        show[col] = (show[col] / 1e6).round(2)
    print("(amounts in millions of local currency)")
    print(show.to_string(index=False))

sys.exit(1 if failures else 0)
