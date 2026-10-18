"""Master data: identifiers, names, products, customers, suppliers, employees, fixed assets."""

import uuid

import numpy as np
import pandas as pd

from . import reference as ref

NAME_LOCALE = {"US": "US", "UK": "UK", "DE": "DE", "NL": "NL", "ES": "ES", "FR": "FR", "TR": "TR"}


# --------------------------------------------------------------------------- identifiers

def vkn_numbers(rng: np.random.Generator, n: int) -> np.ndarray:
    """Unique 10-digit Turkish tax numbers (VKN) with a valid check digit."""
    out, seen = [], set()
    while len(out) < n:
        digits = rng.integers(0, 10, size=(n * 2, 9))
        digits[:, 0] = rng.integers(1, 10, size=n * 2)
        pos = np.arange(1, 10)
        tmp = (digits + 10 - pos) % 10
        v = np.where(tmp == 9, 9, (tmp * (2 ** (10 - pos))) % 9)
        check = (10 - v.sum(axis=1) % 10) % 10
        for row, c in zip(digits, check):
            s = "".join(map(str, row)) + str(c)
            if s not in seen:
                seen.add(s)
                out.append(s)
                if len(out) == n:
                    break
    return np.array(out)


def tckn_numbers(rng: np.random.Generator, n: int) -> np.ndarray:
    """11-digit Turkish personal ID numbers with valid checksums."""
    d = rng.integers(0, 10, size=(n, 9))
    d[:, 0] = rng.integers(1, 10, size=n)
    odd = d[:, [0, 2, 4, 6, 8]].sum(axis=1)
    even = d[:, [1, 3, 5, 7]].sum(axis=1)
    d10 = (odd * 7 - even) % 10
    d11 = (d.sum(axis=1) + d10) % 10
    return np.array(["".join(map(str, r)) + str(a) + str(b) for r, a, b in zip(d, d10, d11)])


def foreign_tax_ids(rng: np.random.Generator, country: str, n: int) -> np.ndarray:
    nums = rng.integers(10 ** 8, 10 ** 9, size=n)
    if country == "US":
        return np.array([f"{x // 10 ** 7:02d}-{x % 10 ** 7:07d}" for x in nums])
    prefix = {"UK": "GB", "DE": "DE", "NL": "NL", "ES": "ES", "FR": "FR"}[country]
    if country == "NL":
        return np.array([f"NL{x}B01" for x in nums])
    return np.array([f"{prefix}{x}" for x in nums])


def uuids(rng: np.random.Generator, n: int) -> np.ndarray:
    """Version-4 style UUIDs from the run's random stream (deterministic)."""
    b = rng.integers(0, 256, size=(n, 16), dtype=np.uint8)
    b[:, 6] = (b[:, 6] & 0x0F) | 0x40
    b[:, 8] = (b[:, 8] & 0x3F) | 0x80
    return np.array([str(uuid.UUID(bytes=r.tobytes())) for r in b], dtype=object)


# --------------------------------------------------------------------------- names

def person_names(rng: np.random.Generator, country: str, n: int):
    loc = NAME_LOCALE[country]
    first = np.array(ref.FIRST_NAMES[loc])
    last = np.array(ref.LAST_NAMES[loc])
    fi = rng.integers(0, len(first), n)
    gender = np.where(fi % 2 == 0, "M", "F")
    return first[fi], last[rng.integers(0, len(last), n)], gender


