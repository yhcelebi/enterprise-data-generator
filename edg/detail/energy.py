"""Energy: weather, power plants with hourly generation, hourly market prices, smart meters.

Plant capacity follows the company's size; wind, solar and hydro output follow the
simulated weather; gas plants run when the market price covers their cost. Smart meters
roll out from the country's real roll-out years and their daily readings respond to
heating and cooling degree days.
"""

import numpy as np
import pandas as pd

from .. import reference as ref
from . import weighted_choice

METER_ROW_BUDGET = 1000e6
LATITUDE = {"TR": 39.0, "ES": 40.0}
SMART_METER_YEAR = {"TR": 2016, "ES": 2011}
# Plant types: unit size MW, first year for Turkey, first year for Spain, capacity factor
PLANT_TYPES = {"gas": (400, 1998, 1995), "hydro": (60, 1996, 1995), "wind": (60, 2012, 2000), "solar": (40, 2020, 2008)}
# Average wholesale price, USD per MWh (2026 money), by year
PRICE_YEARS = [1995, 2000, 2005, 2010, 2015, 2019, 2020, 2021, 2022, 2023, 2024, 2026]
PRICE_USD = [45, 40, 55, 55, 55, 52, 40, 120, 190, 100, 75, 80]


def generate(ctx):
    sim, rng, cal = ctx.sim, ctx.rng, ctx.sim.cal
    country = sim.c.country
    weather = _weather(ctx)
    ctx.w.write("weather_daily", weather.drop(columns=["day"]))
    plants = _plants(ctx)
    ctx.w.write("power_plants", plants.drop(columns=["start_month", "weight"]))
    w_city = weather.set_index(["city", "day"])
    for year in ctx.years:
        days = ctx.year_days(year)
        if len(days) == 0:
            continue
        hours = np.arange(24)
        day_h = np.repeat(days, 24)
        hour_h = np.tile(hours, len(days))
        doy = cal.days.dayofyear.values[day_h]
        dow = cal.days.dayofweek.values[day_h]
        m = sim.dm[day_h]
        yf = sim.ext_year[day_h] + doy / 366
        # Market price with daily and seasonal shape.
        shape = 1 + 0.25 * np.sin((hour_h - 7) / 24 * 2 * np.pi) + np.where((hour_h >= 18) & (hour_h <= 21), 0.25, 0)
        if year >= 2018:  # midday solar pushes prices down
            shape -= np.where((hour_h >= 11) & (hour_h <= 15), 0.25 * min((year - 2017) / 6, 1), 0)
        season = 1 + 0.15 * np.cos((doy - 20) / 365 * 2 * np.pi)
        base = np.interp(yf, PRICE_YEARS, PRICE_USD) * sim.fx_end * sim.P[m]  # real 2026 USD to local money of the day
        price = base * shape * season * np.where(dow >= 5, 0.85, 1.0) * rng.lognormal(0, 0.18, len(day_h))
        demand = (28_000 if country == "ES" else 33_000) * (1 + 0.012 * (yf - 2010)) * (0.8 + 0.25 * shape) * season
        stamp = sim.dates(day_h).astype("datetime64[s]") + (hour_h * 3600).astype("timedelta64[s]")
        ctx.w.write("market_prices_hourly", pd.DataFrame({
            "datetime": stamp, "price": np.round(price, 2), "currency": sim.cur, "system_demand_mw": np.round(demand),
        }), year)
        # Plant output.
        sun = _sun(doy, hour_h, LATITUDE[country])
        parts = []
        for pl in plants.itertuples():
            live = m >= pl.start_month
            if not live.any():
                continue
            idx = np.where(live)[0]
            wd = w_city.loc[[(pl.city, d) for d in days]]
            dpos = np.searchsorted(days, day_h[idx])
            n = len(idx)
            if pl.type == "wind":
                ws_day = wd.wind_speed.values[dpos]
                ws = np.clip(ws_day * (1 + 0.15 * np.sin((hour_h[idx] - 15) / 24 * 2 * np.pi)) * rng.lognormal(0, 0.15, n), 0, 35)
                cf = np.clip((ws - 3) / 9, 0, 1) ** 1.8 * (ws < 25)
                driver = ws
            elif pl.type == "solar":
                cloud = wd.cloud_cover.values[dpos]
                cf = sun[idx] * (1 - 0.75 * cloud) * 0.85
                driver = np.round(sun[idx] * (1 - 0.75 * cloud) * 1000)
            elif pl.type == "hydro":
                cf = np.clip(0.45 + 0.35 * np.cos((doy[idx] - 110) / 365 * 2 * np.pi), 0.1, 0.95) * rng.uniform(0.85, 1.05, n)
                driver = np.round(cf * 100, 1)
            else:  # gas runs when the price covers fuel and carbon
                cost = base[idx] * 0.9
                cf = np.where(price[idx] > cost, 0.92, 0.15) * rng.uniform(0.9, 1.0, n)
                driver = np.round(price[idx] - cost, 2)
            outage = rng.random(n) < 0.015
            avail = np.where(outage, 0.0, 1.0)
            gen = np.round(pl.capacity_mw * np.clip(cf, 0, 1) * avail, 3)
            parts.append(pd.DataFrame({"datetime": stamp[idx], "plant_id": pl.plant_id, "generation_mwh": gen,
                                       "available_mw": np.round(pl.capacity_mw * avail, 1), "driver": np.round(driver, 2),
                                       "price": np.round(price[idx], 2)}))
        if parts:
            ctx.w.write("plant_hourly_generation", pd.concat(parts, ignore_index=True), year)
        _meters_year(ctx, year, days, weather)
        ctx.w.close_year(year)
    if hasattr(ctx, "meters"):
        ctx.w.write("smart_meters", ctx.meters.drop(columns=["install_day", "base", "heat", "cool"]))


