# Vanda Rising

**Probabilistic, CMIP6-forced projections of Lake Vanda's level, extent and ice cover**
(Wright Valley, McMurdo Dry Valleys, Antarctica)

Lake Vanda is a closed-basin, perennially ice-covered lake that has been filling for decades.
Its volume has grown by more than half, and the rising water flooded and closed the old
Vanda Station. Castendyk, Obryk, Leidman, Gooseff & Hawes (2016) concluded that if current
conditions continue, Vanda will keep rising for about two centuries before reaching a new
equilibrium.

This project asks what that trajectory looks like **under explicit emissions scenarios, with
uncertainty attached**, and how the lake's ice cover responds along the way. It couples three
pieces:

1. **Closed-basin water balance (hybrid physics + ML).** Onyx River inflow is learned from
   summer degree-days with a Gaussian process. Water loss through ice-cover ablation is
   calibrated from the LTER record. Lake area at each level comes from the REMA DEM. Because
   area, and therefore loss, grows as the lake rises, every scenario relaxes toward its own
   equilibrium level. The model reports that level and the e-folding time to reach it.
2. **Perennial lake-ice model.** Surface ablation is balanced by basal freezing
   (McKay et al. 1985; Obryk et al. 2016), driven by RACMO2.3p2 warming and sublimation change.
   The ice's ablation rate and the water balance's loss term describe the same physical flux,
   so their ratio is a built-in **closure test**.
3. **Statistical baseline.** A direct regression from forcing to level change, used to show
   what the physics adds.

On top of that sit **flood mapping** (REMA v2, intersected with Quantarctica's ASMA, historic
site and footprint layers) and an independent **fibre-optic check** of the climate forcing:
distributed temperature sensing (DTS) in Allan Hills boreholes, about 100 km away.

```mermaid
flowchart LR
  RACMO["RACMO2.3p2 SSP1-2.6/2-4.5/5-8.5<br/>ΔT₂ₘ, sublimation ratio"] --> F[Warmed station<br/>temperatures]
  MET[LTER Lake Vanda met] --> F
  F --> GPQ[GP: Onyx inflow] --> WB[Water balance<br/>dV = Q − l·A&#40;h&#41;]
  LV[LTER lake levels] --> CAL[Calibrate loss l] --> WB
  Q[LTER Onyx discharge] --> GPQ
  Q --> CAL
  REMA[REMA v2 DEM] --> H[Hypsometry A&#40;h&#41;] --> WB
  WB --> P[Level, area, equilibrium,<br/>e-folding time] --> INU[Flood extents ×<br/>ASMA / sites]
  RACMO --> ICE[Lake-ice model] --> CL{Closure:<br/>l ≈ a·ρᵢ/ρw}
  CAL --> CL
  DTS[Allan Hills fibre-optic DTS] -. checks .-> RACMO
```

## Status

