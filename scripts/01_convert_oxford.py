"""Oxford Battery Degradation Dataset 1 (.mat) -> tidy CSV files.

Usage:
    python scripts/01_convert_oxford.py data/raw/Oxford_Battery_Degradation_Dataset_1.mat data/processed

Outputs (in the output directory):
    summary.csv               one row per cell x characterisation cycle x test
    ocv_curves_1mAh.csv.gz    pseudo-OCV (40 mA) charge/discharge, V and T on a 1 mAh grid
    c1_curves_1mAh.csv.gz     1C (740 mA) charge/discharge, V and T on a 1 mAh grid

Notes on the raw file (checked 2026-11-18):
    * time `t` is a MATLAB datenum in DAYS (the readme says seconds); sampling is ~5 s for pseudo-OCV, ~1 s for 1C
    * charge `q` is in mAh, starts at 0 for every test; negative during discharge
    * the file is loaded one cell at a time to keep memory low (the file is ~254 MB)
"""
import sys
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat, whosmat

TESTS = {"C1ch": ("1C", "charge"), "C1dc": ("1C", "discharge"),
         "OCVch": ("pseudo-OCV", "charge"), "OCVdc": ("pseudo-OCV", "discharge")}
Q_STEP = 1.0  # mAh


def datenum_to_datetime(d):
    return dt.datetime.fromordinal(int(d)) + dt.timedelta(days=float(d) % 1) - dt.timedelta(days=366)


def resample_on_q(q_abs, v, T, step=Q_STEP):
    """Interpolate V and T onto a uniform |q| grid. q_abs must be (weakly) increasing."""
    q_mono = np.maximum.accumulate(q_abs)
    keep = np.concatenate(([True], np.diff(q_mono) > 0))
    qm, vm, Tm = q_mono[keep], v[keep], T[keep]
    grid = np.arange(0.0, np.floor(qm[-1] / step) * step + 1e-9, step)
    return grid, np.interp(grid, qm, vm), np.interp(grid, qm, Tm)


def qc_flags(summary):
    """Plain-text flags for tests that deviate from the nominal protocol (40 degC, 740 mA / 40 mA)."""
    nominal = summary["rate"].map({"1C": 740.0, "pseudo-OCV": 40.0})
    dev = summary["mean_current_mA"] / nominal - 1.0
    flags = []
    for i, row in summary.iterrows():
        f = []
        if row["T_mean_degC"] < 5:
            f.append("temperature sensor reads ~0 degC (sensor fault)")
        elif row["T_mean_degC"] < 38:
            f.append(f"chamber at {row['T_mean_degC']:.0f} degC instead of 40")
        if row["duration_h"] > 30:
            f.append("time gap inside test (pause); q-based curve still usable")
        elif abs(dev.iloc[i]) > 0.03:
            f.append(f"mean current {row['mean_current_mA']:.1f} mA differs from nominal by {dev.iloc[i]*100:+.0f}%")
        flags.append("; ".join(f))
    return flags


def main(mat_path, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = sorted(name for name, _, _ in whosmat(mat_path))
    summary, ocv_parts, c1_parts = [], [], []
    for cell in cells:
        s = loadmat(mat_path, variable_names=[cell], squeeze_me=True, struct_as_record=False)[cell]
        cell_id = int(cell.replace("Cell", ""))
        for cyc_name in s._fieldnames:
            cyc = int(cyc_name.replace("cyc", ""))
            c = getattr(s, cyc_name)
            for test, (rate, direction) in TESTS.items():
                if test not in getattr(c, "_fieldnames", []):
                    continue
                d = getattr(c, test)
                t = np.atleast_1d(np.asarray(d.t, float))
                v = np.atleast_1d(np.asarray(d.v, float))
                q = np.atleast_1d(np.asarray(d.q, float))
                T = np.atleast_1d(np.asarray(d.T, float))
                if t.size < 10:
                    continue
                t_s = (t - t[0]) * 86400.0
                q_abs = np.abs(q - q[0])
                cap = float(q_abs.max())
                i_mean = cap / (t_s[-1] / 3600.0) if t_s[-1] > 0 else np.nan
                summary.append(dict(
                    cell=cell_id, cycle=cyc, test=test, rate=rate, direction=direction,
                    start=datenum_to_datetime(t[0]).isoformat(timespec="seconds"),
                    duration_h=round(t_s[-1] / 3600.0, 4), n_points=int(t.size),
                    dt_median_s=round(float(np.median(np.diff(t_s))), 3),
                    capacity_mAh=round(cap, 3), mean_current_mA=round(i_mean, 2),
                    v_start_V=round(float(v[0]), 4), v_end_V=round(float(v[-1]), 4),
                    v_min_V=round(float(v.min()), 4), v_max_V=round(float(v.max()), 4),
                    T_mean_degC=round(float(T.mean()), 2), T_max_degC=round(float(T.max()), 2),
                ))
                grid, vg, Tg = resample_on_q(q_abs, v, T)
                part = pd.DataFrame(dict(cell=cell_id, cycle=cyc, direction=direction,
                                         q_mAh=grid, v_V=np.round(vg, 5), T_degC=np.round(Tg, 2)))
                (ocv_parts if rate == "pseudo-OCV" else c1_parts).append(part)
        print(f"{cell}: {len(s._fieldnames)} characterisation cycles", flush=True)
        del s
    summary = pd.DataFrame(summary).sort_values(["cell", "cycle", "test"]).reset_index(drop=True)
    summary["qc"] = qc_flags(summary)
    summary.to_csv(out_dir / "summary.csv", index=False)
    pd.concat(ocv_parts, ignore_index=True).to_csv(out_dir / "ocv_curves_1mAh.csv.gz", index=False)
    pd.concat(c1_parts, ignore_index=True).to_csv(out_dir / "c1_curves_1mAh.csv.gz", index=False)
    print(f"summary rows: {len(summary)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
