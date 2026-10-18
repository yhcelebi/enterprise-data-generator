"""Turn a finished simulation into tables (DIMA-compatible columns plus raw detail) and write Parquet."""

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .companies import COMPANIES
from .interco import LINKS, company_tax_number
from .ledger import CHART, chart_table, trial_balance

# Large tables are split into one file per year.
YEARLY = {"invoices", "invoice_lines", "invoice_payments", "gl_journal_lines", "bank_transactions",
          "payroll_lines", "consumer_sales", "trial_balance"}


def build_tables(sim) -> dict:
    c, cal = sim.c, sim.cal
    first_day = int((cal.output_start - cal.start).days)
    date = sim.dates
    t = {}
    foreign = not sim.tr

    # Counterparties.
    cu, su = sim.customers, sim.suppliers
    rate_end = sim.fx_end
    t["counterparties"] = pd.concat([
        pd.DataFrame({"code": cu.code, "name": cu.name, "tax_number": cu.tax_number, "kind": "customer",
                      "segment": cu.segment, "supplier_category": None, "country": cu.country, "city": cu.city,
                      "payment_terms_days": cu.payment_terms_days,
                      "risk_limit": (cu.risk_limit_usd * rate_end).round(-2), "is_export": cu.is_export,
                      "is_individual": cu.is_individual, "interco_company": cu.interco_company,
                      "first_seen": date(sim.month_first_day[np.clip(cu.start_month, 0, cal.n_months - 1)]),
                      "default_date": np.where(cu.default_month >= 0,
                                               date(sim.month_first_day[np.clip(cu.default_month, 0, cal.n_months - 1)]),
                                               np.datetime64("NaT"))}),
        pd.DataFrame({"code": su.code, "name": su.name, "tax_number": su.tax_number, "kind": "supplier",
                      "segment": None, "supplier_category": su.kind, "country": su.country, "city": None,
                      "payment_terms_days": su.payment_terms_days, "risk_limit": np.nan, "is_export": False,
                      "is_individual": False, "interco_company": su.interco_company.replace("", None),
                      "first_seen": np.datetime64("NaT"), "default_date": np.datetime64("NaT")}),
    ], ignore_index=True)

    p = sim.products
    t["products"] = pd.DataFrame({
        "product_id": p.product_id, "sku": p.sku, "name": p.name, "category": p.category, "unit": p.unit,
        "list_price_2026": (p.list_price_usd_2026 * rate_end).round(2), "cost_ratio": p.cost_ratio,
        "launch_date": date(sim.month_first_day[np.clip(p.launch_month, 0, cal.n_months - 1)]),
        "discontinue_date": np.where(p.discontinue_month < cal.n_months,
                                     date(sim.month_first_day[np.clip(p.discontinue_month, 0, cal.n_months - 1)]),
                                     np.datetime64("NaT")),
    })

    # Invoices (sales, returns, purchases).
    inv, r, pi = sim.invoices, sim.returns, sim.purchases
    parts = []
    if len(inv):
        parts.append(pd.DataFrame({
            "direction": "sale", "invoice_type": "invoice", "number": inv.number, "ettn": inv.ettn,
            "channel": inv.channel, "issued_day": inv.day, "due_day": inv.due,
            "counterparty_code": cu.code.values[inv.cust], "counterparty": cu.name.values[inv.cust],
            "currency": inv.currency, "fx_rate": inv.fx_rate, "gross_before_discount": inv.gross,
            "discount": inv["discount"], "net": inv.net, "vat": inv.vat, "gross": inv.total, "gross_fx": inv.total_fx,
            "cost_of_sales": inv.cost, "ledger_account": np.where(inv.export, "601", "600"), "line_count": inv.n_lines}))
    if len(r):
        parts.append(pd.DataFrame({
            "direction": "sale", "invoice_type": "return", "number": r.number, "ettn": None,
            "channel": "e-fatura" if sim.tr else "pdf", "issued_day": r.day, "due_day": r.day,
            "counterparty_code": cu.code.values[r.cust], "counterparty": cu.name.values[r.cust],
            "currency": sim.cur, "fx_rate": 1.0, "gross_before_discount": r.net, "discount": 0.0, "net": r.net,
            "vat": r.vat, "gross": r.total, "gross_fx": r.total, "cost_of_sales": r.cost, "ledger_account": "610",
            "line_count": 0}))
    parts.append(pd.DataFrame({
        "direction": "purchase", "invoice_type": "invoice", "number": pi.number, "ettn": pi.ettn,
        "channel": pi.channel, "issued_day": pi.day, "due_day": pi.due,
        "counterparty_code": su.code.values[pi.supplier], "counterparty": su.name.values[pi.supplier],
        "currency": pi.currency, "fx_rate": pi.fx_rate, "gross_before_discount": pi.net, "discount": 0.0,
        "net": pi.net, "vat": pi.vat, "gross": pi.total, "gross_fx": pi.total_fx, "cost_of_sales": np.nan,
        "ledger_account": pi.account, "line_count": 0}))
    allinv = pd.concat(parts, ignore_index=True)
    allinv["supplier_category"] = None
    allinv.loc[allinv.direction == "purchase", "supplier_category"] = pi.kind.values
    allinv = allinv[allinv.issued_day >= first_day]
    allinv["issued_on"] = date(allinv.issued_day.values)
    allinv["due_on"] = date(allinv.due_day.values)
    allinv["source_system"] = sim.source_system(allinv.issued_day.values)
    t["invoices"] = allinv.drop(columns=["issued_day", "due_day"]).sort_values(["issued_on", "direction"], kind="stable")
    warmup_numbers = set(np.concatenate([inv.number.values[inv.day.values < first_day] if len(inv) else [],
                                         pi.number.values[pi.day.values < first_day]]))

    if len(sim.lines):
        ln = sim.lines
        keep = inv.day.values[ln.inv.values] >= first_day
        ln = ln[keep]
        prod = sim.products
        t["invoice_lines"] = pd.DataFrame({
            "invoice_number": inv.number.values[ln.inv.values],
            "line_no": ln.groupby("inv").cumcount().values + 1,
            "issued_on": date(inv.day.values[ln.inv.values]),
            "product_id": prod.product_id.values[ln.product_idx.values],
            "sku": prod.sku.values[ln.product_idx.values],
            "description": prod.name.values[ln.product_idx.values],
            "quantity": ln.qty.values, "unit": prod.unit.values[ln.product_idx.values],
            "unit_price": ln.unit_price.values, "gross": ln.gross.values, "discount_pct": ln.disc.values.round(4),
            "discount": ln["discount"].values, "net": ln.net.values, "vat_rate": ln.vat_rate.values.round(4),
            "vat": ln.vat.values, "cost": ln.cost.values,
        })

    if len(sim.b2c):
        b = sim.b2c[sim.b2c.day >= first_day]
        t["consumer_sales"] = pd.DataFrame({"date": date(b.day.values), "gross": b.gross.values, "net": b.net.values,
                                            "vat": b.vat.values, "cash": b.cash.values, "card": b.card.values,
                                            "online": b.online.values, "billed": b.billed.values,
                                            "cost_of_sales": b.cost.values})

    pay = pd.concat(sim.payments, ignore_index=True) if sim.payments else pd.DataFrame()
    if len(pay):
        pay = pay[pay.paid_day >= first_day].copy()
        devir = pay.invoice_number.isin(warmup_numbers)
        pay.loc[devir, "invoice_number"] = "DEVIR-" + pay.loc[devir, "counterparty_code"].astype(str)
        pay["paid_on"] = date(pay.paid_day.values)
        pay["source"] = "erp"
        t["invoice_payments"] = pay.drop(columns=["paid_day"]).sort_values("paid_on", kind="stable")

    ch = pd.concat(sim.cheques_in + sim.cheques_out, ignore_index=True) if (sim.cheques_in or sim.cheques_out) else pd.DataFrame()
    if len(ch):
        ch = ch[ch.due_day >= first_day].copy()
        ch["issued_on"] = date(ch.issued_day.values)
        ch["due_on"] = date(ch.due_day.values)
        ch["source"] = "erp"
        t["cheques"] = ch.drop(columns=["issued_day", "due_day"])

    # Journal, trial balance and bank statements.
    gl = sim.J.frame()
    names = {k: v for k, v in sim.names.items() if v}
    tb = trial_balance(gl, cal, names, foreign)
    t["trial_balance"] = tb
    acct_main = gl.account.str[:3]
    gl_out = pd.DataFrame({
        "entry_id": gl.entry.values, "line_no": gl.line.values, "posting_date": date(gl.day.values),
        "account_code": [CHART[a[:3]][1] + a[3:] if foreign else a for a in gl.account.values],
        "tdhp_code": acct_main.values,
        "account_name": [names.get(a) or CHART[a[:3]][2 if foreign else 0] for a in gl.account.values],
        "debit": gl.debit.values, "credit": gl.credit.values, "currency": sim.cur,
        "document_type": gl.doc_type.values, "document_number": gl.doc_no.values, "description": gl.description.values,
        "counterparty_code": gl.cp_code.values, "counterparty_name": gl.cp_name.values,
        "source_system": sim.source_system(gl.day.values),
    })
    t["gl_journal_lines"] = gl_out[gl.day.values >= first_day]

    bank = gl[gl.account.values == sim.bank_account].copy()
    bank["amount"] = (bank.debit - bank.credit).round(2)
    bank["balance_after"] = bank.amount.cumsum().round(2)
    bank = bank[bank.day >= first_day]
    seq = np.arange(1, len(bank) + 1)
    prefix = "LB" if sim.bank == "lale" else "TM"
    t["bank_transactions"] = pd.DataFrame({
        "account": sim.bank_code, "bank": sim.bank, "booked_on": date(bank.day.values),
        "value_date": date(bank.day.values), "description": bank.description.values,
        "amount": bank.amount.values, "balance_after": bank.balance_after.values,
        "currency": sim.cur, "reference": [f"{prefix}{d:%y%m%d}{s:07d}" for d, s in
                                           zip(pd.to_datetime(date(bank.day.values)), seq)],
        "counterparty_name": bank.cp_name.values, "transaction_type": bank.doc_type.values,
    })
    t["bank_accounts"] = pd.DataFrame({
        "code": [sim.bank_code], "bank": [sim.bank], "bank_name": [{"lale": "Lale Bank A.Ş.",
                                                                     "thames": "Thames Mutual Bank plc"}[sim.bank]],
        "currency": [sim.cur], "ledger_account": [CHART["102"][1] if foreign else sim.bank_account],
        "opened_on": [date(np.array([0]))[0]]})

    # People.
    e = sim.employees
    t["employees"] = e.drop(columns=["pay_factor", "hire_month", "term_month"])
    pr = sim.payroll[sim.payroll.m >= cal.month_index(cal.output_start.strftime("%Y-%m"))]
    t["payroll_lines"] = pd.DataFrame({
        "period": cal.months[pr.m.values].astype(str), "pay_date": date(pr.pay_day.values),
        "employee_id": e.employee_id.values[pr.employee_idx.values],
        "sicil_no": e.sicil_no.values[pr.employee_idx.values], "department": pr.department.values,
        **{col: pr[col].values for col in ["gross_pay", "severance_pay", "employee_social", "employee_unemployment",
                                           "income_tax", "stamp_tax", "net_pay", "employer_social",
                                           "employer_unemployment", "total_employer_cost"]},
    })

    fa = sim.assets
    t["fixed_assets"] = pd.DataFrame({
        "asset_id": fa.asset_id, "asset_tag": fa.asset_tag, "asset_class": fa.asset_class,
        "ledger_account": [CHART[a][1] if foreign else a for a in fa.account], "description": fa.description,
        "acquisition_date": _month_date(sim, fa.acq_month.values),
        "cost": fa.cost, "useful_life_months": fa.useful_life_months, "monthly_depreciation": fa.monthly_dep,
        "disposal_date": np.where(fa.dispose_month < cal.n_months, _month_date(sim, fa.dispose_month.values, end=True),
                                  np.datetime64("NaT")),
        "depreciation_account": [CHART[a][1] if foreign else a for a in fa.dep_account],
    })

    # Loans and obligations.
    if len(sim.loans):
        lo = sim.loans
        t["loans"] = pd.DataFrame({
            "loan_no": lo.loan_no, "reference": lo.reference, "bank": lo.bank,
            "ledger_account": [CHART["300"][1] if foreign else a for a in lo.ledger_account],
            "drawdown_date": date(lo.drawdown_day.values), "principal": lo.principal, "currency": lo.currency,
            "term_months": lo.term_months, "annual_rate": lo.annual_rate, "installment": lo.installment,
            "purpose": lo.purpose})
        li = sim.loan_installments
        t["loan_installments"] = pd.DataFrame({
            "loan_no": li.loan_no, "reference": li.reference, "installment": li.installment,
            "due_on": date(li.due_day.values), "principal": li.principal, "interest": li.interest,
            "tax": li.tax, "total": li.total,
            "status": np.where(li.due_day.values <= sim.last_day, "paid", "open")})
    ob = pd.concat(sim.obligation_rows + [pd.DataFrame(sim.tax_rows, columns=[
        "category", "basis", "reference", "period", "due_day", "amount"])], ignore_index=True)
    if len(sim.loans):
        li = sim.loan_installments
        ob = pd.concat([ob, pd.DataFrame({
            "category": "loan", "basis": "schedule", "reference": li.reference.values,
            "period": [str(cal.months[min(m, cal.n_months - 1)]) for m in sim.month_of_day(li.due_day.values)],
            "due_day": li.due_day.values, "amount": li.total.values, "principal": li.principal.values,
            "interest": (li.interest + li.tax).values})], ignore_index=True)
    ob = ob[ob.due_day >= first_day].copy()
    ob["due_on"] = date(ob.due_day.values.astype(np.int64))
    ob["status"] = np.where(ob.due_day.values <= sim.last_day, "paid", "open")
    ob["source"] = "erp"
    t["obligations"] = ob.drop(columns=["due_day"])

    bud = sim.budget
    t["budget_lines"] = bud[bud.period >= cal.output_start.strftime("%Y-%m")].reset_index(drop=True)

    for name, df in t.items():
        df.insert(0, "company_id", c.id)
    return t


