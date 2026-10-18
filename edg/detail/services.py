"""Software and construction detail tables.

Software: subscriptions per customer (licence era, then SaaS after the company's cloud
launch), daily product usage per tenant, and support tickets. A customer's subscription
value equals what was invoiced to that customer.

Construction: projects per customer contract (contract value = what was billed), monthly
progress with planned and actual completion, and daily site logs with crew size, weather
delays and safety incidents.
"""

import numpy as np
import pandas as pd

from .. import reference as ref
from . import weighted_choice


def generate(ctx):
    if ctx.sim.c.industry == "software":
        _software(ctx)
    else:
        _construction(ctx)


def _software(ctx):
    sim, rng, cal = ctx.sim, ctx.rng, ctx.sim.cal
    inv = sim.invoices
    cust = sim.customers
    saas_month = next((cal.month_index(e.month) for e in sim.c.events if "SaaS" in e.label or "Cloud" in e.label), 0)
    g = inv.groupby("cust").agg(first=("day", "min"), last=("day", "max"), billed=("net", "sum"), n=("net", "size"))
    g = g[g["last"] >= ctx.first_day]
    rows = []
    for cid, r in g.iterrows():
        start_m = sim.dm[min(int(r["first"]), sim.last_day)]
        model = "saas" if start_m >= saas_month else "licence"
        end = int(r["last"]) + 30
        churned = end < sim.last_day - 60
        months = max(1, (min(end, sim.last_day) - int(r["first"])) / 30.4)
        rows.append((cid, cust.code.values[cid], model, sim.dates(np.array([int(r["first"])]))[0],
                     sim.dates(np.array([min(end, sim.last_day)]))[0] if churned else np.datetime64("NaT"),
                     int(max(5, rng.lognormal(np.log(40), 1.0))), round(r.billed / months, 2), round(r.billed, 2)))
    subs = pd.DataFrame(rows, columns=["cust", "customer_code", "model", "start_date", "end_date", "seats",
                                       "avg_monthly_value", "total_billed"])
    subs.insert(0, "subscription_id", np.arange(1, len(subs) + 1))
    plans = np.array(["Starter", "Professional", "Enterprise"], dtype=object)
    subs["plan"] = plans[np.digitize(subs.seats.values, [25, 150])]
    ctx.w.write("subscriptions", subs.drop(columns=["cust"]))
    # Daily usage per tenant from the SaaS launch, within the row budget.
    saas = subs[subs.model == "saas"]
    start = np.maximum(((saas.start_date.values.astype("datetime64[D]") - np.datetime64(cal.start.date())).astype(int)),
                       max(ctx.first_day, int(sim.month_first_day[min(saas_month, cal.n_months - 1)])))
    end = np.where(saas.end_date.isna(), sim.last_day,
                   (saas.end_date.values.astype("datetime64[D]") - np.datetime64(cal.start.date())).astype(int))
    for year in ctx.years:
        days = ctx.year_days(year)
        if len(days) == 0:
            continue
        a, b = np.maximum(start, days[0]), np.minimum(end, days[-1]) + 1
        cnt = np.maximum(b - a, 0)
        idx = np.repeat(np.arange(len(saas)), cnt)
        day = np.repeat(a, cnt) + (np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt))
        if len(day) == 0:
            continue
        dow = cal.days.dayofweek.values[day]
        seats = saas.seats.values[idx]
        active = rng.binomial(seats, np.where(dow < 5, 0.62, 0.12))
        k = len(day)
        ctx.w.write("product_usage_daily", pd.DataFrame({
            "date": sim.dates(day), "subscription_id": saas.subscription_id.values[idx], "active_users": active,
            "sessions": rng.poisson(active * 2.3), "api_calls": rng.poisson(active * 180 * (1 + (year - 2012) * 0.15)),
            "storage_gb": np.round(seats * 0.8 * (1 + (day - a[idx]) / 365) * rng.lognormal(0, 0.05, k), 2),
            "errors": rng.poisson(active * 0.02),
        }), year)
        # Support tickets.
        n_t = rng.poisson(max(1, active.sum() * 0.003))
        pick = rng.integers(0, k, n_t)
        opened = sim.dates(day[pick]).astype("datetime64[s]") + (rng.integers(8, 19, n_t) * 3600).astype("timedelta64[s]")
        prio = np.array(["low", "normal", "high", "urgent"], dtype=object)[weighted_choice(rng, np.array([3, 5, 1.5, 0.4]), n_t)]
        hours = rng.gamma(1.4, np.select([prio == "urgent", prio == "high"], [3, 10], 30))
        ctx.w.write("support_tickets", pd.DataFrame({
            "ticket_id": [f"T{year}{i:06d}" for i in range(1, n_t + 1)], "subscription_id": saas.subscription_id.values[idx[pick]],
            "opened": opened, "resolved": opened + (hours * 3600).astype("int64").astype("timedelta64[s]"),
            "priority": prio, "category": np.array(["bug", "how-to", "billing", "feature request", "outage", "integration"],
                                                   dtype=object)[rng.integers(0, 6, n_t)],
            "satisfaction": rng.choice([1, 2, 3, 4, 5], n_t, p=[0.04, 0.06, 0.15, 0.35, 0.40]),
        }), year)
        ctx.w.close_year(year)


