"""Retail: stores, daily store sales, POS receipts with lines, and loyalty members.

Store daily sales add up exactly to the company's daily consumer sales (the Z reports in
the ledger). Receipts are kept for a panel of stores, sized by the detail budget, and add
up exactly to those stores' daily sales.
"""

import numpy as np
import pandas as pd

from .. import reference as ref
from ..masters import person_names
from . import split_exact, weighted_choice

STORE_REVENUE_USD = {True: 4e6, False: 12e6}     # real 2026 USD per store per year
BASKET_USD = {True: 22.0, False: 38.0}           # average receipt, 2026 USD
LINES_PER_RECEIPT = 4.2
LINE_BUDGET = 1200e6                             # receipt lines at detail = 1
FORMATS = [("hypermarket", 0.10, 3.0, 9000), ("supermarket", 0.60, 1.0, 1800), ("express", 0.30, 0.4, 350)]
FORMAT_TR = {"hypermarket": "Hipermarket", "supermarket": "Süpermarket", "express": "Ekspres"}
HOURS = np.array([0, 0, 0, 0, 0, 0, 0, 0.2, 0.5, 0.7, 0.8, 0.9, 1.0, 0.9, 0.8, 0.8, 0.9, 1.1, 1.2, 1.1, 0.9, 0.6,
                  0.3, 0.05])


