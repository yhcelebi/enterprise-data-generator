---
pretty_name: Enterprise Data — 30 Companies, 1995–2026
language:
  - en
  - tr
license: cc-by-4.0
tags:
  - synthetic
  - finance
  - accounting
  - erp
  - enterprise
  - time-series
  - turkish
  - tdhp
  - ifrs
size_categories:
  - 1B<n<10B
task_categories:
  - tabular-classification
  - tabular-regression
  - time-series-forecasting
  - table-question-answering
configs:
  - {config_name: companies, data_files: "shared/companies.parquet"}
  - {config_name: company_events, data_files: "shared/company_events.parquet"}
  - {config_name: interco_links, data_files: "shared/interco_links.parquet"}
  - {config_name: chart_of_accounts, data_files: "shared/chart_of_accounts.parquet"}
  - {config_name: macro_monthly, data_files: "shared/macro_monthly.parquet"}
  - {config_name: fx_daily, data_files: "shared/fx_daily.parquet"}
  - {config_name: trial_balance, data_files: "*/trial_balance/*.parquet"}
  - {config_name: gl_journal_lines, data_files: "*/gl_journal_lines/*.parquet"}
  - {config_name: invoices, data_files: "*/invoices/*.parquet"}
  - {config_name: invoice_lines, data_files: "*/invoice_lines/*.parquet"}
  - {config_name: invoice_payments, data_files: "*/invoice_payments/*.parquet"}
  - {config_name: consumer_sales, data_files: "*/consumer_sales/*.parquet"}
  - {config_name: counterparties, data_files: "*/counterparties/*.parquet"}
  - {config_name: products, data_files: "*/products/*.parquet"}
  - {config_name: cheques, data_files: "*/cheques/*.parquet"}
  - {config_name: bank_accounts, data_files: "*/bank_accounts/*.parquet"}
  - {config_name: bank_transactions, data_files: "*/bank_transactions/*.parquet"}
  - {config_name: loans, data_files: "*/loans/*.parquet"}
  - {config_name: loan_installments, data_files: "*/loan_installments/*.parquet"}
  - {config_name: obligations, data_files: "*/obligations/*.parquet"}
  - {config_name: budget_lines, data_files: "*/budget_lines/*.parquet"}
  - {config_name: employees, data_files: "*/employees/*.parquet"}
  - {config_name: payroll_lines, data_files: "*/payroll_lines/*.parquet"}
  - {config_name: fixed_assets, data_files: "*/fixed_assets/*.parquet"}
  - {config_name: stores, data_files: "*/stores/*.parquet"}
  - {config_name: store_daily_sales, data_files: "*/store_daily_sales/*.parquet"}
  - {config_name: pos_receipts, data_files: "*/pos_receipts/*.parquet"}
  - {config_name: pos_receipt_lines, data_files: "*/pos_receipt_lines/*.parquet"}
  - {config_name: loyalty_members, data_files: "*/loyalty_members/*.parquet"}
  - {config_name: plans, data_files: "*/plans/*.parquet"}
  - {config_name: subscriber_base_monthly, data_files: "*/subscriber_base_monthly/*.parquet"}
  - {config_name: subscribers, data_files: "*/subscribers/*.parquet"}
  - {config_name: subscriber_daily_usage, data_files: "*/subscriber_daily_usage/*.parquet"}
  - {config_name: network_cells, data_files: "*/network_cells/*.parquet"}
  - {config_name: cell_daily_traffic, data_files: "*/cell_daily_traffic/*.parquet"}
  - {config_name: weather_daily, data_files: "*/weather_daily/*.parquet"}
  - {config_name: power_plants, data_files: "*/power_plants/*.parquet"}
  - {config_name: plant_hourly_generation, data_files: "*/plant_hourly_generation/*.parquet"}
  - {config_name: market_prices_hourly, data_files: "*/market_prices_hourly/*.parquet"}
  - {config_name: smart_meters, data_files: "*/smart_meters/*.parquet"}
  - {config_name: meter_daily_readings, data_files: "*/meter_daily_readings/*.parquet"}
  - {config_name: airports, data_files: "*/airports/*.parquet"}
  - {config_name: aircraft, data_files: "*/aircraft/*.parquet"}
  - {config_name: flights, data_files: "*/flights/*.parquet"}
  - {config_name: tickets, data_files: "*/tickets/*.parquet"}
  - {config_name: facilities, data_files: "*/facilities/*.parquet"}
  - {config_name: physicians, data_files: "*/physicians/*.parquet"}
  - {config_name: patients, data_files: "*/patients/*.parquet"}
  - {config_name: encounters, data_files: "*/encounters/*.parquet"}
  - {config_name: encounter_diagnoses, data_files: "*/encounter_diagnoses/*.parquet"}
  - {config_name: diagnosis_codes, data_files: "*/diagnosis_codes/*.parquet"}
  - {config_name: claims, data_files: "*/claims/*.parquet"}
  - {config_name: facility_daily_census, data_files: "*/facility_daily_census/*.parquet"}
  - {config_name: depots, data_files: "*/depots/*.parquet"}
  - {config_name: trucks, data_files: "*/trucks/*.parquet"}
  - {config_name: shipments, data_files: "*/shipments/*.parquet"}
  - {config_name: truck_daily_telemetry, data_files: "*/truck_daily_telemetry/*.parquet"}
  - {config_name: truck_gps_pings, data_files: "*/truck_gps_pings/*.parquet"}
  - {config_name: machines, data_files: "*/machines/*.parquet"}
  - {config_name: machine_daily_metrics, data_files: "*/machine_daily_metrics/*.parquet"}
  - {config_name: machine_sensor_hourly, data_files: "*/machine_sensor_hourly/*.parquet"}
  - {config_name: maintenance_work_orders, data_files: "*/maintenance_work_orders/*.parquet"}
  - {config_name: production_orders, data_files: "*/production_orders/*.parquet"}
  - {config_name: stock_monthly, data_files: "*/stock_monthly/*.parquet"}
  - {config_name: vehicles, data_files: "*/vehicles/*.parquet"}
  - {config_name: warranty_claims, data_files: "*/warranty_claims/*.parquet"}
  - {config_name: programmes, data_files: "*/programmes/*.parquet"}
  - {config_name: programme_milestones, data_files: "*/programme_milestones/*.parquet"}
  - {config_name: programme_evm_monthly, data_files: "*/programme_evm_monthly/*.parquet"}
  - {config_name: subscriptions, data_files: "*/subscriptions/*.parquet"}
  - {config_name: product_usage_daily, data_files: "*/product_usage_daily/*.parquet"}
  - {config_name: support_tickets, data_files: "*/support_tickets/*.parquet"}
  - {config_name: projects, data_files: "*/projects/*.parquet"}
  - {config_name: project_progress_monthly, data_files: "*/project_progress_monthly/*.parquet"}
  - {config_name: site_daily_logs, data_files: "*/site_daily_logs/*.parquet"}
