"""Healthcare: facilities, physicians, patients, encounters with diagnoses, claims, bed census.

Insurer claims add up exactly to each insurer invoice in the ledger (the invoice is the
monthly batch); self-pay encounters add up exactly to each day's patient payments.
Physicians are the employees of the Physicians department in payroll.
"""

import numpy as np
import pandas as pd

from .. import reference as ref
from ..masters import person_names
from . import split_exact, weighted_choice

FACILITY_REVENUE_USD = 120e6
DIAGNOSES = [  # ICD-10 code, description, main setting, weight, winter factor
    ("Z00.00", "General adult medical examination", "outpatient", 8, 1.0),
    ("J06.9", "Acute upper respiratory infection", "outpatient", 9, 2.2),
    ("I10", "Essential hypertension", "outpatient", 7, 1.0),
    ("E11.9", "Type 2 diabetes mellitus", "outpatient", 5, 1.0),
    ("M54.5", "Low back pain", "outpatient", 5, 1.0),
    ("K21.9", "Gastro-oesophageal reflux disease", "outpatient", 3, 1.0),
    ("E78.5", "Hyperlipidaemia", "outpatient", 3, 1.0),
    ("F32.9", "Depressive episode", "outpatient", 2, 1.2),
    ("J45.909", "Asthma", "outpatient", 2, 1.4),
    ("N39.0", "Urinary tract infection", "outpatient", 3, 1.0),
    ("H66.9", "Otitis media", "outpatient", 2, 1.8),
    ("E03.9", "Hypothyroidism", "outpatient", 2, 1.0),
    ("M17.9", "Osteoarthritis of knee", "outpatient", 2, 1.1),
    ("Z34.90", "Supervision of normal pregnancy", "outpatient", 2, 1.0),
    ("R07.9", "Chest pain", "emergency", 3, 1.0),
    ("R10.9", "Abdominal pain", "emergency", 3, 1.0),
    ("S52.5", "Fracture of lower end of radius", "emergency", 1.5, 1.4),
    ("S06.0", "Concussion", "emergency", 1, 1.0),
    ("A09", "Gastroenteritis", "emergency", 2, 1.0),
    ("R50.9", "Fever", "emergency", 2, 1.8),
    ("J18.9", "Pneumonia", "inpatient", 2, 2.5),
    ("I21.9", "Acute myocardial infarction", "inpatient", 1, 1.3),
    ("I63.9", "Cerebral infarction", "inpatient", 1, 1.2),
    ("I48.91", "Atrial fibrillation", "inpatient", 1, 1.0),
    ("J44.9", "Chronic obstructive pulmonary disease", "inpatient", 1.2, 1.8),
    ("N18.3", "Chronic kidney disease, stage 3", "inpatient", 0.8, 1.0),
    ("O80", "Normal delivery", "inpatient", 1.5, 1.0),
    ("C50.9", "Breast cancer", "inpatient", 0.6, 1.0),
    ("C34.90", "Lung cancer", "inpatient", 0.5, 1.0),
    ("K35.80", "Acute appendicitis", "day_surgery", 0.8, 1.0),
    ("K80.20", "Gallstones", "day_surgery", 0.8, 1.0),
    ("M17.1", "Knee replacement for osteoarthritis", "day_surgery", 0.6, 1.0),
    ("U07.1", "COVID-19", "inpatient", 0.0, 1.0),
]
SETTINGS = ("outpatient", "emergency", "day_surgery", "inpatient")
CHARGE_USD = 220.0   # outpatient visit, 2026 USD
SPECIALTIES = ["Family medicine", "Internal medicine", "Cardiology", "Pediatrics", "General surgery", "Orthopedics",
               "Obstetrics & gynecology", "Emergency medicine", "Neurology", "Oncology", "Radiology", "Anesthesiology"]
DENIAL_REASONS = np.array(["missing documentation", "not medically necessary", "coding error", "out of network",
                           "duplicate claim"], dtype=object)


