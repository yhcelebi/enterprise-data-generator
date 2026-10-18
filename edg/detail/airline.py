"""Airline: airports, fleet (from the fixed-asset register), daily flights and tickets.

Each aircraft is a fixed asset in the ledger. Flight revenue each day adds up exactly to
the day's ticket sales in the ledger (consumer sales), and the tickets of a flight add up
exactly to that flight's revenue. Tickets are kept for a sample of flights sized by the
detail budget.
"""

import numpy as np
import pandas as pd

from . import split_exact, weighted_choice

TICKET_BUDGET = 150e6
AIRPORTS = {  # code: (city, country, lat, lon)
    "IST": ("Istanbul", "TR", 41.26, 28.74), "SAW": ("Istanbul", "TR", 40.90, 29.31), "ESB": ("Ankara", "TR", 40.13, 32.99),
    "ADB": ("Izmir", "TR", 38.29, 27.16), "AYT": ("Antalya", "TR", 36.90, 30.80), "TZX": ("Trabzon", "TR", 40.99, 39.79),
    "DLM": ("Dalaman", "TR", 36.71, 28.79), "GZT": ("Gaziantep", "TR", 36.95, 37.48), "ADA": ("Adana", "TR", 36.98, 35.28),
    "LHR": ("London", "UK", 51.47, -0.45), "LGW": ("London", "UK", 51.15, -0.19), "MAN": ("Manchester", "UK", 53.35, -2.27),
    "EDI": ("Edinburgh", "UK", 55.95, -3.36), "GLA": ("Glasgow", "UK", 55.87, -4.43), "BHX": ("Birmingham", "UK", 52.45, -1.75),
    "BFS": ("Belfast", "UK", 54.66, -6.22), "FRA": ("Frankfurt", "DE", 50.03, 8.56), "MUC": ("Munich", "DE", 48.35, 11.79),
    "BER": ("Berlin", "DE", 52.36, 13.50), "CDG": ("Paris", "FR", 49.01, 2.55), "AMS": ("Amsterdam", "NL", 52.31, 4.76),
    "MAD": ("Madrid", "ES", 40.47, -3.56), "BCN": ("Barcelona", "ES", 41.30, 2.08), "FCO": ("Rome", "IT", 41.80, 12.25),
    "VIE": ("Vienna", "AT", 48.11, 16.57), "ZRH": ("Zurich", "CH", 47.46, 8.55), "ATH": ("Athens", "GR", 37.94, 23.94),
    "DXB": ("Dubai", "AE", 25.25, 55.36), "DOH": ("Doha", "QA", 25.27, 51.61), "JFK": ("New York", "US", 40.64, -73.78),
    "ORD": ("Chicago", "US", 41.98, -87.90), "BOS": ("Boston", "US", 42.37, -71.01), "LAX": ("Los Angeles", "US", 33.94, -118.41),
    "YYZ": ("Toronto", "CA", 43.68, -79.63), "NRT": ("Tokyo", "JP", 35.77, 140.39), "ICN": ("Seoul", "KR", 37.46, 126.44),
    "HKG": ("Hong Kong", "HK", 22.31, 113.92), "SIN": ("Singapore", "SG", 1.36, 103.99), "CAI": ("Cairo", "EG", 30.12, 31.41),
    "JNB": ("Johannesburg", "ZA", -26.14, 28.24), "IST_OLD": ("Istanbul", "TR", 40.98, 28.81),
}
NETWORK = {
    "kanat": ("IST", ["ESB", "ADB", "AYT", "TZX", "DLM", "GZT", "ADA", "SAW"],
              ["FRA", "MUC", "BER", "LHR", "CDG", "AMS", "VIE", "ZRH", "FCO", "MAD", "ATH", "DXB", "DOH", "CAI", "JFK",
               "ORD", "NRT", "ICN"]),
    "albion": ("LHR", ["MAN", "EDI", "GLA", "BHX", "BFS", "LGW"],
               ["FRA", "MUC", "CDG", "AMS", "MAD", "BCN", "FCO", "ATH", "ZRH", "JFK", "BOS", "LAX", "ORD", "YYZ", "DXB",
                "HKG", "SIN", "JNB"]),
}
NARROW = [(1990, "Boeing 737-400", 150), (1996, "Airbus A320ceo", 174), (2005, "Boeing 737-800", 189),
          (2010, "Airbus A321ceo", 200), (2017, "Airbus A320neo", 186), (2019, "Boeing 737 MAX 8", 189)]
