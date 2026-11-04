"""Yearly RACMO2.3p2 (CESM2-forced) NetCDF files -> scenario change series at the lake.

Source: van Wessem et al., Zenodo doi:10.5281/zenodo.6416973 (files such as
``t2m_yearlyA_ANT27_CESM2_RACMO2.3p2_SSP245_r567_2011_2099.nc``). The historical run and the
SSP runs come from the same model chain, so the model's own bias cancels in the change.

Method:

* the series at the lake is an inverse-distance mean of the ``n_cells`` nearest 27 km cells
  (the nearest sits about 5 km away but ~900 m higher, so only *changes* are used);
* historical (to 2014) and SSP (from 2015) years are joined and smoothed with a centred
  ``smooth_yr`` running mean, so the forcing carries the forced trend rather than CESM2's own
  year-to-year noise (interannual variability comes from the observed seasons instead);
* change is relative to the ``baseline`` years: additive for temperature, a ratio for
  sublimation.

The output matches ``scenarios.racmo_change`` (columns scenario, mid_year, change), so
``scenarios.change_timeseries`` works on it unchanged.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

BASELINE = (1994, 2025)   # the Lake Vanda station record; hist run to 2014, then each SSP
HIST_END = 2014


def _nearest_cells(grid: Path, lon: float, lat: float, n: int):
    import netCDF4
    with netCDF4.Dataset(grid) as g:
        glat, glon = np.asarray(g["lat"][:]), np.asarray(g["lon"][:])
    dx = (glon - lon) * np.cos(np.radians(lat)) * 111.2
    dy = (glat - lat) * 111.2
    d = np.hypot(dx, dy)
    flat = np.argsort(d, axis=None)[:n]
    rc = [np.unravel_index(i, d.shape) for i in flat]
    dist = np.array([d[r, c] for r, c in rc])
    w = 1.0 / np.maximum(dist, 1.0) ** 2
    return rc, w / w.sum(), dist


def point_series(path: Path, var: str, cells, weights) -> pd.Series:
    """Yearly series (index = calendar year) at the lake from one RACMO yearly file."""
    import netCDF4
    with netCDF4.Dataset(path) as ds:
        x = np.asarray(ds[var][:], dtype=float)
        t = ds["time"]
        dates = netCDF4.num2date(t[:], t.units, getattr(t, "calendar", "standard"))
    x = x.reshape(x.shape[0], -1, *x.shape[-2:])[:, 0]          # drop the singleton height axis
    vals = sum(w * x[:, r, c] for (r, c), w in zip(cells, weights))
    return pd.Series(vals, index=[d.year for d in dates], name=var).groupby(level=0).mean()


def change_table(files: dict[str, Path], var: str, grid: Path, lon: float, lat: float,
                 mode: str = "delta", n_cells: int = 4, smooth_yr: int = 21,
                 baseline: tuple[int, int] = BASELINE) -> pd.DataFrame:
    """``files`` maps 'hist' and each scenario name to a NetCDF path."""
    cells, w, dist = _nearest_cells(grid, lon, lat, n_cells)
    hist = point_series(files["hist"], var, cells, w)
    hist = hist[hist.index <= HIST_END]
    neutral = 0.0 if mode == "delta" else 1.0
    base_mid = (baseline[0] + baseline[1]) / 2
    rows = []
    for scen, p in files.items():
        if scen == "hist":
            continue
        fut = point_series(p, var, cells, w)
        s = pd.concat([hist, fut[fut.index > HIST_END]]).sort_index()
        # Baseline = the years the station record covers, so the observed summers are the
        # zero-change climate. It can run past 2014, so it is taken per scenario.
        base = float(s.loc[baseline[0]:baseline[1]].mean())
        s = s.rolling(smooth_yr, center=True, min_periods=smooth_yr // 2 + 1).mean()
        ch = s - base if mode == "delta" else s / base
        rows.append({"scenario": scen, "mid_year": base_mid, "change": neutral, "value": base, "baseline": base})
        rows += [{"scenario": scen, "mid_year": float(yr), "change": float(c), "value": float(s[yr]), "baseline": base}
                 for yr, c in ch.items() if yr > base_mid]
    out = pd.DataFrame(rows)
    out.attrs.update(cell_distance_km=[round(float(v), 1) for v in dist], baseline=baseline, smooth_yr=smooth_yr)
    return out