def generate(ctx):
    sim, rng = ctx.sim, ctx.rng
    tr = sim.tr
    facilities = _facilities(ctx)
    emp = sim.employees
    doctors = emp[emp.department == "Physicians"].copy()
    doctors["specialty"] = np.array(SPECIALTIES, dtype=object)[rng.integers(0, len(SPECIALTIES), len(doctors))]
    ctx.w.write("physicians", doctors[["employee_id", "first_name", "last_name", "specialty", "hire_date",
                                       "termination_date"]])
    diag = pd.DataFrame(DIAGNOSES, columns=["code", "description", "setting", "weight", "winter"])
    ctx.w.write("diagnosis_codes", diag[["code", "description", "setting"]])
    charge_local = CHARGE_USD * (0.35 if tr else 1.0) * sim.fx_end * sim.P
    b2c = sim.b2c.set_index("day")
    inv = sim.invoices
    cust = sim.customers
    cities = np.array(ref.CITIES[sim.c.country], dtype=object)
    n_patients = 0
    enc_id = 0
    census = []
    patients_parts = []
    for year in ctx.years:
        days = ctx.year_days(year)
        if len(days) == 0:
            continue
        parts = []
        # Self-pay encounters: each day's patient payments.
        gross = b2c.gross.reindex(days).fillna(0).values
        n_self = np.maximum(1, np.round(gross / (charge_local[sim.dm[days]] * 1.4))).astype(int) * (gross > 0)
        amounts = split_exact(rng, gross, n_self, 0.9)
        parts.append(pd.DataFrame({"day": np.repeat(days, n_self), "charge": amounts, "payer": "self-pay",
                                   "invoice_number": None, "billed": amounts, "denied": 0.0}))
        # Insurer claims: each insurer invoice of the year, served in the weeks before the invoice.
        yi = inv[(sim.ext_year[inv.day.values] == year) & (inv.day.values >= ctx.first_day)]
        if len(yi):
            avg_claim = charge_local[sim.dm[np.minimum(yi.day.values, sim.last_day)]] * 6
            k = np.maximum(1, np.round(yi.net.values / avg_claim)).astype(int)
            approved = split_exact(rng, yi.net.values, k, 1.0)
            owner = np.repeat(np.arange(len(yi)), k)
            served = np.maximum(yi.day.values[owner] - rng.integers(5, 40, len(owner)), days[0])
            denial = np.clip(rng.beta(1.2, 14, len(owner)), 0, 0.6)
            billed = np.round(approved / (1 - denial), 2)
            parts.append(pd.DataFrame({"day": served, "charge": approved, "payer": cust.code.values[yi.cust.values][owner],
                                       "invoice_number": yi.number.values[owner], "billed": billed,
                                       "denied": np.round(billed - approved, 2)}))
        e = pd.concat(parts, ignore_index=True)
        e = e[e.charge != 0].sort_values("day", kind="stable").reset_index(drop=True)
        n = len(e)
        if n == 0:
            continue
        m = sim.dm[np.minimum(e.day.values, sim.last_day)]
        # Setting from the charge relative to an outpatient visit.
        rel = e.charge.values / charge_local[m]
        setting = np.where(rel > 15, "inpatient", np.where(rel > 8, "day_surgery",
                                                           np.where(rel > 2.2, "emergency", "outpatient")))
        winter = np.isin(sim.ext_month[e.day.values], [12, 1, 2])
        covid = (e.day.values >= sim.day_of(2020, 3, 15)[0]) & (e.day.values <= sim.day_of(2022, 6, 30)[0])
        code = np.empty(n, dtype=object)
        for s_name in SETTINGS:
            sel = np.where(setting == s_name)[0]
            if len(sel) == 0:
                continue
            d = diag[diag.setting == s_name]
            for flag in (True, False):
                ss = sel[winter[sel] == flag]
                if len(ss) == 0:
                    continue
                w = d.weight.values * (d.winter.values if flag else 1.0)
                code[ss] = d.code.values[weighted_choice(rng, w, len(ss))]
            if s_name == "inpatient":
                cv = sel[covid[sel] & (rng.random(len(sel)) < 0.25)]
                code[cv] = "U07.1"
        los = np.where(setting == "inpatient", np.maximum(1, rng.gamma(1.6, 3.0, n)).astype(int), 0)
        # Facilities and physicians.
        fid = np.empty(n, dtype=np.int64)
        for mm in np.unique(m):
            for inpatient in (True, False):
                sel = (m == mm) & ((setting == "inpatient") == inpatient)
                if not sel.any():
                    continue
                f = facilities[(facilities.open_month <= mm) & ((facilities.type == "hospital") | (not inpatient))]
                fid[sel] = f.facility_id.values[weighted_choice(rng, f.weight.values, sel.sum())]
        hired = doctors.hire_date.values.astype("datetime64[D]") <= np.datetime64(f"{year}-12-31")
        still = doctors.termination_date.isna().values | (doctors.termination_date.values.astype("datetime64[D]")
                                                          >= np.datetime64(f"{year}-01-01"))
        docs = doctors[hired & still]
        doc_id = docs.employee_id.values[rng.integers(0, len(docs), n)] if len(docs) else np.full(n, -1)
        # Patients: returning patients are drawn from earlier ones, recent patients more often.
        new = rng.random(n) < (0.35 if n_patients > 0 else 1.0)
        pid = np.where(new, 0, (rng.random(n) ** 1.8 * max(n_patients, 1)).astype(np.int64) + 1)
        new_ids = n_patients + np.arange(1, new.sum() + 1)
        pid[new] = new_ids
        if new.sum():
            _, _, gender = person_names(rng, sim.c.country, new.sum())
            patients_parts.append(pd.DataFrame({
                "patient_id": new_ids, "gender": gender, "birth_year": rng.integers(1925, year + 1, new.sum()),
                "city": cities[np.minimum(rng.pareto(1.0, new.sum()).astype(int), len(cities) - 1)],
                "first_visit": sim.dates(e.day.values[new])}))
            n_patients = int(new_ids[-1])
        ids = enc_id + np.arange(1, n + 1)
        enc_id += n
        admit = sim.dates(e.day.values)
        ctx.w.write("encounters", pd.DataFrame({
            "encounter_id": ids, "patient_id": pid, "facility_id": fid, "physician_employee_id": doc_id,
            "setting": setting, "admit_date": admit, "discharge_date": admit + los.astype("timedelta64[D]"),
            "length_of_stay": los, "primary_diagnosis": code, "payer": e.payer.values, "charge": e.charge.values,
        }), year)
        claims = e.invoice_number.notna().values
        if claims.any():
            denied = e.denied.values[claims]
            ctx.w.write("claims", pd.DataFrame({
                "claim_id": [f"CLM{x:011d}" for x in ids[claims]], "encounter_id": ids[claims],
                "payer_code": e.payer.values[claims], "invoice_number": e.invoice_number.values[claims],
                "billed_amount": e.billed.values[claims], "approved_amount": e.charge.values[claims],
                "denied_amount": denied,
                "denial_reason": np.where(denied > 0.5, DENIAL_REASONS[rng.integers(0, 5, claims.sum())], None),
            }), year)
        # Secondary diagnoses for about 40% of encounters.
        sec = np.where(rng.random(n) < 0.4)[0]
        if len(sec):
            k = rng.integers(1, 4, len(sec))
            owner = np.repeat(sec, k)
            ctx.w.write("encounter_diagnoses", pd.DataFrame({
                "encounter_id": ids[owner],
                "sequence": (np.arange(len(owner)) - np.repeat(np.cumsum(k) - k, k) + 2).astype(np.int8),
                "diagnosis_code": diag.code.values[weighted_choice(rng, diag.weight.values + 0.5, len(owner))]}), year)
        inp = setting == "inpatient"
        census.append((fid[inp], e.day.values[inp], e.day.values[inp] + los[inp]))
        ctx.w.close_year(year)
    if patients_parts:
        ctx.w.write("patients", pd.concat(patients_parts, ignore_index=True))
    facilities = _census(ctx, facilities, census)
    ctx.w.write("facilities", facilities.drop(columns=["open_month", "weight"]))


