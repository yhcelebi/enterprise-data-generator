"""Telecom: plans, subscriber base, a subscriber panel with daily usage, and the cell network.

The monthly subscriber base is derived from the consumer billing in the ledger
(billing / ARPU). Daily usage is kept for a panel of subscribers sized by the detail
budget; usage follows the real technology eras: voice, the SMS boom, then mobile data.
"""

import numpy as np
import pandas as pd

from .. import reference as ref
from . import blocks, weighted_choice

USAGE_ROW_BUDGET = 1600e6
ARPU_USD_2026 = {True: 9.0, False: 24.0}
# Network generations: (technology, Turkey launch year, France launch year)
TECH = [("2G", 1994, 1992), ("3G", 2009, 2004), ("4G", 2016, 2012), ("5G", 2026, 2020)]
# Usage per active subscriber per day: years, voice minutes, SMS, data MB
YEARS = [1995, 2000, 2005, 2008, 2010, 2013, 2016, 2019, 2022, 2026]
VOICE = [2.5, 4.0, 6.0, 7.0, 8.0, 8.5, 8.0, 7.0, 6.5, 6.0]
SMS = [0.05, 1.0, 2.0, 2.6, 2.4, 1.5, 0.8, 0.5, 0.35, 0.3]
DATA = [0.0, 0.01, 0.5, 2.0, 8.0, 40.0, 180.0, 500.0, 1100.0, 2200.0]
PLANS = [  # name, segment, launch, discontinue, monthly fee (2026 USD, TR), data GB
    ("Hazır Kart Standart", "prepaid", 1995, 2012, 6, 0), ("Faturalı Konuşma 200", "postpaid", 1995, 2010, 12, 0),
    ("Gençlik SMS Paketi", "prepaid", 2004, 2014, 7, 0.1), ("Akıllı 2 GB", "postpaid", 2009, 2017, 12, 2),
    ("Hazır Kart Akıllı", "prepaid", 2012, 2030, 7, 4), ("Sınırsız 10 GB", "postpaid", 2014, 2022, 15, 10),
    ("4.5G 25 GB", "postpaid", 2016, 2030, 16, 25), ("Gençlik 40 GB", "prepaid", 2019, 2030, 9, 40),
    ("Sınırsız Plus", "postpaid", 2022, 2030, 22, 200),
]
PLANS_EN = ["Prepaid Basic", "Talk 200", "Youth Text Pack", "Smart 2 GB", "Prepaid Smart", "Unlimited 10 GB",
            "4G 25 GB", "Youth 40 GB", "Unlimited Plus"]


def _curve(years, xs, ys, log=False):
    if log:
        return np.exp(np.interp(years, xs, np.log(np.array(ys) + 0.01))) - 0.01
    return np.interp(years, xs, ys)


