"""Connected economy: trade between companies in the dataset.

Each link produces one deterministic stream of invoices that both the seller's job and
the buyer's job compute independently from the same inputs (calendar, scale, seed), so
the two sides match without the jobs talking to each other:

- the seller books a sales invoice (with lines) to a customer card for the buyer;
- the buyer books the same invoice number, ETTN, date and amount from a supplier card
  that spells the seller's name differently (entity matching);
- both sides record the payment on the same day, so the bank statements match.

A few deliberate differences are left in for reconciliation demos: about 2% of invoices
are booked by the buyer days later (often across a month end) and about 0.3% are never
booked by the buyer (and stay unpaid). Cross-border links create FX differences.
"""

import zlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import reference as ref
from .companies import BY_ID
from .masters import foreign_tax_ids, uuids, vkn_numbers
from .timeline import activity, fx_daily, fx_monthly, price_index


@dataclass(frozen=True)
class Link:
    seller: str
    buyer: str
    share: float           # share of the seller's (or, for fees, the buyer's) revenue
    kind: str              # buyer's purchase category
    buyer_name: str        # how the buyer's systems spell the seller
    seller_name: str = ""  # how the seller's systems spell the buyer ("" = legal name)
    avg_usd: float = 25_000
    terms: int = 60
    since: str = "1994-07"
    fee: bool = False      # amount follows the buyer's revenue (holding management fee)


LINKS = [
    # Kervan Holding group (consolidation demo)
    Link("anatolia", "marmara", 0.04, "goods", "Anatolia Tekstil San. ve Tic. A.Ş.", "MARMARA OTOMOTIV A.S.", 40_000, 75),
    Link("bosphorus", "anatolia", 0.004, "professional", "Bosphorus Gida A.S.", "", 6_000, 30, "1998-01"),
    Link("bosphorus", "marmara", 0.006, "professional", "BOSPHORUS GIDA", "", 8_000, 30, "1998-01"),
    Link("kervan", "anatolia", 0.005, "professional", "Kervan Holding A.Ş.", fee=True, avg_usd=1e9, terms=30),
    Link("kervan", "bosphorus", 0.005, "professional", "KERVAN HOLDING AS", fee=True, avg_usd=1e9, terms=30),
    Link("kervan", "marmara", 0.004, "professional", "Kervan Holding", fee=True, avg_usd=1e9, terms=30),
    # Turkish supply chains
    Link("bosphorus", "cinar", 0.05, "goods", "BOSPHORUS GIDA AS", "Çınar Market A.Ş.", 9_000, 45),
    Link("anatolia", "cinar", 0.02, "goods", "ANATOLIA TEKSTIL", "", 15_000, 60, "2002-01"),
    Link("ostim", "marmara", 0.05, "goods", "OSTIM END. MAK. A.S.", "", 20_000, 60),
    Link("ostim", "kalkan", 0.04, "goods", "Ostim Endustriyel Makina AS", "KALKAN SAVUNMA", 30_000, 60, "2004-06"),
    Link("sifa", "hayat", 0.06, "goods", "Şifa İlaç Sanayi A.Ş.", "Hayat Saglik Grubu", 12_000, 90),
    Link("ufuk", "bosphorus", 0.08, "logistics", "UFUK LOJ. A.Ş.", "", 4_000, 45),
    Link("ufuk", "anatolia", 0.06, "logistics", "Ufuk Lojistik", "", 4_000, 45),
    Link("ufuk", "marmara", 0.08, "logistics", "UFUK LOJISTIK AS", "", 5_000, 45),
    Link("poyraz", "ostim", 0.01, "utilities", "POYRAZ ENERJI AS", "", 1e9, 30, "2002-03"),
    Link("poyraz", "marmara", 0.02, "utilities", "Poyraz Enerji A.Ş.", "", 1e9, 30, "2002-03"),
    Link("poyraz", "bosphorus", 0.01, "utilities", "POYRAZ ENERJİ", "", 1e9, 30, "2002-03"),
    Link("telekent", "cinar", 0.002, "telecom_it", "TELEKENT ILETISIM HIZ. A.S.", "", 1e9, 30, "2001-06"),
    Link("telekent", "marmara", 0.002, "telecom_it", "Telekent İletişim", "", 1e9, 30, "2001-06"),
    Link("bilge", "ostim", 0.03, "telecom_it", "Bilge Yazilim AS", "", 15_000, 30, "2003-01"),
    Link("bilge", "cinar", 0.04, "telecom_it", "BILGE YAZILIM", "", 20_000, 30, "2005-01"),
    # Foreign supply chains (Alpenhof sells to a US retailer: EUR invoices, USD books)
    Link("alpenhof", "brightmart", 0.03, "goods", "ALPENHOF FOODS GMBH", "Brightmart Retail Group Inc.", 30_000, 45),
    Link("kestrel", "ironclad", 0.04, "goods", "Kestrel Industrial Comp.", "IRONCLAD AEROSPACE", 40_000, 45),
    Link("meridian", "alpenhof", 0.05, "logistics", "MERIDIAN FRT BV", "", 6_000, 30),
    Link("meridian", "helix", 0.03, "logistics", "Meridian Freight", "", 6_000, 30),
    Link("meridian", "rheinwerk", 0.05, "logistics", "Meridian Freight B.V.", "", 8_000, 30),
    Link("solenne", "alpenhof", 0.01, "utilities", "Solenne Energia SA", "", 1e9, 30),
    Link("cobalt", "kestrel", 0.03, "telecom_it", "COBALT SOFTWARE", "", 30_000, 30, "2000-01"),
    Link("cobalt", "northbridge", 0.04, "telecom_it", "Cobalt Software, Inc", "", 40_000, 30, "2004-01"),
    Link("cobalt", "brightmart", 0.02, "telecom_it", "Cobalt Software Inc.", "", 30_000, 30, "2006-01"),
]

