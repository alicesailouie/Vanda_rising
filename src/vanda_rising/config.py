"""Configuration loading."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg["_root"] = path.resolve().parent
    return cfg


def resolve(cfg: dict[str, Any], p: str | Path | None) -> Path | None:
    """Resolve a config path relative to the repository root."""
    if p is None:
        return None
    p = Path(p)
    return p if p.is_absolute() else cfg["_root"] / p


def out_dir(cfg: dict[str, Any], key: str = "outputs") -> Path:
    d = resolve(cfg, cfg["paths"][key])
    d.mkdir(parents=True, exist_ok=True)
    return d
