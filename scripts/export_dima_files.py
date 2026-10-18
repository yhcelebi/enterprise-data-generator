"""Export one Turkish company's Parquet data as the ERP files DIMA reads from a synced folder.

    python scripts/export_dima_files.py OUT_DIR COMPANY_ID TARGET_DIR [--from 2023-01] [--to 2026-09]

Writes semicolon CSV files with Turkish headers and Turkish number format (1.234,56), in
the folder layout DIMA recognizes by file and folder name:

    mizan/mizan_YYYY-MM.csv              cumulative trial balance (main and sub accounts)
    banka/LALE-TRY_YYYY.csv              bank statement per year
    cari/cari_kart.csv                   customer and supplier cards
    fatura/satis_faturalari_YYYY.csv     sales invoices (credit notes with type İADE)
    fatura/alis_faturalari_YYYY.csv      purchase invoices
    tahsilat/tahsilat_kapama_YYYY.csv    collections per invoice
    odeme/odeme_kapama_YYYY.csv          payments per invoice
    cek/musteri_cekleri.csv, cek/firma_cekleri.csv
    kredi/kredi_odeme_plani.csv          loan repayment schedule
    bordro/bordro_ozet_YYYY.csv          payroll declaration summary per month
    kdv/kdv_beyan_ozeti.csv              VAT return summary
    butce/butce_YYYY.csv                 budget (YYYY-AA;metric;amount)

Large tables are split per year to stay under DIMA's 50 MB limit for in-memory files.
"""

import argparse
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("company")
ap.add_argument("target")
ap.add_argument("--from", dest="start", default="1995-01")
ap.add_argument("--to", dest="end", default="2099-12")
args = ap.parse_args()

src, target, company = Path(args.out), Path(args.target), args.company
con = duckdb.connect()


def read(table, where=""):
    path = src / table / company
    if not path.exists():
        return pd.DataFrame()
    return con.sql(f"select * from read_parquet('{path}/*.parquet') {where}").df()


def tr_money(x):
    """1234.5 -> '1.234,50'."""
    s = np.char.mod("%.2f", np.round(np.asarray(x, dtype=float), 2))
    out = []
    for v in s:
        neg = v.startswith("-")
        whole, frac = v.lstrip("-").split(".")
        groups = []
        while len(whole) > 3:
            groups.insert(0, whole[-3:])
            whole = whole[:-3]
        groups.insert(0, whole)
        out.append(("-" if neg else "") + ".".join(groups) + "," + frac)
    return out


def tr_date(x):
    return pd.to_datetime(x).dt.strftime("%d.%m.%Y")


def write(df, rel):
    path = target / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep=";", index=False, encoding="utf-8")
    return path


lo, hi = args.start, args.end
period_filter = f"where period between '{lo}' and '{hi}'"
written = []

# Trial balance: cumulative year-to-date totals and balances; DIMA reads it as cumulative.
tb = read("trial_balance", period_filter)
for period, part in tb.groupby("period"):
    part = part.sort_values("account_code")
    written.append(write(pd.DataFrame({
        "Hesap Kodu": part.account_code, "Hesap Adı": part.account_name, "Borç": tr_money(part.ytd_debit),
        "Alacak": tr_money(part.ytd_credit), "Borç Bakiye": tr_money(part.debit_balance),
        "Alacak Bakiye": tr_money(part.credit_balance)}), f"mizan/mizan_{period}.csv"))

date_filter = lambda col: f"where strftime({col}, '%Y-%m') between '{lo}' and '{hi}'"
bank = read("bank_transactions", date_filter("booked_on"))
for (account, year), part in bank.groupby([bank.account, pd.to_datetime(bank.booked_on).dt.year]):
    written.append(write(pd.DataFrame({
        "Tarih": tr_date(part.booked_on), "Açıklama": part.description, "Tutar": tr_money(part.amount),
        "Bakiye": tr_money(part.balance_after), "Dekont No": part.reference}), f"banka/{account}_{year}.csv"))

cp = read("counterparties")
written.append(write(pd.DataFrame({
    "cari_kodu": cp.code, "unvan": cp.name, "vkn": cp.tax_number,
    "cari_tipi": np.where(cp.kind == "customer", "Müşteri", "Tedarikçi"), "vade_gun": cp.payment_terms_days,
    "risk_limiti": tr_money(cp.risk_limit.fillna(0))}), "cari/cari_kart.csv"))

