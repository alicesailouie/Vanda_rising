"""Perennial lake-ice thickness: surface ablation balanced by basal freezing.

Following the energy-balance framing of McKay et al. (1985) and the 1-D models of Obryk et al.
(2016, J. Glaciol.), the annual-mean thickness H of a perennial ice cover obeys

    rho_i * L_f * dH/dt = k * (T_f - T_s) / H  -  F  -  rho_i * L_f * a

* conductive heat loss through the ice drives freezing at the base (first term);
* ``F`` is an effective basal heat flux. It lumps heat from the water column and shortwave
  absorbed inside the ice, and is calibrated so the model matches observed thickness;
* ``a`` is surface ablation (sublimation plus melt that drains away), in m ice per year.

Equilibrium:   H_eq = k (T_f - T_s) / (F + rho_i L_f a)
Relaxation:    tau  = H_eq / (a + F / (rho_i L_f))       (linearised about H_eq)

Future forcing: T_s is warmed by the RACMO 2 m temperature delta, and ``a`` is scaled by the
RACMO sublimation ratio. The ice cover is the lake's only water-loss pathway, so ``a`` here
and the loss ``l`` in waterbalance.py should agree (l ~ a * rho_i / rho_w). The two are
calibrated independently, and their agreement is a built-in consistency check.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

SEC_PER_YR = 365.25 * 86400


@dataclass
class IceParams:
    k_w_m_k: float = 2.2          # thermal conductivity of lake ice
    rho_i: float = 917.0
    rho_w: float = 1000.0
    latent_j_kg: float = 3.34e5
    t_freeze_c: float = 0.0       # Vanda's surface water is fresh
    ablation_m_yr: float = 0.35   # prior; replace with LTER ablation data or calibrate
    basal_flux_w_m2: float | None = None  # calibrated if None

    @classmethod
    def from_config(cls, d: dict | None) -> "IceParams":
        return cls(**(d or {}))

    @property
    def rho_l(self) -> float:
        return self.rho_i * self.latent_j_kg


def _flux_to_m_yr(flux_w_m2, p: IceParams):
    return np.asarray(flux_w_m2) * SEC_PER_YR / p.rho_l


def equilibrium_thickness(ts_c, a_m_yr, F, p: IceParams):
    dT = np.maximum(p.t_freeze_c - np.asarray(ts_c, float), 0.0)
    return p.k_w_m_k * dT / (F + a_m_yr * p.rho_l / SEC_PER_YR)


def calibrate_basal_flux(h_mean: float, ts_mean_c: float, p: IceParams) -> float:
    """Effective basal flux F (W/m^2) that makes H_eq equal the observed mean thickness."""
    conduct = p.k_w_m_k * (p.t_freeze_c - ts_mean_c) / h_mean
    return float(conduct - p.ablation_m_yr * p.rho_l / SEC_PER_YR)


def response_time(h_eq: float, a_m_yr: float, F: float, p: IceParams) -> float:
    return float(h_eq / (a_m_yr + _flux_to_m_yr(F, p)))


def simulate(h0: float, ts_c: np.ndarray, a_m_yr: np.ndarray, F: float, p: IceParams,
             substeps: int = 24, h_min: float = 0.05) -> np.ndarray:
    """Annual thickness series, integrating with ``substeps`` explicit steps per year."""
    ts_c, a_m_yr = np.broadcast_arrays(np.asarray(ts_c, float), np.asarray(a_m_yr, float))
    h = np.empty(len(ts_c))
    H, dt = float(h0), 1.0 / substeps
    for i in range(len(ts_c)):
        for _ in range(substeps):
            growth = _flux_to_m_yr(p.k_w_m_k * max(p.t_freeze_c - ts_c[i], 0.0) / H - F, p)
            H = max(H + dt * (growth - a_m_yr[i]), h_min)
        h[i] = H
    return h


def fit_ice(h_obs: pd.Series, ts_mean_c: float, p: IceParams) -> dict:
    """Calibrate F from the observed mean, then score the dynamic model on the observed series."""
    F = p.basal_flux_w_m2 if p.basal_flux_w_m2 is not None else calibrate_basal_flux(float(h_obs.mean()), ts_mean_c, p)
    years = h_obs.index.to_numpy()
    sim = simulate(float(h_obs.iloc[0]), np.full(len(years), ts_mean_c), np.full(len(years), p.ablation_m_yr), F, p)
    h_eq = float(equilibrium_thickness(ts_mean_c, p.ablation_m_yr, F, p))
    return {"basal_flux_w_m2": F, "h_eq_m": h_eq, "tau_yr": response_time(h_eq, p.ablation_m_yr, F, p),
            "rmse_m": float(np.sqrt(np.mean((sim - h_obs.to_numpy()) ** 2))),
            "water_loss_equiv_m_yr": p.ablation_m_yr * p.rho_i / p.rho_w, "params": asdict(p)}


def project_ice(h_start: float, ts_mean_c: float, delta_ts: pd.DataFrame, sub_ratio_ts: pd.DataFrame | None,
                F: float, p: IceParams) -> pd.DataFrame:
    rows = []
    years = delta_ts.index.to_numpy()
    for scen in delta_ts.columns:
        ts = ts_mean_c + delta_ts[scen].to_numpy()
        a = p.ablation_m_yr * (1.0 if sub_ratio_ts is None else sub_ratio_ts[scen].to_numpy())
        h = simulate(h_start, ts, a, F, p)
        heq = equilibrium_thickness(ts, a, F, p)
        rows += [{"scenario": scen, "year": int(y), "ice_thickness_m": h[i], "h_eq_m": float(heq[i]),
                  "ts_c": float(ts[i]), "ablation_m_yr": float(np.broadcast_to(a, ts.shape)[i])}
                 for i, y in enumerate(years)]
    return pd.DataFrame(rows)