def _sun(doy, hour, lat):
    """Clear-sky solar factor 0..1 from day of year, hour and latitude."""
    decl = 23.44 * np.sin(np.radians(360 / 365 * (doy - 81)))
    ha = (hour + 0.5 - 12.5) * 15
    elev = np.degrees(np.arcsin(np.sin(np.radians(lat)) * np.sin(np.radians(decl))
                                + np.cos(np.radians(lat)) * np.cos(np.radians(decl)) * np.cos(np.radians(ha))))
    return np.clip(np.sin(np.radians(elev)), 0, 1)


def _weather(ctx):
    sim, rng = ctx.sim, ctx.rng
    cities = ref.CITIES[sim.c.country]
    days = np.arange(ctx.first_day, sim.last_day + 1)
    doy = sim.cal.days.dayofyear.values[days]
    yf = sim.ext_year[days] + doy / 366
    parts = []
    for i, city in enumerate(cities):
        mean = rng.uniform(11, 18)
        amp = rng.uniform(7, 11)
        anomaly = np.zeros(len(days))
        for k in range(1, len(days)):
            anomaly[k] = 0.8 * anomaly[k - 1] + rng.normal(0, 1.6)
        temp = mean + amp * -np.cos((doy - 15) / 365 * 2 * np.pi) + anomaly + 0.03 * (yf - 1995)
        wind = np.clip(rng.weibull(2.0, len(days)) * rng.uniform(6, 9) * (1 + 0.2 * np.cos((doy - 30) / 365 * 2 * np.pi)), 0, 30)
        cloud = np.clip(0.35 + 0.3 * np.cos((doy - 15) / 365 * 2 * np.pi) + rng.normal(0, 0.2, len(days)), 0, 1)
        parts.append(pd.DataFrame({"date": sim.dates(days), "day": days, "city": city,
                                   "temp_mean_c": np.round(temp, 1), "hdd": np.round(np.maximum(18 - temp, 0), 1),
                                   "cdd": np.round(np.maximum(temp - 22, 0), 1), "wind_speed": np.round(wind, 1),
                                   "cloud_cover": np.round(cloud, 2)}))
    return pd.concat(parts, ignore_index=True)