---

# Enterprise Data — 30 Companies, 1995–2026

A large, **fully synthetic and fully reconciled** enterprise dataset: the books and operations of **30 fictional
companies** over **31¾ years** (January 1995 – September 2026), in about **48 GB of Parquet** and about 9.3
billion rows.

Every company is a complete enterprise, with a general ledger, a monthly trial balance (mizan), invoices, payments,
cheques, bank statements, loans, taxes, payroll, fixed assets and budgets, plus the operational data of its industry:
POS receipts, subscriber usage, smart-meter readings, flights, patient encounters, truck GPS, machine sensors and more.
**All of it adds up.** Receipts add up to store-days, store-days to the ledger, the ledger to the trial balance, and
the trial balance to the bank statements, all to the cent.

It was built as demo data for [DIMA](https://usedima.com), an AI finance analyst for companies that keep their books
in the Turkish uniform chart of accounts (TDHP), so the core finance tables follow DIMA's own data model.

> **License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).** You may use, share and adapt the data,
> including commercially, as long as you give credit.
>
> **Everything is synthetic.** The companies, people, customers, invoices and numbers are generated. Names of
> companies and people are invented, and any resemblance to real entities is coincidental. Macro inputs (inflation,
> FX, interest rates, crises) follow real history approximately, and are not meant for financial analysis.