def generate(ctx):
    sim, rng, cal = ctx.sim, ctx.rng, ctx.sim.cal
    tr = sim.tr
    n_m = cal.n_months
    brand = sim.c.name.split()[0]
    stores = _stores(ctx, brand)
    online_launch = next((cal.month_index(e.month) for e in sim.c.events if "nline" in e.label), None)
    if online_launch is not None:
        stores = pd.concat([pd.DataFrame([{
            "store_id": 0, "store_code": f"{brand[:3].upper()}-WEB", "name": f"{brand} Online",
            "format": "online", "city": sim.c.city, "sqm": 0, "open_month": online_launch, "close_month": 10 ** 6,
            "weight": 0.0}]), stores], ignore_index=True)

    b2c = sim.b2c.set_index("day")
    basket_local = BASKET_USD[tr] * sim.fx_end * sim.P
    # Panel of stores with receipt-level detail, sized to the line budget.
    phys_days = b2c.index.values[b2c.index.values >= ctx.first_day]
    phys_gross = (b2c.gross - b2c.online).loc[phys_days].values
    expected_lines = (phys_gross / basket_local[sim.dm[phys_days]]).sum() * LINES_PER_RECEIPT
    share = min(1.0, LINE_BUDGET * ctx.detail / max(expected_lines, 1))
    # Pick stores in random order until their expected receipt lines reach the budget.
    out_months = np.maximum(0, np.minimum(stores.close_month.values, n_m) - np.maximum(stores.open_month.values,
                                                                                         cal.month_index(cal.output_start.strftime("%Y-%m"))))
    phys = stores.store_id.values > 0
    load = np.where(phys, stores.weight.values * out_months, 0.0)
    expected = expected_lines * load / max(load.sum(), 1e-9)
    chosen = np.zeros(len(stores), dtype=bool)
    total = 0.0
    for i in rng.permutation(np.where(phys & (load > 0))[0]):
        if total >= share * expected_lines:
            break
        if total + expected[i] > 1.5 * share * expected_lines and chosen.any():
            continue
        chosen[i] = True
        total += expected[i]
    if not chosen.any():
        chosen[np.where(phys)[0][np.argmin(np.where(load[phys] > 0, load[phys], np.inf))]] = True
    stores["has_receipt_detail"] = chosen
    stores.loc[stores.store_id == 0, "has_receipt_detail"] = share > 0.05

    members = _members(ctx, stores, b2c, basket_local, share)
    ctx.w.write("loyalty_members", members.drop(columns=["join_day"]))
    member_days = members.join_day.values

    prod = sim.products
    price_end = prod.list_price_usd_2026.values * sim.fx_end
    receipt_id = 0
    cash_share = np.where(b2c.gross.values > 0, b2c.cash.values / np.maximum(b2c.gross.values, 0.01), 0)
    for year in ctx.years:
        days = ctx.year_days(year)
        if len(days) == 0:
            continue
        months = sim.dm[days]
        rows = []
        for store in stores.itertuples():
            open_mask = (months >= store.open_month) & (months < store.close_month)
            if open_mask.any():
                rows.append((store.store_id, days[open_mask]))
        # Allocate each day's sales to open stores in proportion to their weight.
        sid = np.concatenate([np.full(len(d), s) for s, d in rows])
        sday = np.concatenate([d for _, d in rows])
        weight_of = stores.set_index("store_id").weight
        open_m = stores.set_index("store_id").open_month
        ramp = np.clip((sim.dm[sday] - open_m.loc[sid].values + 1) / 12, 0.3, 1.0)
        w = weight_of.loc[sid].values * ramp * rng.lognormal(0, 0.08, len(sid))
        online = sid == 0
        day_pos = sday - days[0]
        target = np.where(online, b2c.online.loc[sday].values, 0.0)
        phys = ~online
        wsum = np.bincount(day_pos[phys], weights=w[phys], minlength=len(days))
        phys_total = (b2c.gross - b2c.online).loc[days].values
        target[phys] = np.round(phys_total[day_pos[phys]] * w[phys] / wsum[day_pos[phys]], 2)
        # Put rounding differences on the largest store of the day.
        diff = np.round(phys_total - np.bincount(day_pos[phys], weights=target[phys], minlength=len(days)), 2)
        order = np.lexsort((-w * phys, day_pos))
        first = order[np.searchsorted(day_pos[order], np.arange(len(days)))]
        target[first] += diff
        net_ratio = (b2c.net / b2c.gross.replace(0, np.nan)).fillna(1).loc[sday].values
        cs = np.where(online, 0.0, cash_share[sday])
        n_rec = np.maximum(1, np.round(target / basket_local[sim.dm[sday]])).astype(int)
        daily = pd.DataFrame({
            "date": sim.dates(sday), "store_id": sid, "gross": np.round(target, 2),
            "net": np.round(target * net_ratio, 2), "cash": np.round(target * cs, 2),
            "card": np.round(target - np.round(target * cs, 2), 2), "receipts": n_rec,
        })
        daily["vat"] = np.round(daily.gross - daily.net, 2)
        daily["avg_basket"] = np.round(daily.gross / daily.receipts, 2)
        ctx.w.write("store_daily_sales", daily.sort_values(["date", "store_id"]), year)

        # Receipts and lines for panel stores.
        panel = stores.set_index("store_id").has_receipt_detail.loc[sid].values & (target > 0)
        for s in np.unique(sid[panel]):
            sel = panel & (sid == s)
            d, tot, n = sday[sel], target[sel], n_rec[sel]
            rec_target = split_exact(rng, tot, n, 0.75)
            rday = np.repeat(d, n)
            k = len(rec_target)
            ids = receipt_id + np.arange(1, k + 1)
            receipt_id += k
            n_lines = np.minimum(1 + rng.poisson(LINES_PER_RECEIPT - 1, k), 40)
            owner = np.repeat(np.arange(k), n_lines)
            line_target = split_exact(rng, rec_target, n_lines, 0.9)
            lm = sim.dm[rday[owner]]
            pid = np.empty(len(owner), dtype=np.int64)
            for m in np.unique(lm):
                mm = np.where(lm == m)[0]
                act = np.where((prod.launch_month.values <= m) & (prod.discontinue_month.values > m))[0]
                price_m = price_end[act] * sim.P_price[m]
                typical = basket_local[m] / LINES_PER_RECEIPT
                w = prod.popularity.values[act] * np.minimum(1, typical / price_m) ** 0.8
                pid[mm] = act[weighted_choice(rng, w, len(mm))]
            list_price = price_end[pid] * sim.P_price[lm]
            qty = np.maximum(1, np.round(line_target / list_price)).astype(np.int32)
            # One price per product per store-day: list price times the store-day price level.
            raw = qty * list_price
            day_of_line = np.searchsorted(d, rday[owner])
            level = tot / np.maximum(np.bincount(day_of_line, weights=raw, minlength=len(d)), 0.01)
            unit_price = np.round(list_price * level[day_of_line], 2)
            amount = np.round(qty * unit_price, 2)
            residual = np.round(tot - np.bincount(day_of_line, weights=amount, minlength=len(d)), 2)
            biggest = np.lexsort((-amount, day_of_line))
            first = biggest[np.searchsorted(day_of_line[biggest], np.arange(len(d)))]
            discount = np.zeros(len(amount))
            discount[first] = -residual
            amount[first] = np.round(amount[first] + residual, 2)
            gross = np.round(np.bincount(owner, weights=amount, minlength=k), 2)
            hour = weighted_choice(rng, HOURS, k)
            secs = hour * 3600 + rng.integers(0, 3600, k)
            is_online = s == 0
            pay = np.where(is_online, "online", np.where(rng.random(k) < cash_share[rday], "cash", "card"))
            joined = np.searchsorted(member_days, rday, side="right")
            use = (rng.random(k) < 0.35) & (joined > 0)
            member = np.where(use, (rng.random(k) ** 1.6 * np.maximum(joined, 1)).astype(np.int64) + 1, -1)
            vat = np.round(gross * np.repeat(1 - net_ratio[sel], n), 2)
            receipts = pd.DataFrame({
                "receipt_id": ids, "store_id": s, "date": sim.dates(rday),
                "receipt_time": sim.dates(rday).astype("datetime64[s]") + secs.astype("timedelta64[s]"),
                "till_no": rng.integers(1, 3 if is_online else 13, k), "payment_method": pay,
                "loyalty_member_id": pd.array(np.where(member > 0, member, np.nan), dtype="Int64"),
                "items": n_lines, "gross": gross, "vat": vat,
            })
            lines = pd.DataFrame({
                "receipt_id": ids[owner], "line_no": (np.arange(len(owner)) - np.repeat(np.cumsum(n_lines) - n_lines,
                                                                                         n_lines) + 1).astype(np.int16),
                "product_id": prod.product_id.values[pid], "quantity": qty, "unit_price": unit_price,
                "discount": np.round(discount, 2), "amount": amount,
            })
            ctx.w.write("pos_receipts", receipts, year)
            ctx.w.write("pos_receipt_lines", lines, year)
        ctx.w.close_year(year)

    out = stores.drop(columns=["weight"]).copy()
    out["open_date"] = _month_start(sim, out.open_month.values)
    out["close_date"] = np.where(out.close_month < n_m, _month_start(sim, np.minimum(out.close_month.values, n_m - 1)),
                                 np.datetime64("NaT"))
    ctx.w.write("stores", out.drop(columns=["open_month", "close_month"]))