HOLDING = {"id": "kervan", "name": "Kervan Holding A.Ş.", "country": "TR"}


def company_tax_number(company_id: str) -> str:
    rng = np.random.default_rng(zlib.crc32(f"tax-{company_id}".encode()))
    country = HOLDING["country"] if company_id == HOLDING["id"] else BY_ID[company_id].country
    return vkn_numbers(rng, 1)[0] if country == "TR" else foreign_tax_ids(rng, country, 1)[0]


def legal_name(company_id: str) -> str:
    return HOLDING["name"] if company_id == HOLDING["id"] else BY_ID[company_id].name


def country_of(company_id: str) -> str:
    return HOLDING["country"] if company_id == HOLDING["id"] else BY_ID[company_id].country


def links_for(company_id: str):
    return [l for l in LINKS if l.seller == company_id], [l for l in LINKS if l.buyer == company_id]


def _weekday(cal, day):
    dow = (cal.start.dayofweek + day) % 7
    return day + np.where(dow == 5, 2, np.where(dow == 6, 1, 0))


def _revenue(cal, company_id, scale, base_seed):
    company = BY_ID[company_id]
    seed = base_seed * 1_000_003 + zlib.crc32(company_id.encode())
    region = ref.COUNTRY_REGION[company.country]
    cur = ref.COUNTRY_CURRENCY[company.country]
    act = activity(cal, company, scale, seed)
    return act * fx_monthly(cal, cur)[-1] * price_index(cal, region), cur