## At a glance

| | |
|---|---|
| Companies | 30: 15 industries × one Turkish and one foreign company |
| Period | 1995-01 to 2026-09, monthly trial balances for all 381 months |
| Countries and currencies | Turkey (TRY), United States (USD), United Kingdom (GBP), Germany, Netherlands, Spain, France (EUR) |
| Charts of accounts | Turkish companies: TDHP with customer and supplier sub-accounts. Foreign companies: IFRS-style, with a TDHP mapping on every row |
| Tables | ~80, from the general ledger to hourly machine sensors |
| Size | ~48 GB Parquet (zstd), ~9.3 billion rows |
| Reconciliation | Every company is checked automatically before upload (see *Guarantees*) |

## The companies

| Industry | 🇹🇷 Turkish company | Foreign company |
|---|---|---|
| Industrial manufacturing | Ostim Endüstriyel Makina | Kestrel Industrial (US) |
| Textiles | Anatolia Tekstil *(Kervan Holding)* | Pennine Textiles (UK) |
| Food & beverage | Bosphorus Gıda *(Kervan Holding)* | Alpenhof Foods (DE) |
| Retail | Çınar Market | Brightmart Retail Group (US) |
| Pharma | Şifa İlaç | Helix BioPharma (DE) |
| Logistics | Ufuk Lojistik | Meridian Freight (NL) |
| Energy | Poyraz Enerji | Solenne Energía (ES) |
| Software / SaaS | Bilge Yazılım | Cobalt Software (US) |
| Construction | Temel İnşaat | Granite Peak Construction (US) |
| Banking | Lale Bank | Thames Mutual Bank (UK) |
| Automotive | Marmara Otomotiv *(Kervan Holding, 51%)* | Rheinwerk Automobil (DE) |
| Defense & aerospace | Kalkan Savunma | Ironclad Aerospace & Defense (US) |
| Telecom | Telekent İletişim | Aurore Télécom (FR) |
| Airline | Kanat Hava Yolları | Albion Airways (UK) |
| Healthcare | Hayat Sağlık Grubu | Northbridge Health (US) |

Each company has its own story in `company_events`: acquisitions, new plants, patent expiries, ERP migrations and
industry shocks. Every company also lives through the shared macro history: the 1998 Asian crisis, the 2001 Turkish
banking crisis, the dot-com bust, 2008, the euro crisis, Brexit, Turkey 2018, COVID and the 2022 energy shock. You can
see these in sales, margins, payment delays, layoffs and borrowing.

**The two banks** are everyone's bank. Lale Bank holds the Turkish companies' accounts and loans, and Thames Mutual
the foreign companies'. Their data is the `bank_transactions`, `loans`, `loan_installments` and `cheques` of the other
28 companies, so there are no bank-only folders.

## How the files are organized

The layout is **company → table → year**: everything about one company sits in its own folder.

```
ostim/                                   one folder per company (company_id)
├── invoices/
│   ├── invoices-1995.parquet            one file per year for large tables
│   ├── invoices-1996.parquet
│   └── …
├── trial_balance/
├── bank_transactions/
├── counterparties/counterparties.parquet   one file for small tables
└── …
kestrel/
└── …
shared/                                  tables shared by all companies
├── companies.parquet
├── interco_links.parquet
├── chart_of_accounts.parquet
├── macro_monthly.parquet
└── fx_daily.parquet
```

