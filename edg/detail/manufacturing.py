"""Manufacturing family: production, stock, machines with sensors and maintenance.

Used by manufacturing, textiles, food, pharma, automotive and defense companies.

- Production orders make what is sold: monthly produced quantities keep each product's
  stock near its target, and the monthly stock table reconciles opening + produced - sold
  = closing, with sold quantities taken from the invoice lines.
- Machines are the machinery assets in the fixed-asset register. Daily metrics carry a
  degradation signal before each failure (days_to_failure, useful for predictive
  maintenance demos), and every failure has a corrective work order.
- Food and pharma add production lots (expiry, quality result); automotive adds vehicles
  with valid VINs and warranty claims; defense adds programmes with earned value.
"""

import numpy as np
import pandas as pd

from . import split_exact, weighted_choice

SENSOR_ROW_BUDGET = 80e6
MACHINE_TYPES = {
    "manufacturing": ["CNC lathe", "CNC machining centre", "Hydraulic press", "Grinding machine", "Assembly cell",
                      "Heat treatment furnace"],
    "textiles": ["Air-jet loom", "Circular knitting machine", "Dyeing machine", "Stenter", "Cutting table", "Sewing line"],
    "food": ["Filling line", "Pasteuriser", "Mixer", "Extruder", "Packaging line", "Spiral freezer"],
    "pharma": ["Tablet press", "Granulator", "Coating pan", "Blister line", "Bioreactor", "Vial filling line"],
    "automotive": ["Press line", "Body-in-white robot cell", "Paint robot", "Engine assembly station", "Final assembly line",
                   "Test bench"],
    "defense": ["5-axis machining centre", "Composite autoclave", "Clean-room assembly", "Environmental test chamber",
                "Electronics SMT line", "Radar test range"],
}
CONTINUOUS = {"food", "pharma"}          # three-shift, seven-day operations
BATCH = {"manufacturing": 400, "textiles": 3000, "food": 20000, "pharma": 50000, "automotive": 60, "defense": 2}
SHELF_LIFE_MONTHS = {"food": (6, 18), "pharma": (24, 36)}


def generate(ctx):
    sim, rng = ctx.sim, ctx.rng
    ind = sim.c.industry
    machines = _machines(ctx)
    ctx.w.write("machines", machines.drop(columns=["acq_month", "out_month", "fail_days"]))
    sold = _sold_by_product_month(sim)
    produced = _production_plan(ctx, sold)
    _production_orders(ctx, produced, machines)
    _machine_metrics(ctx, machines, produced)
    if ind == "automotive":
        _vehicles(ctx)
    if ind == "defense":
        _programmes(ctx)


# ---------------------------------------------------------------------------- production

def _sold_by_product_month(sim):
    lines, inv = sim.lines, sim.invoices
    n_m, n_p = sim.cal.n_months, len(sim.products)
    sold = np.zeros((n_m, n_p))
    if len(lines):
        m = sim.dm[inv.day.values[lines.inv.values]]
        np.add.at(sold, (m, lines.product_idx.values), lines.qty.values)
    return sold


def _production_plan(ctx, sold):
    """Monthly production per product that keeps stock near 1.5 months of sales."""
    sim = ctx.sim
    n_m, n_p = sold.shape
    smooth = pd.DataFrame(sold).rolling(3, min_periods=1).mean().values
    target = np.round(smooth * 1.5)
    stock = np.round(sold[:3].mean(axis=0) * 1.5)
    produced = np.zeros_like(sold)
    rows = []
    first_m = sim.cal.month_index(sim.cal.output_start.strftime("%Y-%m"))
    for m in range(n_m):
        produced[m] = np.maximum(0, np.round(target[m] + sold[m] - stock))  # order up to target
        opening = stock.copy()
        stock = opening + produced[m] - sold[m]
        if m >= first_m:
            act = (opening != 0) | (produced[m] != 0) | (sold[m] != 0)
            idx = np.where(act)[0]
            rows.append(pd.DataFrame({"period": str(sim.cal.months[m]), "product_id": sim.products.product_id.values[idx],
                                      "opening_qty": opening[idx], "produced_qty": produced[m][idx],
                                      "sold_qty": sold[m][idx], "closing_qty": stock[idx]}))
    stock_df = pd.concat(rows, ignore_index=True)
    for y, part in stock_df.groupby(stock_df.period.str[:4].astype(int)):
        ctx.w.write("stock_monthly", part, int(y))
    ctx.w.close()
    return produced