def org_names(rng: np.random.Generator, country: str, n: int, sector_hint: str | None = None) -> np.ndarray:
    """Plausible, unique company names for counterparties."""
    out, seen = [], set()
    if country == "TR":
        words, sectors = ref.TR_ORG_WORDS, ref.TR_SECTOR_WORDS
        suffixes = ["A.Ş.", "Ltd. Şti.", "San. ve Tic. A.Ş.", "San. Tic. Ltd. Şti.", "Tic. A.Ş."]
    else:
        words, sectors = ref.ORG_WORDS, ref.EN_SECTOR_WORDS
        suffixes = ref.ORG_SUFFIX[country]
    attempts = 0
    while len(out) < n:
        attempts += 1
        w = words[rng.integers(len(words))]
        s = sector_hint or sectors[rng.integers(len(sectors))]
        if attempts > n * 6:
            w = f"{w} {words[rng.integers(len(words))]}"
        name = f"{w} {s} {suffixes[rng.integers(len(suffixes))]}"
        if name not in seen:
            seen.add(name)
            out.append(name)
    return np.array(out, dtype=object)


# --------------------------------------------------------------------------- products

# Price ranges (2026 USD) for categories that differ from the industry default, by category index.
CATEGORY_PRICES = {"automotive": {0: (16_000, 45_000), 1: (20_000, 40_000), 2: (60_000, 140_000), 3: (40, 2_500),
                                  4: (28_000, 60_000)}}

def products(rng, company, cal, scale: float) -> pd.DataFrame:
    prof = company.profile
    n = max(12, int(prof.products * max(scale, 0.02) ** 0.35))
    cats_en, cats_tr = prof.categories_en, prof.categories_tr
    cat = rng.integers(0, len(cats_en), n)
    lo, hi = prof.price_range_usd
    price = np.exp(rng.uniform(np.log(lo), np.log(hi), n))
    # Categories with their own price range (vehicles vs spare parts).
    for c_idx, (c_lo, c_hi) in CATEGORY_PRICES.get(company.industry, {}).items():
        sel = cat == c_idx
        price[sel] = np.exp(rng.uniform(np.log(c_lo), np.log(c_hi), sel.sum()))
    margin = np.clip(prof.gross_margin + rng.normal(0, 0.07, n), 0.03, 0.92)
    # Launch dates spread over the whole period; a quarter of the catalogue exists from the start.
    span = cal.n_months
    launch = np.where(rng.random(n) < 0.25, 0, rng.integers(0, span, n))
    life = rng.integers(36, 240, n)
    disc = launch + life
    disc = np.where(disc >= span - 1, span + 1000, disc)  # still active at the end
    # Ensure each category always has an active product.
    for c in range(len(cats_en)):
        idx = np.where(cat == c)[0]
        if len(idx):
            launch[idx[0]] = 0
            disc[idx[0]] = span + 1000
    names = cats_tr if company.turkish else cats_en
    code = np.array([f"{company.id[:3].upper()}-{c + 1:02d}{i:05d}" for i, c in enumerate(cat)])
    unit = "adet" if company.turkish else "pcs"
    if company.profile.model == "services":
        unit = "hizmet" if company.turkish else "service"
    pop = rng.pareto(1.1, n) + 0.05
    vat_rate = np.full(n, -1.0)  # resolved per date for Turkish companies
    if company.turkish and company.industry in ("food", "pharma", "healthcare"):
        vat_rate[:] = -2.0  # reduced rate
    return pd.DataFrame({
        "product_id": np.arange(1, n + 1),
        "sku": code,
        "name": [f"{names[c]} {code[i][-5:]}" for i, c in enumerate(cat)],
        "category": np.array(names, dtype=object)[cat],
        "category_idx": cat,
        "unit": unit,
        "list_price_usd_2026": price.round(2),
        "cost_ratio": (1 - margin).round(4),
        "launch_month": launch,
        "discontinue_month": disc,
        "popularity": pop,
        "vat_class": vat_rate,
    })


# --------------------------------------------------------------------------- counterparties

