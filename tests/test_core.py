import numpy as np
import pandas as pd
import pytest

from vanda_rising import hypsometry as hyp
from vanda_rising import lakeice, lter, synthetic, waterbalance
from vanda_rising.model import build_dataset, cross_validate, fit
from vanda_rising.scenarios import change_timeseries


# ---------------------------------------------------------------- hypsometry
def box_basin(n=120, res=10.0):
    """Flat floor (100 m) inside vertical-ish walls rising 1 m per pixel ring."""
    z = np.full((n, n), 100.0)
    c = n // 2
    rr, cc = np.ogrid[:n, :n]
    ring = np.maximum(np.abs(rr - c), np.abs(cc - c))
    z[ring > 20] = 100.0 + (ring[ring > 20] - 20)
    return z, res * res


def test_lake_detection_and_monotone_curve():
    z, px = box_basin()
    seed = hyp.find_flat_seed(z, (60, 60), 30)
    lake, h0 = hyp.lake_mask(z, seed, tol=0.1)
    assert h0 == pytest.approx(100.0)
    assert lake.sum() == 41 * 41
    curve = hyp.hypsometric_curve(z, lake, h0, px, dz=1.0, max_rise=10)
    assert (np.diff(curve["area_km2"]) >= 0).all()
    # each 1 m rise adds one pixel ring: side 41 + 2k
    assert curve["area_km2"].iloc[3] == pytest.approx(47 ** 2 * px / 1e6)


def test_flood_requires_connection():
    z, px = box_basin()
    z[5:10, 5:10] = 90.0  # isolated low pit far from the lake
    lake, h0 = hyp.lake_mask(z, (60, 60), tol=0.1)
    m = hyp.flood_mask(z, lake, h0 + 2)
    assert not m[7, 7]


# ---------------------------------------------------------------- LTER parsing
def test_level_change_uses_consecutive_early_summer_surveys():
    idx = pd.to_datetime(["2000-11-10", "2001-01-20", "2001-11-12", "2002-11-15", "2004-11-15"])
    s = pd.Series([10.0, 10.3, 10.5, 10.4, 11.0], index=idx)
    d = lter.seasonal_level_change(s)
    assert list(d.index) == [2000, 2001]        # 2002 -> 2004 gap is dropped
    assert d.loc[2000] == pytest.approx(0.5)


def test_column_detection(tmp_path):
    p = tmp_path / "levels.csv"
    pd.DataFrame({"LAKE": ["Lake Vanda", "Lake Hoare"], "DATE_TIME": ["2001-11-01", "2001-11-01"],
                  "LAKE_LEVEL_MASL": [94.1, 73.0]}).to_csv(p, index=False)
    s = lter.load_lake_levels(p, "Vanda")
    assert len(s) == 1 and s.iloc[0] == pytest.approx(94.1)


def test_pdd_responds_to_warming():
    m = synthetic.met(start="2000-07-01", end="2003-06-30")
    f = lter.season_forcings(m)
    a, b = lter.features_from_forcing(f[0], 0.0), lter.features_from_forcing(f[0], 2.0)
    assert b["pdd"] > a["pdd"] > 0


# ---------------------------------------------------------------- models
@pytest.fixture(scope="module")
def synth():
    m = synthetic.met()
    levels, inflow, ice = synthetic.lake_records(m)
    feats = lter.features_table(lter.season_forcings(m))
    return m, levels, inflow, ice, feats


def test_gp_beats_climatology(synth):
    _, levels, _, _, feats = synth
    ds = build_dataset(lter.seasonal_level_change(levels), feats)
    metrics, _ = cross_validate(ds, ["pdd"])
    assert metrics.loc["gp", "rmse_m"] < 0.5 * metrics.loc["climatology", "rmse_m"]
    assert 0.7 <= metrics.loc["gp", "coverage_90"] <= 1.0


def test_water_balance_recovers_true_loss(synth):
    _, levels, inflow, _, _ = synth
    loss, sd, _ = waterbalance.calibrate_loss(lter.seasonal_level_change(levels), inflow,
                                              synthetic.TRUE["area0_km2"] * 1e6)
    assert loss == pytest.approx(synthetic.TRUE["loss_m_yr"], abs=0.03)


def test_equilibrium_rise_balances_inflow():
    curve = pd.DataFrame({"rise_m": np.arange(0, 11.0), "area_km2": 5 + np.arange(0, 11.0),
                          "touches_window_edge": False})
    # inflow balances loss at A = 8 km^2 -> rise 3 m
    assert waterbalance.equilibrium_rise(curve, 8e6 * 0.3, 0.3) == pytest.approx(3.0)
    assert np.isnan(waterbalance.equilibrium_rise(curve, 50e6 * 0.3, 0.3))


def test_ice_model_equilibrium_and_warming():
    p = lakeice.IceParams()
    F = lakeice.calibrate_basal_flux(3.75, -20.0, p)
    assert lakeice.equilibrium_thickness(-20.0, p.ablation_m_yr, F, p) == pytest.approx(3.75)
    h = lakeice.simulate(3.75, np.full(200, -20.0), np.full(200, p.ablation_m_yr), F, p)
    assert h[-1] == pytest.approx(3.75, abs=0.01)                 # stays at equilibrium
    warm = lakeice.simulate(3.75, np.full(200, -17.0), np.full(200, p.ablation_m_yr), F, p)
    assert warm[-1] < 3.75                                        # warming thins the ice


def test_change_timeseries_neutral_at_baseline():
    ch = pd.DataFrame({"scenario": ["s"] * 3, "mid_year": [2037.5, 2063.0, 2087.5], "change": [1.0, 2.0, 3.0]})
    ts = change_timeseries(ch, [2000, 2037, 2100], "delta")
    assert ts.loc[2000, "s"] == pytest.approx(0.0, abs=0.02)
    assert ts.loc[2100, "s"] == pytest.approx(3.0)
