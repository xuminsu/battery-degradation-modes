"""Check the converted CSV files against the raw .mat file.

Usage:
    python scripts/03_verify_against_raw.py data/raw/Oxford_Battery_Degradation_Dataset_1.mat data/processed

For a random sample of tests it re-reads the raw arrays and reports
  * capacity difference between summary.csv and the raw q array
  * the largest voltage error when the 1 mAh-grid curve is interpolated back onto the raw points
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

mat_path, proc = sys.argv[1], Path(sys.argv[2])
summary = pd.read_csv(proc / "summary.csv")
curves = {"pseudo-OCV": pd.read_csv(proc / "ocv_curves_1mAh.csv.gz"), "1C": pd.read_csv(proc / "c1_curves_1mAh.csv.gz")}
rng = np.random.default_rng(0)
worst_cap, worst_v, n = 0.0, 0.0, 0
for cell in sorted(summary.cell.unique()):
    raw = loadmat(mat_path, variable_names=[f"Cell{cell}"], squeeze_me=True, struct_as_record=False)[f"Cell{cell}"]
    rows = summary[summary.cell == cell]
    for _, r in rows.sample(12, random_state=int(rng.integers(1e9))).iterrows():
        d = getattr(getattr(raw, f"cyc{r.cycle:04d}"), r.test)
        q = np.abs(np.asarray(d.q, float) - d.q[0]); v = np.asarray(d.v, float)
        worst_cap = max(worst_cap, abs(q.max() - r.capacity_mAh))
        c = curves[r.rate]
        g = c[(c.cell == cell) & (c.cycle == r.cycle) & (c.direction == r.direction)]
        inside = (q >= 2) & (q <= g.q_mAh.max() - 2)          # skip the first/last 2 mAh (steep ends)
        err = np.abs(np.interp(q[inside], g.q_mAh, g.v_V) - v[inside])
        worst_v = max(worst_v, float(err.max())); n += 1
    del raw
print(f"tests checked: {n}")
print(f"largest capacity difference: {worst_cap:.4f} mAh")
print(f"largest voltage error of the 1 mAh grid (2 mAh away from the ends): {worst_v*1e3:.2f} mV")
