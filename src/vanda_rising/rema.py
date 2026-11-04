"""Fetch a REMA v2 mosaic window around the lake straight from the PGC cloud-optimised GeoTIFFs.

REMA heights are relative to the WGS84 ellipsoid, not mean sea level. This project only
uses height *differences* above the lake surface, so no geoid correction is needed.
Over a perennially ice-covered lake the DEM records the ice surface, which sits close to,
but not exactly at, the hydrostatic water level.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge

from .geo import ps_bounds, ps_bounds_to_lonlat

STAC_URL = "https://stac.pgc.umn.edu/api/v1/"
NODATA = -9999.0
_GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif")


def find_tiles(bounds_ps, collection: str) -> list[dict]:
    from pystac_client import Client

    bbox = ps_bounds_to_lonlat(bounds_ps)
    items = Client.open(STAC_URL).search(collections=[collection], bbox=bbox).items()
    return [
        {"id": it.id, "dem": it.assets["dem"].href, "meta": it.assets.get("metadata").href if it.assets.get("metadata") else None}
        for it in items
    ]


def fetch_dem(lon: float, lat: float, buffer_m: float, collection: str, out_path: Path) -> Path:
    bounds = ps_bounds(lon, lat, buffer_m)
    tiles = find_tiles(bounds, collection)
    if not tiles:
        raise RuntimeError(f"No {collection} tiles intersect {bounds}")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.Env(**_GDAL_ENV):
        srcs = [rasterio.open(t["dem"]) for t in tiles]
        try:
            arr, transform = merge(srcs, bounds=bounds, nodata=NODATA)
            crs = srcs[0].crs
        finally:
            for s in srcs:
                s.close()
    profile = dict(
        driver="GTiff", dtype="float32", nodata=NODATA, count=1,
        height=arr.shape[1], width=arr.shape[2], crs=crs, transform=transform,
        compress="deflate", tiled=True, blockxsize=256, blockysize=256,
    )
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr[0].astype("float32"), 1)
        dst.update_tags(source="REMA v2 mosaic via PGC STAC", collection=collection,
                        tiles=",".join(t["id"] for t in tiles))
    # Keep tile metadata (acquisition date range) for provenance.
    for t in tiles:
        if t["meta"]:
            try:
                urllib.request.urlretrieve(t["meta"], out_path.parent / Path(t["meta"]).name)
            except OSError:
                pass
    return out_path


def read_dem(path: Path):
    """Return (dem with NaN for nodata, transform, crs, pixel_area_m2)."""
    with rasterio.open(path) as src:
        dem = src.read(1).astype("float64")
        if src.nodata is not None:
            dem[dem == src.nodata] = np.nan
        transform, crs = src.transform, src.crs
    pixel_area = abs(transform.a * transform.e)
    return dem, transform, crs, pixel_area
