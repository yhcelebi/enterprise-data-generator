# Enterprise data generator

Synthetic, fully reconciled enterprise data for **30 fictional companies** (15 industries × one Turkish and one foreign company) from **January 1995 to September 2026**, written as Parquet. It was built as demo data for DIMA, so the core finance tables use the same columns as DIMA's own tables.

Nothing is random noise on top of a template. Every company is simulated top-down:

1. **Activity curve.** Growth, the company's own events (acquisitions, new plants, patent expiries) and real macro shocks: the 1998 Asian crisis, the 2001 Turkish banking crisis, the dot-com bust, 2008, the euro crisis, Brexit, Turkey 2018, COVID and the 2022 energy shock.
2. **Documents.** Customer invoices with lines, consumer daily sales, purchase invoices, payroll, fixed assets.
3. **Settlement.** Customer payments with realistic delays that worsen in crises, Turkish cheques (received, endorsed, bounced, issued), bad debts moved to doubtful receivables, and FX differences on export receipts.
4. **Treasury.** Working-capital and investment loans (Turkish companies also borrow in EUR and book FX revaluation), early repayments, deposit interest, VAT returns, provisional and corporate tax, dividends and year-end closing.
5. **Ledger.** Everything above is posted to a double-entry journal. The trial balance (mizan) and the bank statements are derived from it, so **every table reconciles with every other table**.

## Companies

| Industry | Turkish company | Foreign company |
|---|---|---|
| Industrial manufacturing | Ostim Endüstriyel Makina | Kestrel Industrial (US) |
| Textiles | Anatolia Tekstil *(Kervan Holding)* | Pennine Textiles (UK) |
| Food & beverage | Bosphorus Gıda *(Kervan Holding)* | Alpenhof Foods (DE) |
| Retail | Çınar Market | Brightmart Retail Group (US) |
| Pharma | Şifa İlaç | Helix BioPharma (DE) |
| Logistics | Ufuk Lojistik | Meridian Freight (NL) |
| Energy | Poyraz Enerji | Solenne Energía (ES) |
| Software | Bilge Yazılım | Cobalt Software (US) |
| Construction | Temel İnşaat | Granite Peak Construction (US) |
| Banking | Lale Bank | Thames Mutual Bank (UK) |
| Automotive | Marmara Otomotiv *(Kervan Holding, 51%)* | Rheinwerk Automobil (DE) |
| Defense & aerospace | Kalkan Savunma | Ironclad Aerospace & Defense (US) |
| Telecom | Telekent İletişim | Aurore Télécom (FR) |
| Airline | Kanat Hava Yolları | Albion Airways (UK) |
| Healthcare | Hayat Sağlık Grubu | Northbridge Health (US) |

**How the books are kept:**
- **Turkish companies:** the Turkish uniform chart of accounts (TDHP) and TRY, expressed in post-2005 new lira for the whole period. Customers and suppliers have their own sub-accounts (`120.01.00034`, `320.01.00012`).
- **Foreign companies:** their own currency and an IFRS-style chart. Every ledger row also carries a `tdhp_code` so the two can be compared.
- **The two banks** are everyone's bank: Lale Bank holds the Turkish companies' accounts and loans, and Thames Mutual the foreign ones'. Their data is the `bank_transactions`, `loans`, `loan_installments` and `cheques` of the other companies, so the bank jobs write nothing of their own.

## Run

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m edg --companies ostim,kestrel --scale 0.1 --out out --shared   # quick test
.venv/bin/python -m edg --scale 1.0 --out out --shared                              # everything
.venv/bin/python scripts/validate.py out                                            # reconciliation checks + KPIs
```

**Command-line options:**
- `--scale` multiplies company size: revenue, customers, employees and document counts.
- `--first-year` and `--end` shorten the period.
- `--shared` also writes the tables that are common to all companies.
- Each company is independent and deterministic for a given `--seed`, so companies can be generated in parallel on different machines.

## Output layout

```
out/<table>/<company_id>/<table>-<year>.parquet   # large tables, one file per year
out/<table>/<company_id>/<table>.parquet          # other company tables
out/<table>/<table>.parquet                       # shared tables
```

Read everything with DuckDB:

```sql
select * from read_parquet('out/invoices/*/*.parquet') where company_id = 'ostim';
```

## Tables

**Shared:** `companies`, `company_events` (the story behind each company), `chart_of_accounts` (TDHP ↔ IFRS), `macro_monthly` (CPI index and policy rate for US, EU, UK and TR), `fx_daily`.

**Per company** (★ = same columns as the DIMA table of the same purpose):

| Table | Content |
|---|---|
| ★ `trial_balance` | Monthly mizan, year-to-date cumulative, main and sub accounts, December before closing (like DIMA `cumulative_balances`) |
| ★ `invoices` | Sales invoices, credit notes and purchase invoices: number, ETTN, e-Fatura/e-Arşiv/paper channel, due date, currency and FX rate |
| `invoice_lines` | Product lines of sales invoices: quantity, price, discount, VAT, cost |
| `consumer_sales` | Daily consumer sales (retail Z reports, subscriber billing, tickets, patient payments) by cash, card and billing |
| ★ `invoice_payments` | Collections and payments per invoice with method (transfer or cheque); payments of pre-1995 invoices reference `DEVIR-<code>` |
| ★ `cheques` | Received and issued cheques with Turkish status (portföyde, tahsilde, tahsil edildi, ciro edildi, karşılıksız, verildi, ödendi) |
| ★ `counterparties` | Customers and suppliers: tax number (valid VKN or TCKN), segment, terms, risk limit, and the other dataset company if they are one |
| ★ `bank_accounts`, ★ `bank_transactions` | Bank statement lines with running balance and unique reference |
| `loans`, `loan_installments` | Loan book with instalment schedule (principal, interest, BSMV), including future instalments |
| ★ `obligations` | Loan instalments, net pay, withholding tax, SGK, VAT, provisional and corporate tax with due dates |
| ★ `budget_lines` | Monthly budget per metric (net_sales, cogs, operating_expenses …) prepared from the prior year |
| `gl_journal_lines` | Full double-entry journal with document references and source ERP system |
| `employees`, `payroll_lines` | Employee master and monthly payroll per employee (SGK, income and stamp tax, severance) |
| `fixed_assets` | Asset register with useful lives, depreciation and disposals |
| `products` | Product and service catalogue with launch and discontinue dates |

## Guarantees checked by `scripts/validate.py`

- Every journal entry balances.
- The trial balance balances for every month.
- The bank statement's month-end balance equals ledger account 102 for every month.