def customers(rng, company, cal, activity_real: np.ndarray, demand: np.ndarray, scale: float) -> pd.DataFrame:
    """B2B customers with lifetimes that follow the company's growth, plus default risk."""
    prof = company.profile
    n_end = max(3, int(round(prof.customers_end * scale ** 0.75)))
    smooth = pd.Series(activity_real).rolling(12, min_periods=1).mean().values
    k = np.maximum(2, n_end * (smooth / smooth[-1]) ** 0.6)
    churn_m = 0.07 / 12
    init = int(round(k[0]))
    arrivals = np.maximum(0, np.diff(k, prepend=k[0])) + k * churn_m
    counts = rng.poisson(arrivals)
    counts[0] += init
    start = np.repeat(np.arange(cal.n_months), counts)
    n = len(start)
    life = rng.exponential(1 / 0.07 * 12, n).astype(int) + 6
    end = start + life
    # Defaults cluster in downturns.
    stress = np.clip(1.02 - demand, 0.005, None)
    p_def = 0.05 if company.turkish else 0.03
    defaults = rng.random(n) < p_def
    def_month = np.full(n, 10 ** 6)
    if defaults.any():
        w = stress / stress.sum()
        cand = rng.choice(cal.n_months, size=defaults.sum(), p=w)
        def_month[defaults] = np.maximum(cand, start[defaults] + 3)
    end = np.minimum(end, def_month)
    # Anchor customers: large accounts that stay for the whole period and never default.
    n_anchor = max(2, int(round(0.05 * n_end)))
    anchor = np.arange(min(n_anchor, n))
    start[anchor] = 0
    end[anchor] = 10 ** 6
    def_month[anchor] = 10 ** 6
    defaults[anchor] = False
    export = np.zeros(n, dtype=bool)
    if company.export_share > 0:
        export = rng.random(n) < min(0.9, company.export_share * 0.8 + 0.05)
    weight = rng.pareto(1.15, n) + 0.1
    weight[anchor] = np.maximum(weight[anchor], np.quantile(weight, 0.95))
    seg = np.where(weight > np.quantile(weight, 0.9), "key_account",
                   np.where(weight > np.quantile(weight, 0.5), "mid_market", "small"))
    country = np.where(export, rng.choice(["DE", "UK", "NL", "FR", "ES", "US"], n), company.country)
    names = org_names(rng, company.country, n)
    if company.turkish:
        tax = vkn_numbers(rng, n).astype(object)
        indiv = (~export) & (rng.random(n) < 0.04)
        tax[indiv] = tckn_numbers(rng, indiv.sum())
        exp_idx = np.where(export)[0]
        for i in exp_idx:
            names[i] = org_names(rng, country[i], 1)[0]
            tax[i] = foreign_tax_ids(rng, country[i], 1)[0]
        code = np.array([f"120.01.{i:05d}" for i in range(1, n + 1)])
        code[export] = [f"120.02.{i:05d}" for i in range(1, export.sum() + 1)]
        cheque_share = np.where(export, 0.0, np.clip(rng.beta(1.2, 2.0, n) * (rng.random(n) < 0.55), 0, 0.9))
        delay_mean = rng.gamma(2.0, 9.0, n) + np.where(seg == "key_account", 5, 0)
    else:
        tax = foreign_tax_ids(rng, company.country, n).astype(object)
        indiv = np.zeros(n, dtype=bool)
        code = np.array([f"C{i:06d}" for i in range(1, n + 1)])
        cheque_share = np.zeros(n)
        delay_mean = rng.gamma(1.6, 5.0, n)
    options = [t for t in prof.payment_terms if t <= 60] if not company.turkish else list(prof.payment_terms)
    terms = rng.choice(options or [min(prof.payment_terms)], n)
    efatura_month = np.full(n, 10 ** 6)
    if company.turkish:
        # e-Fatura became mandatory in waves; larger customers registered earlier.
        first = cal.month_index("2014-01")
        lag = np.where(seg == "key_account", rng.integers(0, 12, n),
                       np.where(seg == "mid_market", rng.integers(6, 60, n), rng.integers(24, 108, n)))
        efatura_month = np.where(export | indiv, 10 ** 6, first + lag)
    risk_limit = (weight / weight.mean() * prof.avg_invoice_usd * 4).round(-3)
    cities = ref.CITIES[company.country]
    city = np.where(export, "", np.array(cities, dtype=object)[rng.integers(0, len(cities), n)])
    return pd.DataFrame({
        "customer_idx": np.arange(n),
        "code": code,
        "name": names,
        "tax_number": tax,
        "is_individual": indiv,
        "segment": seg,
        "country": country,
        "city": city,
        "is_export": export,
        "payment_terms_days": terms,
        "risk_limit_usd": risk_limit,
        "start_month": start,
        "end_month": end,
        "default_month": np.where(defaults, def_month, -1),
        "weight": weight,
        "cheque_share": cheque_share,
        "delay_mean": delay_mean,
        "discount_rate": np.clip(np.where(seg == "key_account", 0.08, np.where(seg == "mid_market", 0.04, 0.01))
                                 + rng.normal(0, 0.015, n), 0, 0.2),
        "efatura_month": efatura_month,
    })


