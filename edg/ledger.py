"""Double-entry journal, chart of accounts (TDHP with IFRS mapping) and trial balance."""

import numpy as np
import pandas as pd

# TDHP main accounts used by the generator: code -> (Turkish name, IFRS code, English name)
CHART = {
    "100": ("Kasa", "1000", "Cash on hand"),
    "101": ("Alınan çekler", "1010", "Cheques received"),
    "102": ("Bankalar", "1100", "Cash at bank"),
    "103": ("Verilen çekler ve ödeme emirleri (-)", "2050", "Cheques issued"),
    "108": ("Diğer hazır değerler", "1150", "Card settlements receivable"),
    "120": ("Alıcılar", "1200", "Trade receivables"),
    "128": ("Şüpheli ticari alacaklar", "1210", "Doubtful receivables"),
    "129": ("Şüpheli ticari alacaklar karşılığı (-)", "1290", "Allowance for doubtful receivables"),
    "150": ("İlk madde ve malzeme", "1300", "Raw materials"),
    "152": ("Mamuller", "1320", "Finished goods"),
    "153": ("Ticari mallar", "1330", "Merchandise"),
    "191": ("İndirilecek KDV", "1400", "Input VAT"),
    "193": ("Peşin ödenen vergiler ve fonlar", "1450", "Prepaid income tax"),
    "252": ("Binalar", "1510", "Buildings"),
    "253": ("Tesis, makine ve cihazlar", "1520", "Plant and machinery"),
    "254": ("Taşıtlar", "1530", "Vehicles"),
    "255": ("Demirbaşlar", "1540", "Furniture and IT equipment"),
    "257": ("Birikmiş amortismanlar (-)", "1590", "Accumulated depreciation"),
    "300": ("Banka kredileri", "2400", "Bank borrowings"),
    "320": ("Satıcılar", "2000", "Trade payables"),
    "335": ("Personele borçlar", "2200", "Wages payable"),
    "360": ("Ödenecek vergi ve fonlar", "2300", "Taxes payable"),
    "361": ("Ödenecek sosyal güvenlik kesintileri", "2310", "Social security payable"),
    "370": ("Dönem kârı vergi ve diğer yasal yükümlülük karşılıkları", "2350", "Income tax provision"),
    "391": ("Hesaplanan KDV", "2100", "Output VAT"),
    "500": ("Sermaye", "3000", "Share capital"),
    "570": ("Geçmiş yıllar kârları", "3100", "Retained earnings"),
    "580": ("Geçmiş yıllar zararları (-)", "3110", "Accumulated losses"),
    "590": ("Dönem net kârı", "3200", "Profit for the year"),
    "591": ("Dönem net zararı (-)", "3210", "Loss for the year"),
    "600": ("Yurtiçi satışlar", "4000", "Revenue - domestic"),
    "601": ("Yurtdışı satışlar", "4010", "Revenue - export"),
    "610": ("Satıştan iadeler (-)", "4100", "Sales returns"),
    "611": ("Satış iskontoları (-)", "4110", "Sales discounts"),
    "620": ("Satılan mamuller maliyeti (-)", "5000", "Cost of goods sold - manufactured"),
    "621": ("Satılan ticari mallar maliyeti (-)", "5010", "Cost of merchandise sold"),
    "622": ("Satılan hizmet maliyeti (-)", "5020", "Cost of services"),
    "630": ("Araştırma ve geliştirme giderleri (-)", "6300", "Research and development"),
    "631": ("Pazarlama, satış ve dağıtım giderleri (-)", "6100", "Selling and distribution expenses"),
    "632": ("Genel yönetim giderleri (-)", "6200", "General and administrative expenses"),
    "642": ("Faiz gelirleri", "7100", "Interest income"),
    "646": ("Kambiyo kârları", "7200", "Foreign exchange gains"),
    "653": ("Komisyon giderleri (-)", "7350", "Bank and card charges"),
    "654": ("Karşılık giderleri (-)", "6250", "Bad debt expense"),
    "656": ("Kambiyo zararları (-)", "7300", "Foreign exchange losses"),
    "660": ("Kısa vadeli borçlanma giderleri (-)", "7500", "Interest expense"),
    "690": ("Dönem kârı veya zararı", "8900", "Income summary"),
    "691": ("Dönem kârı vergi ve diğer yasal yükümlülük karşılıkları (-)", "8000", "Income tax expense"),
}


