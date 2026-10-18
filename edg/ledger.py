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
    """Collects journal lines in vectorized batches of plain numpy arrays.

    Accounts and document types are stored as integer codes so that filtering by
    account prefix stays fast. Every call posts complete, balanced entries. Dates are
    integer day indexes from the calendar start; rows dated after the calendar end are
    dropped when the journal is read (they have not happened yet).
    """

    FIELDS = ("entry", "line", "day", "acct", "debit", "credit", "doc_type", "doc_no", "description",
              "cp_code", "cp_name")

    def __init__(self, last_day: int):
        self.parts = []
        self.next_entry = 0
        self.last_day = last_day
        self.codes = {}       # account string -> id
        self.accounts = []    # id -> account string
        self.types = {}
        self.type_names = []

    def _code(self, value, table, names, n):
        if np.ndim(value) == 0:
            if value not in table:
                table[value] = len(names)
                names.append(value)
            return np.full(n, table[value], dtype=np.int32)
        uniq, inv = np.unique(np.asarray(value).astype(str), return_inverse=True)
        ids = np.empty(len(uniq), dtype=np.int32)
        for i, u in enumerate(uniq):
            if u not in table:
                table[u] = len(names)
                names.append(u)
            ids[i] = table[u]
        return ids[inv]

    def entries(self, day, lines, doc_type, doc_no, desc, cp_code=None, cp_name=None):
        """Post one entry per element of `day`.

        `lines` is a list of (account, debit, credit) where each item is a scalar or an
        array aligned with `day`. Zero lines are dropped when the journal is read.
        """
        day = np.asarray(day, dtype=np.int64)
        n = len(day)
        if n == 0:
            return
        entry = np.arange(n, dtype=np.int64) + self.next_entry
        self.next_entry += n

        def obj(x):
            return np.full(n, x, dtype=object) if np.ndim(x) == 0 else np.asarray(x, dtype=object)

        def num(x):
            return np.full(n, float(x)) if np.ndim(x) == 0 else np.asarray(x, dtype=float)

        dtype_ids = self._code(doc_type, self.types, self.type_names, n)
        doc_no_a, desc_a, cp_code_a, cp_name_a = obj(doc_no), obj(desc), obj(cp_code), obj(cp_name)
        for line_no, (acct, dr, cr) in enumerate(lines):
            self.parts.append((entry, np.full(n, line_no, dtype=np.int16), day,
                               self._code(acct, self.codes, self.accounts, n),
                               np.round(num(dr), 2), np.round(num(cr), 2), dtype_ids,
                               doc_no_a, desc_a, cp_code_a, cp_name_a))

    def pairs(self, day, amount, dr, cr, doc_type, doc_no, desc, cp_code=None, cp_name=None):
        amount = np.round(np.asarray(amount, dtype=float), 2)
        self.entries(day, [(dr, amount, 0.0), (cr, 0.0, amount)], doc_type, doc_no, desc, cp_code, cp_name)

    def _select(self, keep_part=None, numeric_only=False):
        """Concatenate the journal (optionally only rows where keep_part(part) is True)."""
        fields = self.FIELDS[:7] if numeric_only else self.FIELDS
        idx = [self.FIELDS.index(f) for f in fields]
        chunks = {f: [] for f in fields}
        for p in self.parts:
            day, dr, cr = p[2], p[4], p[5]
            m = (day <= self.last_day) & ((dr != 0) | (cr != 0))
            if keep_part is not None:
                m &= keep_part(p)
            if not m.any():
                continue
            for f, i in zip(fields, idx):
                chunks[f].append(p[i][m])
        data = {f: (np.concatenate(v) if v else np.array([])) for f, v in chunks.items()}
        d, c = data["debit"], data["credit"]
        neg_d, neg_c = d < 0, c < 0
        data["debit"] = np.where(neg_d, 0.0, d) + np.where(neg_c, -c, 0.0)
        data["credit"] = np.where(neg_c, 0.0, c) + np.where(neg_d, -d, 0.0)
        data["entry"] = data["entry"].astype(np.int64)
        data["day"] = data["day"].astype(np.int32)
        return data

    def numeric(self) -> pd.DataFrame:
        """Compact journal: numbers plus account and document type as categoricals."""
        data = self._select(numeric_only=True)
        df = pd.DataFrame({k: data[k] for k in ("entry", "line", "day", "debit", "credit")})
        df["account"] = pd.Categorical.from_codes(data["acct"].astype(np.int32), categories=self.accounts)
        df["doc_type"] = pd.Categorical.from_codes(data["doc_type"].astype(np.int32), categories=self.type_names)
        return df

    def frame(self, sort: bool = True, keep_part=None) -> pd.DataFrame:
        """Full journal with text columns (optionally only some rows, e.g. one year or one account)."""
        data = self._select(keep_part)
        acct_names = np.array(self.accounts, dtype=object)
        type_names = np.array(self.type_names, dtype=object)
        df = pd.DataFrame(data)
        df["account"] = acct_names[df.pop("acct").values.astype(np.int64)] if len(df) else []
        df["doc_type"] = type_names[df.doc_type.values.astype(np.int64)] if len(df) else []
        if sort and len(df):
            order = np.lexsort((df.line.values, df.entry.values, df.day.values))
            df = df.iloc[order].reset_index(drop=True)
        return df

    def year_frame(self, lo: int, hi: int) -> pd.DataFrame:
        return self.frame(keep_part=lambda p: (p[2] >= lo) & (p[2] <= hi))

    def account_frame(self, account: str) -> pd.DataFrame:
        code = self.codes.get(account, -1)
        return self.frame(keep_part=lambda p: p[3] == code)

    def _mask(self, prefix: str) -> np.ndarray:
        return np.array([a.startswith(prefix) for a in self.accounts] + [False], dtype=bool)

    def account_flows(self, prefix: str, n_days: int) -> np.ndarray:
        """Daily net debit movement for accounts starting with `prefix`."""
        out = np.zeros(n_days)
        mask = self._mask(prefix)
        for p in self.parts:
            day = p[2]
            m = mask[p[3]] & (day < n_days) & (day >= 0)
            if m.any():
                np.add.at(out, day[m], p[4][m] - p[5][m])
        return out

    def pnl_by_month(self, day_month: np.ndarray, n_months: int) -> np.ndarray:
        """Monthly profit before tax (credit minus debit on class 6 except 69)."""
        out = np.zeros(n_months)
        n_days = len(day_month)
        mask = np.array([a.startswith("6") and not a.startswith("69") for a in self.accounts] + [False])
        for p in self.parts:
            day = p[2]
            m = mask[p[3]] & (day < n_days) & (day >= 0)
            if m.any():
                np.add.at(out, day_month[day[m]], p[5][m] - p[4][m])
        return out