SUPPLIER_KINDS = [
    # kind, share of supplier count, Turkish sector word, English sector word
    ("goods", 0.55, None, None),
    ("subcontract", 0.10, "Hizmet", "Services"),
    ("rent", 0.02, "Gayrimenkul", "Properties"),
    ("utilities", 0.02, "Enerji", "Energy"),
    ("telecom_it", 0.05, "Bilişim", "Technology"),
    ("marketing", 0.05, "Reklam", "Media"),
    ("logistics", 0.05, "Lojistik", "Logistics"),
    ("professional", 0.05, "Danışmanlık", "Consulting"),
    ("maintenance", 0.05, "Teknik", "Maintenance"),
    ("insurance", 0.01, "Sigorta", "Insurance"),
    ("capex", 0.05, "Makina", "Equipment"),
]

# Suppliers that are other companies in the dataset (connected economy), with a
# deliberately different spelling than the company's own name.
INTERCO_SUPPLIERS = {
    True: {"utilities": ("poyraz", "POYRAZ ENERJI AS"), "telecom_it": ("telekent", "Telekent Iletisim A.S."),
           "logistics": ("ufuk", "UFUK LOJ. A.Ş."), "professional": ("bilge", "Bilge Yazilim AS")},
    False: {"utilities": ("solenne", "Solenne Energia SA"), "telecom_it": ("aurore", "AURORE TELECOM"),
            "logistics": ("meridian", "MERIDIAN FRT BV"), "professional": ("cobalt", "Cobalt Software, Inc")},
}


def suppliers(rng, company, scale: float) -> pd.DataFrame:
    prof = company.profile
    n = max(len(SUPPLIER_KINDS) + 4, int(prof.suppliers * max(scale, 0.01) ** 0.6))
    shares = np.array([s for _, s, _, _ in SUPPLIER_KINDS])
    counts = np.maximum(1, np.round(shares / shares.sum() * n).astype(int))
    rows = []
    idx = 0
    for (kind, _, tr_word, en_word), cnt in zip(SUPPLIER_KINDS, counts):
        foreign_share = 0.25 if (company.turkish and kind in ("goods", "capex")) else 0.0
        names = org_names(rng, company.country, cnt, tr_word if company.turkish else en_word)
        for j in range(cnt):
            idx += 1
            is_foreign = rng.random() < foreign_share
            name = names[j]
            if is_foreign:
                foreign_country = str(rng.choice(["DE", "US", "FR", "NL", "UK"]))
                name = org_names(rng, foreign_country, 1, en_word)[0]
            interco = ""
            if j == 0 and kind in INTERCO_SUPPLIERS[company.turkish]:
                other, alias = INTERCO_SUPPLIERS[company.turkish][kind]
                if other != company.id:
                    name, interco = alias, other
            country = foreign_country if is_foreign else company.country
            if company.turkish:
                tax = foreign_tax_ids(rng, country, 1)[0] if is_foreign else vkn_numbers(rng, 1)[0]
                code = f"320.{'02' if is_foreign else '01'}.{idx:05d}"
            else:
                tax = foreign_tax_ids(rng, company.country, 1)[0]
                code = f"V{idx:06d}"
            rows.append((idx - 1, code, name, tax, kind, country, interco,
                         int(rng.choice([30, 45, 60, 90] if kind in ("goods", "capex", "subcontract") else [15, 30])),
                         float(rng.pareto(1.2) + 0.1)))
    df = pd.DataFrame(rows, columns=["supplier_idx", "code", "name", "tax_number", "kind", "country",
                                     "interco_company", "payment_terms_days", "weight"])
    df["cheque_share"] = 0.0
    if company.turkish:
        goods = df.kind.isin(["goods", "subcontract", "capex"])
        df.loc[goods, "cheque_share"] = np.clip(rng.beta(1.3, 2.5, goods.sum()), 0, 0.8)
    return df