WIDE = [(1990, "Boeing 767-300ER", 260), (1999, "Airbus A330-300", 300), (2004, "Boeing 777-300ER", 350),
        (2013, "Boeing 787-9", 296), (2016, "Airbus A350-900", 325)]


def _km(a, b):
    la1, lo1, la2, lo2 = map(np.radians, (AIRPORTS[a][2], AIRPORTS[a][3], AIRPORTS[b][2], AIRPORTS[b][3]))
    h = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(h))


def generate(ctx):
    sim, rng, cal = ctx.sim, ctx.rng, ctx.sim.cal
    hub, domestic, intl = NETWORK[sim.c.id]
    if sim.c.id == "kanat":
        hub_until = cal.month_index("2019-04")  # moved from the old Atatürk airport in April 2019
    else:
        hub_until = -1
    codes = [hub] + domestic + intl + (["IST_OLD"] if sim.c.id == "kanat" else [])
    airports = pd.DataFrame([(c, *AIRPORTS[c]) for c in codes], columns=["airport_code", "city", "country", "lat", "lon"])
    airports.loc[airports.airport_code == "IST_OLD", ["airport_code", "city"]] = ["ISL", "Istanbul (Atatürk)"]
    ctx.w.write("airports", airports)

    fleet = _fleet(ctx)
    ctx.w.write("aircraft", fleet.drop(columns=["acq_month", "out_month"]))
    prefix = "KN" if sim.c.id == "kanat" else "AL"
    dests = np.array(domestic + intl, dtype=object)
    dist = np.array([_km(hub, d) for d in dests])
    long_haul = dist > 4500
    b2c = sim.b2c.set_index("day")
    flight_id = 0
    ticket_id = 0
    total_flights = (fleet.wide.values * 1 + ~fleet.wide.values * 4).sum() * (sim.last_day - ctx.first_day) * 0.6
    sample = min(1.0, TICKET_BUDGET * ctx.detail / max(total_flights * 150, 1))
    ff_members = max(1000, int(TICKET_BUDGET * ctx.detail / 60))
    for year in ctx.years:
        days = ctx.year_days(year)
        if len(days) == 0:
            continue
        rows = []
        for d in days:
            m = sim.dm[d]
            util = float(np.clip(sim.demand[m] * (0.85 + 0.15 * sim.w_day[d]), 0.05, 1.0))
            live = fleet[(fleet.acq_month <= m) & (fleet.out_month > m)]
            if len(live) == 0:
                continue
            flying = max(1, int(round(len(live) * util)))
            for ac in live.sample(n=flying, random_state=int(rng.integers(1 << 31))).itertuples():
                legs = 2 if ac.wide else 4
                pool = np.where(long_haul == ac.wide)[0] if (long_haul == ac.wide).any() else np.arange(len(dests))
                for leg in range(0, legs, 2):
                    j = pool[weighted_choice(rng, 1 / (1 + dist[pool] / 3000), 1)[0]]
                    dep_h = 6 + leg * 4 + rng.integers(0, 3) if not ac.wide else rng.choice([1, 10, 14, 22])
                    rows.append((d, ac.tail_number, ac.seats, j, dep_h))
        if not rows:
            continue
        f = pd.DataFrame(rows, columns=["day", "tail", "seats", "dest", "dep_h"])
        # Each rotation is an outbound and a return flight.
        out = f.assign(origin=hub, destination=dests[f.dest.values], leg="out")
        back = f.assign(origin=dests[f.dest.values], destination=hub, leg="in", dep_h=(f.dep_h + 3 + (dist[f.dest] / 800)).astype(int) % 24)
        fl = pd.concat([out, back], ignore_index=True).sort_values(["day", "dep_h"], kind="stable").reset_index(drop=True)
        if hub_until >= 0:
            old = sim.dm[fl.day.values] < hub_until
            fl.loc[old & (fl.origin == hub), "origin"] = "ISL"
            fl.loc[old & (fl.destination == hub), "destination"] = "ISL"
        n = len(fl)
        km = dist[np.where(fl.leg == "out", fl.dest, fl.dest)]
        m = sim.dm[fl.day.values]
        doy = cal.days.dayofyear.values[fl.day.values]
        season = 0.82 + 0.1 * np.sin((doy - 100) / 365 * 2 * np.pi)
        lf = np.clip(season * np.clip(sim.demand[m], 0.3, 1.1) + rng.normal(0, 0.06, n), 0.12, 1.0)
        cancelled = rng.random(n) < (0.012 + 0.02 * np.isin(sim.ext_month[fl.day.values], [12, 1, 2]))
        if sim.c.id == "albion":
            ash = (fl.day.values >= sim.day_of(2010, 4, 15)[0]) & (fl.day.values <= sim.day_of(2010, 4, 21)[0])
            cancelled |= ash
        pax = np.where(cancelled, 0, np.round(fl.seats.values * lf)).astype(int)
        delay = np.where(cancelled, 0, np.round(rng.exponential(1, n) * np.where(rng.random(n) < 0.25, 35, 4)))
        cause = np.where(delay < 15, None, np.array(["weather", "air traffic control", "technical", "late inbound",
                                                     "ground handling"], dtype=object)[weighted_choice(rng, np.array([1, 2.5, 1, 3, 1.5]), n)])
        # Revenue: each day's ticket sales split over that day's flights by passengers x distance.
        w = pax * km ** 0.7
        totals = b2c.gross.reindex(fl.day.values).fillna(0).values
        day_w = pd.Series(w).groupby(fl.day.values).transform("sum").values
        revenue = np.where(day_w > 0, np.round(totals * w / np.maximum(day_w, 1e-9), 2), 0.0)
        diff = np.round(b2c.gross.reindex(days).fillna(0).values
                        - np.bincount(np.searchsorted(days, fl.day.values), weights=revenue, minlength=len(days)), 2)
        big = pd.Series(w).groupby(fl.day.values).idxmax()
        revenue[big.values] += diff[np.searchsorted(days, big.index.values)]
        dep = sim.dates(fl.day.values).astype("datetime64[s]") + (fl.dep_h.values * 3600 + rng.integers(0, 12, n) * 300).astype("timedelta64[s]")
        block = (km / 780 * 60 + 30).astype(int)
        ids = flight_id + np.arange(1, n + 1)
        flight_id += n
        num = np.array([f"{prefix}{int(x)}" for x in (100 + fl.dest.values * 2 + (fl.leg == "in"))])
        flights = pd.DataFrame({
            "flight_id": ids, "flight_number": num, "date": sim.dates(fl.day.values), "origin": fl.origin.values,
            "destination": fl.destination.values, "tail_number": fl["tail"].values, "scheduled_departure": dep,
            "actual_departure": dep + (delay * 60).astype("timedelta64[s]"),
            "block_minutes": block, "distance_km": np.round(km).astype(int), "seats": fl.seats.values,
            "passengers": pax, "load_factor": np.round(pax / fl.seats.values, 3), "cancelled": cancelled,
            "delay_minutes": delay.astype(int), "delay_cause": cause, "ticket_revenue": np.round(revenue, 2),
        })
        flights["has_ticket_detail"] = (rng.random(n) < sample) & (pax > 0)
        ctx.w.write("flights", flights, year)
        # Tickets for sampled flights.
        t = flights[flights.has_ticket_detail]
        if len(t):
            k = t.passengers.values
            fares = split_exact(rng, t.ticket_revenue.values, k, 0.55)
            owner = np.repeat(np.arange(len(t)), k)
            nt = len(fares)
            lead = np.minimum(rng.gamma(1.6, 18, nt).astype(int), 330)
            app_share = float(np.clip((year - 2011) / 10, 0, 0.55))
            web_share = float(np.clip((year - 1998) / 10, 0, 0.75 - app_share))
            ch_p = np.array([web_share, app_share, max(0.05, 0.6 - web_share - app_share), 0.15, max(0.02, 0.2 - web_share / 4)])
            channel = np.array(["web", "app", "travel agency", "corporate", "call centre"], dtype=object)[weighted_choice(rng, ch_p, nt)]
            fare_class = np.where(fares > np.quantile(fares, 0.93), "business",
                                  np.where(fares > np.quantile(fares, 0.8), "premium economy", "economy"))
            member = np.where(rng.random(nt) < 0.3, rng.integers(1, ff_members + 1, nt), -1)
            tickets = pd.DataFrame({
                "ticket_number": [f"{'235' if prefix == 'KN' else '125'}{x:010d}" for x in ticket_id + np.arange(1, nt + 1)],
                "flight_id": t.flight_id.values[owner],
                "booking_date": (t.date.values[owner].astype("datetime64[D]") - lead.astype("timedelta64[D]")),
                "channel": channel, "fare_class": fare_class, "fare": fares,
                "frequent_flyer_id": pd.array(np.where(member > 0, member, np.nan), dtype="Int64"),
                "checked_bags": rng.choice([0, 1, 2], nt, p=[0.35, 0.55, 0.10]).astype(np.int8),
                "no_show": rng.random(nt) < 0.03,
            })
            ticket_id += nt
            ctx.w.write("tickets", tickets, year)
        ctx.w.close_year(year)