def _month_start(sim, months):
    base = sim.cal.months[0]
    return pd.PeriodIndex([base + int(m) for m in months], freq="M").to_timestamp().values.astype("datetime64[D]")


def _stores(ctx, brand):
    """Store network that grows with the business; a few stores close every year."""
    sim, rng, cal = ctx.sim, ctx.rng, ctx.sim.cal
    annual_real = pd.Series(sim.act_real * 12).rolling(12, min_periods=1).mean().values
    target = np.maximum(1, np.round(annual_real / STORE_REVENUE_USD[sim.tr])).astype(int)
    cities = ref.CITIES[sim.c.country]
    fmt_names = [f[0] for f in FORMATS]
    fmt_p = np.array([f[1] for f in FORMATS])
    rows, open_ids = [], []
    for m in range(cal.n_months):
        if open_ids:
            closing = [i for i in open_ids if rng.random() < 0.0008]
            for i in closing:
                rows[i][7] = m
            open_ids = [i for i in open_ids if i not in closing]
        while len(open_ids) < target[m]:
            f = int(weighted_choice(rng, fmt_p, 1)[0])
            sid = len(rows) + 1
            city = cities[min(int(rng.pareto(1.0)), len(cities) - 1)]
            sqm = int(FORMATS[f][3] * rng.uniform(0.6, 1.4))
            label = FORMAT_TR[fmt_names[f]] if sim.tr else fmt_names[f].title()
            open_m = m if m > 0 else -int(rng.integers(0, 120))
            rows.append([sid, f"{brand[:3].upper()}-{sid:04d}", f"{brand} {label} {city} {sid}", fmt_names[f], city, sqm,
                         open_m, 10 ** 6, FORMATS[f][2] * rng.lognormal(0, 0.3)])
            open_ids.append(len(rows) - 1)
    return pd.DataFrame(rows, columns=["store_id", "store_code", "name", "format", "city", "sqm", "open_month",
                                       "close_month", "weight"])


def _members(ctx, stores, b2c, basket_local, share):
    """Loyalty members who appear on panel receipts; joins follow receipt volume."""
    sim, rng = ctx.sim, ctx.rng
    launch = 2003 if not sim.tr else 2008
    days = b2c.index.values
    eligible = days[(sim.ext_year[days] >= launch) & (days >= ctx.first_day)]
    if len(eligible) == 0:
        return pd.DataFrame(columns=["member_id", "join_date", "home_store_id", "gender", "birth_year", "city", "join_day"])
    receipts = (b2c.gross.loc[eligible].values / basket_local[sim.dm[eligible]]) * share
    n = max(100, int(receipts.sum() * 0.35 / 150))
    join_day = np.sort(eligible[weighted_choice(rng, receipts + 1e-9, n)])
    first, last, gender = person_names(rng, sim.c.country, n)
    panel = stores[stores.has_receipt_detail & (stores.store_id > 0)]
    home = rng.choice(panel.store_id.values if len(panel) else stores.store_id.values, n)
    return pd.DataFrame({
        "member_id": np.arange(1, n + 1), "join_date": sim.dates(join_day), "home_store_id": home, "gender": gender,
        "birth_year": rng.integers(1940, 2006, n), "city": stores.set_index("store_id").city.loc[home].values,
        "join_day": join_day,
    })
