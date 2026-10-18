"""Industry detail tables: operational data that sits behind the finance numbers.

Each industry module exposes `generate(ctx)`. Detail tables are written year by year so
memory stays flat, and they reconcile with the finance tables where they overlap (for
example, POS receipts add up to each store's daily sales, which add up to the ledger).
"""

import zlib
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from ..output import _to_arrow


class DetailWriter:
    """Writes detail tables as `<company>/<table>/<table>-<year>.parquet`, appending chunks."""

    def __init__(self, out: Path, company_id: str):
        self.out = Path(out)
        self.company_id = company_id
        self.open = {}
        self.sizes = {}

    def write(self, table: str, df, year: int | None = None):
        if df is None or len(df) == 0:
            return
        df = df.copy()
        df.insert(0, "company_id", self.company_id)
        arrow = _to_arrow(df)
        key = (table, year)
        if key not in self.open:
            folder = self.out / self.company_id / table
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (f"{table}-{year}.parquet" if year is not None else f"{table}.parquet")
            self.open[key] = (pq.ParquetWriter(path, arrow.schema, compression="zstd"), path, arrow.schema)
        writer, path, schema = self.open[key]
        writer.write_table(arrow.cast(schema))
        rows, size = self.sizes.get(table, (0, 0))
        self.sizes[table] = (rows + len(df), size)

    def close_year(self, year: int):
        for key in [k for k in self.open if k[1] == year]:
            self._close(key)

    def _close(self, key):
        writer, path, _ = self.open.pop(key)
        writer.close()
        rows, size = self.sizes[key[0]]
        self.sizes[key[0]] = (rows, size + path.stat().st_size)

    def close(self):
        for key in list(self.open):
            self._close(key)
        return self.sizes


class Ctx:
    """What a detail generator needs: the finished simulation, a writer and its own random stream."""

    def __init__(self, sim, writer: DetailWriter, detail: float):
        self.sim = sim
        self.w = writer
        self.detail = detail
        self.rng = np.random.default_rng(zlib.crc32(f"detail-{sim.c.id}".encode()) + int(sim.rng.integers(1 << 30)))
        cal = sim.cal
        self.first_day = int((cal.output_start - cal.start).days)
        self.years = list(range(cal.output_start.year, cal.end.year + 1))

    def year_days(self, year: int) -> np.ndarray:
        """Day indexes of a calendar year within the output period."""
        sim = self.sim
        lo = max(self.first_day, int((np.datetime64(f"{year}-01-01") - np.datetime64(sim.cal.start.date())).astype(int)))
        hi = min(sim.last_day, int((np.datetime64(f"{year}-12-31") - np.datetime64(sim.cal.start.date())).astype(int)))
        return np.arange(lo, hi + 1)


def split_exact(rng, totals: np.ndarray, counts: np.ndarray, sigma: float = 0.6) -> np.ndarray:
    """Split each total into `count` positive parts (lognormal weights) that add up exactly (to the cent)."""
    owner = np.repeat(np.arange(len(totals)), counts)
    w = rng.lognormal(0, sigma, len(owner))
    wsum = np.bincount(owner, weights=w, minlength=len(totals))
    parts = np.round(totals[owner] * w / wsum[owner], 2)
    diff = np.round(totals - np.bincount(owner, weights=parts, minlength=len(totals)), 2)
    last = np.cumsum(counts) - 1
    has = counts > 0
    parts[last[has]] += diff[has]
    return np.round(parts, 2)


def blocks(counts: np.ndarray, max_rows: int = 3_000_000):
    """Split entities into consecutive groups whose expanded rows stay under max_rows."""
    counts = np.asarray(counts)
    start, acc = 0, 0
    for i, c in enumerate(counts):
        if acc + c > max_rows and i > start:
            yield np.arange(start, i)
            start, acc = i, 0
        acc += c
    if start < len(counts):
        yield np.arange(start, len(counts))


def weighted_choice(rng, weights: np.ndarray, n: int) -> np.ndarray:
    cw = np.cumsum(weights)
    return np.minimum(np.searchsorted(cw, rng.random(n) * cw[-1], side="right"), len(weights) - 1)


def generate(sim, out: Path, detail: float = 1.0) -> dict:
    from . import airline, energy, healthcare, logistics, manufacturing, retail, services, telecom
    modules = {"retail": retail, "telecom": telecom, "energy": energy, "airline": airline, "healthcare": healthcare,
               "logistics": logistics, **{k: manufacturing for k in ("manufacturing", "textiles", "food", "pharma",
                                                                      "automotive", "defense")},
               "software": services, "construction": services}
    mod = modules.get(sim.c.industry)
    if mod is None or detail <= 0:
        return {}
    writer = DetailWriter(out, sim.c.id)
    mod.generate(Ctx(sim, writer, detail))
    return writer.close()