def _month_date(sim, months, end=False):
    """First (or last) day of a month index, also for months before the calendar start."""
    base = sim.cal.months[0]
    periods = pd.PeriodIndex([base + int(m) for m in months], freq="M")
    ts = periods.to_timestamp(how="end" if end else "start")
    return ts.normalize().values.astype("datetime64[D]")


def shared_tables(first_year: int, end: str) -> dict:
    from .timeline import macro_tables
    cal, monthly, fx = macro_tables(first_year, end)
    comp = pd.DataFrame([{
        "company_id": c.id, "name": c.name, "country": c.country, "industry": c.industry,
        "industry_name": c.profile.name_en, "industry_name_tr": c.profile.name_tr,
        "accounting_model": c.profile.model, "currency": {"TR": "TRY", "US": "USD", "UK": "GBP"}.get(c.country, "EUR"),
        "chart_of_accounts": "TDHP" if c.turkish else "IFRS", "founded": c.founded, "city": c.city,
        "is_bank": c.is_bank, "holding": c.holding or None, "holding_share": c.holding_share or None,
        "export_share": c.export_share, "revenue_1995_musd_real": c.revenue_1995,
        "revenue_2026_musd_real": c.revenue_2026,
        "erp_history": "; ".join(f"{y}: {s}" for y, s in c.erp_history) or None,
        "tax_number": company_tax_number(c.id),
    } for c in COMPANIES])
    events = pd.DataFrame([{"company_id": c.id, "month": e.month, "kind": e.kind, "size": e.size, "label": e.label}
                           for c in COMPANIES for e in c.events])
    erp = pd.DataFrame([{"company_id": c.id, "month": f"{y}-01", "kind": "erp", "size": 0.0,
                         "label": f"ERP: {s}"} for c in COMPANIES for y, s in c.erp_history])
    links = pd.DataFrame([{"seller": l.seller, "buyer": l.buyer, "buyer_purchase_category": l.kind,
                           "seller_name_in_buyer_books": l.buyer_name,
                           "buyer_name_in_seller_books": l.seller_name or None, "payment_terms_days": l.terms,
                           "since": l.since, "holding_fee": l.fee} for l in LINKS])
    return {"interco_links": links, "companies": comp, "company_events": pd.concat([events, erp], ignore_index=True).sort_values(
        ["company_id", "month"]), "chart_of_accounts": chart_table(), "macro_monthly": monthly, "fx_daily": fx}