def link_invoices(link: Link, cal, scale: float, base_seed: int) -> pd.DataFrame:
    """The invoice stream of one link, identical in the seller's and the buyer's job."""
    basis = link.buyer if link.fee else link.seller
    rev, _ = _revenue(cal, basis, scale, base_seed)
    seller_country = country_of(link.seller)
    cur = ref.COUNTRY_CURRENCY[seller_country]
    region = ref.COUNTRY_REGION[seller_country]
    if link.fee:
        rev = rev  # buyer and holding are both Turkish: same currency
    rng = np.random.default_rng(zlib.crc32(f"{link.seller}->{link.buyer}".encode()) + base_seed)
    n_m = cal.n_months
    start = max(0, cal.month_index(link.since))
    amount = link.share * rev * rng.lognormal(0, 0.15, n_m)
    amount[:start] = 0
    P = price_index(cal, region)
    fx_end = fx_monthly(cal, cur)[-1]
    avg = link.avg_usd * fx_end * P
    counts = np.where(amount > 0, np.maximum(1, np.round(amount / avg)), 0).astype(int)
    m = np.repeat(np.arange(n_m), counts)
    if len(m) == 0:
        return pd.DataFrame()
    first = np.array([(p.start_time - cal.start).days for p in cal.months])
    length = cal.months.days_in_month.values
    day = _weekday(cal, first[m] + rng.integers(0, length[m] - 2))
    w = rng.lognormal(0, 0.5, len(m))
    wsum = np.bincount(m, weights=w, minlength=n_m)
    net = np.round(amount[m] * w / wsum[m], 2)
    year = cal.start.year + (cal.start.month - 1 + m) // 12
    cross = country_of(link.buyer) != seller_country
    if cross:
        vat_rate = np.zeros(len(m))
    elif seller_country == "TR":
        vat_rate = np.array([ref.TR_VAT.get(int(y), 0.20) for y in year])
    else:
        vat_rate = np.full(len(m), ref.VAT[seller_country])
    vat = np.round(net * vat_rate, 2)
    order = np.argsort(day, kind="stable")
    df = pd.DataFrame({"m": m, "day": day, "net": net, "vat_rate": vat_rate, "vat": vat, "year": year}).iloc[order]
    df = df.reset_index(drop=True)
    if seller_country == "TR":
        electronic = (df.year.values >= 2014) & (country_of(link.buyer) == "TR")
        prefix = (link.seller[:1] + link.buyer[:1] + "K").upper()   # one e-invoice series per link
        seq_e = df.groupby(df.year.values).cumcount().values + 1
        seq_p = np.cumsum(~electronic)
        df["number"] = np.where(electronic, [f"{prefix}{y}{s:09d}" for y, s in zip(df.year.values, seq_e)],
                                [f"K{(link.seller[:1] + link.buyer[:1]).upper()}-{s:06d}" for s in seq_p])
        df["channel"] = np.where(electronic, "e-fatura", "kağıt")
        ettn = np.full(len(df), None, dtype=object)
        ettn[electronic] = uuids(rng, int(electronic.sum()))
        df["ettn"] = ettn
    else:
        seq = df.groupby(df.year.values).cumcount().values + 1
        df["number"] = [f"IC{link.buyer[:2].upper()}{y}-{s:06d}" for y, s in zip(df.year.values, seq)]
        df["channel"] = "edi"
        df["ettn"] = None
    df["currency"] = cur
    df["total"] = np.round(df.net + df.vat, 2)
    df["due"] = df.day + link.terms
    df["pay_day"] = _weekday(cal, df.due.values + np.maximum(rng.normal(4, 6, len(df)), -3).astype(int))
    lag = rng.random(len(df)) < 0.02
    df["buyer_day"] = np.where(lag, _weekday(cal, df.day.values + rng.integers(3, 21, len(df))), df.day.values)
    df["missing"] = rng.random(len(df)) < 0.003
    df["kind"] = link.kind
    return df


def fx_to_local(cal, cur_from: str, cur_to: str, day: np.ndarray) -> np.ndarray:
    """Units of `cur_to` per unit of `cur_from` on each day."""
    if cur_from == cur_to:
        return np.ones(len(day))
    d = np.clip(day, 0, len(cal.days) - 1)
    per_usd = {c: fx_daily(cal, c) for c in {cur_from, cur_to}}
    return per_usd[cur_to][d] / per_usd[cur_from][d]