def chart_table() -> pd.DataFrame:
    rows = [(k, v[0], v[1], v[2], int(k[0])) for k, v in CHART.items()]
    df = pd.DataFrame(rows, columns=["tdhp_code", "tdhp_name", "ifrs_code", "ifrs_name", "account_class"])
    df["nature"] = np.where(df.tdhp_code.str[0].isin(["3", "4", "5"]) | df.tdhp_code.str[:2].isin(
        ["60", "64", "67", "69"]), "credit", "debit")
    df["statement"] = np.where(df.account_class <= 5, "balance_sheet", "income_statement")
    return df


class Journal:
    """Collects journal lines in vectorized batches.

    Every call posts complete, balanced entries. Dates are integer day indexes from the
    calendar start; rows dated after the calendar end are dropped (not yet happened).
    """

    def __init__(self, last_day: int):
        self.parts = []
        self.next_entry = 0
        self.last_day = last_day

    def entries(self, day, lines, doc_type, doc_no, desc, cp_code=None, cp_name=None):
        """Post one entry per element of `day`.

        `lines` is a list of (account, debit, credit) where each item is a scalar or an
        array aligned with `day`. Zero lines are dropped at the end.
        """
        day = np.asarray(day, dtype=np.int64)
        n = len(day)
        if n == 0:
            return
        entry = np.arange(n, dtype=np.int64) + self.next_entry
        self.next_entry += n

        def arr(x, dtype=None):
            if np.ndim(x) == 0:
                return np.full(n, x, dtype=dtype if dtype else (object if isinstance(x, str) or x is None else float))
            return np.asarray(x, dtype=dtype) if dtype else np.asarray(x)

        doc_type_a, doc_no_a, desc_a = arr(doc_type, object), arr(doc_no, object), arr(desc, object)
        cp_code_a, cp_name_a = arr(cp_code, object), arr(cp_name, object)
        for line_no, (acct, dr, cr) in enumerate(lines):
            self.parts.append(pd.DataFrame({
                "entry": entry, "line": line_no, "day": day,
                "account": arr(acct, object),
                "debit": np.round(arr(dr, float), 2), "credit": np.round(arr(cr, float), 2),
                "doc_type": doc_type_a, "doc_no": doc_no_a, "description": desc_a,
                "cp_code": cp_code_a, "cp_name": cp_name_a,
            }))

    def pairs(self, day, amount, dr, cr, doc_type, doc_no, desc, cp_code=None, cp_name=None):
        amount = np.round(np.asarray(amount, dtype=float), 2)
        self.entries(day, [(dr, amount, 0.0), (cr, 0.0, amount)], doc_type, doc_no, desc, cp_code, cp_name)

    def frame(self) -> pd.DataFrame:
        df = pd.concat(self.parts, ignore_index=True)
        df = df[(df.day <= self.last_day) & ((df.debit != 0) | (df.credit != 0))]
        neg = df.debit < 0
        df.loc[neg, ["debit", "credit"]] = np.c_[np.zeros(neg.sum()), -df.loc[neg, "debit"].values]
        neg = df.credit < 0
        df.loc[neg, ["debit", "credit"]] = np.c_[-df.loc[neg, "credit"].values, np.zeros(neg.sum())]
        return df.sort_values(["day", "entry", "line"], kind="stable").reset_index(drop=True)

    def account_flows(self, prefix: str, n_days: int) -> np.ndarray:
        """Daily net debit movement for accounts starting with `prefix` (current batches)."""
        out = np.zeros(n_days)
        for p in self.parts:
            m = p.account.str.startswith(prefix).values & (p.day.values < n_days) & (p.day.values >= 0)
            if m.any():
                np.add.at(out, p.day.values[m], p.debit.values[m] - p.credit.values[m])
        return out

    def pnl_by_month(self, day_month: np.ndarray, n_months: int) -> np.ndarray:
        """Monthly profit before tax (credit minus debit on class 6 except 69)."""
        out = np.zeros(n_months)
        n_days = len(day_month)
        for p in self.parts:
            a = p.account.str
            m = a.startswith("6").values & ~a.startswith("69").values & (p.day.values < n_days)
            if m.any():
                np.add.at(out, day_month[p.day.values[m]], p.credit.values[m] - p.debit.values[m])
        return out


