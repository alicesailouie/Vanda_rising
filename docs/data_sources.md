# Data sources

Nothing in `data/` is committed. Place files at the paths in `config.yaml`, or edit the paths.

## Scripted (no login)

| Data | How | Licence / citation |
|---|---|---|
| REMA v2 mosaic, 10 m (or 2 m) | `vanda fetch-dem` reads tiles `17_35` and `18_35` from the PGC STAC API (`stac.pgc.umn.edu`, collection `rema-mosaics-v2.0-10m`) as cloud-optimised GeoTIFFs | Howat et al. (2019), *The Cryosphere* 13, 665, doi:10.5194/tc-13-665-2019; data doi:10.7910/DVN/EBW8UC. Acknowledge PGC per its policy. |

## Manual: McMurdo Dry Valleys LTER (EDI)

EDI's portal and its PASTA API now require a login and bot check for downloads. Download the
CSVs in a browser and save them under `data/raw/lter/`. The readers detect column names by
keyword; if a guess is wrong, set the names under `lter.columns` in `config.yaml`.

| File (`config.yaml` key) | EDI package | Notes |
|---|---|---|
| `lake_levels_csv` | **knb-lter-mcm.68**, "Lake level surveys in the McMurdo Dry Valleys, 1991 to present" | Surveyed with rod and level, usually in Oct–Nov and Jan–Feb. The reader keeps Vanda rows (`lake_filter`). |
| `met_csv` | **knb-lter-mcm.7015**, Lake Vanda met station (VAAM), 15-minute data | Air temperature, plus wind if present. Use this rather than the monthly summaries (knb-lter-mcm.7215), because degree-days need sub-daily data. |
| `discharge_csv` | **knb-lter-mcm.9122**, Onyx River at Lake Vanda weir, daily summaries (or knb-lter-mcm.9022 for 15-minute data) | The gauge record begins in 1969. Units default to L/s (`discharge_units`). |
| `ice_thickness_csv` | **knb-lter-mcm.67**, lake ice thickness and density | Optional; enables the lake-ice model. Check that it includes Vanda rows: older versions cover Taylor Valley only. |

Cite each package with the DOI shown on its EDI landing page and follow the
[MCM LTER data use policy](https://mcm.lternet.edu/).

Older lake levels (before 1991) appear in the literature, for example Castendyk et al. 2016
and Hawes et al. 2013 (Fig. 1). If you digitise them, append them to the levels CSV and note
it in your README.

LTER files on Windows: the full paths of the original names exceed the 260-character limit,
so `config.yaml` uses short names: `levels.csv`, `met_hr.csv` (`clim_vaam_hourly.csv`),
`onyx_d.csv` and `ice.csv`.

## Manual: RACMO2.3p2 climate projections (Zenodo)

From [Zenodo 6416973](https://zenodo.org/records/6416973) (van Wessem et al.,
doi:10.1038/s41558-022-01577-1), download these nine files and save them in
`data/raw/racmo/` under the short names shown:

| Zenodo file | Save as |
|---|---|
| `t2m_yearlyA_ANT27_CESM2_RACMO2.3p2_hist_r567_1950_2014.nc` | `t2m_hist.nc` |
| `t2m_yearlyA_ANT27_CESM2_RACMO2.3p2_SSP126_r567_2011_2099.nc` | `t2m_SSP126.nc` |
| `t2m_yearlyA_ANT27_CESM2_RACMO2.3p2_SSP245_r567_2011_2099.nc` | `t2m_SSP245.nc` |
| `t2m_yearlyA_ANT27_CESM2_RACMO2.3p2_SSP585_r567_2015_2099.nc` | `t2m_SSP585.nc` |
| `subl_yearlyS_ANT27_CESM2_RACMO2.3p2_hist_r567_1950_2014.nc` | `subl_hist.nc` |
| `subl_yearlyS_ANT27_CESM2_RACMO2.3p2_SSP126_r567_2011_2099.nc` | `subl_SSP126.nc` |
| `subl_yearlyS_ANT27_CESM2_RACMO2.3p2_SSP245_r567_2011_2099.nc` | `subl_SSP245.nc` |
| `subl_yearlyS_ANT27_CESM2_RACMO2.3p2_SSP585_r567_2015_2099.nc` | `subl_SSP585.nc` |
| `Height_latlon_ANT27.nc` | `grid.nc` |

The historical and SSP runs share one model chain (CESM2 → RACMO2.3p2), so the model's bias
cancels in the change. The ERA5-driven monthly record (Zenodo 7845736) is not needed.

## Manual: Quantarctica (Norwegian Polar Institute)

Optional layers from the [data catalog](https://sites.npolar.no/quantarctica/data-catalog/):

| Layer | Used for | Reference |
|---|---|---|
| ASMA, ASPA polygons, Historic Sites and Monuments (ATS); building and ground disturbance footprints (Brooks) | flood intersection | see each catalogue entry |
| Ice surface flow speed (ITS_LIVE), ICESat-2 ATL15 elevation change | future work: Wright Lower Glacier | see catalogue |
