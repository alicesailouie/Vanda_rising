"""Synthetic but internally consistent data, for tests and ``vanda demo``.

Nothing here is an observation. Every output made from it is labelled SYNTHETIC. It exists
so the full pipeline can run before any real data are downloaded, and so tests can check
that the models recover known parameters.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from rasterio.transform import from_origin

from . import lakeice
from .lter import features_table, season_forcings

TRUE = {"loss_m_yr": 0.33, "q_per_pdd_m3": 6.0e4, "area0_km2": 5.0, "ice_flux_w_m2": 7.5}


def met(start="1994-07-01", end="2024-06-30", freq="3h", seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = pd.date_range(start, end, freq=freq)
    doy = t.dayofyear.to_numpy()
    seasonal = -18.5 + 17.0 * np.cos(2 * np.pi * (doy - 5) / 365.25)
    summer = np.clip(np.cos(2 * np.pi * (doy - 5) / 365.25), 0, None)
    diurnal = 3.0 * summer * np.cos(2 * np.pi * (t.hour.to_numpy() - 14) / 24)
    season = np.where(t.month >= 7, t.year, t.year - 1)
    anom = pd.Series(rng.normal(0, 1.3, season.max() - season.min() + 1), index=np.arange(season.min(), season.max() + 1))
    temp = seasonal + diurnal + anom.loc[season].to_numpy() * (0.5 + summer) + rng.normal(0, 1.5, len(t))
    wind = rng.gamma(2.0, 2.2, len(t))
    return pd.DataFrame({"t_air": temp, "wind": wind}, index=t)


def lake_records(m: pd.DataFrame, seed=1) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Consistent (levels, seasonal inflow, ice thickness) from the water and ice balances."""
    rng = np.random.default_rng(seed)
    feats = features_table(season_forcings(m))
    a0 = TRUE["area0_km2"] * 1e6
    inflow = TRUE["q_per_pdd_m3"] * feats["pdd"] * np.exp(rng.normal(0, 0.15, len(feats)))
    dlevel = (inflow - TRUE["loss_m_yr"] * a0) / a0 + rng.normal(0, 0.03, len(feats))
    level = 100.0 + np.concatenate([[0.0], np.cumsum(dlevel.to_numpy())])
    dates = [pd.Timestamp(int(s), 11, 15) for s in feats.index] + [pd.Timestamp(int(feats.index[-1]) + 1, 11, 15)]
    levels = pd.Series(level + rng.normal(0, 0.01, len(level)), index=pd.DatetimeIndex(dates), name="level_m")
    p = lakeice.IceParams()
    ts = m["t_air"].groupby(m.index.year).mean()
    h = lakeice.simulate(3.4, ts.to_numpy(), np.full(len(ts), p.ablation_m_yr), TRUE["ice_flux_w_m2"], p)
    ice = pd.Series(h + rng.normal(0, 0.08, len(h)), index=ts.index, name="ice_thickness_m")
    return levels, inflow.rename("inflow_m3"), ice


def dem(res=10.0, half=7000.0, a=2500.0, b=650.0, floor=100.0, centre=(0.0, 0.0)):
    """Elliptical basin (flat lake floor = today's ice surface) centred on ``centre`` (EPSG:3031)."""
    n = int(2 * half / res)
    xs = (np.arange(n) + 0.5) * res - half
    X, Y = np.meshgrid(xs, -xs)
    r = np.sqrt((X / a) ** 2 + (Y / b) ** 2)
    z = floor + 20.0 * np.clip(r - 1, 0, None) + 0.002 * np.abs(X)
    z[r < 1] = floor
    transform = from_origin(centre[0] - half, centre[1] + half, res, res)
    return z, transform, "EPSG:3031", res * res


def racmo_changes() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Made-up scenario deltas with a plausible ordering. NOT RACMO output."""
    rows_t, rows_s = [], []
    table_t = {"ssp126": [0.5, 0.7, 0.7], "ssp245": [0.7, 1.3, 1.8], "ssp585": [0.9, 2.2, 3.8]}
    table_s = {"ssp126": [1.02, 1.03, 1.03], "ssp245": [1.03, 1.05, 1.07], "ssp585": [1.04, 1.08, 1.14]}
    for scen in table_t:
        for (period, mid), dt, ds in zip({"2025-2050": 2037.5, "2051-2075": 2063.0, "2076-2099": 2087.5}.items(),
                                         table_t[scen], table_s[scen]):
            rows_t.append({"scenario": scen, "period": period, "mid_year": mid, "change": dt})
            rows_s.append({"scenario": scen, "period": period, "mid_year": mid, "change": ds})
    return pd.DataFrame(rows_t), pd.DataFrame(rows_s)