Every file also carries a `company_id` column, so files can be combined freely:
- **one company:** `ostim/invoices/*.parquet`
- **one table for every company:** `*/invoices/*.parquet`

On this page, each table is a **subset** in the Dataset Viewer, covering all companies.

## Quick start

**DuckDB** reads straight from the Hub:

```sql
-- Monthly net sales of every Turkish company, from the trial balance
select company_id, period,
       sum(month_credit - month_debit) filter (where tdhp_code in ('600','601'))
     - sum(month_debit - month_credit) filter (where tdhp_code in ('610','611')) as net_sales
from 'hf://datasets/yhcelebi/enterprise-data/*/trial_balance/*.parquet'
where level = 'main'
group by all order by company_id, period;
```

**pandas**, one company and one table:

```python
import pandas as pd
inv = pd.read_parquet("hf://datasets/yhcelebi/enterprise-data/ostim/invoices/")
```

**🤗 Datasets**, one table (subset) at a time. Large tables are best streamed:

```python
from datasets import load_dataset
tb = load_dataset("yhcelebi/enterprise-data", "trial_balance", split="train")
usage = load_dataset("yhcelebi/enterprise-data", "subscriber_daily_usage", split="train", streaming=True)
```

## Tables

**Shared reference tables**
- `companies`: the 30 companies with country, currency, chart, holding and ERP history.
- `company_events`: the story behind each company.
- `interco_links`: who sells to whom.
- `chart_of_accounts`: TDHP ↔ IFRS.
- `macro_monthly`: CPI index and policy rate for US, EU, UK and TR.
- `fx_daily`: EUR, GBP and TRY per USD.

**Finance (every operating company).** Columns follow DIMA's data model.
- `trial_balance`: monthly mizan, year-to-date cumulative, main and sub accounts. December is shown before closing.
- `gl_journal_lines`: the full double-entry journal, with document references and the source ERP system of the time.
- `invoices` and `invoice_lines`: sales invoices, credit notes and purchase invoices, with e-Fatura, e-Arşiv or paper channel, ETTN, currency and FX rate.
- `invoice_payments`: collections and payments per invoice (transfer or cheque).
- `consumer_sales`: daily consumer sales (Z reports, subscriber billing, tickets, patient payments).
- `cheques`: received and issued cheques with Turkish statuses (portföyde, tahsil edildi, ciro edildi, karşılıksız…).
- `counterparties` and `products`: customer and supplier cards (valid VKN or TCKN), and the catalogue.
- `bank_accounts` and `bank_transactions`: bank statements with running balance and unique reference.
- `loans` and `loan_installments`: working-capital and investment loans, TRY and EUR, with BSMV and future instalments.
- `obligations`: net pay, withholding tax, SGK, VAT, provisional and corporate tax, and loan instalments with due dates.
- `budget_lines`: the monthly budget per metric, prepared each December.
- `employees`, `payroll_lines` and `fixed_assets`.

**Industry detail**

| Industry | Tables |
|---|---|
| Retail | `stores`, `store_daily_sales`, `pos_receipts`, `pos_receipt_lines`, `loyalty_members` |
| Telecom | `plans`, `subscriber_base_monthly`, `subscribers`, `subscriber_daily_usage`, `network_cells`, `cell_daily_traffic` |
| Energy | `weather_daily`, `power_plants`, `plant_hourly_generation`, `market_prices_hourly`, `smart_meters`, `meter_daily_readings` |
| Airline | `airports`, `aircraft` (owned from the asset register, or leased), `flights`, `tickets` |
| Healthcare | `facilities`, `physicians`, `patients`, `encounters`, `encounter_diagnoses`, `diagnosis_codes`, `claims`, `facility_daily_census` |
| Logistics | `depots`, `trucks`, `shipments`, `truck_daily_telemetry`, `truck_gps_pings` |
| Manufacturing, textiles, food, pharma, automotive, defense | `machines`, `machine_daily_metrics` (with `days_to_failure` for predictive maintenance), `machine_sensor_hourly`, `maintenance_work_orders`, `production_orders` (lots and expiry dates for food and pharma), `stock_monthly`, `vehicles` (valid VINs) and `warranty_claims` for automotive, and `programmes`, `programme_milestones` and `programme_evm_monthly` (earned value) for defense |
| Software | `subscriptions`, `product_usage_daily`, `support_tickets` |
| Construction | `projects`, `project_progress_monthly`, `site_daily_logs` |

