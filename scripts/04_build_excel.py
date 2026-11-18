"""Build one Excel workbook from the converted Oxford data (for people who prefer Excel to CSV).

Usage:
    python scripts/04_build_excel.py data/processed data/processed/oxford_dataset1_processed.xlsx

Sheets: README, capacity (values + SOH formulas + chart), summary, features,
        Cell{n}_OCVdc / Cell{n}_OCVch (pseudo-OCV voltage on a 1 mAh grid, one column per characterisation cycle).
"""
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import ScatterChart, Reference, Series
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.utils.indexed_list import IndexedList

FONT = "Arial"
HEAD = dict(font=Font(name=FONT, size=10, bold=True, color="FFFFFF"), fill=PatternFill("solid", fgColor="1F3864"),
            alignment=Alignment(horizontal="center", vertical="center", wrap_text=True))

README = [
    ("Oxford Battery Degradation Dataset 1 - processed tables", "title"),
    ("What this is", "h"),
    ("Characterisation tests of 8 Kokam SLPB533459H4 pouch cells (740 mAh nominal), aged at 40 degC with a CC-CV charge and an "
     "Artemis-urban drive-cycle discharge. Every 100 drive cycles a 1C cycle (740 mA) and a pseudo-OCV cycle (40 mA) were recorded.", ""),
    ("This workbook is a re-formatted copy of the public .mat file. Nothing was fitted or modelled here.", ""),
    ("Source and licence", "h"),
    ("Birkl, C. & Howey, D. (2017). Oxford Battery Degradation Dataset 1. University of Oxford. DOI 10.5287/bodleian:KO2kdmYGg", ""),
    ("https://ora.ox.ac.uk/objects/uuid:03ba4b01-cfed-46d3-9b1a-7d4a7bdf6fac", ""),
    ("Also cite: C. R. Birkl, Diagnosis and Prognosis of Degradation in Lithium-Ion Batteries, PhD thesis, University of Oxford, 2017.", ""),
    ("Licence of the data: Open Database License (ODbL) 1.0; contents under the Database Contents License (DbCL) 1.0. "
     "This derived workbook is shared under the same ODbL 1.0 terms. (c) 2017 The Chancellor, Masters and Scholars of the University of Oxford.", ""),
    ("Sheets", "h"),
    ("capacity: pseudo-OCV discharge capacity per cell and cycle (values), SOH relative to cycle 0 (formulas), chart.", ""),
    ("summary: one row per cell x cycle x test (C1ch, C1dc, OCVch, OCVdc) with capacity, duration, temperature and a QC note.", ""),
    ("features: one row per cell x cycle - capacities, capacity inside fixed voltage windows, ICA peak heights/positions, "
     "mean charge-discharge gap, resistance proxy.", ""),
    ("Cell{n}_OCVdc / Cell{n}_OCVch: pseudo-OCV voltage (V) on a 1 mAh grid. Rows = capacity passed since the start of the test "
     "(mAh), columns = number of drive cycles. Empty cells = the test ended before that capacity.", ""),
    ("Units and conventions", "h"),
    ("Capacity in mAh (always positive, counted from the start of each test). Voltage in V. Temperature in degC. "
     "Discharge starts at ~4.19 V and ends at 2.7 V; charge starts at 2.7 V and ends at 4.2 V.", ""),
    ("Things found while converting (see the qc column in summary)", "h"),
    ("1) The time vector in the .mat file is a MATLAB datenum in days, not seconds as the readme states.", ""),
    ("2) Pseudo-OCV tests at cycle 3500 (charge) and 3700 (charge and discharge) ran at about 24-25 degC instead of 40 degC for all cells.", ""),
    ("3) Cell 1 at cycle 1600: the temperature channel reads about 0.5 degC (sensor fault).", ""),
    ("4) Cell 1 at cycles 3200 and 4500: the pseudo-OCV tests contain a long pause, so durations are ~183 h; the V-Q curves are still usable.", ""),
    ("5) Cells 1, 3 and 5, cycles 0-600: mean pseudo-OCV current computed from q and t is ~42 mA on charge and ~38 mA on discharge.", ""),
    ("6) Cells 4, 5, 6 stop near 5000 cycles; cell 2 shows a capacity jump at cycle 7500. Treat late-life points with care.", ""),
    ("How it was made", "h"),
    ("scripts/01_convert_oxford.py -> 02_capacity_ica.py -> 04_build_excel.py in the accompanying repository. "
     "Curves were linearly interpolated onto the 1 mAh grid; the largest voltage difference to the raw points in a 96-test check was 2.4 mV.", ""),
]


def style_header(ws, ncol, row=1):
    for c in range(1, ncol + 1):
        cell = ws.cell(row=row, column=c)
        cell.font, cell.fill, cell.alignment = HEAD["font"], HEAD["fill"], HEAD["alignment"]