def _construction(ctx):
    sim, rng, cal = ctx.sim, ctx.rng, ctx.sim.cal
    inv = sim.invoices
    cust = sim.customers
    if len(inv) == 0:
        return
    # A project is a run of billing to one customer without gaps longer than six months.
    inv = inv.sort_values(["cust", "day"])
    gap = inv.groupby("cust").day.diff().fillna(10 ** 6) > 180
    inv = inv.assign(project=gap.cumsum().values)
    proj = inv.groupby("project").agg(cust=("cust", "first"), a=("day", "min"), b=("day", "max"), value=("net", "sum"),
                                      bills=("net", "size")).reset_index()
    proj = proj[proj.b >= ctx.first_day].reset_index(drop=True)
    kinds = (["Konut", "Hastane", "Okul", "Köprü", "Otoyol", "AVM", "Fabrika", "Metro"] if sim.tr else
             ["Residential", "Hospital", "School", "Bridge", "Highway", "Retail centre", "Plant", "Transit"])
    cities = ref.CITIES[sim.c.country]
    proj["project_id"] = np.arange(1, len(proj) + 1)
    proj["name"] = [f"{cities[int(rng.integers(len(cities)))]} {kinds[int(rng.integers(len(kinds)))]} {i}"
                    for i in proj.project_id]
    planned_end = proj.b.values - (rng.uniform(-0.15, 0.1, len(proj)) * (proj.b - proj.a).values).astype(int)
    ctx.w.write("projects", pd.DataFrame({
        "project_id": proj.project_id, "name": proj.name, "customer_code": cust.code.values[proj.cust.values],
        "start_date": sim.dates(np.maximum(proj.a.values - 30, 0)), "planned_end_date": sim.dates(planned_end),
        "actual_end_date": np.where(proj.b.values < sim.last_day - 90, sim.dates(proj.b.values), np.datetime64("NaT")),
        "contract_value": proj.value.round(2), "progress_bills": proj.bills}))
    # Monthly progress: billed to date vs an S-curve plan.
    prog = []
    for p in proj.itertuples():
        sub = inv[inv.project == p.project]
        m0, m1 = sim.dm[min(max(p.a - 30, 0), sim.last_day)], sim.dm[min(p.b, sim.last_day)]
        months = np.arange(m0, m1 + 1)
        x = (months - m0 + 1) / len(months)
        billed = np.bincount(sim.dm[np.minimum(sub.day.values, sim.last_day)] - m0, weights=sub.net.values,
                             minlength=len(months))[:len(months)]
        prog.append(pd.DataFrame({"project_id": p.project_id, "period": cal.months[months].astype(str),
                                  "planned_pct": np.round(100 * (3 * x ** 2 - 2 * x ** 3), 1),
                                  "actual_pct": np.round(100 * np.cumsum(billed) / p.value, 1),
                                  "billed_to_date": np.round(np.cumsum(billed), 2)}))
    pr = pd.concat(prog, ignore_index=True)
    ctx.w.write("project_progress_monthly", pr[pr.period >= cal.output_start.strftime("%Y-%m")])
    # Daily site logs for active projects.
    a = np.maximum(proj.a.values - 30, ctx.first_day)
    b = np.minimum(proj.b.values, sim.last_day)
    for year in ctx.years:
        days = ctx.year_days(year)
        if len(days) == 0:
            continue
        s, e = np.maximum(a, days[0]), np.minimum(b, days[-1]) + 1
        cnt = np.maximum(e - s, 0)
        idx = np.repeat(np.arange(len(proj)), cnt)
        day = np.repeat(s, cnt) + (np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt))
        if len(day) == 0:
            continue
        k = len(day)
        dow = cal.days.dayofweek.values[day]
        winter = np.isin(sim.ext_month[day], [12, 1, 2])
        weather_stop = rng.random(k) < np.where(winter, 0.12, 0.03)
        size = np.sqrt(proj.value.values[idx] / max(proj.value.median(), 1))
        crew = np.where((dow == 6) | weather_stop, 0, np.round(rng.lognormal(np.log(35), 0.3, k) * size)).astype(int)
        ctx.w.write("site_daily_logs", pd.DataFrame({
            "date": sim.dates(day), "project_id": proj.project_id.values[idx], "crew_on_site": crew,
            "labour_hours": np.round(crew * rng.uniform(7.5, 10, k), 1), "weather_delay": weather_stop,
            "concrete_m3": np.round(np.where(crew > 0, rng.gamma(1.2, 12, k) * size, 0), 1),
            "safety_incidents": rng.poisson(crew * 0.0008),
        }), year)
        ctx.w.close_year(year)
