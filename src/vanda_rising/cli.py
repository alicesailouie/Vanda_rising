"""Command-line pipeline.

    vanda fetch-dem       # REMA window around the lake (cloud-optimised GeoTIFF, no login)
    vanda hypsometry      # real-data level-area-volume curve and flood extents (DEM only)
    vanda run             # full analysis on real data (see docs/data_sources.md)
    vanda dts-check       # Allan Hills fibre-optic DTS vs RACMO / IMAU-FDM
    vanda demo            # whole pipeline on SYNTHETIC data, no downloads needed
"""
from __future__ import annotations

import argparse
import json
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import hypsometry as hyp
from . import lakeice, lter, plots, synthetic
from .config import load_config, out_dir, resolve
from .geo import to_crs_point
from .inundation import assets_at_risk, flood_polygons
from .model import build_dataset, cross_validate, fit
from .scenarios import change_timeseries, project_statistical, racmo_change
from .waterbalance import calibrate_loss, e_folding_time, project_waterbalance


@dataclass
class Inputs:
    dem: tuple                       # (array, transform, crs, pixel_area_m2)
    levels: pd.Series
    met: pd.DataFrame
    t_change: pd.DataFrame           # RACMO 2 m temperature deltas
    s_change: pd.DataFrame | None    # RACMO sublimation ratios
    inflow: pd.Series | None         # seasonal Onyx River volume (m^3)
    ice: pd.Series | None            # seasonal mean ice thickness (m)
    rema_offset_m: float = 0.0       # level change between the DEM epoch and the last survey


def _exists(cfg, p):
    q = resolve(cfg, p)
    return q if q is not None and q.exists() else None


def load_real_inputs(cfg) -> Inputs:
    from .rema import read_dem

    L, c = cfg["lter"], cfg["lter"]["columns"]
    dem_path = resolve(cfg, cfg["rema"]["dem_path"])
    if not dem_path.exists():
        raise SystemExit(f"{dem_path} missing: run `vanda fetch-dem` first")
    levels = lter.load_lake_levels(resolve(cfg, L["lake_levels_csv"]), L["lake_filter"],
                                   c["levels"]["date"], c["levels"]["level"], c["levels"]["lake"])
    met = lter.load_met(resolve(cfg, L["met_csv"]), c["met"]["date"], c["met"]["temp"], c["met"]["wind"])
    inflow = ice = None
    if (p := _exists(cfg, L.get("discharge_csv"))):
        inflow = lter.seasonal_volume(lter.load_discharge(p, units=L.get("discharge_units", "l/s")))
    if (p := _exists(cfg, L.get("ice_thickness_csv"))):
        ice = lter.load_ice_thickness(p, L["lake_filter"])
    lon, lat = cfg["lake"]["lon"], cfg["lake"]["lat"]
    R = cfg["racmo"]
    if R.get("format") == "netcdf":
        from .racmo_nc import change_table
        kw = dict(grid=resolve(cfg, R["grid"]), lon=lon, lat=lat, n_cells=R.get("n_cells", 4),
                  smooth_yr=R.get("smooth_yr", 21), baseline=tuple(R.get("baseline", (1995, 2014))))
        tch = change_table({k: resolve(cfg, v) for k, v in R["t2m"].items()}, "t2m", mode="delta", **kw)
        # Yearly files give annual-mean warming; summer warming can be smaller (Antarctic
        # warming is winter-amplified). summer_scaling converts one to the other.
        tch["change"] *= float(R.get("summer_scaling", 1.0))
        sch = None
        if R.get("sublimation"):
            sch = change_table({k: resolve(cfg, v) for k, v in R["sublimation"].items()}, "subl", mode="ratio", **kw)
        offset = 0.0
        if L.get("rema_epoch"):
            offset = float(levels.iloc[-1] - lter.level_at(levels, L["rema_epoch"]))
        return Inputs(read_dem(dem_path), levels, met, tch, sch, inflow, ice, offset)
    tch = racmo_change(resolve(cfg, R["t2m_hist"]), {s: {k: resolve(cfg, v) for k, v in d.items()}
                                                      for s, d in R["t2m_future"].items()}, lon, lat, "delta")
    sch = None
    if R.get("sublimation_hist") and _exists(cfg, R["sublimation_hist"]):
        sch = racmo_change(resolve(cfg, R["sublimation_hist"]), {s: {k: resolve(cfg, v) for k, v in d.items()}
                                                                 for s, d in R["sublimation_future"].items()}, lon, lat, "ratio")
    offset = 0.0
    if L.get("rema_epoch"):
        offset = float(levels.iloc[-1] - lter.level_at(levels, L["rema_epoch"]))
    return Inputs(read_dem(dem_path), levels, met, tch, sch, inflow, ice, offset)


