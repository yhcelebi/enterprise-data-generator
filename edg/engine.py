"""Simulation of one company: documents, settlements, payroll, assets, financing and ledger.

Everything is generated top-down from a monthly activity curve, then posted to a
double-entry journal. The trial balance, bank statements and tax obligations are all
derived from that journal, so every table reconciles with every other table.
"""

import numpy as np
import pandas as pd

from . import masters
from . import reference as ref
from .companies import BANK_FOR, BY_ID, Company
from .ledger import CHART, Journal, trial_balance
from .timeline import (activity, day_weights, demand_factor, fx_daily, fx_monthly,
                       interest_monthly, price_index)

# Revenue per employee (real 2026 USD thousands) for developed-market companies.
RPE_K = {"manufacturing": 400, "textiles": 280, "food": 500, "retail": 400, "pharma": 550,
         "logistics": 260, "energy": 1300, "software": 300, "construction": 370, "banking": 400,
         "automotive": 850, "defense": 400, "telecom": 800, "airline": 500, "healthcare": 190}
WAGE_FACTOR = {"manufacturing": 1.0, "textiles": 0.75, "food": 0.85, "retail": 0.6, "pharma": 1.3,
               "logistics": 0.85, "energy": 1.2, "software": 1.5, "construction": 1.0, "banking": 1.2,
               "automotive": 1.15, "defense": 1.3, "telecom": 1.1, "airline": 1.2, "healthcare": 1.0}
TR_PRODUCTIVITY = 0.45
EMPLOYEE_SOCIAL = {"US": 0.0765, "UK": 0.08, "DE": 0.20, "NL": 0.12, "ES": 0.0635, "FR": 0.22}

OPEX_SPLIT = {
    # category: (supplier kind, account, default share)
    "rent": ("rent", "632", 0.18), "utilities": ("utilities", "632", 0.08),
    "telecom_it": ("telecom_it", "632", 0.12), "marketing": ("marketing", "631", 0.20),
    "logistics": ("logistics", "631", 0.12), "professional": ("professional", "632", 0.12),
    "maintenance": ("maintenance", "632", 0.10), "insurance": ("insurance", "632", 0.08),
}

# Target bank debt as a share of annual sales (capital-intensive industries borrow more).
LEVERAGE = {"manufacturing": 0.25, "textiles": 0.35, "food": 0.25, "retail": 0.20, "pharma": 0.15,
            "logistics": 0.35, "energy": 0.80, "software": 0.03, "construction": 0.35, "banking": 0.0,
            "automotive": 0.30, "defense": 0.15, "telecom": 0.60, "airline": 0.70, "healthcare": 0.40}

# Share of investment loans a Turkish company takes in euros (exporters and capital-heavy firms).
TR_FX_LOAN_SHARE = {"airline": 0.8, "energy": 0.7, "telecom": 0.6, "automotive": 0.6, "defense": 0.5,
                    "textiles": 0.5, "logistics": 0.4, "construction": 0.4}

BANK_NAMES = {"lale": "Lale Bank A.Ş.", "thames": "Thames Mutual Bank plc"}

DESC = {  # bank statement wording: (Turkish, English)
    "receipt": ("EFT GELEN", "INCOMING TRANSFER"), "payment": ("EFT GİDEN", "OUTGOING PAYMENT"),
    "cheque_in": ("ÇEK TAHSİLATI", "CHEQUE COLLECTION"), "cheque_out": ("ÇEK ÖDEMESİ", "CHEQUE PAID"),
    "payroll": ("MAAŞ ÖDEMESİ", "PAYROLL"), "withholding": ("MUHTASAR VE DAMGA VERGİSİ ÖDEMESİ", "PAYROLL TAX REMITTANCE"),
    "sgk": ("SGK PRİM ÖDEMESİ", "SOCIAL SECURITY CONTRIBUTIONS"), "vat": ("KDV ÖDEMESİ", "VAT PAYMENT"),
    "prov_tax": ("GEÇİCİ VERGİ ÖDEMESİ", "ESTIMATED TAX PAYMENT"),
    "corp_tax": ("KURUMLAR VERGİSİ ÖDEMESİ", "CORPORATE TAX PAYMENT"),
    "corp_refund": ("VERGİ İADESİ", "TAX REFUND"),
    "loan_in": ("KREDİ KULLANDIRIM", "LOAN DRAWDOWN"), "loan_out": ("KREDİ TAKSİT TAHSİLATI", "LOAN REPAYMENT"),
    "pos": ("POS TAHSİLAT", "CARD SETTLEMENT"), "cash": ("NAKİT YATIRMA", "CASH DEPOSIT"),
    "billing": ("ABONE TAHSİLATLARI", "DIRECT DEBIT COLLECTIONS"),
    "fee": ("HESAP İŞLETİM VE EFT ÜCRETLERİ", "ACCOUNT AND TRANSFER FEES"),
    "interest": ("VADELİ HESAP FAİZİ", "DEPOSIT INTEREST"), "dividend": ("KÂR PAYI ÖDEMESİ", "DIVIDEND PAYMENT"),
    "opening": ("DEVİR BAKİYESİ", "OPENING BALANCE"),
}