def generate(ctx):
    sim, rng, cal = ctx.sim, ctx.rng, ctx.sim.cal
    tr = sim.tr
    fr_factor = 1.0 if tr else 1.4
    n_m = cal.n_months
    # Plans.
    plans = pd.DataFrame(PLANS, columns=["name", "segment", "launch_year", "discontinue_year", "fee_usd", "data_gb"])
    if not tr:
        plans["name"] = PLANS_EN
        plans["fee_usd"] = plans.fee_usd * 2.2
    plans.insert(0, "plan_id", np.arange(1, len(plans) + 1))
    plans["monthly_fee_2026"] = np.round(plans.fee_usd * sim.fx_end, 2)
    ctx.w.write("plans", plans.drop(columns=["fee_usd"]))

    # Subscriber base from billing.
    billed_m = np.bincount(sim.dm, weights=sim.b2c.billed.values, minlength=n_m)
    year_f = cal.months.year.values + (cal.months.month.values - 1) / 12
    arpu = ARPU_USD_2026[tr] * sim.fx_end * sim.P * 1.03 ** (-cal.t_end)  # real ARPU fell ~3% a year
    subs = np.maximum(1, billed_m / arpu)
    postpaid_share = np.interp(year_f, [1995, 2010, 2026], [0.25, 0.35, 0.55] if tr else [0.5, 0.65, 0.8])
    churn = np.interp(year_f, [1995, 2005, 2026], [0.012, 0.025, 0.018])
    base = []
    for seg, share in (("postpaid", postpaid_share), ("prepaid", 1 - postpaid_share)):
        s = np.round(subs * share)
        churned = np.round(s * churn * (0.6 if seg == "postpaid" else 1.4))
        adds = np.maximum(0, s - np.concatenate([[s[0]], s[:-1]]) + churned)
        base.append(pd.DataFrame({"period": cal.months.astype(str), "segment": seg, "active_subscribers": s.astype(np.int64),
                                  "gross_adds": adds.astype(np.int64), "churned": churned.astype(np.int64),
                                  "arpu": np.round(arpu * (1.4 if seg == "postpaid" else 0.6), 2)}))
    base = pd.concat(base)
    first_m = cal.month_index(cal.output_start.strftime("%Y-%m"))
    ctx.w.write("subscriber_base_monthly", base[base.period >= cal.months[first_m].strftime("%Y-%m")])

    # Panel: subscribers drawn in proportion to gross adds, sized to the usage-row budget.
    budget = USAGE_ROW_BUDGET * ctx.detail
    adds_total = base.groupby("period", sort=False).gross_adds.sum().values.astype(float)
    adds_total[0] += subs[0]
    churn_eff = churn.mean()
    mean_life_days = 30.4 / churn_eff
    days_left = sim.last_day - ctx.first_day
    n_panel = int(budget / min(mean_life_days * 0.8, days_left * 0.5)) + 1
    start_m = weighted_choice(rng, adds_total, n_panel * 2)
    start_day = sim.month_first_day[start_m] + rng.integers(0, 28, len(start_m))
    start_day = np.where(start_m == 0, rng.integers(-3000, 1, len(start_m)), start_day)
    life = rng.exponential(mean_life_days, len(start_m)).astype(np.int64) + 30
    end_day = start_day + life
    a = np.maximum(start_day, ctx.first_day)
    b = np.minimum(end_day, sim.last_day + 1)
    active_days = np.maximum(b - a, 0)
    keep = active_days > 0
    order = np.where(keep)[0]
    cum = np.cumsum(active_days[order])
    order = order[:max(1, np.searchsorted(cum, budget) + 1)]
    start_day, end_day, a, b = start_day[order], end_day[order], a[order], b[order]
    n = len(order)
    yr0 = sim.ext_year[np.clip(np.maximum(start_day, 0), 0, len(sim.ext_year) - 1)]
    seg = np.where(rng.random(n) < np.interp(yr0, year_f, postpaid_share), "postpaid", "prepaid")
    # Newest plan on sale in the activation year, per segment.
    plan_id = np.empty(n, dtype=np.int64)
    for sg in ("prepaid", "postpaid"):
        lookup = {}
        for y in range(1990, 2031):
            ok = plans[(plans.segment == sg) & (plans.launch_year <= max(y, 1995)) & (plans.discontinue_year > y)]
            lookup[y] = ok.plan_id.values[-1] if len(ok) else plans[plans.segment == sg].plan_id.values[0]
        sel = seg == sg
        plan_id[sel] = [lookup[int(min(max(y, 1990), 2030))] for y in yr0[sel]]
    cities = np.array(ref.CITIES[sim.c.country], dtype=object)
    heavy = rng.lognormal(0, 0.6, n)
    subscribers = pd.DataFrame({
        "subscriber_id": np.arange(1, n + 1), "msisdn_hash": [f"{x:016x}" for x in rng.integers(0, 2 ** 62, n)],
        "segment": seg, "plan_id": plan_id, "city": cities[np.minimum(rng.pareto(1.0, n).astype(int), len(cities) - 1)],
        "activation_date": sim.dates(start_day),
        "churn_date": np.where(end_day <= sim.last_day, sim.dates(np.minimum(end_day, sim.last_day)), np.datetime64("NaT")),
    })
    ctx.w.write("subscribers", subscribers)

    fee = plans.set_index("plan_id").monthly_fee_2026
    for year in ctx.years:
        days = ctx.year_days(year)
        if len(days) == 0:
            continue
        lo, hi = days[0], days[-1] + 1
        s_a_all, s_b_all = np.maximum(a, lo), np.minimum(b, hi)
        cnt_all = np.maximum(s_b_all - s_a_all, 0)
        for ent in blocks(cnt_all):
            cnt = cnt_all[ent]
            idx = np.repeat(ent, cnt)
            day = np.repeat(s_a_all[ent], cnt) + (np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt))
            k = len(day)
            if k == 0:
                continue
            yf = sim.ext_year[day] + sim.cal.days.dayofyear.values[np.minimum(day, sim.last_day)] / 366
            dow = sim.cal.days.dayofweek.values[np.minimum(day, sim.last_day)]
            weekend = dow >= 5
            post = seg[idx] == "postpaid"
            h = heavy[idx]
            voice = rng.poisson(_curve(yf, YEARS, VOICE) * h * np.where(post, 1.3, 0.7) * np.where(weekend, 0.7, 1.05))
            sms = rng.poisson(_curve(yf, YEARS, SMS) * h * np.where(post, 0.8, 1.3))
            data_mb = np.round(_curve(yf, YEARS, DATA, log=True) * fr_factor * h * rng.lognormal(0, 0.5, k)
                               * np.where(weekend, 1.15, 1.0), 1)
            data_mb = np.where(yf < 2001, 0.0, np.maximum(data_mb, 0))
            month = sim.ext_month[day]
            roaming = (rng.random(k) < np.where(np.isin(month, [7, 8]), 0.02, 0.004)) & (yf > 1998)
            m_idx = np.minimum(sim.month_of_day(day), n_m - 1)
            daily_fee = fee.loc[plan_id[idx]].values * sim.P[m_idx] / 30.4
            charge = np.round(daily_fee * np.where(post, 1.0, rng.uniform(0.6, 1.2, k)) + roaming * daily_fee * 3, 2)
            df = pd.DataFrame({"date": sim.dates(day), "subscriber_id": idx + 1, "voice_minutes": voice.astype(np.int32),
                               "sms": sms.astype(np.int32), "data_mb": data_mb, "roaming": roaming, "charge": charge})
            ctx.w.write("subscriber_daily_usage", df.sort_values(["date", "subscriber_id"], kind="stable"), year)
        ctx.w.close_year(year)

    _network(ctx, subs, year_f)


