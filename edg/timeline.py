"""Calendar, macro indices and the activity curve that drives each company."""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from . import reference as ref
from .companies import Company


@dataclass
class Calendar:
    """Simulation calendar. Months before `output_start` are a warm-up and are not written."""

    start: pd.Timestamp
    output_start: pd.Timestamp
    end: pd.Timestamp

    def __post_init__(self):
        self.days = pd.date_range(self.start, self.end, freq="D")
        self.months = pd.period_range(self.start, self.end, freq="M")
        self.day_month = (self.days.year - self.start.year) * 12 + (self.days.month - self.start.month)
        self.month_start = self.months.to_timestamp(how="start")
        self.month_end = self.months.to_timestamp(how="end").normalize()
        self.years = self.months.year.values
        # Fractional time in years, 0 at the end of the calendar.
        self.t_end = ((self.months.year - self.end.year) + (self.months.month - self.end.month) / 12).values

    @property
    def n_months(self) -> int:
        return len(self.months)

    def month_index(self, ym: str) -> int:
        p = pd.Period(ym, freq="M")
        return (p.year - self.start.year) * 12 + (p.month - self.start.month)


def make_calendar(first_year: int = 1995, end: str = "2026-09-30", warmup_months: int = 6) -> Calendar:
    output_start = pd.Timestamp(f"{first_year}-01-01")
    start = output_start - pd.DateOffset(months=warmup_months)
    return Calendar(start, output_start, pd.Timestamp(end))


def _annual(series: dict, key: str, kind: str, year: int) -> float:
    if year <= 1994:
        return ref.YEAR_1994[kind][key]
    idx = min(year, ref.YEARS[-1]) - ref.YEARS[0]
    return series[key][idx]


def price_index(cal: Calendar, region: str) -> np.ndarray:
    """Monthly consumer price index for a region, 1.0 in the final month."""
    monthly = np.array([(1 + _annual(ref.INFLATION, region, "inflation", y) / 100) ** (1 / 12)
                        for y in cal.years])
    level = np.cumprod(monthly)
    return level / level[-1]


def fx_monthly(cal: Calendar, currency: str) -> np.ndarray:
    """Local currency units per USD for each month, interpolated from annual averages."""
    years = np.arange(1994, ref.YEARS[-1] + 1)
    values = np.array([_annual(ref.FX_PER_USD, currency, "fx", y) for y in years])
    anchor = years + 0.5  # annual averages sit in the middle of the year
    t = cal.months.year.values + (cal.months.month.values - 0.5) / 12
    return np.exp(np.interp(t, anchor, np.log(values)))


def fx_daily(cal: Calendar, currency: str, seed: int = 7) -> np.ndarray:
    """Daily rate with realistic day-to-day noise around the monthly path."""
    monthly = fx_monthly(cal, currency)
    if currency == "USD":
        return np.ones(len(cal.days))
    t_month = np.arange(cal.n_months) + 0.5
    t_day = cal.day_month + (cal.days.day.values - 0.5) / cal.days.days_in_month.values
    base = np.exp(np.interp(t_day, t_month, np.log(monthly)))
    rng = np.random.default_rng(seed + sum(map(ord, currency)))
    vol = 0.012 if currency == "TRY" else 0.004
    noise = np.zeros(len(base))
    for i in range(1, len(base)):
        noise[i] = 0.97 * noise[i - 1] + rng.normal(0, vol)
    return base * np.exp(noise)


def interest_monthly(cal: Calendar, region: str) -> np.ndarray:
    return np.array([_annual(ref.INTEREST, region, "interest", y) / 100 for y in cal.years])


def _bump(cal: Calendar, ym: str, depth: float, down: int, recover: int) -> np.ndarray:
    """Multiplicative factor that falls by `depth` over `down` months and recovers over `recover`."""
    f = np.ones(cal.n_months)
    i0 = cal.month_index(ym)
    for i in range(max(i0, 0), cal.n_months):
        k = i - i0
        if k < down:
            x = (k + 1) / down
        elif k < down + recover:
            x = 1 - (k - down + 1) / recover
        else:
            break
        f[i] = 1 + depth * x
    return f