# --------------------------------------------------------------------------- fixed assets

ASSET_CLASSES = {
    # class: (TDHP account, useful life years, typical unit cost USD 2026, Turkish name, English name)
    "building": ("252", 30, 2_500_000, "Bina", "Building"),
    "machinery": ("253", 10, 180_000, "Makina ve tesis", "Plant & machinery"),
    "vehicle": ("254", 6, 45_000, "Taşıt", "Vehicle"),
    "it_furniture": ("255", 4, 15_000, "Demirbaş", "IT & furniture"),
}

ASSET_MIX = {
    "manufacturing": {"building": 0.25, "machinery": 0.55, "vehicle": 0.05, "it_furniture": 0.15},
    "textiles": {"building": 0.25, "machinery": 0.60, "vehicle": 0.05, "it_furniture": 0.10},
    "food": {"building": 0.30, "machinery": 0.55, "vehicle": 0.10, "it_furniture": 0.05},
    "retail": {"building": 0.45, "machinery": 0.25, "vehicle": 0.10, "it_furniture": 0.20},
    "pharma": {"building": 0.35, "machinery": 0.50, "vehicle": 0.02, "it_furniture": 0.13},
    "logistics": {"building": 0.20, "machinery": 0.10, "vehicle": 0.60, "it_furniture": 0.10},
    "energy": {"building": 0.10, "machinery": 0.82, "vehicle": 0.03, "it_furniture": 0.05},
    "software": {"building": 0.0, "machinery": 0.20, "vehicle": 0.0, "it_furniture": 0.80},
    "construction": {"building": 0.05, "machinery": 0.60, "vehicle": 0.30, "it_furniture": 0.05},
    "banking": {"building": 0.6, "machinery": 0.0, "vehicle": 0.0, "it_furniture": 0.4},
    "automotive": {"building": 0.25, "machinery": 0.65, "vehicle": 0.02, "it_furniture": 0.08},
    "defense": {"building": 0.30, "machinery": 0.50, "vehicle": 0.0, "it_furniture": 0.20},
    "telecom": {"building": 0.10, "machinery": 0.75, "vehicle": 0.03, "it_furniture": 0.12},
    "airline": {"building": 0.05, "machinery": 0.08, "vehicle": 0.85, "it_furniture": 0.02},
    "healthcare": {"building": 0.35, "machinery": 0.50, "vehicle": 0.02, "it_furniture": 0.13},
}

# Useful life overrides in years (aircraft, trucks, network equipment).
LIFE_OVERRIDE = {("airline", "vehicle"): 20, ("logistics", "vehicle"): 8, ("energy", "machinery"): 25,
                 ("telecom", "machinery"): 8}

# Typical unit cost overrides for asset-heavy industries (aircraft, turbines, network sites).
UNIT_COST_OVERRIDE = {("airline", "vehicle"): 60_000_000, ("energy", "machinery"): 2_000_000,
                      ("telecom", "machinery"): 250_000, ("logistics", "vehicle"): 130_000,
                      ("automotive", "machinery"): 900_000}