| Piece | State |
|---|---|
| REMA fetch, lake detection, hypsometry | **Working on real data** (figures below) |
| Water-balance, lake-ice and statistical engines | Working; tested on synthetic data with known parameters |
| LTER lake levels, Onyx discharge, met, ice thickness | **You download these** (EDI has a login and bot check, so scripted downloads aren't possible) |
| RACMO layers | **You download these** from the Quantarctica package |
| Allan Hills DTS check | Reader written; data download sits behind a reCAPTCHA |

### Real data: Lake Vanda hypsometry from REMA v2 (10 m)

![Flood extents](figures/flood_extents_rema.png)
![Hypsometry](figures/hypsometry_rema.png)

The ice surface sits at 41.4 m above the WGS84 ellipsoid. REMA heights are ellipsoidal;
only height differences are used, so no geoid correction is needed. The lake plus the
connected low ground covers about 7.2 km² today. The curve flattens up-valley to the west,
so each metre of rise adds about 0.15–0.2 km².

### Pipeline demo (synthetic data, **not results**)

`vanda demo` runs everything on internally consistent synthetic data. It checks that the
machinery recovers known parameters: calibrated loss 0.325 m/yr against a true 0.33, and a
closure ratio of 1.01. Figures are in [`figures/demo_SYNTHETIC/`](figures/demo_SYNTHETIC/).

![demo projections](figures/demo_SYNTHETIC/projections.png)

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
vanda demo          # synthetic end-to-end run, no downloads
vanda fetch-dem     # REMA v2 window over Lake Vanda (public COGs, no login)
vanda hypsometry    # real level-area-volume curve and flood maps
# ...download LTER and Quantarctica files (docs/data_sources.md), edit config.yaml, then:
vanda run
vanda dts-check     # optional: Allan Hills fibre-optic DTS vs RACMO / IMAU-FDM
pytest
```

## Research questions

1. **Trajectory.** How high will Vanda be in 2050 and 2100 under SSP1-2.6, SSP2-4.5 and
   SSP5-8.5, and how wide are the uncertainty bands?
2. **Equilibrium.** What level and area balance inflow against ablation in each scenario's
   late-century climate? Is the e-folding time consistent with the two-century adjustment
   that Castendyk et al. (2016) described?
3. **Ice cover.** Does warming thin Vanda's ~3.5–4 m ice (Hawes et al. 2013), and over what
   response time? Does the ice model's ablation agree with the water balance's loss term?
4. **Footprint.** Which protected-area zones, historic sites and disturbance footprints do the
   projected shorelines reach?
5. **Forcing credibility.** Do RACMO 2 m temperature and IMAU-FDM firn temperature match the
   DTS-measured near-surface ice temperature at Allan Hills?

## Method notes and honest limitations

- **Delta change.** RACMO's 27 km grid cannot resolve the valley (and its föhn events), so
  only RACMO *changes* are used. Annual-mean warming is applied evenly to every summer hour.
  That's a first-order assumption, because summer warming can differ from the annual mean.
- **Extrapolation.** Warm-scenario summers can lie outside the observed degree-day range.
  The GP has a linear kernel term so it doesn't revert to the mean outside the data, and
  every projection reports `frac_outside_training`. Read high-end SSP5-8.5 numbers with that
  in mind.
- **Bathymetry.** The DEM sees only the ground above today's level. That is enough for a
  rising lake, but it means the model cannot handle a falling one.
- **Glacier supply is treated as unlimited.** Inflow responds to degree-days only. Changes in
  the Wright Lower Glacier itself (ITS_LIVE velocity, ICESat-2 elevation change, both in
  Quantarctica) are a natural next step.
- **Lumped ice physics.** The basal flux `F` lumps water-column heat with shortwave absorbed
  in the ice. Obryk et al. (2016) resolve these separately; this model does not.
- **DEM epoch.** Set `lter.rema_epoch` to the REMA acquisition date (see the tile `meta.txt`
  files) so flood extents start from the right shoreline.

## Fibre-optic sensing

Public Antarctic fibre-optic datasets found (Nov 2026) and how they are used:
[docs/fibre_optic_datasets.md](docs/fibre_optic_datasets.md). No DAS or DTS deployment in the
Dry Valleys turned up. The Allan Hills borehole DTS is the closest and serves as a forcing check.

## Key references

- Castendyk, D.N., Obryk, M.K., Leidman, S.Z., Gooseff, M., Hawes, I. (2016). Lake Vanda: a sentinel for climate change in the McMurdo Sound Region of Antarctica. *Global and Planetary Change* 144, 213–227. doi:10.1016/j.gloplacha.2016.06.007
- Hawes, I., Sumner, D.Y., Andersen, D.T., Jungblut, A.D., Mackey, T.J. (2013). Timescales of growth response of microbial mats to environmental change in an ice-covered Antarctic lake. *Biology* 2, 151–176. doi:10.3390/biology2010151. Source for Vanda's lake-level history, its 3.5–4 m ice and light transmission.
- Obryk, M.K., et al. (2016). Modeling the thickness of perennial ice covers on stratified lakes of the Taylor Valley, Antarctica. *Journal of Glaciology*.
- McKay, C.P., Clow, G.D., Wharton, R.A., Squyres, S.W. (1985). Thickness of ice on perennially frozen lakes. *Nature* 313, 561–562.
- Data sources and licences: [docs/data_sources.md](docs/data_sources.md).

## Licence

Code: MIT (see `LICENSE`). Data keep their own licences; cite them as listed in
`docs/data_sources.md`. This is an independent hobby project and is not affiliated with the
McMurdo LTER, Antarctica New Zealand or the cited authors.
