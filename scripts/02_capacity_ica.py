"""First-pass analysis of the converted Oxford data: capacity fade, ICA (dQ/dV), DVA (dV/dQ), features.

Usage:
    python scripts/02_capacity_ica.py data/processed figures

Reads  summary.csv, ocv_curves_1mAh.csv.gz, c1_curves_1mAh.csv.gz
Writes ica_curves_5mV.csv.gz, features.csv and PNG figures.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter

V_LO, V_HI, DV = 3.30, 4.15, 0.001      # ICA voltage window and grid (V)
SG_WINDOW_V, SG_ORDER = 0.031, 3          # Savitzky-Golay window for dQ/dV (V)
DVA_WINDOW_MAH = 21                       # Savitzky-Golay window for dV/dQ (mAh, odd)
# Fixed windows chosen by eye from the fresh-cell ICA curve (see fig2); they are NOT assigned to electrodes yet.
Q_WINDOWS = [(3.30, 3.60), (3.60, 3.75), (3.75, 3.90), (3.90, 4.15)]
PEAK_WINDOWS = {"peakA": (3.40, 3.60), "peakB": (3.66, 3.745), "peakC": (3.745, 3.83)}


def q_of_v(q, v, direction):
    """Interpolate capacity onto a uniform voltage grid. Returns (v_grid, q_grid)."""
    if direction == "discharge":          # v falls as q grows -> flip to make v increasing
        q, v = q[::-1], v[::-1]
    v_mono = np.maximum.accumulate(v)
    keep = np.concatenate(([True], np.diff(v_mono) > 0))
    grid = np.arange(V_LO, V_HI + 1e-9, DV)
    return grid, np.interp(grid, v_mono[keep], q[keep])


def ica(q, v, direction):
    grid, qg = q_of_v(q, v, direction)
    win = int(round(SG_WINDOW_V / DV)) | 1
    dqdv = savgol_filter(qg, win, SG_ORDER, deriv=1, delta=DV)
    return grid, np.abs(dqdv)             # mAh/V, positive for both directions


def dva(q, v):
    return savgol_filter(v, DVA_WINDOW_MAH, 3, deriv=1, delta=1.0)   # V/mAh on the 1 mAh grid


def main(proc_dir, fig_dir):
    proc, fig_dir = Path(proc_dir), Path(fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(proc / "summary.csv", keep_default_na=False, na_values=[""])
    summary["qc"] = summary["qc"].fillna("")
    ocv = pd.read_csv(proc / "ocv_curves_1mAh.csv.gz")
    c1 = pd.read_csv(proc / "c1_curves_1mAh.csv.gz")

    # ---------- features per cell x cycle ----------
    cap = summary.pivot_table(index=["cell", "cycle"], columns="test", values="capacity_mAh").reset_index()
    cap.columns.name = None
    cap = cap.rename(columns={"OCVdc": "cap_ocv_dc_mAh", "OCVch": "cap_ocv_ch_mAh",
                              "C1dc": "cap_1C_dc_mAh", "C1ch": "cap_1C_ch_mAh"})
    q0 = cap[cap.cycle == 0].set_index("cell")["cap_ocv_dc_mAh"]
    cap["soh_ocv_dc"] = cap["cap_ocv_dc_mAh"] / cap["cell"].map(q0)
    flags = summary[summary.qc != ""].groupby(["cell", "cycle"])["qc"].agg(lambda x: " | ".join(sorted(set(x))))
    cap = cap.merge(flags.rename("qc"), on=["cell", "cycle"], how="left").fillna({"qc": ""})

    ica_rows, feat_rows = [], []
    ocv_g = {k: g for k, g in ocv.groupby(["cell", "cycle", "direction"])}
    c1_g = {k: g for k, g in c1.groupby(["cell", "cycle", "direction"])}
    for (cell, cyc), _ in cap.groupby(["cell", "cycle"]):
        f = dict(cell=cell, cycle=cyc)
        for direction in ("discharge", "charge"):
            g = ocv_g.get((cell, cyc, direction))
            if g is None:
                continue
            vg, dq = ica(g.q_mAh.values, g.v_V.values, direction)
            sel = slice(None, None, 5)                       # store on a 5 mV grid
            ica_rows.append(pd.DataFrame(dict(cell=cell, cycle=cyc, direction=direction,
                                              v_V=np.round(vg[sel], 3), dqdv_mAh_per_V=np.round(dq[sel], 1))))
            tag = "dc" if direction == "discharge" else "ch"
            _, qg = q_of_v(g.q_mAh.values, g.v_V.values, direction)
            for lo, hi in Q_WINDOWS:          # capacity exchanged inside fixed voltage windows
                i0, i1 = np.searchsorted(vg, [lo, hi])
                f[f"q_{tag}_{lo:.2f}_{hi:.2f}_mAh"] = round(float(abs(qg[min(i1, len(qg) - 1)] - qg[i0])), 2)
            for name, (lo, hi) in PEAK_WINDOWS.items():   # ICA peak height/position inside fixed windows
                m = (vg >= lo) & (vg <= hi)
                k = np.argmax(dq[m])
                f[f"ica_{tag}_{name}_V"] = round(float(vg[m][k]), 3)
                f[f"ica_{tag}_{name}_mAh_per_V"] = round(float(dq[m][k]), 1)
        gd, gc = ocv_g.get((cell, cyc, "discharge")), ocv_g.get((cell, cyc, "charge"))
        if gd is not None and gc is not None:
            # hysteresis + polarisation between pseudo-OCV charge and discharge on a common SOC axis
            soc = np.linspace(0.05, 0.95, 181)
            vd = np.interp(soc, 1 - gd.q_mAh.values[::-1] / gd.q_mAh.max(), gd.v_V.values[::-1])
            vc = np.interp(soc, gc.q_mAh.values / gc.q_mAh.max(), gc.v_V.values)
            f["ocv_gap_mean_mV"] = round(float(np.mean(vc - vd)) * 1e3, 2)
        g1 = c1_g.get((cell, cyc, "discharge"))
        if gd is not None and g1 is not None:
            # resistance proxy at 50 % of the pseudo-OCV discharge capacity: dV / dI
            qh = 0.5 * gd.q_mAh.max()
            if g1.q_mAh.max() > qh:
                dv = np.interp(qh, gd.q_mAh, gd.v_V) - np.interp(qh, g1.q_mAh, g1.v_V)
                f["r_proxy_mOhm"] = round(float(dv) / (0.740 - 0.040) * 1e3, 1)
        feat_rows.append(f)
    feats = cap.merge(pd.DataFrame(feat_rows), on=["cell", "cycle"], how="left")
    feats.to_csv(proc / "features.csv", index=False)
    pd.concat(ica_rows, ignore_index=True).to_csv(proc / "ica_curves_5mV.csv.gz", index=False)

    # ---------- figures ----------
    plt.rcParams.update({"figure.dpi": 130, "font.size": 9, "axes.grid": True, "grid.alpha": 0.3})
    cmap = plt.get_cmap("tab10")

    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for cell, g in feats.groupby("cell"):
        ax[0].plot(g.cycle, g.cap_ocv_dc_mAh, "-", color=cmap(cell - 1), lw=1.2, label=f"Cell {cell}")
        bad = g[g.qc != ""]
        ax[0].plot(bad.cycle, bad.cap_ocv_dc_mAh, "x", color=cmap(cell - 1), ms=5)
        ax[1].plot(g.cycle, g.cap_1C_dc_mAh, "-", color=cmap(cell - 1), lw=1.2)
    ax[0].set(title="Pseudo-OCV discharge capacity (40 mA)", xlabel="Drive cycles", ylabel="Capacity / mAh")
    ax[1].set(title="1C discharge capacity (740 mA)", xlabel="Drive cycles")
    ax[0].legend(ncol=2, fontsize=7, title="x = QC-flagged test", title_fontsize=7)
    fig.tight_layout(); fig.savefig(fig_dir / "fig1_capacity_fade.png"); plt.close(fig)

    cell = 1
    cycs = [c for c in (0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000) if (cell, c, "discharge") in ocv_g]
    col = plt.get_cmap("viridis")(np.linspace(0, 0.95, len(cycs)))
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.9))
    for c, k in zip(cycs, col):
        g = ocv_g[(cell, c, "discharge")]
        ax[0].plot(g.q_mAh, g.v_V, color=k, lw=1, label=f"{c}")
        vg, dq = ica(g.q_mAh.values, g.v_V.values, "discharge")
        ax[1].plot(vg, dq, color=k, lw=1)
        ax[2].plot(g.q_mAh.values[15:-15], -dva(g.q_mAh.values, g.v_V.values)[15:-15] * 1e3, color=k, lw=1)
    ax[0].set(title=f"Cell {cell}: pseudo-OCV discharge", xlabel="Discharged capacity / mAh", ylabel="Voltage / V")
    ax[1].set(title="ICA: |dQ/dV|", xlabel="Voltage / V", ylabel="mAh / V")
    ax[2].set(title="DVA: -dV/dQ", xlabel="Discharged capacity / mAh", ylabel="mV / mAh", ylim=(0, 6))
    ax[0].legend(title="cycles", fontsize=7, title_fontsize=7)
    fig.tight_layout(); fig.savefig(fig_dir / "fig2_cell1_ocv_ica_dva.png"); plt.close(fig)

    fig, ax = plt.subplots(1, 3, figsize=(13, 3.6))
    for cell, g in feats.groupby("cell"):
        ok = g[g.qc == ""]
        ax[0].plot(ok.soh_ocv_dc * 100, ok.ica_dc_peakC_mAh_per_V, ".", color=cmap(cell - 1), ms=3, label=f"Cell {cell}")
        ax[1].plot(ok.soh_ocv_dc * 100, ok.ocv_gap_mean_mV, ".", color=cmap(cell - 1), ms=3)
        ax[2].plot(ok.soh_ocv_dc * 100, ok.r_proxy_mOhm, ".", color=cmap(cell - 1), ms=3)
    ax[0].set(title="ICA peak C height (3.745-3.83 V, discharge)", xlabel="SOH / %", ylabel="mAh / V")
    ax[1].set(title="Mean charge-discharge gap at 40 mA", xlabel="SOH / %", ylabel="mV")
    ax[2].set(title="Resistance proxy at 50 % (1C vs pseudo-OCV)", xlabel="SOH / %", ylabel="mOhm")
    for a in ax:
        a.invert_xaxis()
    ax[0].legend(ncol=2, fontsize=7)
    fig.tight_layout(); fig.savefig(fig_dir / "fig3_features_vs_soh.png"); plt.close(fig)
    print(feats.describe().T[["count", "min", "50%", "max"]].round(2).to_string())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