def _production_orders(ctx, produced, machines):
    sim, rng = ctx.sim, ctx.rng
    ind = sim.c.industry
    batch = BATCH[ind]
    first_m = sim.cal.month_index(sim.cal.output_start.strftime("%Y-%m"))
    prefix = "URT" if sim.tr else "PO"
    order_no = 0
    lot_no = 0
    for m in range(first_m, sim.cal.n_months):
        mi, pi = np.nonzero(produced[m:m + 1])
        if len(pi) == 0:
            continue
        qty = produced[m, pi]
        k = np.minimum(np.maximum(1, np.ceil(qty / batch)), 25).astype(int)
        good = split_exact(rng, qty.astype(float), k, 0.25)
        good = np.round(good)
        owner = np.repeat(np.arange(len(pi)), k)
        # Rounding to whole units: fix each product's last order so the total matches exactly.
        diff = qty - np.bincount(owner, weights=good, minlength=len(pi))
        good[np.cumsum(k) - 1] += diff
        n = len(owner)
        scrap = np.round(good * rng.beta(1.5, 60, n))
        d0, d1 = sim.month_first_day[m], sim.month_last_day[m]
        start = rng.integers(d0, d1 + 1, n)
        hours = np.round(np.maximum(1, good / batch * rng.uniform(6, 30, n)), 1)
        live = machines[(machines.acq_month <= m) & (machines.out_month > m)]
        mach = live.machine_id.values[rng.integers(0, len(live), n)] if len(live) else np.full(n, -1)
        year = int(sim.cal.months[m].year)
        ids = order_no + np.arange(1, n + 1)
        order_no += n
        df = pd.DataFrame({
            "order_number": [f"{prefix}-{year}-{x:07d}" for x in ids],
            "product_id": sim.products.product_id.values[pi[owner]], "machine_id": mach,
            "start_time": sim.dates(start).astype("datetime64[s]") + (rng.integers(6, 22, n) * 3600).astype("timedelta64[s]"),
            "run_hours": hours, "planned_qty": good + scrap, "good_qty": good, "scrap_qty": scrap,
        })
        df["end_time"] = df.start_time + (df.run_hours * 3600).astype("int64").values.astype("timedelta64[s]")
        if ind in SHELF_LIFE_MONTHS:
            lo, hi = SHELF_LIFE_MONTHS[ind]
            df["lot_number"] = [f"L{year % 100:02d}{m % 12 + 1:02d}{x:06d}" for x in lot_no + np.arange(1, n + 1)]
            lot_no += n
            df["expiry_date"] = (sim.dates(start) + (rng.integers(lo, hi + 1, n) * 30).astype("timedelta64[D]"))
            df["qc_result"] = np.array(["released", "released after rework", "rejected"], dtype=object)[
                weighted_choice(rng, np.array([0.965, 0.025, 0.01]), n)]
        ctx.w.write("production_orders", df, year)
        if sim.cal.months[m].month == 12:
            ctx.w.close_year(year)


# ---------------------------------------------------------------------------- machines