def analyse(inp: Inputs, cfg, out: Path, figs: Path, tag: str | None = None) -> dict:
    lk, M = cfg["lake"], cfg["model"]
    dem, transform, crs, px = inp.dem
    res = abs(transform.a)
    summary: dict = {"tag": tag}

    # ---- lake & hypsometry
    lake, h0, curve = detect_lake(cfg, dem, transform, crs, px)
    curve.to_csv(out / "hypsometry.csv", index=False)
    # Area at zero rise includes low ground connected to the lake (channel, delta); use it
    # everywhere so the water balance and hypsometry agree.
    area0 = float(curve["area_km2"].iloc[0] * 1e6)
    summary.update(lake_area_km2=area0 / 1e6, lake_ice_mask_km2=float(lake.sum() * px / 1e6),
                   dem_surface_m=h0, rema_offset_m=inp.rema_offset_m)
    plots.plot_hypsometry(curve, figs / "hypsometry.png", tag)

    # ---- seasonal data
    forcings = lter.season_forcings(inp.met, cfg["lter"]["min_season_coverage"])
    feats = lter.features_table(forcings)
    dlevel = lter.seasonal_level_change(inp.levels)
    feats.join(dlevel, how="outer").to_csv(out / "seasonal_table.csv")
    features = M["features"]
    years = range(M["start_year"], M["end_year"] + 1)
    delta_ts = change_timeseries(inp.t_change, years, "delta")
    sub_ts = change_timeseries(inp.s_change, years, "ratio") if inp.s_change is not None else None
    # Control run: today's climate held fixed. It isolates the lake's committed rise from the
    # effect of warming, and needs no extrapolation beyond the observed summers.
    if M.get("control_run", True):
        delta_ts.insert(0, "no_warming", 0.0)
        if sub_ts is not None:
            sub_ts.insert(0, "no_warming", 1.0)
    pd.concat({"delta_t2m_c": delta_ts, **({"sublimation_ratio": sub_ts} if sub_ts is not None else {})}, axis=1).to_csv(out / "forcing_timeseries.csv")

    # ---- engine 1: statistical
    ds = build_dataset(dlevel, feats)
    if len(ds) < 8:
        raise SystemExit(f"only {len(ds)} seasons with both forcing and level change; need >= 8")
    m_s, p_s = cross_validate(ds, features, "dlevel_m", M["seed"])
    m_s.to_csv(out / "cv_statistical.csv"); p_s.to_csv(out / "cv_statistical_predictions.csv")
    stat_model = fit(ds, features, "dlevel_m", M["seed"])
    stat_proj, _ = project_statistical(stat_model, forcings, delta_ts, M["n_sims"], M["seed"])
    stat_proj.to_csv(out / "projection_statistical.csv", index=False)
    plots.plot_cv(p_s, m_s, figs / "cv_statistical.png", "m", "Seasonal level change: GP cross-validation", tag)
    summary["n_seasons_level"] = len(ds)
    summary["cv_statistical"] = m_s.round(4).to_dict(orient="index")
    panels = {"Statistical engine (forcing → Δlevel)": stat_proj}
    engine = stat_proj

    # ---- engine 2: water balance
    if inp.inflow is not None:
        # Seasonal inflow is heavy-tailed (one flood summer can carry 10x the median), so the
        # GP learns ln(volume) by default: errors become multiplicative, as in the observations.
        log_q = bool(M.get("log_inflow", True))
        target = np.log(inp.inflow.clip(lower=1.0)) if log_q else inp.inflow
        dq = build_dataset(target, feats)
        m_q, p_q = cross_validate(dq, features, "inflow_m3", M["seed"])
        m_q.to_csv(out / "cv_inflow.csv"); p_q.to_csv(out / "cv_inflow_predictions.csv")
        q_model = fit(dq, features, "inflow_m3", M["seed"])
        loss_mean, loss_sd, loss_tab = calibrate_loss(dlevel, inp.inflow, area0)
        loss_tab.to_csv(out / "water_balance_calibration.csv")
        wb_proj, eq, _ = project_waterbalance(q_model, forcings, delta_ts, sub_ts, curve, loss_mean, loss_sd,
                                              len(loss_tab), M["n_sims"], M["seed"], log_inflow=log_q)
        eq["e_folding_time_yr"] = [e_folding_time(curve, q, l) for q, l in zip(eq["mean_inflow_m3"], eq["loss_m_yr"])]
        wb_proj.to_csv(out / "projection_waterbalance.csv", index=False)
        eq.to_csv(out / "equilibrium.csv", index=False)
        if log_q:
            plots.plot_cv(p_q, m_q, figs / "cv_inflow.png", "ln m³",
                          "Onyx River seasonal inflow (log): GP cross-validation", tag)
        else:
            plots.plot_cv(p_q / 1e6, (m_q / 1e6).assign(coverage_90=m_q["coverage_90"]), figs / "cv_inflow.png",
                          "10⁶ m³", "Onyx River seasonal inflow: GP cross-validation", tag)
        summary["water_balance"] = {"loss_m_yr": loss_mean, "loss_sd_m_yr": loss_sd, "n_seasons": len(loss_tab),
                                    "equilibrium": eq.round(3).to_dict(orient="records")}
        panels["Water-balance engine (inflow − ice ablation)"] = wb_proj
        engine = wb_proj
    plots.plot_projections(panels, figs / "projections.png", "Lake level rise since last survey (m)", tag)

    # ---- lake ice
    if inp.ice is not None:
        ts_mean = float(lter.mean_annual_temperature(inp.met).mean())
        p = lakeice.IceParams.from_config(cfg.get("ice"))
        fi = lakeice.fit_ice(inp.ice, ts_mean, p)
        ice_proj = lakeice.project_ice(float(inp.ice.iloc[-1]), ts_mean, delta_ts, sub_ts, fi["basal_flux_w_m2"], p)
        ice_proj.to_csv(out / "projection_ice.csv", index=False)
        plots.plot_ice(ice_proj, inp.ice, figs / "ice_thickness.png", tag)
        fi["mean_annual_air_temp_c"] = ts_mean
        if "water_balance" in summary:
            fi["consistency_ratio_wb_loss_to_ice_ablation"] = summary["water_balance"]["loss_m_yr"] / fi["water_loss_equiv_m_yr"]
        summary["lake_ice"] = fi

    # ---- inundation at chosen years / quantiles
    I = cfg["inundation"]
    rises = {}
    for scen in engine["scenario"].unique():
        for yr in I["years"]:
            row = engine[(engine["scenario"] == scen) & (engine["year"] == yr)]
            for q in I["quantiles"]:
                if len(row):
                    rises[f"{plots.SCENARIO_LABELS.get(scen, scen)} {yr} {q}"] = float(row[q].iloc[0]) + inp.rema_offset_m
    sel = {k: v for k, v in rises.items() if k.endswith(f"{I['years'][-1]} {I['quantiles'][0]}")}
    floods = flood_polygons(dem, transform, crs, lake, h0, rises)
    floods.to_file(out / "inundation.gpkg", driver="GPKG")
    floods.drop(columns="geometry").to_csv(out / "inundation_areas.csv", index=False)
    plots.plot_inundation(dem, transform, floods[floods["label"].isin(["present", *sel])], figs / "inundation.png", tag)
    assets = [resolve(cfg, a) for a in I.get("assets", []) if _exists(cfg, a)]
    if assets:
        assets_at_risk(floods, assets).to_csv(out / "assets_at_risk.csv", index=False)
    summary["flood_area_km2"] = floods.set_index("label")["area_km2"].round(3).to_dict()

    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    return summary