class CompanySim:
    def __init__(self, company: Company, cal, scale: float, seed: int):
        self.c = company
        self.p = company.profile
        self.cal = cal
        self.scale = scale
        self.rng = np.random.default_rng(seed)
        self.tr = company.turkish
        self.region = ref.COUNTRY_REGION[company.country]
        self.cur = ref.COUNTRY_CURRENCY[company.country]
        self.P = price_index(cal, self.region)
        self.fx_m = fx_monthly(cal, self.cur)
        self.fx_end = self.fx_m[-1]
        self.fx_d = fx_daily(cal, self.cur)
        self.eur_d = fx_daily(cal, "EUR")
        self.rate = interest_monthly(cal, self.region)
        self.demand = demand_factor(cal, company)
        self.act_real = activity(cal, company, scale, seed)
        self.rev_local = self.act_real * self.fx_end * self.P
        self.n_days = len(cal.days)
        self.last_day = self.n_days - 1
        self.dm = np.asarray(cal.day_month)
        self.w_day = day_weights(cal, company)
        self.month_first_day = np.searchsorted(self.dm, np.arange(cal.n_months))
        self.month_last_day = np.append(self.month_first_day[1:] - 1, self.n_days - 1)
        self.J = Journal(self.last_day)
        self.names = {}
        self.tables = {}
        self.bank = BANK_FOR[self.tr]
        self.bank_account = "102.01" if self.tr else "102"
        self.bank_code = f"{self.bank.upper()}-{self.cur}"
        self.inv_account = {"manufacturing": "152", "trading": "153", "services": None}[self.p.model]
        self.cogs_account = {"manufacturing": "620", "trading": "621", "services": "622"}[self.p.model]
        self._calendar_ext()
        self._price_steps()

    # ------------------------------------------------------------------ helpers

    def _calendar_ext(self):
        """Extended calendar (to cover due dates after the end) and next-business-day table."""
        ext = pd.date_range(self.cal.start, self.cal.end + pd.Timedelta(days=900), freq="D")
        hol = set(ref.HOLIDAYS[self.c.country])
        is_hol = np.array([(m, d) in hol for m, d in zip(ext.month, ext.day)])
        biz = (ext.dayofweek.values < 5) & ~is_hol
        nxt = np.empty(len(ext), dtype=np.int64)
        k = len(ext) - 1
        for i in range(len(ext) - 1, -1, -1):
            if biz[i]:
                k = i
            nxt[i] = k
        self.ext_dates = ext
        self.next_biz = nxt
        self.ext_year = ext.year.values
        self.ext_month = ext.month.values

    def biz(self, day):
        day = np.clip(np.asarray(day, dtype=np.int64), 0, len(self.next_biz) - 1)
        return self.next_biz[day]

    def day_of(self, year, month, dom):
        """Day index of a calendar date (vectorized); day-of-month is clipped to the month."""
        year, month, dom = np.broadcast_arrays(np.asarray(year), np.asarray(month), np.asarray(dom))
        last = pd.to_datetime(pd.DataFrame({"year": year.ravel(), "month": month.ravel(), "day": 1})) \
            + pd.offsets.MonthEnd(0)
        d = np.minimum(dom.ravel(), last.dt.day.values)
        ts = pd.to_datetime(pd.DataFrame({"year": year.ravel(), "month": month.ravel(), "day": d}))
        return ((ts - self.cal.start).dt.days.values).astype(np.int64)

    def next_month_day(self, m, dom):
        """Day index of day `dom` in the month after month index m."""
        m = np.asarray(m)
        y = self.cal.start.year + (self.cal.start.month - 1 + m + 1) // 12
        mo = (self.cal.start.month - 1 + m + 1) % 12 + 1
        return self.day_of(y, mo, dom)

    def dates(self, day):
        return (np.datetime64(self.cal.start.date(), "D") + np.asarray(day, dtype="timedelta64[D]"))

    def month_of_day(self, day):
        day = np.asarray(day, dtype=np.int64)
        y = self.ext_year[np.clip(day, 0, len(self.ext_year) - 1)]
        mo = self.ext_month[np.clip(day, 0, len(self.ext_month) - 1)]
        return (y - self.cal.start.year) * 12 + (mo - self.cal.start.month)

    def desc(self, key):
        return DESC[key][0 if self.tr else 1]

    def vat_rate(self, day, reduced=False):
        if self.c.country == "US":
            return np.zeros(len(np.atleast_1d(day)))
        year = self.ext_year[np.clip(np.asarray(day, dtype=np.int64), 0, len(self.ext_year) - 1)]
        if self.tr:
            if reduced:
                return np.where(year >= 2023, 0.10, 0.08)
            return np.array([ref.TR_VAT.get(int(y), 0.20) for y in np.atleast_1d(year)])
        std = ref.VAT[self.c.country]
        return np.full(len(np.atleast_1d(year)), std * (0.5 if reduced else 1.0))

    def _price_steps(self):
        """Price lists are updated monthly in high inflation, quarterly or yearly otherwise."""
        infl = np.array([ref.INFLATION[self.region][min(max(y, 1995), 2026) - 1995] for y in self.cal.years])
        steps = np.empty(self.cal.n_months)
        cur = self.P[0]
        months = self.cal.months.month.values
        for m in range(self.cal.n_months):
            if infl[m] > 25 or (infl[m] > 8 and months[m] in (1, 4, 7, 10)) or months[m] == 1 or m == 0:
                cur = self.P[m]
            steps[m] = cur
        self.P_price = steps
        self.infl = infl

    def source_system(self, day):
        years = self.ext_year[np.clip(np.asarray(day, dtype=np.int64), 0, len(self.ext_year) - 1)]
        hist = sorted(self.c.erp_history) or [(1900, "ERP")]
        starts = np.array([h[0] for h in hist])
        idx = np.clip(np.searchsorted(starts, years, side="right") - 1, 0, len(hist) - 1)
        return np.array([h[1] for h in hist], dtype=object)[idx]

    def pick_days(self, m, n):
        d0, d1 = self.month_first_day[m], self.month_last_day[m] + 1
        w = self.w_day[d0:d1]
        return d0 + self.rng.choice(d1 - d0, size=n, p=w / w.sum())

    # ------------------------------------------------------------------ run

    def run(self):
        self.build_masters()
        self.opening_balance()
        self.gen_sales()
        self.gen_b2c()
        self.gen_payroll()
        self.gen_assets()
        self.gen_costs_and_purchases()
        self.settle_purchases_prepare()
        self.settle_sales()
        self.settle_purchases()
        self.gen_vat()
        self.gen_bank_fees()
        self.financing_loop()
        self.closing_entries()
        self.gen_budget()
        self.finalize()
        return self.tables

    # ------------------------------------------------------------------ masters

    def build_masters(self):
        rng, c, cal = self.rng, self.c, self.cal
        self.products = masters.products(rng, c, cal, self.scale)
        self.customers = masters.customers(rng, c, cal, self.act_real, self.demand, self.scale)
        self.suppliers = masters.suppliers(rng, c, self.scale)
        for code, name in zip(self.customers.code, self.customers.name):
            self.names[code] = name
        for code, name in zip(self.suppliers.code, self.suppliers.name):
            self.names[code] = name
        self.cust_acct = self.customers.code.values if self.tr else np.full(len(self.customers), "120", object)
        self.supp_acct = self.suppliers.code.values if self.tr else np.full(len(self.suppliers), "320", object)
        self.retail_code = "120.99.00001" if self.tr else "120"
        self.names["120.99.00001"] = "Bireysel müşteriler"
        self.names[self.bank_account] = f"{BANK_NAMES[self.bank]} {self.cur}" if self.tr else None

    def opening_balance(self):
        """Opening balance sheet at the start of the warm-up (company existed before)."""
        monthly_rev = self.rev_local[:3].mean()
        self.opening = {
            "cash": round(monthly_rev * 0.4, 2),
            "inventory": round(monthly_rev * (1 - self.p.gross_margin) * self.p.dio_days / 30, 2)
            if self.inv_account else 0.0,
            "raw": 0.0,
        }
        if self.p.model == "manufacturing":
            self.opening["raw"] = round(self.opening["inventory"] * 0.4, 2)
            self.opening["inventory"] = round(self.opening["inventory"] * 0.6, 2)

    # ------------------------------------------------------------------ sales (B2B invoices)

    def gen_sales(self):
        rng, p, cal = self.rng, self.p, self.cal
        cust, prod = self.customers, self.products
        R = self.rev_local * (1 - p.b2c_share)
        if p.avg_invoice_usd <= 0 or R.sum() <= 0:
            self.invoices = pd.DataFrame()
            self.lines = pd.DataFrame()
            return
        avg_inv = p.avg_invoice_usd * self.fx_end * self.P
        n_m = rng.poisson(np.maximum(R, 0) / avg_inv)
        price_end = prod.list_price_usd_2026.values * self.fx_end
        drift = (1 + p.real_price_drift) ** cal.t_end
        lag = int(round(p.dio_days / 30))  # stock sold this month was bought `lag` months ago
        c_start, c_end = cust.start_month.values, cust.end_month.values
        c_exp, c_w = cust.is_export.values, cust.weight.values
        inv_parts, line_parts = [], []
        for m in range(cal.n_months):
            n = int(n_m[m])
            if n == 0:
                continue
            day = self.pick_days(m, n)
            active = (c_start <= m) & (c_end > m)
            dom_ids = np.where(active & ~c_exp)[0]
            exp_ids = np.where(active & c_exp)[0]
            want_exp = (rng.random(n) < self.c.export_share) if len(exp_ids) else np.zeros(n, bool)
            if len(dom_ids) == 0:
                want_exp[:] = True
                if len(exp_ids) == 0:
                    continue
            cid = np.empty(n, dtype=np.int64)
            for flag, ids in ((True, exp_ids), (False, dom_ids)):
                sel = want_exp == flag
                if sel.any():
                    w = c_w[ids]
                    cid[sel] = rng.choice(ids, size=sel.sum(), p=w / w.sum())
            size = rng.lognormal(0, 0.7, n) * c_w[cid] ** 0.25
            target = size / size.sum() * R[m]
            k = np.minimum(1 + rng.poisson(max(p.lines_per_invoice - 1, 0), n), 40)
            inv_local = np.repeat(np.arange(n), k)
            g = rng.gamma(1.0, size=len(inv_local))
            share = g / np.bincount(inv_local, weights=g)[inv_local]
            line_target = target[inv_local] * share
            prod_active = np.where((prod.launch_month.values <= m) & (prod.discontinue_month.values > m))[0]
            price_m = price_end[prod_active] * self.P_price[m] * drift[m]
            cost_base_m = price_end[prod_active] * self.P_price[max(m - lag, 0)] * drift[m]
            tlv = avg_inv[m] / max(p.lines_per_invoice, 1)
            pw = prod.popularity.values[prod_active] * np.minimum(1, tlv / price_m) ** 0.8
            pick = rng.choice(len(prod_active), size=len(inv_local), p=pw / pw.sum())
            pid = prod_active[pick]
            # Credit sales carry the cost of financing the payment term (vade farkı).
            terms_l = cust.payment_terms_days.values[cid][inv_local]
            fin = 1 + max(self.rate[m] - 0.02, 0) * terms_l / 365
            unit_price = np.round(price_m[pick] * fin, 4)
            disc = np.clip(cust.discount_rate.values[cid][inv_local]
                           + np.where(rng.random(len(inv_local)) < 0.08, rng.uniform(0.05, 0.15, len(inv_local)), 0),
                           0, 0.4)
            raw_qty = line_target / (unit_price * (1 - disc))
            qty = np.maximum(1, np.floor(raw_qty + rng.random(len(raw_qty))))
            inv_parts.append(pd.DataFrame({"m": m, "day": day, "cust": cid, "export": want_exp, "n_lines": k}))
            line_parts.append(pd.DataFrame({"m": m, "inv_local": inv_local, "product_idx": pid, "qty": qty,
                                            "unit_price": unit_price, "disc": disc, "cost_base": cost_base_m[pick]}))
        # Assign global invoice ids in date order.
        offsets = np.cumsum([0] + [len(x) for x in inv_parts[:-1]])
        for off, ip, lp in zip(offsets, inv_parts, line_parts):
            ip["tmp"] = np.arange(len(ip)) + off
            lp["tmp"] = lp.inv_local.values + off
        inv = pd.concat(inv_parts, ignore_index=True)
        lines = pd.concat(line_parts, ignore_index=True)
        order = np.lexsort((inv.tmp.values, inv.day.values))
        new_id = np.empty(len(inv), dtype=np.int64)
        new_id[order] = np.arange(len(inv))
        inv["inv"] = new_id[inv.tmp.values]
        lines["inv"] = new_id[lines.tmp.values]
        inv = inv.sort_values("inv").reset_index(drop=True)
        lines = lines.sort_values(["inv"], kind="stable").reset_index(drop=True)

        # Amounts.
        lines_day = inv.day.values[lines.inv.values]
        lines_export = inv.export.values[lines.inv.values]
        reduced = prod.vat_class.values[lines.product_idx.values] == -2.0
        vr = np.where(lines_export, 0.0, np.where(reduced, self.vat_rate(lines_day, True), self.vat_rate(lines_day)))
        lines["gross"] = np.round(lines.qty.values * lines.unit_price.values, 2)
        lines["discount"] = np.round(lines.gross.values * lines.disc.values, 2)
        lines["net"] = np.round(lines.gross.values - lines.discount.values, 2)
        lines["vat_rate"] = vr
        lines["vat"] = np.round(lines.net.values * vr, 2)
        lines["cost"] = np.round(lines.qty.values * lines.cost_base.values
                                 * prod.cost_ratio.values[lines.product_idx.values] * 0.96
                                 * rng.lognormal(0, 0.03, len(lines)), 2)
        sums = lines.groupby("inv")[["gross", "discount", "net", "vat", "cost"]].sum()
        for col in sums.columns:
            inv[col] = sums[col].reindex(inv.inv).values.round(2)
        inv["total"] = (inv.net + inv.vat).round(2)
        terms = cust.payment_terms_days.values[inv.cust.values]
        inv["due"] = inv.day.values + terms
        # Currency for export invoices.
        cc = cust.country.values[inv.cust.values]
        inv["currency"] = np.where(inv.export, np.where(cc == "US", "USD", "EUR"), self.cur)
        local_per_usd = self.fx_d[inv.day.values]
        rate = np.where(inv.currency == "USD", local_per_usd,
                        np.where(inv.currency == "EUR", local_per_usd / self.eur_d[inv.day.values], 1.0))
        inv["fx_rate"] = np.round(rate, 6)
        inv["total_fx"] = np.where(inv.export, np.round(inv.total / inv.fx_rate, 2), inv.total)
        self._number_sales(inv)
        self.invoices = inv
        self.lines = lines
        self._returns()
        self._post_sales()

    def _number_sales(self, inv):
        rng, c = self.rng, self.c
        year = self.ext_year[inv.day.values]
        if self.tr:
            efat = inv.m.values >= self.customers.efatura_month.values[inv.cust.values]
            earsiv = (~efat) & (year >= 2016) & ~inv.export.values
            channel = np.where(efat, "e-fatura", np.where(earsiv, "e-arşiv", "kağıt"))
            channel = np.where(inv.export.values & (year >= 2019), "e-fatura (ihracat)", channel)
            prefix = c.id[:3].upper()
            seq = inv.groupby([year, channel]).cumcount().values + 1
            electronic = channel != "kağıt"
            letter = np.where(channel == "e-arşiv", prefix[:2] + "A", prefix)
            num = np.where(electronic,
                           np.char.add(np.char.add(letter.astype(str), year.astype(str)),
                                       np.char.zfill(seq.astype(str), 9)),
                           np.char.add("A-", np.char.zfill((inv.groupby(year).cumcount().values + 1).astype(str), 6)))
            inv["channel"] = channel
            inv["number"] = num.astype(object)
            ettn = np.full(len(inv), None, dtype=object)
            ettn[electronic] = masters.uuids(rng, electronic.sum())
            inv["ettn"] = ettn
        else:
            seq = inv.groupby(year).cumcount().values + 1
            inv["channel"] = "edi" if c.industry in ("automotive", "retail") else "pdf"
            inv["number"] = [f"INV{y}-{s:07d}" for y, s in zip(year, seq)]
            inv["ettn"] = None

    def _returns(self):
        rng = self.rng
        inv = self.invoices
        pick = (~inv.export.values) & (rng.random(len(inv)) < 0.015)
        idx = np.where(pick)[0]
        frac = rng.uniform(0.1, 1.0, len(idx))
        r = pd.DataFrame({
            "orig": inv.inv.values[idx], "cust": inv.cust.values[idx],
            "day": self.biz(inv.day.values[idx] + rng.integers(5, 40, len(idx))),
            "net": -np.round(inv.net.values[idx] * frac, 2), "vat": -np.round(inv.vat.values[idx] * frac, 2),
            "cost": -np.round(inv.cost.values[idx] * frac, 2),
        })
        r["total"] = (r.net + r.vat).round(2)
        r = r[r.day <= self.last_day].reset_index(drop=True)
        r["number"] = [f"IAD{self.ext_year[d]}{i + 1:09d}" if self.tr else f"CR{self.ext_year[d]}-{i + 1:06d}"
                       for i, d in enumerate(r.day.values)]
        self.returns = r

    def _post_sales(self):
        inv, r = self.invoices, self.returns
        acct = self.cust_acct[inv.cust.values]
        rev = np.where(inv.export.values, "601", "600")
        names = self.customers.name.values[inv.cust.values]
        codes = self.customers.code.values[inv.cust.values]
        desc = np.char.add("Satış faturası " if self.tr else "Sales invoice ", inv.number.values.astype(str))
        self.J.entries(inv.day.values, [(acct, inv.total.values, 0.0), (rev, 0.0, inv.gross.values),
                                        ("611", inv.discount.values, 0.0), ("391", 0.0, inv.vat.values)],
                       "sales_invoice", inv.number.values, desc, codes, names)
        if self.inv_account:
            self.J.pairs(inv.day.values, inv.cost.values, self.cogs_account, self.inv_account, "cogs",
                         inv.number.values, "Satışların maliyeti" if self.tr else "Cost of sales")
        if len(r):
            racct = self.cust_acct[r.cust.values]
            self.J.entries(r.day.values, [("610", -r.net.values, 0.0), ("391", -r.vat.values, 0.0),
                                          (racct, 0.0, -r.total.values)],
                           "sales_return", r.number.values,
                           "Satış iadesi" if self.tr else "Credit note",
                           self.customers.code.values[r.cust.values], self.customers.name.values[r.cust.values])
            if self.inv_account:
                self.J.pairs(r.day.values, -r.cost.values, self.inv_account, self.cogs_account, "cogs_return",
                             r.number.values, "İade maliyeti" if self.tr else "Returned goods")

    # ------------------------------------------------------------------ consumer sales (daily summaries)

    def gen_b2c(self):
        p, rng, cal = self.p, self.rng, self.cal
        if p.b2c_share <= 0:
            self.b2c = pd.DataFrame()
            return
        wsum = np.bincount(self.dm, weights=self.w_day, minlength=cal.n_months)
        rev = self.rev_local[self.dm] * p.b2c_share * self.w_day / wsum[self.dm]
        rev *= rng.lognormal(0, 0.04, self.n_days)
        days = np.arange(self.n_days)
        year = self.ext_year[days] + self.cal.days.dayofyear.values / 366
        ind = self.c.industry
        reduced_mix = {"retail": 0.5, "healthcare": 1.0}.get(ind, 0.0)
        vr = (1 - reduced_mix) * self.vat_rate(days) + reduced_mix * self.vat_rate(days, True)
        if not self.tr and ind == "retail":
            vr = vr * 0.5
        gross = np.round(rev, 2)
        net = np.round(gross / (1 + vr), 2)
        vat = np.round(gross - net, 2)
        cash = card = billed = np.zeros(self.n_days)
        if ind in ("retail", "healthcare"):
            start_cash, end_cash = (0.8, 0.25) if self.tr else (0.65, 0.15)
            cash_share = np.interp(year, [1995, 2026.8], [start_cash, end_cash])
            if ind == "healthcare":
                cash_share = cash_share * 0.6
            cash = np.round(gross * cash_share, 2)
            card = np.round(gross - cash, 2)
        elif ind == "airline":
            card = np.round(gross * 0.85, 2)
            billed = np.round(gross - card, 2)
        else:  # telecom, energy and other subscription billing
            billed = gross
        online = np.zeros(self.n_days)
        if ind == "retail":
            launch = next((cal.month_index(e.month) for e in self.c.events if "nline" in e.label), None)
            if launch is not None:
                ramp = np.clip((self.dm - launch) / 120, 0, 1) * 0.12
                online = np.round(card * np.where(self.dm >= launch, ramp, 0), 2)
        self.b2c = pd.DataFrame({"day": days, "gross": gross, "net": net, "vat": vat, "cash": cash,
                                 "card": card, "billed": billed, "online": online})
        if self.inv_account:
            lag = int(round(p.dio_days / 30))
            lagged = self.P_price[np.maximum(self.dm - lag, 0)] / self.P_price[self.dm]
            self.b2c["cost"] = np.round(net * (1 - p.gross_margin) * lagged * rng.lognormal(0, 0.02, self.n_days), 2)
        else:
            self.b2c["cost"] = 0.0
        b = self.b2c
        label = {"retail": "Z raporu", "healthcare": "Hasta tahsilatları", "airline": "Bilet satışları"}.get(
            ind, "Abone faturaları") if self.tr else {"retail": "Store sales", "healthcare": "Patient payments",
                                                      "airline": "Ticket sales"}.get(ind, "Subscriber billing")
        doc = np.char.add(f"{label} ", self.dates(days).astype(str))
        self.J.entries(days, [("100", b.cash.values, 0.0), ("108", b.card.values, 0.0),
                              (self.retail_code, b.billed.values, 0.0), ("600", 0.0, b.net.values),
                              ("391", 0.0, b.vat.values)], "consumer_sales", doc, label)
        if self.inv_account:
            self.J.pairs(days, b.cost.values, self.cogs_account, self.inv_account, "cogs", doc,
                         "Satışların maliyeti" if self.tr else "Cost of sales")
        nxt = self.biz(days + 1)
        self.J.pairs(nxt, b.cash.values, self.bank_account, "100", "cash_deposit", doc, self.desc("cash"))
        comm_rate = 0.012 if self.tr else 0.015
        comm = np.round(b.card.values * comm_rate, 2)
        self.J.entries(nxt, [(self.bank_account, b.card.values - comm, 0.0), ("653", comm, 0.0),
                             ("108", 0.0, b.card.values)], "card_settlement", doc, self.desc("pos"))
        if b.billed.sum() > 0:
            collect = [(20, 0.97), (50, 0.02)]
            for lag, share in collect:
                amt = np.round(b.billed.values * share, 2)
                self.J.pairs(self.biz(days + lag), amt, self.bank_account, self.retail_code, "billing_collection",
                             doc, self.desc("billing"))
            bad = np.round(b.billed.values - np.round(b.billed.values * 0.97, 2) - np.round(b.billed.values * 0.02, 2), 2)
            month_end = self.month_last_day[np.minimum(self.dm + 6, cal.n_months - 1)]
            self.J.pairs(month_end, bad, "128", self.retail_code, "doubtful_transfer", doc,
                         "Şüpheli alacağa aktarım" if self.tr else "Transfer to doubtful")
            self.J.pairs(month_end, bad, "654", "129", "bad_debt_provision", doc,
                         "Şüpheli alacak karşılığı" if self.tr else "Allowance for doubtful receivables")

    # ------------------------------------------------------------------ payroll

    def gen_payroll(self):
        c, cal, rng = self.c, self.cal, self.rng
        prof = self.p
        from dataclasses import replace
        # masters.employees applies a 0.6 productivity factor to Turkish companies; undo it here.
        rpe = RPE_K[c.industry] * (TR_PRODUCTIVITY / 0.6 if self.tr else 1.0)
        prof_local = replace(prof, rev_per_employee_k=rpe)
        emp = masters.employees(rng, _ProfileProxy(self.c, prof_local), cal, self.act_real, self.scale)
        self.employees = emp
        n_m = cal.n_months
        m_from = np.maximum(emp.hire_month.values, 0)
        m_to = np.minimum(emp.term_month.values, n_m - 1)
        length = np.maximum(m_to - m_from + 1, 0)
        e_idx = np.repeat(np.arange(len(emp)), length)
        month = m_from[e_idx] + (np.arange(len(e_idx)) - np.repeat(np.cumsum(length) - length, length))
        # Wage index with raises in January (and July in high inflation for Turkey).
        months = cal.months.month.values
        raise_idx = np.empty(n_m)
        cur = self.P[0]
        for m in range(n_m):
            if m == 0 or months[m] == 1 or (self.tr and months[m] == 7 and self.infl[m] >= 15):
                cur = self.P[m]
            raise_idx[m] = cur
        wage_idx = raise_idx * 1.012 ** cal.t_end
        grade = emp.grade.values[e_idx] - 1
        tenure = np.clip((month - emp.hire_month.values[e_idx]) / 12, 0, 40)
        ratio = masters.GRADE_MULT[grade] * emp.pay_factor.values[e_idx] * np.minimum(1 + 0.008 * tenure, 1.25)
        base = masters.BASE_WAGE_END[c.country] * WAGE_FACTOR[c.industry]
        gross = np.round(base * ratio * wage_idx[month], 2)
        is_term = (month == emp.term_month.values[e_idx])
        reason = emp.termination_reason.values[e_idx]
        sev_mult = np.where(is_term & (reason == "layoff"), tenure * (1.0 if self.tr else 0.5),
                            np.where(is_term & (reason == "retirement") & self.tr, tenure, 0.0))
        severance = np.round(gross * sev_mult, 2)
        eff = 0.15 + 0.20 * (1 - ratio ** -0.6)
        if self.tr:
            emp_soc = np.round(gross * 0.14, 2)
            emp_unemp = np.round(gross * 0.01, 2)
            income_tax = np.round((gross - emp_soc - emp_unemp) * eff, 2)
            stamp = np.round((gross + severance) * 0.00759, 2)
            er_soc = np.round(gross * 0.155, 2)
            er_unemp = np.round(gross * 0.02, 2)
        else:
            emp_soc = np.round(gross * EMPLOYEE_SOCIAL[c.country], 2)
            emp_unemp = np.zeros(len(gross))
            income_tax = np.round(gross * ref.PAYROLL_TAX[c.country] * (0.75 + 0.35 * (1 - ratio ** -0.6)), 2)
            stamp = np.zeros(len(gross))
            er_soc = np.round(gross * ref.EMPLOYER_COST[c.country], 2)
            er_unemp = np.zeros(len(gross))
        net = np.round(gross + severance - emp_soc - emp_unemp - income_tax - stamp, 2)
        pay = pd.DataFrame({
            "m": month, "employee_idx": e_idx, "department": emp.department.values[e_idx],
            "gross_pay": gross, "severance_pay": severance, "employee_social": emp_soc,
            "employee_unemployment": emp_unemp, "income_tax": income_tax, "stamp_tax": stamp,
            "net_pay": net, "employer_social": er_soc, "employer_unemployment": er_unemp,
        })
        pay["total_employer_cost"] = (pay.gross_pay + pay.severance_pay + pay.employer_social
                                      + pay.employer_unemployment).round(2)
        # Pay day.
        pay_rule = "month_end" if (not self.tr or rng.random() < 0.6) else "next_5"
        month_end_biz = np.array([self.next_biz[d] if self.ext_dates[self.next_biz[d]].month == self.ext_dates[d].month
                                  else self._prev_biz(d) for d in self.month_last_day])
        pay_day_m = month_end_biz if pay_rule == "month_end" else self.biz(self.next_month_day(np.arange(n_m), 5))
        pay["pay_day"] = pay_day_m[pay.m.values]
        self.payroll = pay
        self._post_payroll(pay)

    def _prev_biz(self, d):
        while not ((self.ext_dates[d].dayofweek < 5) and self.next_biz[d] == d):
            d -= 1
        return d

    def _bucket_account(self, bucket):
        if bucket == "cost":
            return {"manufacturing": "152", "services": "622", "trading": "631"}[self.p.model]
        return bucket

    def _post_payroll(self, pay):
        dept_bucket = {d: self._bucket_account(b) for d, _, b in self.p.departments}
        g = pay.groupby(["m", "department"], sort=True).agg(
            gross=("gross_pay", "sum"), sev=("severance_pay", "sum"), es=("employee_social", "sum"),
            eu=("employee_unemployment", "sum"), it=("income_tax", "sum"), st=("stamp_tax", "sum"),
            net=("net_pay", "sum"), ers=("employer_social", "sum"), eru=("employer_unemployment", "sum"),
            pay_day=("pay_day", "first")).reset_index()
        g["acct"] = g.department.map(dept_bucket)
        g["cost"] = (g.gross + g.sev + g.ers + g.eru).round(2)
        g["withholding"] = (g.it + g.st).round(2)
        g["social"] = (g.es + g.eu + g.ers + g.eru).round(2)
        g["net"] = (g.cost - g.withholding - g.social).round(2)
        day = self.month_last_day[g.m.values]
        period = self.cal.months[g.m.values].astype(str)
        label = "Bordro " if self.tr else "Payroll "
        doc = np.char.add(label, np.char.add(period.values.astype(str), np.char.add(" ", g.department.values.astype(str))))
        self.J.entries(day, [(g.acct.values, g.cost.values, 0.0), ("335", 0.0, g.net.values),
                             ("360", 0.0, g.withholding.values), ("361", 0.0, g.social.values)],
                       "payroll", doc, doc)
        self.payroll_cost_by_bucket = g.groupby(["m", "acct"])["cost"].sum()
        mtot = g.groupby("m").agg(net=("net", "sum"), withholding=("withholding", "sum"),
                                  social=("social", "sum"), pay_day=("pay_day", "first")).reset_index()
        periods = self.cal.months[mtot.m.values].astype(str).values
        self.J.pairs(mtot.pay_day.values, mtot.net.values, "335", self.bank_account, "salary_payment",
                     np.char.add(label, periods.astype(str)), np.char.add(self.desc("payroll") + " ", periods.astype(str)))
        if self.tr:
            wh_day = self.biz(self.next_month_day(mtot.m.values, 26))
            sgk_day = self.biz(self.next_month_day(mtot.m.values, 31))
        else:
            wh_day = sgk_day = self.biz(self.next_month_day(mtot.m.values, 15))
        self.J.pairs(wh_day, mtot.withholding.values, "360", self.bank_account, "withholding_payment",
                     np.char.add("MUH-" if self.tr else "PTX-", periods.astype(str)),
                     np.char.add(self.desc("withholding") + " ", periods.astype(str)))
        self.J.pairs(sgk_day, mtot.social.values, "361", self.bank_account, "social_security_payment",
                     np.char.add("SGK-" if self.tr else "SOC-", periods.astype(str)),
                     np.char.add(self.desc("sgk") + " ", periods.astype(str)))
        self.obligation_rows = []
        for cat, amounts, days in (("payroll", mtot.net.values, mtot.pay_day.values),
                                   ("withholding", mtot.withholding.values, wh_day),
                                   ("sgk", mtot.social.values, sgk_day)):
            self.obligation_rows.append(pd.DataFrame({
                "category": cat, "basis": "payroll", "reference": periods, "period": periods,
                "due_day": days, "amount": np.round(amounts, 2), "principal": np.nan, "interest": np.nan}))

    # ------------------------------------------------------------------ fixed assets

    def gen_assets(self):
        rng, cal, p = self.rng, self.cal, self.p
        capex = self.rev_local * p.capex_ratio * rng.lognormal(0, 0.25, cal.n_months)
        for ev in self.c.events:
            if ev.kind == "step" and ev.size > 0:
                i0 = cal.month_index(ev.month)
                extra = ev.size * self.rev_local[max(i0, 0)] * 12 * p.capex_ratio * 4
                for k in range(max(ev.ramp, 1)):
                    if 0 <= i0 - 6 + k < cal.n_months:
                        capex[i0 - 6 + k] += extra / max(ev.ramp, 1)
        opening_nbv = self.rev_local[0] * 12 * p.capex_ratio * 7
        fa = masters.fixed_assets(rng, self.c, cal, capex, self.fx_end, self.P, opening_nbv)
        fa["acq_month"] = np.maximum(fa.acq_month.values, -(fa.useful_life_months.values - 1))
        fa["dispose_month"] = fa.acq_month + fa.useful_life_months
        model = p.model

        def bucket(cls):
            if cls in ("building", "machinery"):
                return {"manufacturing": "152", "services": "622", "trading": "631"}[model]
            if cls == "vehicle":
                return "622" if model == "services" else "631"
            return "632"

        fa["dep_account"] = fa.asset_class.map(bucket)
        fa["monthly_dep"] = (fa.cost / fa.useful_life_months).round(2)
        self.assets = fa
        # Opening stock and its accumulated depreciation.
        old = fa[fa.acq_month < 0]
        acc_open = (old.monthly_dep * np.maximum(0, -1 - old.acq_month)).round(2)
        lines = [(self.bank_account, self.opening["cash"], 0.0)]
        if self.inv_account:
            lines.append((self.inv_account, self.opening["inventory"], 0.0))
        if self.opening["raw"]:
            lines.append(("150", self.opening["raw"], 0.0))
        for acct, cost in old.groupby("account").cost.sum().items():
            lines.append((acct, round(cost, 2), 0.0))
        lines.append(("257", 0.0, round(acc_open.sum(), 2)))
        total_dr = sum(d for _, d, _ in lines)
        total_cr = sum(cr for _, _, cr in lines)
        lines.append(("500", 0.0, round(total_dr - total_cr, 2)))
        self.J.entries([0], [(a, np.array([d]), np.array([cr])) for a, d, cr in lines], "opening",
                       "AÇILIŞ" if self.tr else "OPENING", self.desc("opening"))
        # Monthly depreciation by expense account.
        n_m = cal.n_months
        self.dep_by_bucket = {}
        for acct, grp in fa.groupby("dep_account"):
            diff = np.zeros(n_m + 1)
            start = np.clip(grp.acq_month.values + 1, 0, n_m)
            stop = np.clip(grp.acq_month.values + grp.useful_life_months.values + 1, 0, n_m)
            np.add.at(diff, start, grp.monthly_dep.values)
            np.add.at(diff, stop, -grp.monthly_dep.values)
            dep = np.round(np.cumsum(diff)[:n_m], 2)
            self.dep_by_bucket[acct] = dep
            mm = np.where(dep > 0)[0]
            self.J.pairs(self.month_last_day[mm], dep[mm], acct, "257", "depreciation",
                         np.char.add("AMR-" if self.tr else "DEP-", cal.months[mm].astype(str).values.astype(str)),
                         "Amortisman" if self.tr else "Depreciation")
        disp = fa[(fa.dispose_month >= 0) & (fa.dispose_month < n_m)]
        if len(disp):
            self.J.pairs(self.month_last_day[disp.dispose_month.values], disp.cost.values, "257", disp.account.values,
                         "asset_disposal", disp.asset_tag.values, "Aktiften çıkış" if self.tr else "Asset disposal")
        new = fa[fa.acq_month >= 0]
        self.capex_invoices = pd.DataFrame({
            "m": new.acq_month.values, "day": [self.pick_days(m, 1)[0] for m in new.acq_month.values],
            "account": new.account.values, "net": new.cost.values, "kind": "capex", "asset_tag": new.asset_tag.values,
        })

    # ------------------------------------------------------------------ costs, purchases and opex

    def _monthly(self, day, amount):
        return np.bincount(self.dm[np.clip(day, 0, self.last_day)], weights=amount, minlength=self.cal.n_months)

    def gen_costs_and_purchases(self):
        p, cal, rng = self.p, self.cal, self.rng
        n_m = cal.n_months
        inv, r, b = self.invoices, self.returns, self.b2c
        ns = np.zeros(n_m)
        cogs = np.zeros(n_m)
        if len(inv):
            ns += self._monthly(inv.day.values, inv.net.values)
            cogs += self._monthly(inv.day.values, inv.cost.values)
        if len(r):
            ns += self._monthly(r.day.values, r.net.values)
            cogs += self._monthly(r.day.values, r.cost.values)
        if len(b):
            ns += self._monthly(b.day.values, b.net.values)
            cogs += self._monthly(b.day.values, b.cost.values)
        self.net_sales_m = ns
        pay_b = self.payroll_cost_by_bucket.unstack(fill_value=0.0).reindex(range(n_m), fill_value=0.0)

        def bucket(acct):
            return pay_b[acct].values if acct in pay_b.columns else np.zeros(n_m)

        def dep(acct):
            return self.dep_by_bucket.get(acct, np.zeros(n_m))

        purchases = []
        if p.model == "trading":
            target = pd.Series(cogs).rolling(3, min_periods=1).mean().values * p.dio_days / 30
            inv_bal = self.opening["inventory"]
            buy = np.zeros(n_m)
            for m in range(n_m):
                buy[m] = max(0.0, cogs[m] + target[m] - inv_bal)
                inv_bal += buy[m] - cogs[m]
            purchases.append(("goods", "153", buy, 1.5))
        elif p.model == "manufacturing":
            labor = bucket("152")
            depp = dep("152")
            cogs_s = pd.Series(cogs).rolling(12, min_periods=1).mean().values  # lumpy sales -> smooth targets
            oh = 0.07 * cogs_s
            fg_t = cogs_s * p.dio_days * 0.6 / 30
            fg = self.opening["inventory"]
            rm = self.opening["raw"]
            mc = np.zeros(n_m)
            rmp = np.zeros(n_m)
            idle = np.zeros(n_m)
            for m in range(n_m):
                pc = cogs[m] + fg_t[m] - fg
                mc[m] = max(0.25 * max(pc, 0), pc - labor[m] - depp[m] - oh[m])
                fg += mc[m] + labor[m] + depp[m] + oh[m] - cogs[m]
                # Production cost beyond normal stock levels is expensed as idle capacity.
                cap = 1.5 * fg_t[m]
                if fg > cap:
                    idle[m] = fg - cap
                    fg = cap
                rm_t = cogs_s[m] * 0.6 * p.dio_days * 0.4 / 30
                rmp[m] = max(0.0, mc[m] + rm_t - rm)
                rm += rmp[m] - mc[m]
            mi = np.where(idle > 0)[0]
            self.J.pairs(self.month_last_day[mi], np.round(idle[mi], 2), "620", "152", "idle_capacity",
                         np.char.add("ATL-" if self.tr else "IDL-", cal.months[mi].astype(str).values.astype(str)),
                         "Atıl kapasite ve üretim farkları" if self.tr else "Idle capacity and production variances")
            purchases.append(("goods", "150", rmp, 1.5))
            purchases.append(("utilities", "152", oh * 0.6, 0.5))
            purchases.append(("maintenance", "152", oh * 0.4, 0.3))
            mm = np.where(mc > 0)[0]
            self.J.pairs(self.month_last_day[mm], np.round(mc[mm], 2), "152", "150", "production",
                         np.char.add("URT-" if self.tr else "PRD-", cal.months[mm].astype(str).values.astype(str)),
                         "Üretime sevk edilen hammadde" if self.tr else "Materials issued to production")
        else:  # services: direct costs
            dc = ns * (1 - p.gross_margin) * rng.lognormal(0, 0.03, n_m)
            other = np.maximum(0.1 * dc, dc - bucket("622") - dep("622"))
            purchases.append(("subcontract", "622", other * 0.65, 1.0))
            purchases.append(("goods", "622", other * 0.35, 1.0))
        # Operating expenses with operating leverage (fixed part follows last year's sales).
        smooth = pd.Series(ns).rolling(12, min_periods=1).mean().shift(6).bfill().values
        opex = p.opex_ratio * ((1 - p.fixed_opex_share) * ns + p.fixed_opex_share * smooth)
        nonpay = opex - bucket("631") - bucket("632") - bucket("630") - dep("631") - dep("632")
        nonpay = np.maximum(0.2 * opex, nonpay)
        split = dict((k, v[2]) for k, v in OPEX_SPLIT.items())
        if p.model == "services":
            split["logistics"] = 0.03
        if self.c.industry in ("retail", "pharma", "telecom", "software"):
            split["marketing"] = 0.30
        total_share = sum(split.values())
        rnd_heavy = self.c.industry in ("pharma", "defense", "software", "automotive")
        for cat, (kind, acct, _) in OPEX_SPLIT.items():
            amt = nonpay * split[cat] / total_share
            if cat == "rent" and self.c.industry == "retail":
                acct = "631"
            if cat == "professional" and rnd_heavy:
                purchases.append((kind, "630", amt * 0.5, 0.3))
                amt = amt * 0.5
            purchases.append((kind, acct, amt, 0.3 if cat not in ("rent", "utilities", "insurance") else 0))
        rows = [self._purchase_rows(kind, acct, amounts, size) for kind, acct, amounts, size in purchases]
        cap = self.capex_invoices
        if len(cap):
            sup = self.suppliers[self.suppliers.kind == "capex"]
            cap = cap.assign(supplier=rng.choice(sup.supplier_idx.values, len(cap),
                                                 p=sup.weight.values / sup.weight.sum()))
            rows.append(cap[["m", "day", "supplier", "account", "net", "kind"]])
        pi = pd.concat(rows, ignore_index=True)
        pi = pi[pi.net > 0.005].sort_values(["day"], kind="stable").reset_index(drop=True)
        self._finish_purchases(pi)

    def _purchase_rows(self, kind, acct, amounts, size_usd_k):
        """Split monthly purchase amounts into supplier invoices."""
        rng = self.rng
        sup = self.suppliers[self.suppliers.kind == kind]
        if len(sup) == 0:
            sup = self.suppliers[self.suppliers.kind == "goods"]
        avg = max(self.p.avg_invoice_usd, 2000) * size_usd_k * self.fx_end * self.P if size_usd_k else None
        parts = []
        for m in np.where(amounts > 0)[0]:
            n = 1 if avg is None else int(min(300, max(1, rng.poisson(amounts[m] / avg[m] + 0.5))))
            if kind == "insurance" and self.cal.months[m].month % 3 != 1:
                continue
            amt = amounts[m] * (3 if kind == "insurance" else 1)
            w = sup.weight.values
            s = rng.choice(sup.supplier_idx.values, n, p=w / w.sum())
            g = rng.gamma(1.0, size=n)
            day = self.pick_days(m, n) if kind not in ("rent",) else np.full(n, self.month_first_day[m])
            parts.append(pd.DataFrame({"m": m, "day": day, "supplier": s, "account": acct,
                                       "net": np.round(amt * g / g.sum(), 2), "kind": kind}))
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
            columns=["m", "day", "supplier", "account", "net", "kind"])

    def _finish_purchases(self, pi):
        rng = self.rng
        sup = self.suppliers
        country = sup.country.values[pi.supplier.values]
        cur = np.where(country == self.c.country, self.cur, np.where(country == "US", "USD", "EUR"))
        foreign = cur != self.cur
        pi["currency"] = cur
        day_c = np.clip(pi.day.values, 0, self.last_day)
        rate = np.where(cur == "USD", self.fx_d[day_c], np.where(cur == "EUR", self.fx_d[day_c] / self.eur_d[day_c], 1.0))
        pi["fx_rate"] = np.where(foreign, np.round(rate, 6), 1.0)
        reduced = (self.c.industry in ("food",)) & (pi.kind.values == "goods")
        vr = np.where(foreign, 0.0, np.where(reduced, self.vat_rate(pi.day.values, True), self.vat_rate(pi.day.values)))
        if self.tr:
            vr = np.where(pi.kind.values == "rent", 0.0, vr)  # rent from individuals: withholding, no VAT
        pi["vat"] = np.round(pi.net.values * vr, 2)
        pi["total"] = (pi.net + pi.vat).round(2)
        pi["total_fx"] = np.where(pi.currency != self.cur, np.round(pi.total / pi.fx_rate, 2), pi.total)
        pi["due"] = pi.day.values + sup.payment_terms_days.values[pi.supplier.values]
        pi.loc[pi.kind == "rent", "due"] = pi.loc[pi.kind == "rent", "day"]
        year = self.ext_year[pi.day.values]
        if self.tr:
            electronic = (year >= 2014) & ~foreign & (rng.random(len(pi)) < np.clip((year - 2013) / 6, 0, 0.95))
            pref = np.array(["".join(rng.choice(list("ABCDEFGHKLMNPRSTUVYZ"), 3)) for _ in range(len(sup))])
            seq = rng.integers(1, 999_999_999, len(pi))
            num = np.where(electronic,
                           [f"{pref[s]}{y}{q:09d}" for s, y, q in zip(pi.supplier.values, year, seq)],
                           [f"{pref[s][0]}-{q % 1_000_000:06d}" for s, q in zip(pi.supplier.values, seq)])
            pi["channel"] = np.where(electronic, "e-fatura", "kağıt")
            ettn = np.full(len(pi), None, dtype=object)
            ettn[electronic] = masters.uuids(rng, electronic.sum())
            pi["ettn"] = ettn
        else:
            seq = rng.integers(1, 9_999_999, len(pi))
            num = [f"S{s:04d}-{y}-{q:07d}" for s, y, q in zip(pi.supplier.values, year, seq)]
            pi["channel"] = "pdf"
            pi["ettn"] = None
        pi["number"] = np.array(num, dtype=object)
        pi = pi.drop_duplicates("number").reset_index(drop=True)
        pi["pinv"] = np.arange(len(pi))
        self.purchases = pi
        acct = self.supp_acct[pi.supplier.values]
        names = sup.name.values[pi.supplier.values]
        codes = sup.code.values[pi.supplier.values]
        self.J.entries(pi.day.values, [(pi.account.values, pi.net.values, 0.0), ("191", pi.vat.values, 0.0),
                                       (acct, 0.0, pi.total.values)], "purchase_invoice", pi.number.values,
                       np.char.add("Alış faturası " if self.tr else "Supplier invoice ", pi.number.values.astype(str)),
                       codes, names)

    # ------------------------------------------------------------------ settlement

    def _stress(self, day):
        m = np.clip(self.month_of_day(day), 0, self.cal.n_months - 1)
        return 1 + 3 * np.clip(1 - self.demand[m], 0, None)

    def _cheque_era(self, day):
        year = self.ext_year[np.clip(day, 0, len(self.ext_year) - 1)]
        return np.interp(year, [1994, 2017, 2026], [1.0, 1.0, 0.45])

    def settle_purchases_prepare(self):
        """Planned payment day of every supplier invoice (needed before cheques are endorsed)."""
        rng = self.rng
        pi = self.purchases
        delay = rng.normal(3, 5, len(pi)) + 12 * (self._stress(pi.due.values) - 1)
        pi["pay_day"] = self.biz(pi.due.values + np.maximum(delay, -5).astype(int))
        pi.loc[pi.kind == "rent", "pay_day"] = self.biz(pi.loc[pi.kind == "rent", "day"].values)
        pi["remaining"] = pi.total.values.copy()

    def settle_sales(self):
        rng, cust = self.rng, self.customers
        inv, r = self.invoices, self.returns
        self.payments, self.cheques_in, self.cheques_out = [], [], []
        if len(inv) == 0:
            return
        amount = inv.total.values.copy()
        ret_total = np.zeros(len(inv))
        if len(r):
            np.add.at(ret_total, r.orig.values, -r.total.values)
        due_amt = np.round(amount - ret_total, 2)
        cid = inv.cust.values
        dm = cust.delay_mean.values[cid] * self._stress(inv.due.values)
        delay = rng.normal(dm, 4 + 0.4 * dm)
        pay_day = self.biz(inv.due.values + np.maximum(delay, -10).astype(int))
        default_m = cust.default_month.values[cid]
        defaulted = (default_m >= 0) & (self.month_of_day(pay_day) >= default_m)
        partial = (rng.random(len(inv)) < 0.08) & ~defaulted
        first_share = np.where(partial, rng.uniform(0.5, 0.9, len(inv)), 1.0)
        a1 = np.round(due_amt * first_share, 2)
        a2 = np.round(due_amt - a1, 2)
        d2 = self.biz(pay_day + rng.integers(15, 45, len(inv)))
        pays = pd.concat([
            pd.DataFrame({"inv": inv.inv.values, "day": pay_day, "amount": a1}),
            pd.DataFrame({"inv": inv.inv.values[partial], "day": d2[partial], "amount": a2[partial]}),
        ], ignore_index=True)
        pays = pays[~defaulted[pays.inv.values] & (pays.amount > 0.004)]
        pays = pays[pays.day <= self.last_day].reset_index(drop=True)
        pc = inv.cust.values[pays.inv.values]
        export = inv.export.values[pays.inv.values]
        cheque_p = cust.cheque_share.values[pc] * self._cheque_era(pays.day.values)
        is_cheque = (~export) & (rng.random(len(pays)) < cheque_p)
        pays["method"] = np.where(is_cheque, "cheque", "transfer")
        pays["cust"] = pc
        self._post_receipts(pays, inv)
        self._bad_debts(inv, due_amt, defaulted)

    def _post_receipts(self, pays, inv):
        rng, cust = self.rng, self.customers
        acct = self.cust_acct[pays.cust.values]
        codes = cust.code.values[pays.cust.values]
        names = cust.name.values[pays.cust.values]
        number = inv.number.values[pays.inv.values]
        tr = pays.method.values == "transfer"
        # FX difference on export receipts.
        export = inv.export.values[pays.inv.values]
        fx_inv = inv.fx_rate.values[pays.inv.values]
        cur = inv.currency.values[pays.inv.values]
        day_c = np.clip(pays.day.values, 0, self.last_day)
        fx_pay = np.where(cur == "USD", self.fx_d[day_c],
                          np.where(cur == "EUR", self.fx_d[day_c] / self.eur_d[day_c], 1.0))
        amount_fx = np.where(export, pays.amount.values / np.where(fx_inv > 0, fx_inv, 1), pays.amount.values)
        bank_amt = np.round(np.where(export, amount_fx * fx_pay, pays.amount.values), 2)
        diff = np.round(bank_amt - pays.amount.values, 2)
        gain = np.where(diff > 0, diff, 0.0)
        loss = np.where(diff < 0, -diff, 0.0)
        desc = np.char.add(np.char.add(self.desc("receipt") + " ", names.astype(str)), np.char.add(" ", number.astype(str)))
        t = tr
        self.J.entries(pays.day.values[t], [(self.bank_account, bank_amt[t], 0.0), ("656", loss[t], 0.0),
                                            (acct[t], 0.0, pays.amount.values[t]), ("646", 0.0, gain[t])],
                       "customer_receipt", number[t], desc[t], codes[t], names[t])
        self.payments.append(pd.DataFrame({
            "direction": "sale", "invoice_number": number, "counterparty_code": codes, "paid_day": pays.day.values,
            "amount": pays.amount.values, "method": pays.method.values, "amount_fx": np.round(amount_fx, 2),
            "currency": cur}))
        # Cheques received.
        q = pays[~tr].reset_index(drop=True)
        if len(q) == 0:
            return
        qn = number[~tr]
        qcodes, qnames, qacct = codes[~tr], names[~tr], acct[~tr]
        tenor = rng.choice([30, 45, 60, 90, 120], len(q), p=[0.25, 0.15, 0.3, 0.2, 0.1])
        due = self.biz(q.day.values + tenor)
        numbers = np.char.zfill(rng.integers(1, 9_999_999, len(q)).astype(str), 7)
        numbers = np.array([f"{n}-{i}" for i, n in enumerate(numbers)]) if len(set(numbers)) < len(numbers) else numbers
        self.J.pairs(q.day.values, q.amount.values, "101", qacct, "cheque_received", numbers,
                     np.char.add("Müşteri çeki " if self.tr else "Cheque received ", qn.astype(str)), qcodes, qnames)
        bounce_p = 0.02 * self._stress(due)
        bounced = rng.random(len(q)) < bounce_p
        endorse_try = (~bounced) & (rng.random(len(q)) < 0.15)
        endorsed_day = np.full(len(q), -1)
        endorsed_supplier = np.full(len(q), -1)
        pi = self.purchases
        cand = pi[(pi.kind.isin(["goods", "subcontract", "capex"])) & (pi.currency == self.cur)]
        cand_day = cand.pay_day.values
        cand_idx = cand.pinv.values
        order = np.argsort(cand_day, kind="stable")
        cand_day, cand_idx = cand_day[order], cand_idx[order]
        remaining = pi.remaining.to_numpy(copy=True)
        for i in np.where(endorse_try)[0]:
            lo = np.searchsorted(cand_day, q.day.values[i] + 1)
            hi = np.searchsorted(cand_day, due[i] - 1)
            if hi <= lo:
                continue
            for j in rng.integers(lo, hi, min(5, hi - lo)):
                k = cand_idx[j]
                if remaining[k] >= q.amount.values[i]:
                    remaining[k] = round(remaining[k] - q.amount.values[i], 2)
                    endorsed_day[i] = cand_day[j]
                    endorsed_supplier[i] = k
                    break
        pi["remaining"] = remaining
        endorsed = endorsed_day >= 0
        collected = ~bounced & ~endorsed
        self.J.pairs(due[collected], q.amount.values[collected], self.bank_account, "101", "cheque_collection",
                     numbers[collected], np.char.add(self.desc("cheque_in") + " ", numbers[collected].astype(str)),
                     qcodes[collected], qnames[collected])
        if endorsed.any():
            k = endorsed_supplier[endorsed]
            sacct = self.supp_acct[pi.supplier.values[k]]
            self.J.pairs(endorsed_day[endorsed], q.amount.values[endorsed], sacct, "101", "cheque_endorsed",
                         numbers[endorsed], np.char.add("Çek cirosu " if self.tr else "Endorsed cheque ",
                                                        pi.number.values[k].astype(str)),
                         self.suppliers.code.values[pi.supplier.values[k]],
                         self.suppliers.name.values[pi.supplier.values[k]])
            self.payments.append(pd.DataFrame({
                "direction": "purchase", "invoice_number": pi.number.values[k],
                "counterparty_code": self.suppliers.code.values[pi.supplier.values[k]],
                "paid_day": endorsed_day[endorsed], "amount": q.amount.values[endorsed], "method": "cheque",
                "amount_fx": q.amount.values[endorsed], "currency": self.cur}))
        if bounced.any():
            b = np.where(bounced)[0]
            self.J.pairs(due[b], q.amount.values[b], qacct[b], "101", "cheque_bounced", numbers[b],
                         "Karşılıksız çek" if self.tr else "Bounced cheque", qcodes[b], qnames[b])
            recover = rng.random(len(b)) < 0.7
            rd = self.biz(due[b] + rng.integers(30, 90, len(b)))
            self.J.pairs(rd[recover], q.amount.values[b][recover], self.bank_account, qacct[b][recover],
                         "customer_receipt", numbers[b][recover],
                         np.char.add(self.desc("receipt") + " ", qnames[b][recover].astype(str)),
                         qcodes[b][recover], qnames[b][recover])
            self.payments.append(pd.DataFrame({
                "direction": "sale", "invoice_number": None, "counterparty_code": qcodes[b][recover],
                "paid_day": rd[recover], "amount": q.amount.values[b][recover], "method": "transfer",
                "amount_fx": q.amount.values[b][recover], "currency": self.cur}))
            lost = b[~recover]
            dd = self.biz(due[lost] + 180)
            doubtful = np.array(["128" + a[3:] for a in qacct[lost]], dtype=object)
            for a, d in zip(qacct[lost], doubtful):
                self.names.setdefault(d, self.names.get(a))
            self.J.pairs(dd, q.amount.values[lost], doubtful, qacct[lost],
                         "doubtful_transfer", numbers[lost], "Şüpheli alacağa aktarım" if self.tr else "Transfer to doubtful",
                         qcodes[lost], qnames[lost])
            self.J.pairs(dd, q.amount.values[lost], "654", "129", "bad_debt_provision", numbers[lost],
                         "Şüpheli alacak karşılığı" if self.tr else "Allowance for doubtful receivables")
        status = np.where(due > self.last_day,
                          np.where(endorsed & (endorsed_day <= self.last_day), "ciro edildi",
                                   np.where(due - self.last_day <= 7, "tahsilde", "portföyde")),
                          np.where(bounced, "karşılıksız", np.where(endorsed, "ciro edildi", "tahsil edildi")))
        self.cheques_in.append(pd.DataFrame({
            "direction": "received", "number": numbers, "counterparty_code": qcodes, "issued_day": q.day.values,
            "due_day": due, "amount": q.amount.values, "status": status,
            "endorsed_to": np.where(endorsed, self.suppliers.code.values[pi.supplier.values[np.maximum(endorsed_supplier, 0)]],
                                    None)}))

    def _bad_debts(self, inv, due_amt, defaulted):
        """Invoices of defaulted customers move to doubtful receivables 180 days after due."""
        idx = np.where(defaulted & (due_amt > 0))[0]
        if len(idx) == 0:
            return
        day = self.biz(inv.due.values[idx] + 180)
        acct = self.cust_acct[inv.cust.values[idx]]
        doubtful = np.array(["128" + a[3:] for a in acct], dtype=object) if self.tr else "128"
        if self.tr:
            for a, d in zip(acct, doubtful):
                self.names[d] = self.names.get(a)
        codes = self.customers.code.values[inv.cust.values[idx]]
        names = self.customers.name.values[inv.cust.values[idx]]
        self.J.pairs(day, due_amt[idx], doubtful, acct, "doubtful_transfer", inv.number.values[idx],
                     "Şüpheli alacağa aktarım" if self.tr else "Transfer to doubtful", codes, names)
        self.J.pairs(day, due_amt[idx], "654", "129", "bad_debt_provision", inv.number.values[idx],
                     "Şüpheli alacak karşılığı" if self.tr else "Allowance for doubtful receivables", codes, names)

    def settle_purchases(self):
        rng = self.rng
        pi = self.purchases
        sup = self.suppliers
        amt = pi.remaining.values
        ok = (amt > 0.004) & (pi.pay_day.values <= self.last_day)
        p = pi[ok].reset_index(drop=True)
        amt = amt[ok]
        cheque_p = sup.cheque_share.values[p.supplier.values] * self._cheque_era(p.pay_day.values)
        is_cheque = (p.currency.values == self.cur) & (rng.random(len(p)) < cheque_p)
        acct = self.supp_acct[p.supplier.values]
        codes = sup.code.values[p.supplier.values]
        names = sup.name.values[p.supplier.values]
        foreign = p.currency.values != self.cur
        day_c = np.clip(p.pay_day.values, 0, self.last_day)
        fx_pay = np.where(p.currency.values == "USD", self.fx_d[day_c],
                          np.where(p.currency.values == "EUR", self.fx_d[day_c] / self.eur_d[day_c], 1.0))
        amount_fx = np.where(foreign, amt / p.fx_rate.values, amt)
        bank_amt = np.round(np.where(foreign, amount_fx * fx_pay, amt), 2)
        diff = np.round(bank_amt - amt, 2)
        loss = np.where(diff > 0, diff, 0.0)
        gain = np.where(diff < 0, -diff, 0.0)
        t = ~is_cheque
        desc = np.char.add(self.desc("payment") + " ", names.astype(str))
        self.J.entries(p.pay_day.values[t], [(acct[t], amt[t], 0.0), ("656", loss[t], 0.0),
                                             (self.bank_account, 0.0, bank_amt[t]), ("646", 0.0, gain[t])],
                       "supplier_payment", p.number.values[t], desc[t], codes[t], names[t])
        self.payments.append(pd.DataFrame({
            "direction": "purchase", "invoice_number": p.number.values, "counterparty_code": codes,
            "paid_day": p.pay_day.values, "amount": np.round(amt, 2), "method": np.where(is_cheque, "cheque", "transfer"),
            "amount_fx": np.round(amount_fx, 2), "currency": p.currency.values}))
        c = np.where(is_cheque)[0]
        if len(c):
            due = self.biz(p.pay_day.values[c] + rng.choice([30, 60, 90], len(c)))
            numbers = np.array([f"{self.c.id[:2].upper()}{i:07d}" for i in range(1, len(c) + 1)])
            self.J.pairs(p.pay_day.values[c], amt[c], acct[c], "103", "cheque_issued", numbers,
                         np.char.add("Firma çeki " if self.tr else "Cheque issued ", p.number.values[c].astype(str)),
                         codes[c], names[c])
            self.J.pairs(due, amt[c], "103", self.bank_account, "cheque_paid", numbers,
                         np.char.add(self.desc("cheque_out") + " ", numbers.astype(str)), codes[c], names[c])
            self.cheques_out.append(pd.DataFrame({
                "direction": "given", "number": numbers, "counterparty_code": codes[c], "issued_day": p.pay_day.values[c],
                "due_day": due, "amount": amt[c], "status": np.where(due > self.last_day, "verildi", "ödendi"),
                "endorsed_to": None}))

    # ------------------------------------------------------------------ VAT and fees

    def gen_vat(self):
        if self.c.country == "US":
            return
        n_m = self.cal.n_months
        out = -np.bincount(self.dm, weights=self.J.account_flows("391", self.n_days), minlength=n_m)
        inp = np.bincount(self.dm, weights=self.J.account_flows("191", self.n_days), minlength=n_m)
        carry = 0.0
        rows = []
        for m in range(n_m):
            avail = inp[m] + carry
            offset = min(avail, out[m])
            payable = round(out[m] - offset, 2)
            carry = avail - offset
            rows.append((m, round(out[m], 2), round(offset, 2), payable))
        v = pd.DataFrame(rows, columns=["m", "out", "offset", "payable"])
        day = self.month_last_day[v.m.values]
        periods = self.cal.months[v.m.values].astype(str).values.astype(str)
        doc = np.char.add("KDV-" if self.tr else "VAT-", periods)
        self.J.entries(day, [("391", v.out.values, 0.0), ("191", 0.0, v.offset.values), ("360", 0.0, v.payable.values)],
                       "vat_return", doc, "KDV mahsubu" if self.tr else "VAT return")
        if self.tr:
            dom = np.where(self.cal.years[v.m.values] >= 2020, 28, 26)
            due = self.biz(self.next_month_day(v.m.values, dom))
        else:
            due = self.biz(self.next_month_day(v.m.values, 25))
        self.J.pairs(due, v.payable.values, "360", self.bank_account, "vat_payment", doc,
                     np.char.add(self.desc("vat") + " ", periods))
        self.obligation_rows.append(pd.DataFrame({
            "category": "vat", "basis": "declaration", "reference": periods, "period": periods,
            "due_day": due, "amount": v.payable.values, "principal": np.nan, "interest": np.nan}))

    def gen_bank_fees(self):
        flows = self.J.account_flows(self.bank_account, self.n_days)
        out = -np.bincount(self.dm, weights=np.minimum(flows, 0), minlength=self.cal.n_months)
        fixed = (300 if self.tr else 40) * self.P
        fee = np.round(fixed + out * 0.0002, 2)
        day = self.month_last_day
        self.J.pairs(day, fee, "653", self.bank_account, "bank_fee",
                     np.char.add("UCR-" if self.tr else "FEE-", self.cal.months.astype(str).values.astype(str)),
                     self.desc("fee"))

    # ------------------------------------------------------------------ financing, taxes, dividends

    def financing_loop(self):
        """Month by month treasury: loans, instalments, prepayments, deposits, taxes, dividends.

        Instalments are posted month by month so surplus cash can repay loans early.
        Owners inject capital when debt grows beyond a healthy level.
        """
        rng, cal = self.rng, self.cal
        n_m = cal.n_months
        base = self.J.account_flows(self.bank_account, self.n_days)
        pnl = self.J.pnl_by_month(self.dm, n_m)
        extra = np.zeros(self.n_days + 1)
        pnl_extra = np.zeros(n_m + 1)
        corp_rate = (lambda y: ref.TR_CORPORATE_TAX.get(y, 0.25)) if self.tr else (
            lambda y: ref.CORPORATE_TAX[self.c.country])
        months = cal.months.month.values
        active, loans, inst_rows = [], [], []
        cash, prov_paid, loss_cf = 0.0, 0.0, 0.0
        profit_year = {}
        self.tax_rows = []
        bsmv = 0.05 if self.tr else 0.0

        def post_cash(day, amount):
            if day < self.n_days:
                extra[day] += amount

        target = LEVERAGE[self.c.industry] * (0.7 if self.tr else 1.0) * rng.uniform(0.7, 1.3)

        eur_local = self.fx_d / self.eur_d  # local currency per EUR, daily
        eu_rate = interest_monthly(cal, "EU")

        def fx_at(cur, day):
            return 1.0 if cur == self.cur else float(eur_local[min(day, self.n_days - 1)])

        def new_loan(amount, dday, term, m, purpose):
            fx_loan = self.tr and purpose == "investment" and rng.random() < TR_FX_LOAN_SHARE.get(self.c.industry, 0.3)
            cur = "EUR" if fx_loan else self.cur
            base_rate = eu_rate[m] + 0.035 if fx_loan else self.rate[m] + (0.05 if self.tr else 0.02)
            annual = base_rate - (0.01 if purpose == "investment" else 0)
            r = annual / 12
            no = len(loans) + 1
            code = (f"300.02.{no:03d}" if fx_loan else f"300.01.{no:03d}") if self.tr else "300"
            ref_no = f"{self.bank.upper()}-{self.c.id[:3].upper()}-{no:04d}"
            if self.tr:
                self.names[code] = f"{BANK_NAMES[self.bank]} {'döviz kredisi' if fx_loan else 'kredi'} {ref_no}"
            rate0 = fx_at(cur, dday)
            principal_fx = round(amount / rate0, 2)
            self.J.pairs([dday], [amount], self.bank_account, code, "loan_drawdown", ref_no,
                         f"{self.desc('loan_in')} {ref_no}" + (f" EUR {principal_fx:,.2f}" if fx_loan else ""))
            post_cash(dday, amount)
            pmt = round(principal_fx * r / (1 - (1 + r) ** -term), 2)
            active.append({"no": no, "ref": ref_no, "code": code, "balance": principal_fx, "book": amount, "r": r,
                           "pmt": pmt, "term": term, "paid": 0, "dom": int(self.ext_dates[dday].day), "cur": cur})
            loans.append((no, ref_no, code, self.bank, dday, principal_fx, term, round(annual, 4), pmt, purpose, cur))

        for m in range(n_m):
            d0, d1 = self.month_first_day[m], self.month_last_day[m] + 1
            y = int(cal.years[m])
            buffer = 0.5 * self.rev_local[m]
            # Instalments due this month.
            for ln in active:
                if ln["balance"] <= 0.004:
                    continue
                day = int(self.biz(self.day_of(y, months[m], ln["dom"]))[0])
                fxr = fx_at(ln["cur"], day)
                interest_fx = round(ln["balance"] * ln["r"], 2)
                principal_fx = round(min(max(ln["pmt"] - interest_fx, 0), ln["balance"]), 2)
                if ln["paid"] + 1 >= ln["term"]:
                    principal_fx = round(ln["balance"], 2)
                principal = round(ln["book"] if principal_fx >= ln["balance"] else principal_fx * fxr, 2)
                interest = round(interest_fx * fxr, 2)
                tax = round(interest * bsmv, 2)
                total = round(principal + interest + tax, 2)
                ln["paid"] += 1
                ln["balance"] = round(ln["balance"] - principal_fx, 2)
                ln["book"] = round(ln["book"] - principal, 2)
                doc = f"{ln['ref']}/{ln['paid']:02d}"
                self.J.entries([day], [(ln["code"], np.array([principal]), np.array([0.0])),
                                       ("660", np.array([interest + tax]), np.array([0.0])),
                                       (self.bank_account, np.array([0.0]), np.array([total]))],
                               "loan_installment", doc, f"{self.desc('loan_out')} {doc}")
                post_cash(day, -total)
                pnl_extra[m] -= interest + tax
                inst_rows.append((ln["no"], doc, ln["paid"], day, principal, interest, tax, total))
            active = [ln for ln in active if ln["balance"] > 0.004]
            # Dividends in May from last year's profit after tax.
            if months[m] == 5 and profit_year.get(y - 1, 0) > 0:
                div = round(min(0.6 * profit_year[y - 1], max(cash - 3 * buffer, 0)), -2)
                if div > 0:
                    dday = int(self.biz(self.day_of(y, 5, 31))[0])
                    self.J.pairs([dday], [div], "570", self.bank_account, "dividend",
                                 f"KAR-{y - 1}" if self.tr else f"DIV-{y - 1}", self.desc("dividend"))
                    post_cash(dday, -div)
            flows = base[d0:d1] + extra[d0:d1]
            cum = cash + np.cumsum(flows)
            annual_rev = self.rev_local[max(0, m - 11):m + 1].sum() * 12 / min(m + 1, 12)
            debt = sum(ln["book"] for ln in active)
            # Working-capital loan if cash would fall below half the buffer.
            if cum.min() < 0.5 * buffer:
                unit = 10 ** max(int(np.log10(max(buffer, 10))) - 1, 2)
                amount = float(np.ceil((1.2 * buffer - cum.min()) / unit) * unit)
                term = int(rng.choice([12, 18]) if self.infl[m] > 30 else rng.choice([12, 24, 36]))
                new_loan(amount, int(self.biz(d0)), term, m, "working_capital")
                flows = base[d0:d1] + extra[d0:d1]
                cum = cash + np.cumsum(flows)
            # Investment loans keep debt near the company's target leverage.
            elif months[m] in (1, 4, 7, 10) and m > 0 and debt < 0.7 * target * annual_rev:
                unit = 10 ** max(int(np.log10(max(annual_rev, 10))) - 2, 2)
                amount = float(np.round((target * annual_rev - debt) / unit) * unit)
                if amount > 0:
                    term = int(rng.choice([12, 24]) if self.infl[m] > 30 else rng.choice([36, 48, 60]))
                    new_loan(amount, int(self.biz(d0 + 9)), term, m, "investment")
                    flows = base[d0:d1] + extra[d0:d1]
                    cum = cash + np.cumsum(flows)
            # Revalue euro loans at the month-end rate (kur farkı).
            for ln in active:
                if ln["cur"] == self.cur:
                    continue
                new_book = round(ln["balance"] * fx_at(ln["cur"], d1 - 1), 2)
                diff = round(new_book - ln["book"], 2)
                if abs(diff) >= 0.01:
                    acct = "656" if diff > 0 else "646"
                    self.J.entries([d1 - 1], [(acct if diff > 0 else ln["code"], np.array([abs(diff)]), np.array([0.0])),
                                              (ln["code"] if diff > 0 else acct, np.array([0.0]), np.array([abs(diff)]))],
                                   "fx_revaluation", f"{ln['ref']}/KUR-{cal.months[m]}",
                                   "Döviz kredisi kur farkı" if self.tr else "FX revaluation")
                    pnl_extra[m] -= diff
                    ln["book"] = new_book
            # Owners inject capital when debt is far above target (rare, mostly crises).
            debt = sum(ln["book"] for ln in active)
            if months[m] == 12 and debt > max(0.6, 2 * target) * annual_rev:
                inj = round(debt - target * annual_rev, -2)
                self.J.pairs([d1 - 1], [inj], self.bank_account, "500", "capital_increase",
                             f"SRM-{y}" if self.tr else f"CAP-{y}",
                             "SERMAYE ARTIRIMI" if self.tr else "CAPITAL INJECTION")
                post_cash(d1 - 1, inj)
                cum = cum + inj
            # Repay loans early with surplus cash, but only down to the target debt level.
            surplus = min(cum[-1] - 3 * buffer, debt - target * annual_rev) if debt > 1.2 * target * annual_rev else 0
            for ln in sorted(active, key=lambda x: x["no"]):
                if surplus <= 0:
                    break
                pay = round(min(ln["book"], surplus), 2)
                if pay < 0.01:
                    continue
                self.J.pairs([d1 - 1], [pay], ln["code"], self.bank_account, "loan_prepayment",
                             f"{ln['ref']}/ERK", f"{'ERKEN KAPAMA' if self.tr else 'EARLY REPAYMENT'} {ln['ref']}")
                post_cash(d1 - 1, -pay)
                share = pay / ln["book"] if ln["book"] else 1.0
                ln["balance"] = round(ln["balance"] * (1 - share), 2)
                ln["book"] = round(ln["book"] - pay, 2)
                surplus -= pay
                cum = cum.copy()
                cum[-1] -= pay
            active = [ln for ln in active if ln["balance"] > 0.004 and ln["book"] > 0.004]
            # Deposit interest on positive balances.
            dep_rate = max(self.rate[m] - 0.02, 0.001)
            interest_in = round(max(cum.mean(), 0) * dep_rate / 12, 2)
            if interest_in > 0:
                self.J.pairs([d1 - 1], [interest_in], self.bank_account, "642", "deposit_interest",
                             f"FAIZ-{cal.months[m]}" if self.tr else f"INT-{cal.months[m]}", self.desc("interest"))
                post_cash(d1 - 1, interest_in)
                pnl_extra[m] += interest_in
            y0 = int(np.where(cal.years == y)[0][0])
            ytd = (pnl[y0:m + 1] + pnl_extra[y0:m + 1]).sum()
            if months[m] in (3, 6, 9):
                due_amt = round(max(0.0, max(ytd - loss_cf, 0) * corp_rate(y) - prov_paid), 2)
                q = months[m] // 3
                pday = int(self.biz(self.next_month_day(m + 1, 17))[0])
                if due_amt > 0:
                    self.J.pairs([pday], [due_amt], "193", self.bank_account, "provisional_tax", f"GV-{y}-Q{q}",
                                 f"{self.desc('prov_tax')} {y}/{q}")
                    post_cash(pday, -due_amt)
                    prov_paid += due_amt
                self.tax_rows.append(("provisional_tax", "declaration", f"{y}-Q{q}", f"{y}-{months[m]:02d}", pday, due_amt))
            if months[m] == 12:
                taxable = ytd - loss_cf
                tax = round(max(taxable, 0) * corp_rate(y), 2)
                loss_cf = max(-taxable, 0)
                if tax > 0:
                    self.J.pairs([d1 - 1], [tax], "691", "370", "income_tax_provision", f"KV-{y}",
                                 "Kurumlar vergisi karşılığı" if self.tr else "Income tax provision")
                settle = int(self.biz(self.day_of(y + 1, 4, 30))[0])
                rest = round(tax - prov_paid, 2)
                lines = [("370", np.array([tax]), np.array([0.0])), ("193", np.array([0.0]), np.array([prov_paid]))]
                lines.append((self.bank_account, np.array([max(-rest, 0.0)]), np.array([max(rest, 0.0)])))
                self.J.entries([settle], lines, "corporate_tax", f"KV-{y}",
                               f"{self.desc('corp_tax' if rest >= 0 else 'corp_refund')} {y}")
                post_cash(settle, -rest)
                self.tax_rows.append(("corporate_tax", "declaration", str(y), f"{y}-12", settle, max(rest, 0.0)))
                profit_year[y] = ytd - tax
                prov_paid = 0.0
            cash = cash + base[d0:d1].sum() + extra[d0:d1].sum()
        # Remaining schedule of loans still open at the end (future obligations, not yet booked).
        for ln in active:
            bal, k = ln["balance"], ln["paid"]
            fxr = fx_at(ln["cur"], self.last_day)
            m = n_m
            while bal > 0.004 and k < ln["term"] + 600:
                k += 1
                interest = round(bal * ln["r"], 2)
                principal = round(bal if k >= ln["term"] else min(max(ln["pmt"] - interest, 0), bal), 2)
                tax = round(interest * bsmv, 2)
                yy = cal.start.year + (cal.start.month - 1 + m) // 12
                mo = (cal.start.month - 1 + m) % 12 + 1
                day = int(self.biz(self.day_of(yy, mo, ln["dom"]))[0])
                inst_rows.append((ln["no"], f"{ln['ref']}/{k:02d}", k, day, round(principal * fxr, 2),
                                  round(interest * fxr, 2), round(tax * fxr, 2),
                                  round((principal + interest + tax) * fxr, 2)))
                bal = round(bal - principal, 2)
                m += 1
        self.loans = pd.DataFrame(loans, columns=["loan_no", "reference", "ledger_account", "bank", "drawdown_day",
                                                  "principal", "term_months", "annual_rate", "installment", "purpose", "currency"])
        self.loan_installments = pd.DataFrame(inst_rows, columns=["loan_no", "reference", "installment", "due_day",
                                                                  "principal", "interest", "tax", "total"])
        self.profit_year = profit_year

    def closing_entries(self):
        """Close income statement accounts at each year end and carry the result to equity."""
        gl = pd.concat(self.J.parts, ignore_index=True)
        gl = gl[gl.day <= self.last_day]
        pl = gl[gl.account.str[0] == "6"]
        year = self.ext_year[pl.day.values]
        bal = pl.assign(year=year, net=pl.debit - pl.credit).groupby(["year", "account"])["net"].sum()
        last_year = self.cal.end.year if self.cal.end.month == 12 and self.cal.end.day == 31 else self.cal.end.year - 1
        for y in sorted(set(year)):
            if y > last_year or y < self.cal.output_start.year - 1:
                continue
            b = bal.loc[y]
            b = b[b.abs() > 0.004]
            result = -b.sum()
            day = self.day_of(y, 12, 31)[0]
            lines = [(a, np.array([max(-v, 0.0)]), np.array([max(v, 0.0)])) for a, v in b.items()]
            lines.append(("690", np.array([max(b.sum(), 0.0)]), np.array([max(-b.sum(), 0.0)])))
            self.J.entries([day], lines, "closing", f"KAPANIS-{y}" if self.tr else f"CLOSE-{y}",
                           "Dönem sonu kapanış" if self.tr else "Year-end closing")
            if result >= 0:
                self.J.entries([day], [("690", np.array([result]), np.array([0.0])), ("590", np.array([0.0]), np.array([result]))],
                               "closing", f"KAPANIS-{y}" if self.tr else f"CLOSE-{y}",
                               "Dönem net kârı" if self.tr else "Profit for the year")
                tday = self.biz(self.day_of(y + 1, 4, 15))[0]
                self.J.pairs([tday], [result], "590", "570", "profit_transfer", f"GKY-{y}" if self.tr else f"RE-{y}",
                             "Geçmiş yıllar kârlarına aktarım" if self.tr else "Transfer to retained earnings")
            else:
                self.J.entries([day], [("591", np.array([-result]), np.array([0.0])), ("690", np.array([0.0]), np.array([-result]))],
                               "closing", f"KAPANIS-{y}" if self.tr else f"CLOSE-{y}",
                               "Dönem net zararı" if self.tr else "Loss for the year")
                tday = self.biz(self.day_of(y + 1, 4, 15))[0]
                self.J.pairs([tday], [-result], "580", "591", "profit_transfer", f"GYZ-{y}" if self.tr else f"RE-{y}",
                             "Geçmiş yıllar zararlarına aktarım" if self.tr else "Transfer of loss")

    # ------------------------------------------------------------------ budget

    def gen_budget(self):
        """Annual budget prepared each December from the year's actuals, phased by month."""
        rng, cal = self.rng, self.cal
        gl = pd.concat(self.J.parts, ignore_index=True)
        gl = gl[(gl.day <= self.last_day) & (gl.doc_type != "closing")]
        m = self.dm[gl.day.values]
        acc2 = gl.account.str[:2]
        def monthly(prefixes, sign):
            sel = acc2.isin(prefixes).values
            v = np.bincount(m[sel], weights=(gl.credit.values[sel] - gl.debit.values[sel]) * sign, minlength=cal.n_months)
            return v
        actual = {"gross_sales": monthly(["60"], 1), "sales_deductions": monthly(["61"], -1),
                  "cogs": monthly(["62"], -1), "operating_expenses": monthly(["63"], -1),
                  "finance_expenses": monthly(["66"], -1)}
        actual["net_sales"] = actual["gross_sales"] - actual["sales_deductions"]
        rows = []
        years = sorted(set(cal.years))
        for y in years[1:]:
            prev = np.where(cal.years == y - 1)[0]
            if len(prev) < 12:
                continue
            cur = np.where(cal.years == y)[0]
            infl = self.infl[prev[-1]] / 100
            growth = (1 + infl) * (1 + 0.04 + rng.normal(0.02, 0.04))
            for metric, series in actual.items():
                base = series[prev]
                g = growth if metric not in ("operating_expenses", "finance_expenses") else (1 + infl) * (1 + rng.normal(0.01, 0.02))
                for k, mi in enumerate(cur):
                    if k >= 12:
                        break
                    rows.append((str(cal.months[mi]), metric, round(base[k] * g, 2)))
        b = pd.DataFrame(rows, columns=["period", "metric", "amount"])
        piv = b.pivot_table(index="period", columns="metric", values="amount", aggfunc="sum")
        extra = []
        for period, r in piv.iterrows():
            extra.append((period, "gross_profit", round(r.net_sales - r.cogs, 2)))
            extra.append((period, "operating_profit", round(r.net_sales - r.cogs - r.operating_expenses, 2)))
        self.budget = pd.concat([b, pd.DataFrame(extra, columns=b.columns)], ignore_index=True)

    # ------------------------------------------------------------------ outputs

    def finalize(self):
        from .output import build_tables
        self.tables = build_tables(self)


class _ProfileProxy:
    """Company look-alike with an adjusted industry profile (used for headcount sizing)."""

    def __init__(self, company, profile):
        self._c = company
        self.profile = profile

    def __getattr__(self, name):
        return getattr(self._c, name)
