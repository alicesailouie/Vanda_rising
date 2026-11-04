"""Readers for McMurdo Dry Valleys LTER CSVs (lake-level surveys and meteorology).

EDI exports use slightly different column names between packages and revisions, so the
readers detect columns by keyword and accept explicit overrides from config.yaml.

Season convention: season ``s`` runs 1 July ``s`` to 30 June ``s+1``, so the melt summer
of season 2001 is Nov 2001 - Feb 2002.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MELT_MONTHS = (10, 11, 12, 1, 2, 3)
CORE_MONTHS = (11, 12, 1, 2)


def find_col(df: pd.DataFrame, *keys: str, exclude: tuple[str, ...] = (), required: bool = True) -> str | None:
    """First column whose lowercase name equals, then contains, one of ``keys``."""
    cols = [c for c in df.columns if c not in exclude]
    low = {c: str(c).strip().lower() for c in cols}
    for k in keys:
        for c in cols:
            if low[c] == k:
                return c
    for k in keys:
        for c in cols:
            if k in low[c]:
                return c
    if required:
        raise KeyError(f"None of {keys} found in columns {list(df.columns)}; set the column name in config.yaml")
    return None


def season_of(index) -> np.ndarray:
    idx = pd.DatetimeIndex(index)
    return np.where(idx.month >= 7, idx.year, idx.year - 1)


# --------------------------------------------------------------------------- lake levels
def load_lake_levels(path, lake: str = "Vanda", date: str | None = None,
                     level: str | None = None, lake_col: str | None = None) -> pd.Series:
    df = pd.read_csv(path)
    level = level or find_col(df, "lake_level_masl", "masl", "lake_level", "level", "elevation")
    date = date or find_col(df, "date_time", "datetime", "date", "time", exclude=(level,))
    lake_col = lake_col or find_col(df, "lake", "location", "site", exclude=(level, date), required=False)
    if lake_col is not None and lake:
        df = df[df[lake_col].astype(str).str.contains(lake, case=False, na=False)]
    s = pd.Series(pd.to_numeric(df[level], errors="coerce").to_numpy(),
                  index=pd.to_datetime(df[date], errors="coerce"), name="level_m")
    s = s[s.index.notna()].dropna().sort_index()
    if s.empty:
        raise ValueError(f"No lake-level rows for '{lake}' in {path}")
    return s


def seasonal_level_change(levels: pd.Series, months=(10, 11, 12)) -> pd.Series:
    """Change between consecutive early-summer surveys = net change over the summer between."""
    df = levels.rename("level_m").to_frame()
    df["season"] = season_of(df.index)
    early = df[df.index.month.isin(months)].groupby("season")["level_m"].first()
    seasons = early.index.to_numpy()
    d = early.shift(-1) - early
    consecutive = np.append(np.diff(seasons) == 1, False)
    d = d[consecutive].dropna()
    d.name = "dlevel_m"
    return d


def level_at(levels: pd.Series, when) -> float:
    t = pd.Timestamp(when).value
    return float(np.interp(t, levels.index.astype("int64"), levels.to_numpy()))


# --------------------------------------------------------------------------- Onyx River inflow
_Q_TO_M3S = {"l/s": 1e-3, "m3/s": 1.0, "cfs": 0.0283168}


def load_discharge(path, date: str | None = None, q: str | None = None, units: str = "l/s") -> pd.Series:
    """Discharge series in m^3/s. MCM LTER stream gauges report L/s; set ``units`` otherwise."""
    df = pd.read_csv(path, low_memory=False)
    q = q or find_col(df, "discharge_rate", "discharge", "dsch", "flow")
    date = date or find_col(df, "date_time", "datetime", "timestamp", "date", "time", exclude=(q,))
    s = pd.Series(pd.to_numeric(df[q], errors="coerce").to_numpy() * _Q_TO_M3S[units.lower()],
                  index=pd.to_datetime(df[date], errors="coerce"), name="q_m3s")
    s = s[s.index.notna()].sort_index()
    return s[~s.index.duplicated()].clip(lower=0)


def seasonal_volume(q_m3s: pd.Series, min_days: int = 20) -> pd.Series:
    """Seasonal inflow volume (m^3). Gaps are treated as zero flow (gauges run in summer only)."""
    dt = q_m3s.index.to_series().diff().dt.total_seconds().clip(upper=86400).fillna(0)
    vol = (q_m3s.fillna(0) * dt).groupby(season_of(q_m3s.index)).sum()
    days = q_m3s.notna().groupby(season_of(q_m3s.index)).sum() * (dt.median() / 86400)
    vol = vol[days >= min_days]
    vol.name = "inflow_m3"
    return vol


# --------------------------------------------------------------------------- lake ice
def load_ice_thickness(path, lake: str = "Vanda", date: str | None = None,
                       thick: str | None = None, lake_col: str | None = None) -> pd.Series:
    """Seasonal mean ice thickness (m) for one lake."""
    df = pd.read_csv(path, low_memory=False)
    thick = thick or find_col(df, "z_ice", "ice_thickness", "thickness", "z_ice_m")
    date = date or find_col(df, "date_time", "datetime", "date", "time", exclude=(thick,))
    lake_col = lake_col or find_col(df, "lake", "location", exclude=(thick, date), required=False)
    if lake_col is not None and lake:
        df = df[df[lake_col].astype(str).str.contains(lake, case=False, na=False)]
    s = pd.Series(pd.to_numeric(df[thick], errors="coerce").to_numpy(),
                  index=pd.to_datetime(df[date], errors="coerce")).dropna()
    s = s[s.index.notna()]
    out = s.groupby(season_of(s.index)).mean()
    out.name = "ice_thickness_m"
    return out


def mean_annual_temperature(met: pd.DataFrame, min_coverage: float = 0.8) -> pd.Series:
    """Calendar-year mean air temperature for well-covered years."""
    g = met["t_air"].groupby(met.index.year)
    dt = float(pd.Series(met.index).diff().median() / pd.Timedelta(days=1))
    cov = g.count() * dt / 365.25
    return g.mean()[cov >= min_coverage]


# --------------------------------------------------------------------------- meteorology
def load_met(path, date: str | None = None, temp: str | None = None, wind: str | None = None) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    temp = temp or find_col(df, "airt3m", "airt", "air_temp", "airtemp", "temp")
    wind = wind or find_col(df, "wspd", "wind_speed", "windspeed", "wind", exclude=(temp,), required=False)
    date = date or find_col(df, "date_time", "datetime", "timestamp", "date", "time", exclude=(temp, wind or ""))
    out = pd.DataFrame(index=pd.to_datetime(df[date], errors="coerce"))
    out["t_air"] = pd.to_numeric(df[temp], errors="coerce").to_numpy()
    if wind is not None:
        out["wind"] = pd.to_numeric(df[wind], errors="coerce").to_numpy()
    out = out[out.index.notna()].sort_index()
    out = out[~out.index.duplicated()]
    out.loc[(out["t_air"] < -80) | (out["t_air"] > 30), "t_air"] = np.nan
    return out


@dataclass
class SeasonForcing:
    """Melt-window (Oct-Mar) air temperatures for one season at native time step."""
    season: int
    t: np.ndarray
    dt_days: float
    wind_djf: float
    coverage: float


def season_forcings(met: pd.DataFrame, min_coverage: float = 0.8) -> list[SeasonForcing]:
    dt_days = float(pd.Series(met.index).diff().median() / pd.Timedelta(days=1))
    m = met[met.index.month.isin(MELT_MONTHS)].copy()
    m["season"] = season_of(m.index)
    out = []
    for s, g in m.groupby("season"):
        core = g[g.index.month.isin(CORE_MONTHS)]
        expected = (pd.Timestamp(int(s) + 1, 3, 1) - pd.Timestamp(int(s), 11, 1)) / pd.Timedelta(days=dt_days)
        coverage = float(core["t_air"].notna().sum() / expected)
        wind = float(g.loc[g.index.month.isin((12, 1, 2)), "wind"].mean()) if "wind" in g else np.nan
        t = g["t_air"].to_numpy(float)
        out.append(SeasonForcing(int(s), t[np.isfinite(t)], dt_days, wind, min(coverage, 1.0)))
    return [f for f in out if f.coverage >= min_coverage]


def features_from_forcing(f: SeasonForcing, delta_t: float = 0.0) -> dict:
    """Melt-relevant features, optionally with air temperature shifted by ``delta_t`` (°C)."""
    t = f.t + delta_t
    scale = 1.0 / max(f.coverage, 1e-6)  # gap-fill by proportional scaling
    return {
        "season": f.season,
        "pdd": float(np.clip(t, 0, None).sum() * f.dt_days * scale),          # positive degree-days
        "hours_above_0": float((t > 0).sum() * f.dt_days * 24 * scale),
        "wind_djf": f.wind_djf,
    }


def features_table(forcings: list[SeasonForcing], delta_t: float = 0.0) -> pd.DataFrame:
    return pd.DataFrame([features_from_forcing(f, delta_t) for f in forcings]).set_index("season")
