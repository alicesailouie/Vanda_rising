"""Closed-basin water balance for Lake Vanda (hybrid physics + ML engine).

Lake Vanda is endorheic: water arrives almost entirely as Onyx River inflow and leaves only
through ablation of the ice cover (plus moat evaporation), which is replaced by freezing at
the ice base. Per season:

    dV = Q_in - l * A(h)          dh = dV / A(h)

* ``Q_in``: seasonal inflow volume, from a Gaussian process trained on LTER Onyx River
  discharge versus summer degree-days (the glacier-melt signal);
* ``l``:    water-equivalent loss per unit lake area (m/yr), calibrated from observed level
  and inflow; scaled in the future by RACMO's sublimation ratio;
* ``A(h)``: lake area at level ``h`` from the REMA hypsometry.

Because ``A`` grows as the lake rises, losses rise too, and the lake relaxes towards an
equilibrium area ``A_eq = mean(Q_in) / l``. This is the mechanism behind the ~200-year
re-equilibration that Castendyk, Obryk, Leidman, Gooseff & Hawes (2016, Global and Planetary
Change 144:213-227) report. This module gives it a probabilistic, CMIP6-forced form.

Below today's level the bathymetry is not in the DEM. Area changes over a season are small,
so A at the start of each season is used.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .lter import SeasonForcing
from .model import LevelModel
from .scenarios import _quantile_rows, predict_cached


def calibrate_loss(dlevel: pd.Series, inflow_m3: pd.Series, area0_m2: float) -> tuple[float, float, pd.DataFrame]:
    """Per-season loss l = (Q - A0*dh) / A0. Returns (mean, standard deviation, table)."""
    df = pd.concat({"dlevel_m": dlevel, "inflow_m3": inflow_m3}, axis=1).dropna()
    df["inflow_m"] = df["inflow_m3"] / area0_m2
    df["loss_m"] = df["inflow_m"] - df["dlevel_m"]
    return float(df["loss_m"].mean()), float(df["loss_m"].std(ddof=1)), df


def area_m2(curve: pd.DataFrame, rise) -> np.ndarray:
    return np.interp(rise, curve["rise_m"], curve["area_km2"]) * 1e6


def equilibrium_rise(curve: pd.DataFrame, q_mean_m3: float, loss_m: float) -> float:
    """Rise (m) at which l*A(h) balances mean inflow; NaN if beyond the DEM window."""
    a_eq = q_mean_m3 / loss_m
    a = curve["area_km2"].to_numpy() * 1e6
    if loss_m <= 0 or a_eq > a.max() or curve["touches_window_edge"].iloc[np.searchsorted(a, a_eq)]:
        return np.nan
    if a_eq <= a[0]:
        return 0.0
    return float(np.interp(a_eq, np.maximum.accumulate(a), curve["rise_m"]))


def project_waterbalance(inflow_model: LevelModel, forcings: list[SeasonForcing], delta_ts: pd.DataFrame,
                         sub_ratio_ts: pd.DataFrame | None, curve: pd.DataFrame, loss_mean: float,
                         loss_sd: float, n_seasons_calib: int, n_sims: int = 2000, seed: int = 42,
                         log_inflow: bool = False):
    """``log_inflow``: the inflow model predicts ln(volume), so samples are exp(normal)."""
    rng = np.random.default_rng(seed)
    years = delta_ts.index.to_numpy()
    max_rise = float(curve["rise_m"].max())
    rows, eq_rows, sims_out = [], [], {}
    for scen in delta_ts.columns:
        cache: dict = {}
        # parameter uncertainty in l (standard error), then year-to-year scatter
        l_sim = rng.normal(loss_mean, loss_sd / np.sqrt(max(n_seasons_calib, 1)), size=n_sims)
        rise = np.zeros(n_sims)
        cum = np.empty((n_sims, len(years)))
        q_year_mean = np.empty(len(years))
        extrap = np.empty(len(years))
        for j, yr in enumerate(years):
            mu, sd, out = predict_cached(inflow_model, forcings, cache, delta_ts.loc[yr, scen])
            pick = rng.integers(len(forcings), size=n_sims)
            if log_inflow:
                q = np.exp(rng.normal(mu[pick], sd[pick]))
                q_mean = float(np.exp(mu + sd ** 2 / 2).mean())
            else:
                q = np.clip(rng.normal(mu[pick], sd[pick]), 0, None)
                q_mean = float(mu.mean())
            ratio = 1.0 if sub_ratio_ts is None else float(sub_ratio_ts.loc[yr, scen])
            loss = np.clip(l_sim * ratio + rng.normal(0, loss_sd, n_sims), 0, None)
            a = area_m2(curve, np.clip(rise, 0, max_rise))
            rise = rise + (q - loss * a) / a
            cum[:, j] = rise
            q_year_mean[j] = q_mean
            extrap[j] = out[pick].mean()
        rows += _quantile_rows(scen, years, cum, {"delta_t": delta_ts[scen].to_numpy(),
                                                  "mean_inflow_m3": q_year_mean,
                                                  "frac_outside_training": extrap})
        ratio_end = 1.0 if sub_ratio_ts is None else float(sub_ratio_ts[scen].iloc[-1])
        eq_rows.append({"scenario": scen, "climate_of_year": int(years[-1]),
                        "mean_inflow_m3": q_year_mean[-1], "loss_m_yr": loss_mean * ratio_end,
                        "equilibrium_rise_m": equilibrium_rise(curve, q_year_mean[-1], loss_mean * ratio_end),
                        "equilibrium_area_km2": q_year_mean[-1] / (loss_mean * ratio_end) / 1e6})
        sims_out[scen] = cum
    return pd.DataFrame(rows), pd.DataFrame(eq_rows), sims_out


def e_folding_time(curve: pd.DataFrame, q_mean_m3: float, loss_m: float) -> float:
    """Linearised relaxation time (yr) towards equilibrium: tau = A / (l * dA/dh) at equilibrium."""
    h_eq = equilibrium_rise(curve, q_mean_m3, loss_m)
    if not np.isfinite(h_eq):
        return np.nan
    a = curve["area_km2"].to_numpy() * 1e6
    dadh = np.gradient(a, curve["rise_m"].to_numpy())
    k = int(np.argmin(np.abs(curve["rise_m"].to_numpy() - h_eq)))
    return float(a[k] / (loss_m * dadh[k])) if dadh[k] > 0 else np.nan