def _plants(ctx):
    sim, rng, cal = ctx.sim, ctx.rng, ctx.sim.cal
    tr = sim.tr
    annual_real = pd.Series(sim.act_real * 12).rolling(12, min_periods=1).mean().values
    capacity = annual_real / (8760 * 0.38 * 65)
    year_f = cal.months.year.values + (cal.months.month.values - 1) / 12
    mix_years = [1995, 2005, 2012, 2020, 2026]
    mix = {"gas": [0.6, 0.55, 0.45, 0.35, 0.3], "hydro": [0.4, 0.3, 0.2, 0.15, 0.12],
           "wind": [0.0, 0.15, 0.3, 0.33, 0.33], "solar": [0.0, 0.0, 0.05, 0.17, 0.25]}
    cities = ref.CITIES[sim.c.country]
    have = {t: 0.0 for t in PLANT_TYPES}
    rows = []
    for m in range(cal.n_months):
        for t, (unit, y_tr, y_es) in PLANT_TYPES.items():
            if year_f[m] < (y_tr if tr else y_es):
                continue
            share = np.interp(year_f[m], mix_years, mix[t])
            unit = unit * np.clip(capacity[-1] / 3000, 0.05, 1.0)  # smaller units for smaller companies
            while have[t] + unit * 0.5 < capacity[m] * share:
                size = round(unit * rng.uniform(0.6, 1.4), 1)
                have[t] += size
                rows.append((t, size, m, cities[int(rng.integers(len(cities)))]))
    df = pd.DataFrame(rows, columns=["type", "capacity_mw", "start_month", "city"])
    df.insert(0, "plant_id", np.arange(1, len(df) + 1))
    names = {"gas": ("DGKÇ Santrali", "Combined Cycle"), "hydro": ("HES", "Hydro"), "wind": ("RES", "Wind Farm"),
             "solar": ("GES", "Solar Park")}
    df["name"] = [f"{c} {names[t][0 if tr else 1]} {i}" for c, t, i in zip(df.city, df.type, df.plant_id)]
    df["commissioned"] = sim.dates(sim.month_first_day[df.start_month.values])
    df["weight"] = 1.0
    return df


def _meters_year(ctx, year, days, weather):
    """Smart meters installed from the roll-out year; daily kWh responds to temperature."""
    sim, rng = ctx.sim, ctx.rng
    country = sim.c.country
    start_year = SMART_METER_YEAR[country]
    if not hasattr(ctx, "meters"):
        total_days = sim.last_day - max(ctx.first_day, int((np.datetime64(f"{start_year}-01-01")
                                                            - np.datetime64(sim.cal.start.date())).astype(int)))
        n = max(50, int(METER_ROW_BUDGET * ctx.detail / max(total_days * 0.55, 1)))
        install_year = start_year + np.minimum(rng.exponential(2.5, n), sim.cal.end.year - start_year)
        install_day = ((install_year - 1970) * 365.25).astype(np.int64) - int((np.datetime64(sim.cal.start.date())
                                                                               - np.datetime64("1970-01-01")).astype(int))
        install_day = np.clip(install_day, ctx.first_day, sim.last_day)
        commercial = rng.random(n) < 0.15
        cities = np.array(ref.CITIES[country], dtype=object)
        ctx.meters = pd.DataFrame({
            "meter_id": np.arange(1, n + 1), "customer_type": np.where(commercial, "commercial", "residential"),
            "city": cities[np.minimum(rng.pareto(1.0, n).astype(int), len(cities) - 1)],
            "contracted_kw": np.where(commercial, rng.choice([15, 30, 50, 100], n), rng.choice([3.3, 4.6, 5.75, 6.9], n)),
            "has_solar": rng.random(n) < 0.06, "install_date": sim.dates(install_day), "install_day": install_day,
            "base": np.where(commercial, rng.lognormal(np.log(120), 0.5, n), rng.lognormal(np.log(7 if country == "TR" else 9), 0.4, n)),
            "heat": rng.uniform(0.0, 0.6, n), "cool": rng.uniform(0.1, 0.9, n),
        })
    me = ctx.meters
    live = me[me.install_day <= days[-1]]
    if len(live) == 0:
        return
    start = np.maximum(live.install_day.values, days[0])
    cnt = days[-1] + 1 - start
    idx = np.repeat(np.arange(len(live)), cnt)
    day = np.repeat(start, cnt) + (np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt))
    wx = weather.set_index(["city", "day"])
    key = pd.MultiIndex.from_arrays([live.city.values[idx], day])
    hdd = wx.hdd.reindex(key).values
    cdd = wx.cdd.reindex(key).values
    dow = sim.cal.days.dayofweek.values[day]
    commercial = live.customer_type.values[idx] == "commercial"
    base = live.base.values[idx]
    kwh = base * (1 + live.heat.values[idx] * hdd / 10 + live.cool.values[idx] * cdd / 6) \
        * np.where(commercial, np.where(dow >= 5, 0.35, 1.1), np.where(dow >= 5, 1.12, 0.96)) * rng.lognormal(0, 0.15, len(day))
    solar = live.has_solar.values[idx] & (sim.ext_year[day] >= 2019)
    export = np.where(solar, np.round(rng.uniform(2, 14, len(day)) * (1 - 0.6 * np.minimum(hdd / 12, 1)), 2), 0.0)
    ctx.w.write("meter_daily_readings", pd.DataFrame({
        "date": sim.dates(day), "meter_id": live.meter_id.values[idx], "import_kwh": np.round(kwh, 2),
        "export_kwh": export,
    }), year)