def _to_arrow(df: pd.DataFrame) -> pa.Table:
    df = df.reset_index(drop=True)
    date_only = set()
    for col in df.columns:
        if df[col].dtype == object:
            vals = df[col].dropna()
            if len(vals) and isinstance(vals.iloc[0], (bool, np.bool_)):
                df[col] = df[col].astype("boolean")
            elif len(vals) == 0:
                df[col] = df[col].astype("string")
        elif pd.api.types.is_datetime64_any_dtype(df[col].dtype):
            ns = df[col].values.astype("datetime64[ns]").astype("int64")
            valid = ~np.isnat(df[col].values)
            if (ns[valid] % 86_400_000_000_000 == 0).all():
                date_only.add(col)
    table = pa.Table.from_pandas(df, preserve_index=False)
    fields = []
    for f in table.schema:
        if pa.types.is_timestamp(f.type):
            fields.append(pa.field(f.name, pa.date32() if f.name in date_only else pa.timestamp("s")))
        else:
            fields.append(f)
    return table.cast(pa.schema(fields))


def write_tables(tables: dict, out: Path, company_id: str | None = None) -> dict:
    sizes = {}
    for name, df in tables.items():
        if df is None or len(df) == 0:
            continue
        base = out / name
        if company_id is None:
            base.mkdir(parents=True, exist_ok=True)
            path = base / f"{name}.parquet"
            pq.write_table(_to_arrow(df), path, compression="zstd")
            sizes[name] = (len(df), path.stat().st_size)
            continue
        folder = base / company_id
        folder.mkdir(parents=True, exist_ok=True)
        rows, size = 0, 0
        if name in YEARLY:
            datecol = next(c for c in ("issued_on", "posting_date", "booked_on", "paid_on", "date", "pay_date", "period")
                           if c in df.columns)
            years = pd.to_datetime(df[datecol]).dt.year if datecol != "period" else df[datecol].str[:4].astype(int)
            for y, part in df.groupby(years.values):
                path = folder / f"{name}-{y}.parquet"
                pq.write_table(_to_arrow(part), path, compression="zstd")
                rows += len(part)
                size += path.stat().st_size
        else:
            path = folder / f"{name}.parquet"
            pq.write_table(_to_arrow(df), path, compression="zstd")
            rows, size = len(df), path.stat().st_size
        sizes[name] = (rows, size)
    return sizes
