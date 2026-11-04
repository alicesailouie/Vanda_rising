"""CMIP6 scenario forcing from RACMO2.3p2 (Quantarctica) and the statistical projection engine.

Delta-change method: RACMO's 27 km grid cannot resolve the Wright Valley, so absolute values
are never used. For each SSP the change in a period-mean field relative to 1979-2022 is
sampled at the lake and interpolated to a yearly series:

* 2 m temperature -> additive delta (°C), added to observed Lake Vanda station temperatures;
* sublimation     -> multiplicative ratio, applied to lake-ice ablation / water loss.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from .geo import to_crs_point
from .lter import SeasonForcing, features_from_forcing
from .model import LevelModel

PERIOD_MID = {"2025-2050": 2037.5, "2051-2075": 2063.0, "2076-2099": 2087.5}
BASELINE_MID = 2000.5  # 1979-2022


def sample_raster(path, lon: float, lat: float, kelvin_to_c: bool = True) -> float:
    with rasterio.open(path) as src:
        x, y = to_crs_point(lon, lat, src.crs)
        v = float(next(src.sample([(x, y)]))[0])
        if src.nodata is not None and v == src.nodata:
            return np.nan
    return v - 273.15 if (kelvin_to_c and v > 100) else v


def racmo_change(hist: Path, future: dict[str, dict[str, Path]], lon: float, lat: float,
                 mode: str = "delta") -> pd.DataFrame:
    """Change per scenario/period: ``delta`` (future - hist) or ``ratio`` (future / hist)."""
    temp = mode == "delta"
    base = sample_raster(hist, lon, lat, kelvin_to_c=temp)
    rows = []
    for scen, periods in future.items():
        for period, p in periods.items():
            v = sample_raster(p, lon, lat, kelvin_to_c=temp)
            rows.append({"scenario": scen, "period": period, "mid_year": PERIOD_MID[period],
                         "value": v, "baseline": base, "change": v - base if temp else v / base})
    return pd.DataFrame(rows)


def change_timeseries(change: pd.DataFrame, years, mode: str = "delta") -> pd.DataFrame:
    years = np.asarray(list(years), dtype=float)
    neutral = 0.0 if mode == "delta" else 1.0
    out = {}
    for scen, g in change.groupby("scenario"):
        g = g.sort_values("mid_year")
        out[scen] = np.interp(years, [BASELINE_MID, *g["mid_year"]], [neutral, *g["change"]])
    return pd.DataFrame(out, index=years.astype(int))


def _quantile_rows(scen, years, cum, extra: dict[str, np.ndarray]) -> list[dict]:
    q = np.percentile(cum, [5, 25, 50, 75, 95], axis=0)
    rows = []
    for j, yr in enumerate(years):
        r = {"scenario": scen, "year": int(yr), "p05": q[0, j], "p25": q[1, j], "p50": q[2, j],
             "p75": q[3, j], "p95": q[4, j]}
        r.update({k: float(v[j]) for k, v in extra.items()})
        rows.append(r)
    return rows


def predict_cached(model: LevelModel, forcings: list[SeasonForcing], cache: dict, d: float):
    d = round(float(d), 2)
    if d not in cache:
        X = pd.DataFrame([features_from_forcing(f, d) for f in forcings])[model.features]
        mu, sd = model.predict(X)
        cache[d] = (mu, sd, model.outside_training(X))
    return cache[d]


def project_statistical(model: LevelModel, forcings: list[SeasonForcing], delta_ts: pd.DataFrame,
                        n_sims: int = 2000, seed: int = 42) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Cumulative level rise (m) from the direct forcing -> level-change regression."""
    rng = np.random.default_rng(seed)
    years = delta_ts.index.to_numpy()
    rows, sims_out = [], {}
    for scen in delta_ts.columns:
        cache: dict = {}
        sims = np.empty((n_sims, len(years)))
        extrap = np.empty(len(years))
        for j, yr in enumerate(years):
            mu, sd, out = predict_cached(model, forcings, cache, delta_ts.loc[yr, scen])
            pick = rng.integers(len(forcings), size=n_sims)
            sims[:, j] = rng.normal(mu[pick], sd[pick])
            extrap[j] = out[pick].mean()
        cum = sims.cumsum(axis=1)
        rows += _quantile_rows(scen, years, cum, {"delta_t": delta_ts[scen].to_numpy(),
                                                  "frac_outside_training": extrap})
        sims_out[scen] = cum
    return pd.DataFrame(rows), sims_out
