"""Flood extents at projected levels and the protected areas / sites / footprints they reach."""
from __future__ import annotations

import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio.features import shapes
from shapely.geometry import shape
from shapely.ops import unary_union

from .hypsometry import flood_mask

_NAME_COLS = ("name", "Name", "NAME", "title", "Title", "site_name", "Site_name", "place_name", "id", "ID")


def mask_to_polygon(mask: np.ndarray, transform):
    geoms = [shape(g) for g, v in shapes(mask.astype("uint8"), mask=mask, transform=transform) if v == 1]
    return unary_union(geoms) if geoms else None


def flood_polygons(dem, transform, crs, lake, h0: float, rises: dict[str, float]) -> gpd.GeoDataFrame:
    rows = [{"label": "present", "rise_m": 0.0, "geometry": mask_to_polygon(lake, transform)}]
    for label, r in rises.items():
        rows.append({"label": label, "rise_m": float(r), "geometry": mask_to_polygon(flood_mask(dem, lake, h0 + r), transform)})
    g = gpd.GeoDataFrame(rows, crs=crs)
    g["level_dem_m"] = h0 + g["rise_m"]
    g["area_km2"] = g.area / 1e6
    return g


def assets_at_risk(floods: gpd.GeoDataFrame, asset_paths: list[Path]) -> pd.DataFrame:
    present = floods.loc[floods["label"] == "present", "geometry"].iloc[0]
    rows = []
    for p in asset_paths:
        if not Path(p).exists():
            warnings.warn(f"asset layer {p} not found, skipped")
            continue
        layer = gpd.read_file(p).to_crs(floods.crs)
        layer = layer[layer.intersects(floods.unary_union.envelope)]
        name_col = next((c for c in _NAME_COLS if c in layer.columns), None)
        for _, f in floods[floods["label"] != "present"].iterrows():
            hit = layer[layer.intersects(f.geometry) & ~layer.within(present)]
            for idx, a in hit.iterrows():
                rows.append({"layer": Path(p).stem, "feature": a[name_col] if name_col else idx,
                             "flood": f["label"], "rise_m": f["rise_m"]})
    return pd.DataFrame(rows, columns=["layer", "feature", "flood", "rise_m"])