def _network(ctx, subs, year_f):
    """Cell sites grow with the subscriber base and each technology generation."""
    sim, rng, cal = ctx.sim, ctx.rng, ctx.sim.cal
    tr = sim.tr
    cities = ref.CITIES[sim.c.country]
    rows = []
    for tech, y_tr, y_fr in TECH:
        launch = y_tr if tr else y_fr
        if launch > cal.end.year:
            continue
        target = np.where(year_f >= launch, np.maximum(1, subs / 2500 * np.clip((year_f - launch) / 5, 0.1, 1)), 0)
        have = 0
        for m in range(cal.n_months):
            while have < target[m]:
                have += 1
                rows.append((tech, m, cities[min(int(rng.pareto(0.9)), len(cities) - 1)]))
    cells = pd.DataFrame(rows, columns=["technology", "launch_month", "city"])
    cells.insert(0, "cell_id", np.arange(1, len(cells) + 1))
    cells["site_id"] = (cells.cell_id - 1) // 3 + 1
    cells["capacity_users"] = cells.technology.map({"2G": 400, "3G": 800, "4G": 1500, "5G": 3000})
    cells["launch_date"] = sim.dates(sim.month_first_day[cells.launch_month.values])
    ctx.w.write("network_cells", cells.drop(columns=["launch_month"]))
    load = rng.lognormal(0, 0.4, len(cells))
    for year in ctx.years:
        days = ctx.year_days(year)
        if len(days) == 0:
            continue
        m = sim.dm[days]
        open_ = cells.launch_month.values[None, :] <= m[:, None]
        di, ci = np.nonzero(open_)
        day = days[di]
        yf = sim.ext_year[day] + 0.5
        k = len(day)
        tech = cells.technology.values[ci]
        users = np.round(cells.capacity_users.values[ci] * 0.35 * load[ci] * rng.lognormal(0, 0.1, k))
        data_gb = np.round(users * _curve(yf, YEARS, DATA, log=True) / 1024 * np.where(tech == "2G", 0.02, 1.0)
                           * rng.lognormal(0, 0.15, k), 2)
        df = pd.DataFrame({
            "date": sim.dates(day), "cell_id": cells.cell_id.values[ci], "avg_connected_users": users.astype(np.int32),
            "data_gb": data_gb, "voice_erlang": np.round(users * 0.02 * rng.lognormal(0, 0.1, k), 2),
            "dropped_call_pct": np.round(np.clip(rng.gamma(2, 0.25, k) * np.where(tech == "2G", 1.5, 1.0), 0, 15), 3),
            "availability_pct": np.round(np.clip(100 - rng.exponential(0.15, k), 90, 100), 3),
        })
        ctx.w.write("cell_daily_traffic", df, year)
        ctx.w.close_year(year)