def write_table(ws, df, widths=None):
    ws.append(list(df.columns))
    for row in df.itertuples(index=False):
        ws.append([None if pd.isna(v) else v for v in row])
    style_header(ws, df.shape[1])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for i, col in enumerate(df.columns, 1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(col, max(10, min(28, len(str(col)) + 2)))


def main(proc_dir, out_path):
    proc = Path(proc_dir)
    summary = pd.read_csv(proc / "summary.csv", keep_default_na=False, na_values=[""])
    feats = pd.read_csv(proc / "features.csv", keep_default_na=False, na_values=[""])
    ocv = pd.read_csv(proc / "ocv_curves_1mAh.csv.gz")

    wb = Workbook()
    wb._fonts = IndexedList([Font(name=FONT, size=10)])          # default font for every cell

    ws = wb.active
    ws.title = "README"
    ws.column_dimensions["A"].width = 130
    for text, kind in README:
        ws.append([text])
        c = ws.cell(row=ws.max_row, column=1)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if kind == "title":
            c.font = Font(name=FONT, size=14, bold=True)
        elif kind == "h":
            c.font = Font(name=FONT, size=10, bold=True, color="1F3864")

    # ---- capacity: values, SOH formulas, chart ----
    ws = wb.create_sheet("capacity")
    cap = feats.pivot(index="cycle", columns="cell", values="cap_ocv_dc_mAh").sort_index()
    cells = list(cap.columns)
    n = len(cap)
    ws.append(["Pseudo-OCV discharge capacity (mAh), 40 mA, values copied from the features sheet"])
    ws.append(["cycle"] + [f"Cell {c}" for c in cells] + [None] + ["cycle"] + [f"SOH Cell {c}" for c in cells])
    style_header(ws, 1 + len(cells), row=2)
    for c in range(len(cells) + 3, 2 * len(cells) + 4):
        cell = ws.cell(row=2, column=c)
        cell.font, cell.fill, cell.alignment = HEAD["font"], HEAD["fill"], HEAD["alignment"]
    ws.cell(row=1, column=len(cells) + 3, value="SOH = capacity / capacity at cycle 0 (formula)")
    for i, (cyc, row) in enumerate(cap.iterrows(), start=3):
        ws.cell(row=i, column=1, value=int(cyc))
        for j, v in enumerate(row.values, start=2):
            if not pd.isna(v):
                ws.cell(row=i, column=j, value=float(v)).number_format = "0.0"
        ws.cell(row=i, column=len(cells) + 3, value=f"=A{i}")
        for j in range(len(cells)):
            src = get_column_letter(2 + j)
            f = ws.cell(row=i, column=len(cells) + 4 + j, value=f'=IF({src}{i}="","",{src}{i}/{src}$3)')
            f.number_format = "0.0%"
    last = n + 2
    r0 = last + 2
    for k, (label, fn) in enumerate([("first capacity (mAh)", "INDEX({c}3:{c}{l},1)"), ("last recorded capacity (mAh)", "LOOKUP(2,1/({c}3:{c}{l}<>\"\"),{c}3:{c}{l})"),
                                      ("last recorded cycle", "LOOKUP(2,1/({c}3:{c}{l}<>\"\"),$A3:$A{l})"), ("number of characterisations", "COUNT({c}3:{c}{l})")]):
        ws.cell(row=r0 + k, column=1, value=label).font = Font(name=FONT, size=10, bold=True)
        for j in range(len(cells)):
            col = get_column_letter(2 + j)
            ws.cell(row=r0 + k, column=2 + j, value="=" + fn.format(c=col, l=last)).number_format = "0.0" if k < 2 else "0"
    ws.column_dimensions["A"].width = 28
    ws.freeze_panes = "B3"
    ch = ScatterChart()
    ch.title, ch.style = "Pseudo-OCV discharge capacity vs drive cycles", 13
    ch.x_axis.title, ch.y_axis.title = "Drive cycles", "Capacity / mAh"
    ch.roundedCorners = False
    ch.legend.overlay = False
    ch.title.overlay = False
    ch.x_axis.title.overlay = False
    ch.y_axis.title.overlay = False
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    ch.y_axis.scaling.min, ch.y_axis.scaling.max = 500, 760
    ch.height, ch.width = 9.5, 20
    xref = Reference(ws, min_col=1, min_row=3, max_row=last)
    for j in range(len(cells)):
        s = Series(Reference(ws, min_col=2 + j, min_row=2, max_row=last), xref, title_from_data=True)
        s.marker.symbol = "none"
        ch.series.append(s)
    ws.add_chart(ch, f"A{r0 + 6}")

    write_table(wb.create_sheet("summary"), summary, widths={"qc": 60, "start": 20})
    write_table(wb.create_sheet("features"), feats, widths={"qc": 60})

    for cell_id in sorted(ocv.cell.unique()):
        for direction, tag in (("discharge", "OCVdc"), ("charge", "OCVch")):
            g = ocv[(ocv.cell == cell_id) & (ocv.direction == direction)]
            wide = g.pivot(index="q_mAh", columns="cycle", values="v_V").sort_index()
            ws = wb.create_sheet(f"Cell{cell_id}_{tag}")
            ws.append(["q_mAh \\ cycle"] + [int(c) for c in wide.columns])
            for q, row in zip(wide.index, wide.values):
                ws.append([float(q)] + [None if pd.isna(v) else round(float(v), 4) for v in row])
            style_header(ws, wide.shape[1] + 1)
            ws.freeze_panes = "B2"
            ws.column_dimensions["A"].width = 14
    wb.save(out_path)
    print("saved", out_path, "sheets:", len(wb.sheetnames))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