def _machines(ctx):
    sim, rng = ctx.sim, ctx.rng
    fa = sim.assets[sim.assets.asset_class == "machinery"]
    n = len(fa)
    types = MACHINE_TYPES[sim.c.industry]
    start_day = sim.month_first_day[np.clip(fa.acq_month.values, 0, sim.cal.n_months - 1)]
    end_day = np.where(fa.dispose_month.values < sim.cal.n_months,
                       sim.month_last_day[np.clip(fa.dispose_month.values, 0, sim.cal.n_months - 1)], sim.last_day + 1)
    # Failure days over each machine's life; failures get more frequent with age.
    fail_days = []
    for a, b in zip(start_day, end_day):
        days, d, age = [], a, 0
        while True:
            gap = rng.exponential(max(60, 420 - age * 0.04))
            d = int(d + gap)
            if d >= b:
                break
            days.append(d)
            age = d - a
        fail_days.append(np.array(days, dtype=np.int64))
    return pd.DataFrame({
        "machine_id": np.arange(1, n + 1), "asset_tag": fa.asset_tag.values,
        "machine_type": np.array(types, dtype=object)[rng.integers(0, len(types), n)],
        "line": [f"L{int(x):02d}" for x in rng.integers(1, max(2, n // 6 + 2), n)],
        "rated_output_per_hour": np.round(rng.lognormal(np.log(BATCH[sim.c.industry] / 8 + 1), 0.4, n), 1),
        "installed": sim.dates(start_day), "acq_month": fa.acq_month.values, "out_month": fa.dispose_month.values,
        "fail_days": fail_days,
    })


def _machine_metrics(ctx, machines, produced):
    sim, rng = ctx.sim, ctx.rng
    ind = sim.c.industry
    if len(machines) == 0:
        return
    util_m = produced.sum(axis=1)
    util_m = np.clip(util_m / max(np.percentile(util_m[util_m > 0], 90), 1) if (util_m > 0).any() else util_m, 0.15, 1.0)
    cont = ind in CONTINUOUS
    wo_id = 0
    total_alive_days = sum(max(0, min(r.out_month, sim.cal.n_months) - max(r.acq_month, 0)) * 30 for r in machines.itertuples())
    hours_per_year = total_alive_days / max(len(ctx.years), 1) * 16
    years_hourly = max(1, int(SENSOR_ROW_BUDGET * ctx.detail / max(hours_per_year, 1)))
    for year in ctx.years:
        days = ctx.year_days(year)
        if len(days) == 0:
            continue
        m = sim.dm[days]
        live = (machines.acq_month.values[None, :] <= m[:, None]) & (machines.out_month.values[None, :] > m[:, None])
        di, ci = np.nonzero(live)
        if len(di) == 0:
            continue
        day = days[di]
        k = len(day)
        dow = sim.cal.days.dayofweek.values[day]
        planned = np.where(cont, 24.0, np.where(dow < 5, 16.0, np.where(dow == 5, 8.0, 0.0)))
        # Days until the next failure of each machine (degradation signal before failures).
        ttf = np.full(k, 9999, dtype=np.int64)
        failed_today = np.zeros(k, dtype=bool)
        for c in np.unique(ci):
            sel = np.where(ci == c)[0]
            fd = machines.fail_days.values[c]
            if len(fd) == 0:
                continue
            j = np.searchsorted(fd, day[sel])
            nxt = np.where(j < len(fd), fd[np.minimum(j, len(fd) - 1)], 10 ** 9)
            ttf[sel] = np.minimum(nxt - day[sel], 9999)
            failed_today[sel] = ttf[sel] == 0
        down = np.where(failed_today, np.round(rng.uniform(2, 24, k), 1), 0.0)
        u = util_m[m[di]]
        run = np.round(np.clip(planned * u * rng.uniform(0.85, 1.0, k) - down, 0, None), 2)
        availability = np.where(planned > 0, run / np.maximum(planned, 1e-9), 0)
        performance = np.clip(rng.normal(0.9, 0.05, k) - 0.15 * np.exp(-ttf / 12), 0.3, 1.0)
        quality = np.clip(rng.normal(0.975, 0.01, k) - 0.05 * np.exp(-ttf / 8), 0.7, 1.0)
        rated = machines.rated_output_per_hour.values[ci]
        output = np.round(run * rated * performance)
        vib = np.round(rng.lognormal(np.log(2.2), 0.12, k) + 9 * np.exp(-ttf / 10), 3)
        temp = np.round(rng.normal(55, 3, k) + 18 * np.exp(-ttf / 7) + (run > 0) * 8, 2)
        df = pd.DataFrame({
            "date": sim.dates(day), "machine_id": machines.machine_id.values[ci], "planned_hours": planned,
            "run_hours": run, "downtime_hours": down, "output_units": output,
            "oee": np.round(availability * performance * quality, 4), "energy_kwh": np.round(run * rng.uniform(15, 60, k), 1),
            "avg_temperature_c": temp, "vibration_rms_mm_s": vib, "failure": failed_today,
            "days_to_failure": np.where(ttf >= 9999, np.nan, ttf),
        })
        ctx.w.write("machine_daily_metrics", df, year)
        # Work orders: corrective for each failure, preventive every quarter per machine.
        fi = np.where(failed_today)[0]
        pm = np.where((sim.ext_month[day] % 3 == 1) & (sim.cal.days.day.values[day] == 5))[0]
        idx = np.r_[fi, pm]
        if len(idx):
            kind = np.r_[np.full(len(fi), "corrective"), np.full(len(pm), "preventive")]
            cost_base = 900 * sim.fx_end * sim.P[m[di[idx]]]  # 900 USD (2026) in local money of the day
            ids = wo_id + np.arange(1, len(idx) + 1)
            wo_id += len(idx)
            ctx.w.write("maintenance_work_orders", pd.DataFrame({
                "work_order": [f"{'IE' if sim.tr else 'WO'}-{year}-{x:06d}" for x in ids],
                "machine_id": machines.machine_id.values[ci[idx]], "type": kind, "opened": sim.dates(day[idx]),
                "downtime_hours": np.where(kind == "corrective", down[idx], np.round(rng.uniform(1, 4, len(idx)), 1)),
                "cost": np.round(cost_base * np.where(kind == "corrective", rng.lognormal(1.2, 0.6, len(idx)),
                                                      rng.lognormal(0, 0.3, len(idx))), 2),
                "failure_mode": np.where(kind == "corrective", np.array(["bearing wear", "hydraulic leak", "motor overheating",
                                                                         "sensor fault", "belt/coupling failure",
                                                                         "electrical fault"], dtype=object)[
                    rng.integers(0, 6, len(idx))], None),
            }), year)
        # Hourly sensor readings for the most recent years.
        if year > sim.cal.end.year - years_hourly and year >= 2015:
            on = np.where(run > 0)[0]
            hrs = np.minimum(np.ceil(run[on]).astype(int), 24)
            owner = np.repeat(on, hrs)
            step = np.arange(len(owner)) - np.repeat(np.cumsum(hrs) - hrs, hrs)
            ts = sim.dates(day[owner]).astype("datetime64[s]") + ((6 * (~cont) + step) * 3600).astype("timedelta64[s]")
            nh = len(owner)
            ctx.w.write("machine_sensor_hourly", pd.DataFrame({
                "machine_id": machines.machine_id.values[ci[owner]], "timestamp": ts,
                "temperature_c": np.round(temp[owner] + rng.normal(0, 1.5, nh), 2),
                "vibration_rms_mm_s": np.round(vib[owner] * rng.lognormal(0, 0.08, nh), 3),
                "motor_current_a": np.round(rng.normal(42, 4, nh) + 6 * np.exp(-ttf[owner] / 10), 2),
                "output_units": np.round(output[owner] / np.maximum(hrs[np.searchsorted(on, owner)], 1)),
            }), year)
        ctx.w.close_year(year)


# ---------------------------------------------------------------------------- automotive

VIN_VALUES = {**{str(i): i for i in range(10)}, **dict(zip("ABCDEFGH", range(1, 9))),
              **dict(zip("JKLMN", range(1, 6))), "P": 7, "R": 9, **dict(zip("STUVWXYZ", range(2, 10)))}
VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
VIN_YEAR = "ABCDEFGHJKLMNPRSTVWXY123456789"   # model year codes from 1980, repeating every 30 years


def _vin(wmi, vds, year, plant, serial):
    year_code = VIN_YEAR[(year - 1980) % 30]
    body = f"{wmi}{vds}0{year_code}{plant}{serial:06d}"
    total = sum(VIN_VALUES[ch] * w for ch, w in zip(body, VIN_WEIGHTS))
    check = total % 11
    return body[:8] + ("X" if check == 10 else str(check)) + body[9:]


def _vehicles(ctx):
    """One row per vehicle sold, with a valid VIN; warranty claims for a share of them."""
    sim, rng = ctx.sim, ctx.rng
    lines, inv, prod = sim.lines, sim.invoices, sim.products
    vehicle_cats = {"Passenger cars", "Light commercial vehicles", "Trucks", "Electric vehicles", "Binek araçlar",
                    "Hafif ticari araçlar", "Kamyonlar", "Elektrikli araçlar"}
    is_vehicle = np.isin(prod.category.values[lines.product_idx.values], list(vehicle_cats))
    vl = lines[is_vehicle]
    day = inv.day.values[vl.inv.values]
    keep = day >= ctx.first_day
    vl, day = vl[keep], day[keep]
    qty = np.minimum(vl.qty.values.astype(int), 500)
    owner = np.repeat(np.arange(len(vl)), qty)
    n = len(owner)
    if n == 0:
        return
    sale_day = day[owner]
    prod_day = sale_day - rng.integers(10, 90, n)
    year = sim.ext_year[np.clip(prod_day, 0, len(sim.ext_year) - 1)]
    wmi = "NMR" if sim.tr else "WRW"
    cat = prod.category.values[vl.product_idx.values[owner]]
    model_names = {"Passenger cars": "Kartal" if sim.tr else "R5", "Binek araçlar": "Kartal",
                   "Light commercial vehicles": "Yük" if sim.tr else "Transporter", "Hafif ticari araçlar": "Yük",
                   "Trucks": "Atlas" if sim.tr else "Titan", "Kamyonlar": "Atlas",
                   "Electric vehicles": "e-Kartal" if sim.tr else "eR4", "Elektrikli araçlar": "e-Kartal"}
    model = np.array([model_names.get(c, "Kartal") for c in cat], dtype=object)
    vds = np.array(["".join(rng.choice(list("ABCDEFGHJKLMNPRSTUVWXYZ0123456789"), 5)) for _ in range(min(n, 50))])
    vds_pick = vds[rng.integers(0, len(vds), n)]
    plants = "BCDEFG" if sim.tr else "STUVWX"
    vins = [_vin(wmi, v, int(y), plants[(i // 1_000_000) % len(plants)], i % 1_000_000)
            for i, (v, y) in enumerate(zip(vds_pick, year), 1)]
    powertrain = np.where(np.char.startswith(model.astype(str), "e"), "electric",
                          np.where(year < 2015, np.where(rng.random(n) < 0.6, "diesel", "petrol"),
                                   np.array(["diesel", "petrol", "hybrid"], dtype=object)[rng.integers(0, 3, n)]))
    vehicles = pd.DataFrame({
        "vin": vins, "model": model, "category": cat, "model_year": year, "powertrain": powertrain,
        "colour": np.array(["white", "black", "grey", "silver", "blue", "red"], dtype=object)[rng.integers(0, 6, n)],
        "production_date": sim.dates(np.maximum(prod_day, 0)), "sale_date": sim.dates(sale_day),
        "dealer_code": sim.customers.code.values[inv.cust.values[vl.inv.values[owner]]],
        "invoice_number": inv.number.values[vl.inv.values[owner]],
        "net_price": np.round(vl.net.values[owner] / qty[owner], 2),
    })
    for y, part in vehicles.groupby(sim.ext_year[sale_day]):
        ctx.w.write("vehicles", part, int(y))
    # Warranty claims within three years of sale.
    wc = np.where(rng.random(n) < 0.06)[0]
    claim_day = sale_day[wc] + rng.integers(30, 1095, len(wc))
    ok = claim_day <= sim.last_day
    wc, claim_day = wc[ok], claim_day[ok]
    m = np.minimum(sim.month_of_day(claim_day), sim.cal.n_months - 1)
    ctx.w.write("warranty_claims", pd.DataFrame({
        "claim_number": [f"WC{x:09d}" for x in range(1, len(wc) + 1)], "vin": np.array(vins, dtype=object)[wc],
        "claim_date": sim.dates(claim_day), "mileage_km": (rng.gamma(2, 9000, len(wc))).astype(int),
        "component": np.array(["infotainment", "brakes", "suspension", "engine", "gearbox", "electrical", "battery", "paint"],
                              dtype=object)[rng.integers(0, 8, len(wc))],
        "cost": np.round(rng.lognormal(np.log(450), 0.8, len(wc)) * sim.fx_end * sim.P[m], 2),
    }))


# ---------------------------------------------------------------------------- defense

def _programmes(ctx):
    """Each customer contract is a programme; its milestones are the invoices. Monthly earned
    value: planned value follows an S-curve, earned value follows billing, actual cost
    follows earned value through a drifting cost-performance index."""
    sim, rng = ctx.sim, ctx.rng
    inv = sim.invoices
    rows, evm = [], []
    for cid, grp in inv.groupby("cust"):
        cust = sim.customers.iloc[cid]
        value = grp.net.sum()
        a, b = int(grp.day.min()), int(grp.day.max())
        if b - a < 60:
            b = a + 60
        name = f"{['Kalkan', 'Atmaca', 'Bora', 'Şimşek', 'Yıldırım'][cid % 5] if sim.tr else ['Sentinel', 'Talon', 'Aegis', 'Vanguard', 'Trident'][cid % 5]}-{cid + 1}"
        rows.append((cid + 1, name, cust.code, cust["name"], sim.dates(np.array([a]))[0], sim.dates(np.array([b]))[0],
                     round(value, 2)))
        m0, m1 = sim.dm[min(a, sim.last_day)], sim.dm[min(b, sim.last_day)]
        months = np.arange(m0, m1 + 1)
        x = (months - m0 + 1) / max(len(months), 1)
        pv = value * (3 * x ** 2 - 2 * x ** 3)
        billed = np.bincount(sim.dm[np.minimum(grp.day.values, sim.last_day)] - m0, weights=grp.net.values,
                             minlength=len(months))[:len(months)]
        ev = np.cumsum(billed)
        cpi = np.empty(len(months))
        level = 1.0
        for i in range(len(months)):   # cost performance wanders but reverts toward 1.0
            level = 1 + 0.92 * (level - 1) + rng.normal(0, 0.012)
            cpi[i] = level
        cpi = np.clip(cpi, 0.8, 1.15)
        ac = ev / cpi
        evm.append(pd.DataFrame({"programme_id": cid + 1, "period": sim.cal.months[months].astype(str),
                                 "planned_value": np.round(pv, 2), "earned_value": np.round(ev, 2),
                                 "actual_cost": np.round(ac, 2), "cpi": np.round(cpi, 3),
                                 "spi": np.round(np.where(pv > 0, ev / np.maximum(pv, 1e-9), 1), 3)}))
    ctx.w.write("programmes", pd.DataFrame(rows, columns=["programme_id", "name", "customer_code", "customer_name",
                                                          "start_date", "end_date", "contract_value"]))
    if evm:
        e = pd.concat(evm, ignore_index=True)
        ctx.w.write("programme_evm_monthly", e[e.period >= sim.cal.output_start.strftime("%Y-%m")])
    inv_out = inv[inv.day >= ctx.first_day]
    ctx.w.write("programme_milestones", pd.DataFrame({
        "programme_id": inv_out.cust.values + 1, "invoice_number": inv_out.number.values,
        "milestone_date": sim.dates(inv_out.day.values), "amount": inv_out.net.values}))