def demand_factor(cal: Calendar, company: Company) -> np.ndarray:
    """Macro shocks, COVID and company-specific shocks combined."""
    prof = company.profile
    region = ref.COUNTRY_REGION[company.country]
    f = np.ones(cal.n_months)
    for _, where, start, down, recover, depth in ref.SHOCKS:
        if where in ("ALL", region):
            f *= _bump(cal, start, -depth * prof.cycle_sensitivity, down, recover)
    covid = ref.COVID_IMPACT.get(prof.covid, 1.0)
    if company.industry == "airline":
        covid = 0.08 if company.turkish else 0.05
    f *= _bump(cal, "2020-03", covid - 1, 2, 16)
    for ev in company.events:
        if ev.kind == "shock":
            f *= _bump(cal, ev.month, ev.size, ev.ramp, ev.recover)
    return f


def activity(cal: Calendar, company: Company, scale: float, seed: int) -> np.ndarray:
    """Monthly revenue in real 2026 USD (scaled), including growth, events, shocks and noise."""
    rng = np.random.default_rng(seed)
    steps = np.ones(cal.n_months)
    total_step = 1.0
    for ev in company.events:
        if ev.kind != "step":
            continue
        i0 = cal.month_index(ev.month)
        ramp = np.clip((np.arange(cal.n_months) - i0 + 1) / max(ev.ramp, 1), 0, 1)
        steps *= 1 + ev.size * ramp
        total_step *= 1 + ev.size
    years_span = (cal.end - pd.Timestamp("1995-01-01")).days / 365.25
    r_end = company.revenue_2026 * 1e6 / total_step
    growth = (r_end / (company.revenue_1995 * 1e6 / 1.0)) ** (1 / years_span)
    base = r_end * growth ** cal.t_end
    wave = 1 + 0.03 * np.sin(2 * np.pi * (cal.t_end / rng.uniform(6, 9)) + rng.uniform(0, 6.28))
    noise = np.zeros(cal.n_months)
    for i in range(1, cal.n_months):
        noise[i] = 0.75 * noise[i - 1] + rng.normal(0, 0.02)
    season = np.array(company.profile.seasonality, dtype=float)
    season = season / season.mean()
    seasonal = season[cal.months.month.values - 1]
    monthly = base * steps * wave * np.exp(noise) * demand_factor(cal, company) * seasonal / 12
    return monthly * scale


def day_weights(cal: Calendar, company: Company) -> np.ndarray:
    """Relative business volume per calendar day (weekends, holidays, month-end push)."""
    prof = company.profile
    dow = cal.days.dayofweek.values
    w = np.where(dow >= 5, prof.weekend_activity, 1.0)
    if prof.weekend_activity < 0.5:
        w = np.where(dow == 5, prof.weekend_activity * 1.5, w)
    hol = set(ref.HOLIDAYS[company.country])
    is_hol = np.array([(m, d) in hol for m, d in zip(cal.days.month.values, cal.days.day.values)])
    w = np.where(is_hol, np.minimum(w, 0.1 if prof.weekend_activity < 0.5 else 0.7), w)
    if prof.b2c_share < 0.5:
        days_left = cal.days.days_in_month.values - cal.days.day.values
        w = np.where((days_left < 3) & (dow < 5), w * 1.35, w)
    return w


@lru_cache(maxsize=None)
def macro_tables(first_year: int, end: str):
    """Monthly macro indicators and daily FX for the shared `macro_*` tables."""
    cal = make_calendar(first_year, end)
    rows = []
    for region in ("US", "EU", "UK", "TR"):
        pi = price_index(cal, region)
        rate = interest_monthly(cal, region)
        for i, m in enumerate(cal.months):
            rows.append((region, str(m), pi[i], rate[i]))
    monthly = pd.DataFrame(rows, columns=["region", "period", "cpi_index", "policy_rate"])
    fx = pd.DataFrame({"date": cal.days})
    for cur in ("EUR", "GBP", "TRY"):
        fx[f"{cur.lower()}_per_usd"] = fx_daily(cal, cur)
    return cal, monthly, fx
