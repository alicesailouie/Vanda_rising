"""Coordinate helpers. All gridded work is done in Antarctic Polar Stereographic (EPSG:3031)."""
from __future__ import annotations

from pyproj import Transformer

_TO_PS = Transformer.from_crs("EPSG:4326", "EPSG:3031", always_xy=True)
_TO_LL = Transformer.from_crs("EPSG:3031", "EPSG:4326", always_xy=True)


def lonlat_to_ps(lon: float, lat: float) -> tuple[float, float]:
    return _TO_PS.transform(lon, lat)


def ps_bounds(lon: float, lat: float, buffer_m: float) -> tuple[float, float, float, float]:
    x, y = lonlat_to_ps(lon, lat)
    return (x - buffer_m, y - buffer_m, x + buffer_m, y + buffer_m)


def ps_bounds_to_lonlat(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return _TO_LL.transform_bounds(*bounds, densify_pts=21)


def to_crs_point(lon: float, lat: float, crs) -> tuple[float, float]:
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)