def trial_balance(gl: pd.DataFrame, cal, names: dict, foreign: bool) -> pd.DataFrame:
    """Year-to-date cumulative trial balance (mizan) per month, main and sub accounts.

    Balance-sheet accounts open each year with last year's closing balance (shown in the
    year-to-date totals, like an opening voucher). Year-end closing entries are left out
    of December so that the December trial balance is the pre-closing one. Expects the
    compact journal from Journal.numeric() (account as a categorical); sums with bincount.
    """
    codes = gl.account.cat.codes.values.astype(np.int64)
    cats = np.array(gl.account.cat.categories, dtype=object)
    n_a, n_m = len(cats), cal.n_months
    m = np.asarray(cal.day_month)[gl.day.values]
    years = cal.years
    y0 = int(years[0])
    n_y = int(years[-1]) - y0 + 1
    yi = years[m] - y0
    closing = (gl.doc_type == "closing").values
    debit, credit = gl.debit.values, gl.credit.values
    key = codes * n_m + m
    deb = np.bincount(key[~closing], weights=debit[~closing], minlength=n_a * n_m).reshape(n_a, n_m)
    cre = np.bincount(key[~closing], weights=credit[~closing], minlength=n_a * n_m).reshape(n_a, n_m)
    net_y = np.bincount(codes * n_y + yi, weights=debit - credit, minlength=n_a * n_y).reshape(n_a, n_y)
    cum_y = np.cumsum(net_y, axis=1)
    first_out = cal.month_index(cal.output_start.strftime("%Y-%m"))
    parts = []
    for y in sorted(set(years[first_out:])):
        ms = np.where(years == y)[0]
        opening = cum_y[:, y - y0 - 1] if y > y0 else np.zeros(n_a)
        opening = np.where(np.abs(opening) > 0.004, opening, 0.0)
        ytd_d = np.cumsum(deb[:, ms], axis=1) + np.maximum(opening, 0)[:, None]
        ytd_c = np.cumsum(cre[:, ms], axis=1) + np.maximum(-opening, 0)[:, None]
        keep_m = ms >= first_out
        ai, mi = np.nonzero((np.abs(ytd_d[:, keep_m]) > 0.004) | (np.abs(ytd_c[:, keep_m]) > 0.004))
        cols = np.where(keep_m)[0][mi]
        parts.append(pd.DataFrame({"account": cats[ai], "m": ms[cols], "month_debit": deb[ai, ms[cols]],
                                   "month_credit": cre[ai, ms[cols]], "ytd_debit": ytd_d[ai, cols],
                                   "ytd_credit": ytd_c[ai, cols]}))
    tb = pd.concat(parts, ignore_index=True)
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
    res["account_code"] = [CHART[a[:3]][1] + a[3:] for a in res.account] if foreign else res.account
    res["parent_code"] = [None if p is None else (CHART[p][1] if foreign else p) for p in res.parent]
    for c in ("month_debit", "month_credit", "ytd_debit", "ytd_credit"):
        res[c] = res[c].round(2)
    res = res.sort_values(["m", "account"], kind="stable")
    return res[["period", "account_code", "account_name", "level", "parent_code", "tdhp_code",
                "month_debit", "month_credit", "ytd_debit", "ytd_credit", "debit_balance", "credit_balance"]]
