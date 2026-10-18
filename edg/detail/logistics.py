"""Logistics: depots, trucks (from the asset register), shipments, daily telemetry, GPS pings.

Every invoice line is a shipment, so shipment revenue adds up exactly to the invoice in
the ledger. Trucks are the vehicle assets; drivers are employees of the fleet department.
GPS pings are kept for the most recent years, sized by the detail budget.
"""

import numpy as np
import pandas as pd

from .. import reference as ref
from . import weighted_choice

GPS_ROW_BUDGET = 150e6
LANES = {  # extra international destinations
    True: ["Mersin Port", "Kapıkule", "München", "Köln", "Milano", "Wien", "Budapest", "Bucureşti"],
    False: ["Antwerpen", "Hamburg", "Duisburg", "Lyon", "Milano", "Wien", "Warszawa", "Praha", "Barcelona"],
}


def generate(ctx):
    sim, rng, cal = ctx.sim, ctx.rng, ctx.sim.cal
    cities = ref.CITIES[sim.c.country] + LANES[sim.tr]
    n_dom = len(ref.CITIES[sim.c.country])
    coords = {c: (rng.uniform(-400, 400), rng.uniform(-300, 300)) for c in cities[:n_dom]}
    coords.update({c: (rng.uniform(800, 2200) * rng.choice([-1, 1]), rng.uniform(-600, 600)) for c in cities[n_dom:]})
    depots = pd.DataFrame({"depot_id": np.arange(1, n_dom + 1), "city": cities[:n_dom],
                           "type": np.where(np.arange(n_dom) < 2, "hub", "cross-dock")})
    ctx.w.write("depots", depots)
    trucks = _trucks(ctx)
    ctx.w.write("trucks", trucks.drop(columns=["acq_month", "out_month"]))
    emp = sim.employees
    drivers = emp[emp.department == "Drivers & fleet"]
    inv, lines, prod = sim.invoices, sim.lines, sim.products
    if len(lines) == 0:
        return
    line_day = inv.day.values[lines.inv.values]
    shipment_id = 0
    km_by_truck_day = pd.DataFrame({"truck_id": pd.Series(dtype=np.int64), "day": pd.Series(dtype=np.int64),
                                    "km": pd.Series(dtype=float)})
    for year in ctx.years:
        days = ctx.year_days(year)
        if len(days) == 0:
            continue
        sel = np.where((line_day >= days[0]) & (line_day <= days[-1]))[0]
        if len(sel):
            n = len(sel)
            invoice_day = line_day[sel]
            origin = np.array(cities, dtype=object)[weighted_choice(rng, np.r_[np.full(2, 6.0), np.ones(n_dom - 2),
                                                                              np.zeros(len(cities) - n_dom)], n)]
            intl = rng.random(n) < (0.25 if year >= 2010 or not sim.tr else 0.08)
            dest_dom = np.array(cities[:n_dom], dtype=object)[rng.integers(0, n_dom, n)]
            dest_int = np.array(cities[n_dom:], dtype=object)[rng.integers(0, len(cities) - n_dom, n)]
            dest = np.where(intl, dest_int, dest_dom)
            dest = np.where(dest == origin, np.array(cities[:n_dom], dtype=object)[(rng.integers(1, n_dom, n))], dest)
            ox = np.array([coords[c][0] for c in origin]); oy = np.array([coords[c][1] for c in origin])
            dx = np.array([coords[c][0] for c in dest]); dy = np.array([coords[c][1] for c in dest])
            km = np.round(np.hypot(ox - dx, oy - dy) * 1.25 + rng.uniform(20, 60, n))
            pickup = invoice_day - rng.integers(1, 6, n)
            transit = np.ceil(km / 650).astype(int)
            planned = pickup + transit
            late = rng.random(n) < 0.08 * sim._stress(pickup)
            actual = planned + np.where(late, rng.integers(1, 4, n), 0)
            m = sim.dm[np.clip(pickup, 0, sim.last_day)]
            truck = np.full(n, -1, dtype=np.int64)
            for mm in np.unique(m):
                lt = trucks.truck_id.values[(trucks.acq_month.values <= mm) & (trucks.out_month.values > mm)]
                sm = m == mm
                if len(lt):
                    truck[sm] = lt[rng.integers(0, len(lt), sm.sum())]
            ok_drv = drivers[(drivers.hire_month <= m.max())]
            driver = ok_drv.employee_id.values[rng.integers(0, len(ok_drv), n)] if len(ok_drv) else np.full(n, -1)
            category = prod.category.values[lines.product_idx.values[sel]]
            qty = lines.qty.values[sel]
            weight = np.round(np.clip(qty * rng.lognormal(np.log(400), 0.8, n), 5, 24000))
            ids = shipment_id + np.arange(1, n + 1)
            shipment_id += n
            ship = pd.DataFrame({
                "shipment_id": ids, "invoice_number": inv.number.values[lines.inv.values[sel]],
                "customer_code": sim.customers.code.values[inv.cust.values[lines.inv.values[sel]]],
                "service": category, "origin": origin, "destination": dest, "international": intl,
                "distance_km": km.astype(int), "weight_kg": weight, "pallets": np.maximum(1, np.round(weight / 450)).astype(int),
                "pickup_date": sim.dates(pickup), "planned_delivery": sim.dates(planned),
                "actual_delivery": sim.dates(actual), "on_time": ~late, "truck_id": truck, "driver_employee_id": driver,
                "revenue": lines.net.values[sel],
            })
            ctx.w.write("shipments", ship, year)
            moved = pd.DataFrame({"truck_id": truck, "day": pickup, "km": km})
            km_by_truck_day = pd.concat([km_by_truck_day, moved[moved.truck_id > 0]]).groupby(
                ["truck_id", "day"], as_index=False).km.sum()
        _telemetry(ctx, trucks, days, year, km_by_truck_day)
        ctx.w.close_year(year)
        km_by_truck_day = km_by_truck_day[km_by_truck_day.day > days[-1]]