def trial_balance(gl: pd.DataFrame, cal, names: dict, foreign: bool) -> pd.DataFrame:
    """Year-to-date cumulative trial balance (mizan) per month, main and sub accounts.

    Balance-sheet accounts open each year with last year's closing balance (shown in the
    year-to-date totals, like an opening voucher). Year-end closing entries are left out
    of December so that the December trial balance is the pre-closing one.
    """
    g = gl[["day", "account", "debit", "credit", "doc_type"]].copy()
    g["m"] = cal.day_month[g.day.values]
    g["year"] = cal.years[g.m.values]
    first_out = cal.month_index(cal.output_start.strftime("%Y-%m"))
    closing = g.doc_type.values == "closing"

    mv = g[~closing].groupby(["account", "m"], sort=False)[["debit", "credit"]].sum().reset_index()
    net_all = g.assign(net=g.debit - g.credit).groupby(["account", "year"])["net"].sum().unstack(fill_value=0.0)
    cum_by_year_end = net_all.cumsum(axis=1)

    out = []
    years = sorted(set(cal.years[first_out:]))
    for y in years:
        m_lo = max(first_out, int(np.argmax(cal.years == y)))
        m_hi = int(np.where(cal.years == y)[0][-1])
        prev_years = [c for c in cum_by_year_end.columns if c < y]
        opening = cum_by_year_end[prev_years[-1]] if prev_years else pd.Series(0.0, index=cum_by_year_end.index)
        opening = opening[opening.abs() > 0.004]
        mv_y = mv[(mv.m >= int(np.argmax(cal.years == y))) & (mv.m <= m_hi)]
        accounts = sorted(set(opening.index) | set(mv_y.account))
        months = np.arange(m_lo, m_hi + 1)
        grid = pd.MultiIndex.from_product([accounts, np.arange(int(np.argmax(cal.years == y)), m_hi + 1)],
                                          names=["account", "m"])
        dense = mv_y.set_index(["account", "m"]).reindex(grid, fill_value=0.0)
        ytd = dense.groupby(level=0).cumsum()
        ytd = ytd.reset_index()
        ytd = ytd[ytd.m.isin(months)]
        month_mv = dense.reset_index()
        month_mv = month_mv[month_mv.m.isin(months)]
        op = opening.reindex(ytd.account.values).fillna(0.0).values
        ytd["month_debit"] = month_mv.debit.values
        ytd["month_credit"] = month_mv.credit.values
        ytd["ytd_debit"] = ytd.debit.values + np.where(op > 0, op, 0)
        ytd["ytd_credit"] = ytd.credit.values + np.where(op < 0, -op, 0)
        out.append(ytd.drop(columns=["debit", "credit"]))
    tb = pd.concat(out, ignore_index=True)
    tb = tb[(tb.ytd_debit.abs() > 0.004) | (tb.ytd_credit.abs() > 0.004)]
    tb["main"] = tb.account.str[:3]
    has_sub = tb.account.str.len() > 3

    main = tb.groupby(["main", "m"], sort=False)[["month_debit", "month_credit", "ytd_debit", "ytd_credit"]].sum()
    main = main.reset_index().rename(columns={"main": "account"})
    main["level"] = "main"
    main["parent"] = None
    sub = tb[has_sub].drop(columns=["main"]).copy()
    sub["level"] = "sub"
    sub["parent"] = sub.account.str[:3]
    res = pd.concat([main, sub], ignore_index=True)
    bal = res.ytd_debit - res.ytd_credit
    res["debit_balance"] = np.where(bal > 0, bal, 0.0).round(2)
    res["credit_balance"] = np.where(bal < 0, -bal, 0.0).round(2)
    res["period"] = cal.months[res.m.values].astype(str)
    res["tdhp_code"] = res.account.str[:3]
    res["account_name"] = [names.get(a) or CHART[a[:3]][2 if foreign else 0] for a in res.account]
    if foreign:
        res["account_code"] = [CHART[a[:3]][1] + a[3:] for a in res.account]
    else:
        res["account_code"] = res.account
    res["parent_code"] = [None if p is None else (CHART[p][1] if foreign else p) for p in res.parent]
    for c in ("month_debit", "month_credit", "ytd_debit", "ytd_credit"):
        res[c] = res[c].round(2)
    res = res.sort_values(["m", "account"], kind="stable")
    return res[["period", "account_code", "account_name", "level", "parent_code", "tdhp_code",
                "month_debit", "month_credit", "ytd_debit", "ytd_credit", "debit_balance", "credit_balance"]]