The largest detail tables cover a panel or the most recent years:
- receipts: a panel of stores (`stores.has_receipt_detail`)
- subscriber usage: a panel of subscribers
- smart meters: from the country's roll-out year
- GPS pings: from 2008
- hourly sensors: from 2015
- tickets: a sample of flights (`flights.has_ticket_detail`)

## Connected economy

The companies trade with each other (`interco_links`):
- Turkish supply chains: Bosphorus and Anatolia supply Çınar Market; Ostim supplies Marmara and Kalkan; Ufuk delivers for the Kervan group.
- European and US chains: Meridian delivers for Alpenhof, Helix and Rheinwerk; Cobalt sells software to US companies.
- Kervan Holding charges management fees to its subsidiaries.

On every link, the seller's sales invoice and the buyer's purchase invoice share the **same number, ETTN, date and
amount**, and **both bank statements show the payment on the same day**. The buyer's systems spell the seller's name
differently, e.g. *Bosphorus Gıda A.Ş.* vs *BOSPHORUS GIDA AS*. That's realistic, and good for entity-matching demos.

For reconciliation exercises, about **2%** of invoices are booked by the buyer a few days late (often in the next
month), and about **0.3%** are never booked by the buyer. Cross-border links (euro invoices in dollar books) add FX
differences. Anatolia, Bosphorus and Marmara (51%) form **Kervan Holding**, a ready-made consolidation case with
intercompany eliminations and a minority interest.

## Guarantees

Before upload, every company is validated:
- every journal entry balances;
- the trial balance balances for every month;
- month-end bank statement balances equal ledger account 102;
- detail tables add up to the ledger, to the cent:
  - receipt lines → receipts → store-days → daily consumer sales
  - flights → daily ticket sales, and tickets → flights
  - claims → insurer invoices, and self-pay encounters → patient payments
  - shipments → invoices
  - stock: opening + produced − sold = closing, with sold equal to invoice lines and produced equal to production orders
- invoice numbers are unique.

Both sides of every inter-company link are checked as well: matching invoices, equal amounts and the same payment day.

## Good uses

- **Finance analytics and FP&A:** margins, working capital, cash conversion and budget variance across three decades of crises.
- **Natural-language questions over financial data,** for AI agents and text-to-SQL.
- **Reconciliation and audit-style checks:** bank vs ledger, intercompany, consolidation.
- **Entity resolution:** the same company spelled differently in different systems.
- **Forecasting:** sales, usage, energy load, passenger demand.
- **Predictive maintenance:** sensors with failure labels.
- **Data-platform demos and benchmarks** at realistic enterprise scale.

## Limitations

- **Synthetic by design.** The distributions are plausible and internally consistent, but they're not fitted to any real company.
- **Approximate macro inputs.** Inflation, FX and interest rates follow real history approximately.
- **Currency.** Turkish amounts use the new lira for the whole period (pre-2005 old-lira amounts are not used).
- **Panels.** Very large operational tables cover a panel or recent years, not the whole population.
- **US sales tax** is not modelled (US companies show no VAT).

## How it was made

The dataset was generated by a deterministic Python generator, with one job per company running in parallel. Each
company is simulated top-down from an activity curve, through documents, settlement, treasury and taxes, into a
double-entry ledger. The trial balance, bank statements and tax obligations are all derived from that ledger. Detail
tables are generated year by year and tied back to the ledger. The same seed always gives the same data.