def _trucks(ctx):
    sim, rng = ctx.sim, ctx.rng
    fa = sim.assets[sim.assets.asset_class == "vehicle"]
    n = len(fa)
    plate_city = "33" if sim.tr else ""
    letters = np.array(list("ABCDEFGHJKLMNPRSTUVYZ"))
    if sim.tr:
        plates = [f"{plate_city} {''.join(rng.choice(letters, 2))} {int(rng.integers(100, 9999))}" for _ in range(n)]
    else:
        plates = [f"{''.join(rng.choice(letters, 2))}-{int(rng.integers(10, 99))}-{''.join(rng.choice(letters, 3))}"
                  for _ in range(n)]
    acq_year = sim.cal.start.year + (sim.cal.start.month - 1 + fa.acq_month.values) // 12
    makes = np.array(["Volvo FH", "Mercedes-Benz Actros", "Scania R", "DAF XF", "MAN TGX", "Renault T", "Iveco S-Way"],
                     dtype=object)
    return pd.DataFrame({
        "truck_id": np.arange(1, n + 1), "plate": plates, "asset_tag": fa.asset_tag.values,
        "model": makes[rng.integers(0, len(makes), n)],
        "euro_norm": np.select([acq_year < 2001, acq_year < 2006, acq_year < 2009, acq_year < 2014],
                               ["Euro 2", "Euro 3", "Euro 4", "Euro 5"], "Euro 6"),
        "acq_month": fa.acq_month.values, "out_month": fa.dispose_month.values,
        "in_service": sim.dates(sim.month_first_day[np.clip(fa.acq_month.values, 0, sim.cal.n_months - 1)]),
    })


def _telemetry(ctx, trucks, days, year, km_by_truck_day):
    """Daily telemetry for every truck in service, plus GPS pings for the last years."""
    sim, rng = ctx.sim, ctx.rng
    m = sim.dm[days]
    live = (trucks.acq_month.values[None, :] <= m[:, None]) & (trucks.out_month.values[None, :] > m[:, None])
    di, ti = np.nonzero(live)
    if len(di) == 0:
        return
    day = days[di]
    tid = trucks.truck_id.values[ti]
    k = len(day)
    dow = sim.cal.days.dayofweek.values[day]
    base_km = km_by_truck_day.set_index(["truck_id", "day"]).km.reindex(
        pd.MultiIndex.from_arrays([tid, day])).fillna(0).values
    working = (dow < 6) & (rng.random(k) < 0.88)
    km = np.where(working, np.maximum(base_km, rng.gamma(4, 110, k)), base_km * 0.3)
    km = np.round(np.minimum(km, 1100))
    hours = np.round(km / rng.uniform(55, 72, k) + rng.uniform(0.2, 1.0, k) * (km > 0), 2)
    fuel = np.round(km * rng.uniform(0.28, 0.36, k) * np.where(sim.ext_year[day] >= 2014, 0.92, 1.0), 1)
    df = pd.DataFrame({"date": sim.dates(day), "truck_id": tid, "km": km, "engine_hours": hours, "fuel_litres": fuel,
                       "idle_minutes": np.round(rng.gamma(2, 18, k) * (km > 0)).astype(int),
                       "avg_speed_kmh": np.round(np.where(hours > 0, km / np.maximum(hours, 0.1), 0), 1),
                       "harsh_braking_events": rng.poisson(0.6, k) * (km > 0)})
    ctx.w.write("truck_daily_telemetry", df, year)
    # GPS pings every 15 minutes of driving, for the most recent years within the budget.
    rows_per_year = (km > 0).sum() * 9 * 4
    years_kept = max(1, int(GPS_ROW_BUDGET * ctx.detail / max(rows_per_year, 1)))
    if year <= sim.cal.end.year - years_kept or year < 2008:  # fleet telematics became common around 2008
        return
    drive = np.where(km > 0)[0]
    pings = np.minimum(np.maximum(1, (hours[drive] * 4).astype(int)), 60)
    owner = np.repeat(drive, pings)
    step = np.arange(len(owner)) - np.repeat(np.cumsum(pings) - pings, pings)
    start_h = rng.uniform(5, 9, len(drive))
    t = sim.dates(day[owner]).astype("datetime64[s]") + ((np.repeat(start_h, pings) * 3600) + step * 900).astype("timedelta64[s]")
    lat0 = rng.uniform(36.5, 41.5, len(drive)) if sim.tr else rng.uniform(48.5, 53.0, len(drive))
    lon0 = rng.uniform(27, 40, len(drive)) if sim.tr else rng.uniform(3, 12, len(drive))
    heading = rng.uniform(0, 2 * np.pi, len(drive))
    dist = step * 0.25 * df.avg_speed_kmh.values[owner] / 111
    ctx.w.write("truck_gps_pings", pd.DataFrame({
        "truck_id": tid[owner], "timestamp": t,
        "lat": np.round(np.repeat(lat0, pings) + np.sin(np.repeat(heading, pings)) * dist, 5),
        "lon": np.round(np.repeat(lon0, pings) + np.cos(np.repeat(heading, pings)) * dist, 5),
        "speed_kmh": np.round(np.clip(df.avg_speed_kmh.values[owner] * rng.lognormal(0, 0.2, len(owner)), 0, 95), 1),
    }), year)
