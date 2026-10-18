"""Synthetic enterprise data generator: 30 companies, 1995-2026, DIMA-compatible Parquet."""

import pandas as pd

# Plain numpy object strings are much faster than Arrow strings for the many small
# concatenations and filters the generator does.
pd.set_option("future.infer_string", False)
