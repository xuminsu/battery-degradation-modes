# Data notice

The files in `data/processed/` are a derived database of

> Birkl, C. & Howey, D. (2017). Oxford Battery Degradation Dataset 1. University of Oxford.
> DOI 10.5287/bodleian:KO2kdmYGg - https://ora.ox.ac.uk/objects/uuid:03ba4b01-cfed-46d3-9b1a-7d4a7bdf6fac

The original data are copyright (c) 2017, The Chancellor, Masters and Scholars of the University of Oxford, and the
'Oxford Battery Degradation Dataset 1' researchers, and are made available under the Open Database License (ODbL) 1.0:
http://opendatacommons.org/licenses/odbl/1.0/. Any rights in individual contents of the database are licensed under the
Database Contents License (DbCL) 1.0: http://opendatacommons.org/licenses/dbcl/1.0/.

The derived files here are shared under the same ODbL 1.0 terms. If you use them, cite the dataset by its DOI and the PhD thesis
of C. R. Birkl ("Diagnosis and Prognosis of Degradation in Lithium-Ion Batteries", University of Oxford, 2017), as the original readme asks.

What was changed: the MATLAB structure was flattened into tables; time was converted from MATLAB datenum (days) to seconds;
charge was made positive and counted from the start of each test; curves were linearly interpolated onto a 1 mAh grid;
dQ/dV was computed with a Savitzky-Golay filter (31 mV window, order 3). No measurement was removed; deviations from the
nominal protocol are flagged in the `qc` column of `summary.csv`.

`data/raw/` is intentionally empty in the repository. Put `Oxford_Battery_Degradation_Dataset_1.mat` there.