def _facilities(ctx):
    sim, rng, cal = ctx.sim, ctx.rng, ctx.sim.cal
    annual_real = pd.Series(sim.act_real * 12).rolling(12, min_periods=1).mean().values
    need = np.maximum(1, np.round(annual_real / FACILITY_REVENUE_USD * 3)).astype(int)   # hospitals and clinics
    cities = ref.CITIES[sim.c.country]
    rows = []
    for m in range(cal.n_months):
        while len(rows) < need[m]:
            hospital = len(rows) % 3 == 0
            fid = len(rows) + 1
            city = cities[min(int(rng.pareto(1.0)), len(cities) - 1)]
            label = ("Hastanesi" if hospital else "Tıp Merkezi") if sim.tr else ("Hospital" if hospital else "Medical Center")
            rows.append((fid, f"{sim.c.name.split()[0]} {city} {label}", "hospital" if hospital else "clinic", city,
                         0, m if m > 0 else -int(rng.integers(0, 200)), 3.0 if hospital else 1.0))
    df = pd.DataFrame(rows, columns=["facility_id", "name", "type", "city", "beds", "open_month", "weight"])
    df["opened"] = sim.dates(sim.month_first_day[np.clip(df.open_month.values, 0, cal.n_months - 1)])
    return df


def _census(ctx, facilities, census):
    """Daily inpatient census per facility. Beds are added as demand grows (never removed),
    sized for about 78% average occupancy (busy days can exceed 100%); facilities keep their latest bed count."""
    sim = ctx.sim
    facilities = facilities.copy()
    if not census:
        return facilities
    fid = np.concatenate([c[0] for c in census])
    a = np.concatenate([c[1] for c in census])
    b = np.concatenate([c[2] for c in census])
    lo, hi = ctx.first_day, sim.last_day + 1
    days = np.arange(lo, hi)
    years = sim.ext_year[days]
    for f in np.unique(fid):
        sel = fid == f
        diff = np.zeros(hi - lo + 1)
        np.add.at(diff, np.clip(a[sel] - lo, 0, hi - lo), 1)
        np.add.at(diff, np.clip(b[sel] - lo, 0, hi - lo), -1)
        occ = np.cumsum(diff)[:hi - lo].astype(np.int32)
        beds_by_year, current = {}, 10
        for y in np.unique(years):
            o = occ[years == y]
            need = int(np.ceil(o.mean() / 0.78)) if (o > 0).any() else current
            current = max(current, need)
            beds_by_year[y] = current
        beds = np.array([beds_by_year[y] for y in years], dtype=np.int32)
        facilities.loc[facilities.facility_id == f, "beds"] = current
        df = pd.DataFrame({"date": sim.dates(days), "facility_id": f, "inpatients": occ, "beds": beds,
                           "occupancy_pct": np.round(100 * occ / beds, 1)})
        for y, part in df.groupby(years):
            ctx.w.write("facility_daily_census", part, int(y))
    return facilities