def cmd_fetch_dem(cfg):
    from .rema import fetch_dem

    lk = cfg["lake"]
    p = fetch_dem(lk["lon"], lk["lat"], lk["buffer_m"], cfg["rema"]["collection"], resolve(cfg, cfg["rema"]["dem_path"]))
    print(f"wrote {p}")


def detect_lake(cfg, dem, transform, crs, px):
    lk = cfg["lake"]
    x, y = to_crs_point(lk["lon"], lk["lat"], crs)
    col, row = ~transform * (x, y)
    seed = hyp.find_flat_seed(dem, (int(row), int(col)), int(lk["seed_search_m"] / abs(transform.a)))
    lake, h0 = hyp.lake_mask(dem, seed, lk["surface_tolerance_m"])
    curve = hyp.hypsometric_curve(dem, lake, h0, px, cfg["hypsometry"]["dz_m"], cfg["hypsometry"]["max_rise_m"])
    return lake, h0, curve


def cmd_hypsometry(cfg):
    """Real-data result that needs only the REMA DEM."""
    from .rema import read_dem

    dem, transform, crs, px = read_dem(resolve(cfg, cfg["rema"]["dem_path"]))
    lake, h0, curve = detect_lake(cfg, dem, transform, crs, px)
    out, figs = out_dir(cfg), resolve(cfg, cfg["paths"]["figures"])
    curve.to_csv(out / "hypsometry.csv", index=False)
    rises = {f"+{r:g} m": float(r) for r in (5, 10, 20)}
    floods = flood_polygons(dem, transform, crs, lake, h0, rises)
    floods.to_file(out / "hypsometry_floods.gpkg", driver="GPKG")
    plots.plot_hypsometry(curve, figs / "hypsometry_rema.png", "REMA v2 10 m mosaic")
    plots.plot_inundation(dem, transform, floods, figs / "flood_extents_rema.png", "REMA v2 10 m mosaic (illustrative rises)")
    print(f"lake ice surface (WGS84 ellipsoidal) {h0:.2f} m; ice-surface mask {lake.sum() * px / 1e6:.2f} km2; "
          f"connected area at present level {curve['area_km2'].iloc[0]:.2f} km2")
    print(curve.iloc[:: max(1, len(curve) // 10)].round(3).to_string(index=False))


def cmd_dts(cfg):
    from . import dts

    D = cfg["dts"]
    df = dts.load_dts_dir(resolve(cfg, D["allan_hills_dir"]))
    nst = dts.near_surface_temperature(df, tuple(D["depth_band_m"]))
    cmp = dts.compare_with_models(nst, {k: resolve(cfg, v) for k, v in D["compare_rasters"].items()},
                                  D["site_lon"], D["site_lat"])
    out = out_dir(cfg)
    cmp.to_csv(out / "dts_check.csv")
    print(cmp.round(2).to_string())


def cmd_demo(cfg):
    m = synthetic.met()
    levels, inflow, ice = synthetic.lake_records(m)
    tch, sch = synthetic.racmo_changes()
    centre = to_crs_point(cfg["lake"]["lon"], cfg["lake"]["lat"], "EPSG:3031")
    inp = Inputs(synthetic.dem(centre=centre), levels, m, tch, sch, inflow, ice, 0.0)
    out = out_dir(cfg) / "demo_SYNTHETIC"
    out.mkdir(parents=True, exist_ok=True)
    figs = resolve(cfg, cfg["paths"]["figures"]) / "demo_SYNTHETIC"
    s = analyse(inp, cfg, out, figs, tag="SYNTHETIC DATA: pipeline demo, not results")
    s["true_parameters"] = synthetic.TRUE
    (out / "summary.json").write_text(json.dumps(s, indent=2, default=float))
    print(json.dumps({k: s[k] for k in ("lake_area_km2", "cv_statistical", "water_balance", "lake_ice") if k in s},
                     indent=2, default=lambda v: round(float(v), 3)))
    print(f"\nSYNTHETIC outputs in {out} and {figs}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vanda", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("command", choices=["fetch-dem", "hypsometry", "run", "dts-check", "demo"])
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    warnings.filterwarnings("ignore", message=".*ConvergenceWarning.*")
    if a.command == "fetch-dem":
        cmd_fetch_dem(cfg)
    elif a.command == "hypsometry":
        cmd_hypsometry(cfg)
    elif a.command == "run":
        s = analyse(load_real_inputs(cfg), cfg, out_dir(cfg), resolve(cfg, cfg["paths"]["figures"]))
        print(json.dumps(s, indent=2, default=float))
    elif a.command == "dts-check":
        cmd_dts(cfg)
    else:
        cmd_demo(cfg)


if __name__ == "__main__":
    main()
