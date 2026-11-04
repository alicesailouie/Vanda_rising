"""Fibre-optic distributed temperature sensing (DTS): an independent check on the climate forcing.

Dataset: Manos & Shaya, "Borehole temperature measurements using distributed temperature
sensing in Allan Hills, Antarctica (2022-2024)", USAP-DC, doi:10.15784/602025, CC BY 4.0.
Allan Hills lies ~100 km NW of Lake Vanda in southern Victoria Land.

Below ~10 m the seasonal temperature wave is damped out, so the 10-20 m mean of a borehole
profile approximates the local mean annual surface temperature. Comparing that with RACMO
2 m temperature and IMAU-FDM 10 m firn temperature (both in Quantarctica) shows how well
the regional models represent this part of Victoria Land.

Note: the projections in this repo use RACMO *changes* (deltas), so a constant model bias
cancels. The check tests whether the forcing model is credible here, not its bias-corrected
value. The file layout inside the archive is not documented on the landing page, so the
reader detects depth/temperature columns by keyword.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from .lter import find_col

_BH = re.compile(r"ALHIC\d{4}", re.IGNORECASE)
_SUFFIXES = {".csv", ".txt", ".dat", ".tsv"}


def load_dts_dir(path) -> pd.DataFrame:
    """Long table: borehole, file, depth_m, temp_c (all readable tabular files under ``path``)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download temp_data_sorted_by_borehole.zip from "
            "https://www.usap-dc.org/view/dataset/602025 and unzip it there."
        )
    frames = []
    for f in sorted(p for p in path.rglob("*") if p.suffix.lower() in _SUFFIXES):
        if f.name.lower().startswith("readme"):
            continue
        try:
            df = pd.read_csv(f, sep=None, engine="python", comment="#")
            dcol = find_col(df, "depth_m", "depth")
            tcol = find_col(df, "temp_c", "temperature", "temp", exclude=(dcol,))
        except Exception as exc:  # noqa: BLE001 - skip files that are not profiles
            warnings.warn(f"skipping {f.name}: {exc}")
            continue
        m = _BH.search(str(f.relative_to(path)))
        frames.append(pd.DataFrame({
            "borehole": m.group(0).upper() if m else f.stem,
            "file": str(f.relative_to(path)),
            "depth_m": pd.to_numeric(df[dcol], errors="coerce"),
            "temp_c": pd.to_numeric(df[tcol], errors="coerce"),
        }).dropna())
    if not frames:
        raise ValueError(f"No depth/temperature tables found under {path}")
    return pd.concat(frames, ignore_index=True)


def near_surface_temperature(df: pd.DataFrame, band=(10.0, 20.0)) -> pd.DataFrame:
    sel = df[(df["depth_m"] >= band[0]) & (df["depth_m"] <= band[1])]
    g = sel.groupby("borehole")["temp_c"]
    return pd.DataFrame({"t_band_mean_c": g.mean(), "t_band_std_c": g.std(), "n": g.size()})


def compare_with_models(nst: pd.DataFrame, rasters: dict[str, Path], lon: float, lat: float) -> pd.DataFrame:
    from .scenarios import sample_raster

    out = nst.copy()
    site_mean = float(nst["t_band_mean_c"].mean())
    for label, p in rasters.items():
        if p is None or not Path(p).exists():
            warnings.warn(f"{label}: raster {p} not found, skipped")
            continue
        v = sample_raster(p, lon, lat)
        out[f"{label}_c"] = v
        out[f"{label}_minus_dts_c"] = v - out["t_band_mean_c"]
    out.attrs["site_mean_dts_c"] = site_mean
    return out
