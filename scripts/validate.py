"""Consistency checks and yearly KPIs for generated companies.

    python scripts/validate.py OUT_DIR [company ...]
"""

import sys
from pathlib import Path

import duckdb

out = Path(sys.argv[1])
con = duckdb.connect()


def table(name, company):
    return f"read_parquet('{out}/{name}/{company}/*.parquet')"


companies = sys.argv[2:] or sorted(p.name for p in (out / "trial_balance").iterdir())
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