REVENUE_PER_AIRCRAFT_USD = 35e6   # real 2026 USD per aircraft per year
LESSORS = ["AerCap", "Avolon", "SMBC Aviation Capital", "Air Lease Corp", "BOC Aviation", "Carlyle Aviation"]


def _fleet(ctx):
    """Owned aircraft come from the fixed-asset register; leased aircraft fill the gap to the
    fleet the business needs (lessors' names are real aircraft lessors, used generically)."""
    sim, rng, cal = ctx.sim, ctx.rng, ctx.sim.cal
    n_m = cal.n_months
    fa = sim.assets[sim.assets.asset_class == "vehicle"]
    owned = pd.DataFrame({"asset_tag": fa.asset_tag.values, "acq_month": fa.acq_month.values,
                          "out_month": fa.dispose_month.values, "ownership": "owned", "lessor": None})
    annual_real = pd.Series(sim.act_real * 12).rolling(12, min_periods=1).mean().values
    need = np.maximum(1, np.round(annual_real / REVENUE_PER_AIRCRAFT_USD)).astype(int)
    leases = []
    for m in range(n_m):
        active = ((owned.acq_month <= m) & (owned.out_month > m)).sum() + sum(1 for a, b in leases if a <= m < b)
        while active < need[m]:
            term = int(rng.integers(96, 145))
            start = m if m > 0 else -int(rng.integers(0, 60))
            leases.append((start, start + term))
            active += 1
    leased = pd.DataFrame({"asset_tag": None, "acq_month": [a for a, _ in leases], "out_month": [b for _, b in leases],
                           "ownership": "operating lease",
                           "lessor": np.array(LESSORS, dtype=object)[rng.integers(0, len(LESSORS), len(leases))]})
    fleet = pd.concat([owned, leased], ignore_index=True)
    acq_year = cal.start.year + (cal.start.month - 1 + fleet.acq_month.values) // 12
    wide = rng.random(len(fleet)) < 0.28
    types, seats = [], []
    for y, w in zip(acq_year, wide):
        table = WIDE if w else NARROW
        cand = [t for t in table if t[0] <= y] or [table[0]]
        typ = cand[-1] if rng.random() < 0.7 or len(cand) == 1 else cand[-2]
        types.append(typ[1])
        seats.append(typ[2])
    reg = "TC-K" if sim.c.id == "kanat" else "G-AL"
    letters = "ABCDEFGHJKLMNPRSTUVWXYZ"
    tails = [f"{reg}{letters[i // len(letters) % len(letters)]}{letters[i % len(letters)]}{i // 529 or ''}"
             for i in range(len(fleet))]
    return pd.DataFrame({
        "tail_number": tails, "asset_tag": fleet.asset_tag.values, "ownership": fleet.ownership.values,
        "lessor": fleet.lessor.values, "aircraft_type": types, "wide": wide,
        "body": np.where(wide, "wide-body", "narrow-body"), "seats": seats,
        "delivery_date": _month_date(sim, fleet.acq_month.values),
        "exit_date": np.where(fleet.out_month.values < n_m, _month_date(sim, np.minimum(fleet.out_month.values, n_m - 1)),
                              np.datetime64("NaT")),
        "acq_month": fleet.acq_month.values, "out_month": fleet.out_month.values,
    })


def _month_date(sim, months):
    base = sim.cal.months[0]
    return pd.PeriodIndex([base + int(m) for m in months], freq="M").to_timestamp().values.astype("datetime64[D]")
