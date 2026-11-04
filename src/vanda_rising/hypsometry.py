"""Lake detection and level-area-volume (hypsometric) curves from a DEM.

The DEM sees the lake's ice surface, so only the basin *above* today's level is known.
Volumes are therefore storage gained relative to today's level, which is exactly what a
rising lake needs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import ndimage

_EIGHT = np.ones((3, 3), dtype=bool)


def component_containing(mask: np.ndarray, seed: np.ndarray) -> np.ndarray:
    lab, _ = ndimage.label(mask, structure=_EIGHT)
    ids = np.unique(lab[seed & mask])
    ids = ids[ids > 0]
    return np.isin(lab, ids)


def find_flat_seed(dem: np.ndarray, rc: tuple[int, int], radius_px: int, win: int = 7) -> tuple[int, int]:
    """Flattest pixel among the lowest quarter of a search window (lake ice is very flat)."""
    r0, c0 = rc
    if not (0 <= r0 < dem.shape[0] and 0 <= c0 < dem.shape[1]):
        raise ValueError(f"lake coordinate falls outside the DEM (row {r0}, col {c0}, shape {dem.shape})")
    rs, cs = max(r0 - radius_px, 0), max(c0 - radius_px, 0)
    sub = dem[rs:r0 + radius_px + 1, cs:c0 + radius_px + 1]
    ok = np.isfinite(sub)
    filled = np.where(ok, sub, np.nanmean(sub))
    m = ndimage.uniform_filter(filled, win)
    rough = np.sqrt(np.maximum(ndimage.uniform_filter(filled ** 2, win) - m * m, 0))
    rough[~ok | (sub > np.nanpercentile(sub, 25))] = np.inf
    i, j = np.unravel_index(np.argmin(rough), rough.shape)
    return int(i + rs), int(j + cs)


def lake_mask(dem: np.ndarray, seed_rc: tuple[int, int], tol: float = 0.75, win: int = 7):
    r, c = seed_rc
    h0 = float(np.nanmedian(dem[max(r - win, 0):r + win + 1, max(c - win, 0):c + win + 1]))
    near = np.isfinite(dem) & (np.abs(dem - h0) <= tol)
    seed = np.zeros_like(near)
    seed[r, c] = True
    mask = ndimage.binary_fill_holes(component_containing(near, seed))
    return mask, h0


def flood_mask(dem: np.ndarray, lake: np.ndarray, level: float) -> np.ndarray:
    """Area connected to the lake lying at or below ``level``."""
    below = (np.isfinite(dem) & (dem <= level)) | lake
    return component_containing(below, lake)


def touches_edge(m: np.ndarray) -> bool:
    return bool(m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any())


def hypsometric_curve(dem, lake, h0, pixel_area_m2, dz=0.25, max_rise=40.0) -> pd.DataFrame:
    rises = np.arange(0.0, max_rise + dz / 2, dz)
    areas, edge = np.empty(len(rises)), np.empty(len(rises), dtype=bool)
    for k, r in enumerate(rises):
        m = flood_mask(dem, lake, h0 + r)
        areas[k], edge[k] = m.sum() * pixel_area_m2, touches_edge(m)
    dvol = np.concatenate([[0.0], np.cumsum(0.5 * (areas[1:] + areas[:-1]) * dz)])
    return pd.DataFrame({"rise_m": rises, "level_dem_m": h0 + rises, "area_km2": areas / 1e6,
                         "dvol_km3": dvol / 1e9, "touches_window_edge": edge})


def area_at_rise(curve: pd.DataFrame, rise: float) -> float:
    return float(np.interp(rise, curve["rise_m"], curve["area_km2"]))
