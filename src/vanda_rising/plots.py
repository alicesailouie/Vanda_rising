"""Static figures for the README (matplotlib, light surface)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Categorical slots in fixed order (validated reference palette); ink tokens for text.
SCENARIO_COLORS = {"ssp126": "#2a78d6", "ssp245": "#eb6834", "ssp585": "#1baf7a"}
SCENARIO_LABELS = {"no_warming": "No further warming", "ssp126": "SSP1-2.6", "ssp245": "SSP2-4.5", "ssp585": "SSP5-8.5"}
INK, INK2, MUTED, SURFACE, GRID = "#0b0b0b", "#52514e", "#898781", "#fcfcfb", "#e6e5e0"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": MUTED,
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "lines.linewidth": 2, "font.size": 10, "savefig.dpi": 160,
})


def _color(s):
    return SCENARIO_COLORS.get(s, INK2)


def _save(fig, path: Path, tag: str | None):
    if tag:
        fig.text(0.99, 0.01, tag, ha="right", va="bottom", color=MUTED, fontsize=8)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def plot_hypsometry(curve: pd.DataFrame, path: Path, tag: str | None = None):
    fig, ax = plt.subplots(figsize=(5.5, 4))
    ax.plot(curve["area_km2"], curve["rise_m"], color=_color("ssp126"))
    edge = curve[curve["touches_window_edge"]]
    if len(edge):
        ax.axhline(edge["rise_m"].iloc[0], color=MUTED, ls="--", lw=1)
        ax.text(ax.get_xlim()[0], edge["rise_m"].iloc[0], " flood reaches DEM window edge", color=INK2, va="bottom", fontsize=8)
    ax.set_xlabel("Lake area (km²)")
    ax.set_ylabel("Rise above present level (m)")
    ax.set_title("Lake Vanda hypsometry from REMA", loc="left")
    _save(fig, path, tag)


def plot_cv(preds: pd.DataFrame, metrics: pd.DataFrame, path: Path, unit: str, title: str, tag: str | None = None):
    fig, ax = plt.subplots(figsize=(4.8, 4.5))
    lo, hi = np.nanmin(preds[["obs", "gp"]].to_numpy()), np.nanmax(preds[["obs", "gp"]].to_numpy())
    ax.plot([lo, hi], [lo, hi], color=MUTED, lw=1)
    ax.errorbar(preds["obs"], preds["gp"], yerr=1.645 * preds["gp_sd"], fmt="o", ms=5, color=_color("ssp126"),
                ecolor=GRID, elinewidth=1.5, mec=SURFACE, mew=1)
    r = metrics.loc["gp"]
    ax.text(0.03, 0.97, f"GP RMSE {r.rmse_m:.3g} {unit}\nclimatology RMSE {metrics.loc['climatology', 'rmse_m']:.3g} {unit}\n"
            f"90% interval coverage {r.coverage_90:.0%}", transform=ax.transAxes, va="top", color=INK2, fontsize=8.5)
    ax.set_xlabel(f"Observed ({unit})")
    ax.set_ylabel(f"Leave-one-season-out prediction ({unit})")
    ax.set_title(title, loc="left")
    _save(fig, path, tag)


def plot_projections(panels: dict[str, pd.DataFrame], path: Path, ylabel: str, tag: str | None = None):
    fig, axes = plt.subplots(1, len(panels), figsize=(5.2 * len(panels), 4.2), sharey=True, squeeze=False)
    for ax, (title, df) in zip(axes[0], panels.items()):
        for scen, g in df.groupby("scenario"):
            c = _color(scen)
            ax.fill_between(g["year"], g["p05"], g["p95"], color=c, alpha=0.15, lw=0)
            ax.plot(g["year"], g["p50"], color=c, label=SCENARIO_LABELS.get(scen, scen))
            ax.text(g["year"].iloc[-1] + 1, g["p50"].iloc[-1], SCENARIO_LABELS.get(scen, scen), color=INK2, va="center", fontsize=8)
        ax.set_title(title, loc="left")
        ax.set_xlabel("Year")
    axes[0, 0].set_ylabel(ylabel)
    axes[0, 0].legend(frameon=False, loc="upper left", title="median, 5-95% band", title_fontsize=8)
    _save(fig, path, tag)


def plot_ice(proj: pd.DataFrame, h_obs: pd.Series | None, path: Path, tag: str | None = None):
    fig, ax = plt.subplots(figsize=(6, 4))
    for scen, g in proj.groupby("scenario"):
        ax.plot(g["year"], g["ice_thickness_m"], color=_color(scen), label=SCENARIO_LABELS.get(scen, scen))
        ax.plot(g["year"], g["h_eq_m"], color=_color(scen), lw=1, ls=":")
    if h_obs is not None and len(h_obs):
        ax.plot(h_obs.index, h_obs.to_numpy(), "o", ms=5, color=INK2, mec=SURFACE, label="observed")
    ax.set_xlabel("Year")
    ax.set_ylabel("Ice thickness (m)")
    ax.set_title("Lake Vanda ice cover (solid) and equilibrium thickness (dotted)", loc="left", fontsize=10)
    ax.legend(frameon=False)
    _save(fig, path, tag)


def plot_inundation(dem, transform, floods, path: Path, tag: str | None = None):
    from matplotlib.colors import LightSource

    fig, ax = plt.subplots(figsize=(7, 5.5))
    extent = (transform.c, transform.c + transform.a * dem.shape[1],
              transform.f + transform.e * dem.shape[0], transform.f)
    hs = LightSource(azdeg=315, altdeg=35).hillshade(np.nan_to_num(dem, nan=np.nanmin(dem)), dx=transform.a, dy=-transform.e)
    ax.imshow(hs, cmap="gray", extent=extent, alpha=0.9)
    # Sequential blue ramp: present lake darkest, larger floods lighter; draw largest first.
    f = floods.sort_values("rise_m").reset_index(drop=True)
    ramp = ["#0d366b", "#256abf", "#5598e7", "#9ec5f4", "#cde2fb"]
    colors = [ramp[min(i, len(ramp) - 1)] for i in range(len(f))]
    handles = []
    for i in range(len(f) - 1, -1, -1):
        f.iloc[[i]].plot(ax=ax, color=colors[i], edgecolor=SURFACE, linewidth=0.8)
    for i, r in f.iterrows():
        if r["label"] == "present":
            lab = f"present lake ({r['area_km2']:.1f} km²)"
        elif str(r["label"]).startswith("+"):
            lab = f"{r['label']} ({r['area_km2']:.1f} km²)"
        else:
            lab = f"{r['label']} (+{r['rise_m']:.1f} m, {r['area_km2']:.1f} km²)"
        handles.append((plt.Rectangle((0, 0), 1, 1, color=colors[i]), lab))
    ax.legend(*zip(*handles), frameon=False, loc="lower left", fontsize=8)
    b = f.total_bounds
    pad = 0.25 * max(b[2] - b[0], b[3] - b[1])
    ax.set_xlim(b[0] - pad, b[2] + pad); ax.set_ylim(b[1] - pad, b[3] + pad)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_xlabel(""); ax.set_ylabel(""); ax.grid(False)
    ax.set_title("Lake Vanda flood extents (EPSG:3031)", loc="left")
    _save(fig, path, tag)