inv = read("invoices", date_filter("issued_on"))
for (direction, year), part in inv.groupby([inv.direction, pd.to_datetime(inv.issued_on).dt.year]):
    name = "satis_faturalari" if direction == "sale" else "alis_faturalari"
    written.append(write(pd.DataFrame({
        "fatura_no": part.number, "fatura_tarihi": tr_date(part.issued_on), "cari_kodu": part.counterparty_code,
        "unvan": part.counterparty, "fatura_tipi": np.where(part.invoice_type == "return", "İADE", "SATIŞ" if direction == "sale" else "ALIŞ"),
        "matrah": tr_money(part.net.abs()), "kdv": tr_money(part.vat.abs()), "genel_toplam": tr_money(part.gross.abs()),
        "doviz": part.currency, "kur": part.fx_rate.round(4), "vade_tarihi": tr_date(part.due_on),
        "ettn": part.ettn.fillna("")}), f"fatura/{name}_{year}.csv"))

pay = read("invoice_payments", date_filter("paid_on"))
method = {"transfer": "Havale/EFT", "cheque": "Çek", "offset": "Mahsup"}
for (direction, year), part in pay.groupby([pay.direction, pd.to_datetime(pay.paid_on).dt.year]):
    rel = f"tahsilat/tahsilat_kapama_{year}.csv" if direction == "sale" else f"odeme/odeme_kapama_{year}.csv"
    written.append(write(pd.DataFrame({
        "fatura_no": part.invoice_number.fillna(""), "cari_kodu": part.counterparty_code,
        "tarih": tr_date(part.paid_on), "tutar": tr_money(part.amount),
        "tahsilat_turu": part.method.map(method).fillna("")}), rel))

ch = read("cheques", date_filter("due_on"))
for direction, rel in (("received", "cek/musteri_cekleri.csv"), ("given", "cek/firma_cekleri.csv")):
    part = ch[ch.direction == direction] if len(ch) else ch
    if len(part):
        written.append(write(pd.DataFrame({
            "cek_no": part.number, "cari_kodu": part.counterparty_code, "alis_tarihi": tr_date(part.issued_on),
            "vade": tr_date(part.due_on), "tutar": tr_money(part.amount), "durum": part.status}), rel))

li = read("loan_installments", date_filter("due_on"))
if len(li):
    written.append(write(pd.DataFrame({
        "kredi_no": li.reference.str.rsplit("/", n=1).str[0], "taksit_no": li.installment,
        "vade_tarihi": tr_date(li.due_on), "taksit_tutari": tr_money(li.total), "anapara": tr_money(li.principal),
        "faiz": tr_money(li.interest), "bsmv": tr_money(li.tax),
        "durum": np.where(li.status == "paid", "ÖDENDİ", "AÇIK")}), "kredi/kredi_odeme_plani.csv"))

pr = read("payroll_lines", f"where period between '{lo}' and '{hi}'")
if len(pr):
    s = pr.groupby("period").agg(sgk_isci=("employee_social", "sum"), issizlik_isci=("employee_unemployment", "sum"),
                                 sgk_isveren=("employer_social", "sum"), issizlik_isveren=("employer_unemployment", "sum"),
                                 gv_kesilen=("income_tax", "sum"), dv_kesilen=("stamp_tax", "sum"),
                                 odenecek_net=("net_pay", "sum")).reset_index()
    for year, part in s.groupby(s.period.str[:4]):
        written.append(write(pd.DataFrame({"donem": part.period, **{c: tr_money(part[c]) for c in s.columns if c != "period"}}),
                             f"bordro/bordro_ozet_{year}.csv"))

ob = read("obligations", f"where category = 'vat' and period between '{lo}' and '{hi}'")
gl_vat = con.sql(f"""select strftime(posting_date, '%Y-%m') period,
        sum(case when tdhp_code = '391' and document_type = 'vat_return' then debit else 0 end) hesaplanan,
        sum(case when tdhp_code = '191' and document_type = 'vat_return' then credit else 0 end) indirilecek
        from read_parquet('{src}/gl_journal_lines/{company}/*.parquet') group by 1""").df() if (src / "gl_journal_lines" / company).exists() else pd.DataFrame()
if len(ob) and len(gl_vat):
    v = ob.merge(gl_vat, on="period", how="left").fillna(0)
    written.append(write(pd.DataFrame({"donem": v.period, "hesaplanan": tr_money(v.hesaplanan),
                                       "indirilecek": tr_money(v.indirilecek), "odenecek": tr_money(v.amount)}),
                         "kdv/kdv_beyan_ozeti.csv"))

bud = read("budget_lines", f"where period between '{lo}' and '{hi}'")
for year, part in bud.groupby(bud.period.str[:4]) if len(bud) else []:
    written.append(write(pd.DataFrame({"donem": part.period, "metrik": part.metric,
                                       "tutar": tr_money(part.amount)}), f"butce/butce_{year}.csv"))

total = sum(p.stat().st_size for p in written)
print(f"{len(written)} files, {total / 1e6:,.1f} MB in {target}")
largest = max(written, key=lambda p: p.stat().st_size)
print(f"largest: {largest.relative_to(target)} ({largest.stat().st_size / 1e6:,.1f} MB; DIMA reads up to 50 MB in memory)")