def fixed_assets(rng, company, cal, capex_local: np.ndarray, usd_to_local_end: float,
                 price_idx: np.ndarray, opening_ppe_local: float) -> pd.DataFrame:
    """Asset register: an opening stock bought before the data starts, then monthly capex."""
    mix = ASSET_MIX[company.industry]
    classes = [c for c, s in mix.items() if s > 0]
    shares = np.array([mix[c] for c in classes])
    rows = []

    def unit_cost(cls, month_idx):
        base = UNIT_COST_OVERRIDE.get((company.industry, cls), ASSET_CLASSES[cls][2])
        return base * usd_to_local_end * price_idx[max(month_idx, 0)]

    carry = {cls: 0.0 for cls in classes}

    def buy(budget, month_idx, opening=False):
        """Buy whole units; budget that does not cover a unit carries over to later months."""
        for cls, sh in zip(classes, shares):
            amount = budget * sh + (0.0 if opening else carry[cls])
            if amount <= 0:
                continue
            uc = unit_cost(cls, month_idx)
            n = max(1, int(round(amount / uc))) if opening else int(amount // uc)
            if n == 0:
                carry[cls] = amount
                continue
            spend = amount if opening else n * uc
            carry[cls] = 0.0 if opening else amount - spend
            costs = uc * rng.lognormal(0, 0.25, n)
            costs *= spend / costs.sum()
            life = LIFE_OVERRIDE.get((company.industry, cls), ASSET_CLASSES[cls][1]) * 12
            for c in costs:
                age = int(rng.integers(1, life)) if opening else 0
                rows.append((cls, month_idx - age, float(c)))

    # Opening stock: net book value roughly 55% of cost.
    buy(opening_ppe_local / 0.55, 0, opening=True)
    for m in range(cal.n_months):
        if capex_local[m] > 0:
            buy(capex_local[m], m)
    df = pd.DataFrame(rows, columns=["asset_class", "acq_month", "cost"])
    df["account"] = df.asset_class.map(lambda c: ASSET_CLASSES[c][0])
    life_years = df.asset_class.map(lambda c: LIFE_OVERRIDE.get((company.industry, c), ASSET_CLASSES[c][1])).values
    df["useful_life_months"] = (life_years * 12 * rng.uniform(0.8, 1.2, len(df))).astype(int)
    df["dispose_month"] = df.acq_month + df.useful_life_months
    name_idx = 3 if company.turkish else 4
    df["description"] = df.asset_class.map(lambda c: ASSET_CLASSES[c][name_idx])
    df = df.sort_values(["acq_month"], kind="stable").reset_index(drop=True)
    df.insert(0, "asset_id", np.arange(1, len(df) + 1))
    df["asset_tag"] = [f"{company.id[:3].upper()}-FA-{i:06d}" for i in df.asset_id]
    df["cost"] = df.cost.round(2)
    return df


# --------------------------------------------------------------------------- employees

GRADE_SHARE = np.array([0.45, 0.25, 0.15, 0.09, 0.045, 0.015])
GRADE_MULT = np.array([1.0, 1.4, 2.0, 2.9, 4.2, 7.0])
TITLES_EN = ["Associate", "Specialist", "Senior Specialist", "Manager", "Director", "Executive"]
TITLES_TR = ["Uzman Yardımcısı", "Uzman", "Kıdemli Uzman", "Müdür", "Direktör", "Genel Müdür Yardımcısı"]
# Monthly gross pay for grade 1 in the final month, local currency.
BASE_WAGE_END = {"TR": 42_000, "US": 4_200, "UK": 2_700, "DE": 3_300, "NL": 3_300, "ES": 2_000, "FR": 2_500}


def employees(rng, company, cal, activity_real: np.ndarray, scale: float):
    """Monthly headcount simulation per department: hires, attrition and layoffs.

    Returns the employee master and the list of active months per employee.
    """
    prof = company.profile
    productivity = 1.015 ** cal.t_end  # productivity grows 1.5% a year
    rpe = prof.rev_per_employee_k * 1000 * (0.6 if company.turkish else 1.0)
    smooth = pd.Series(activity_real * 12).rolling(12, min_periods=1).mean().shift(3).bfill().values
    target_total = np.maximum(3, smooth / (rpe * productivity))
    depts = prof.departments
    attr_annual = 0.14 if company.turkish else 0.12
    if company.industry == "retail":
        attr_annual = 0.35
    p_leave = 1 - (1 - attr_annual) ** (1 / 12)

    emp_dept, emp_grade, emp_hire, emp_term, emp_reason = [], [], [], [], []
    active = {d: [] for d, _, _ in depts}
    for m in range(cal.n_months):
        for d, share, _ in depts:
            target = max(1, int(round(target_total[m] * share)))
            ids = active[d]
            if ids:
                leave = rng.random(len(ids)) < p_leave
                keep = []
                for e, l in zip(ids, leave):
                    if l:
                        emp_term[e] = m
                        emp_reason[e] = "resignation" if rng.random() < 0.8 else "retirement"
                    else:
                        keep.append(e)
                ids = keep
            if len(ids) > target * 1.06:
                n_cut = len(ids) - target
                ids_sorted = sorted(ids, key=lambda e: -emp_hire[e])
                for e in ids_sorted[:n_cut]:
                    emp_term[e] = m
                    emp_reason[e] = "layoff"
                cut = set(ids_sorted[:n_cut])
                ids = [e for e in ids if e not in cut]
            hires = max(0, target - len(ids))
            if m == 0:
                hires = target
            for _ in range(hires):
                e = len(emp_dept)
                emp_dept.append(d)
                emp_grade.append(int(rng.choice(6, p=GRADE_SHARE)))
                emp_hire.append(m if m > 0 else -int(rng.integers(0, 240)))
                emp_term.append(10 ** 6)
                emp_reason.append("")
                ids.append(e)
            active[d] = ids

    n = len(emp_dept)
    first, last, gender = person_names(rng, company.country, n)
    hire = np.array(emp_hire)
    age_at_hire = rng.integers(20, 50, n)
    hire_dates = cal.month_start[np.clip(hire, 0, None)] + pd.to_timedelta(rng.integers(0, 27, n), unit="D")
    hire_dates = np.where(hire < 0, (cal.month_start[0] + pd.to_timedelta(hire * 30.4, unit="D")).values,
                          hire_dates.values)
    hire_dates = pd.to_datetime(hire_dates).normalize()
    birth = hire_dates - pd.to_timedelta(age_at_hire * 365.25 + rng.integers(0, 365, n), unit="D")
    term = np.array(emp_term)
    term_dates = pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns]")
    has_term = term < cal.n_months
    term_dates[has_term] = (cal.month_end[term[has_term]] - pd.to_timedelta(rng.integers(0, 20, has_term.sum()),
                                                                            unit="D")).values
    titles = np.array(TITLES_TR if company.turkish else TITLES_EN, dtype=object)
    grade = np.array(emp_grade)
    df = pd.DataFrame({
        "employee_id": np.arange(1, n + 1),
        "sicil_no": [f"{company.id[:2].upper()}{i:06d}" for i in range(1, n + 1)],
        "first_name": first, "last_name": last, "gender": gender,
        "birth_date": birth.normalize(),
        "hire_date": hire_dates,
        "termination_date": term_dates.values,
        "termination_reason": np.where(has_term, np.array(emp_reason, dtype=object), None),
        "department": np.array(emp_dept, dtype=object),
        "grade": grade + 1,
        "title": titles[grade],
        "pay_factor": rng.lognormal(0, 0.1, n),
        "hire_month": hire,
        "term_month": term,
    })
    return df
