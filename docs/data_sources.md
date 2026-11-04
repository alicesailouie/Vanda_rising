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
| `met_csv` | Lake Vanda meteorological station (search EDI for "Lake Vanda meteorological") | Air temperature, plus wind if present. Sub-daily data preferred. |
| `discharge_csv` | Onyx River at Lake Vanda weir (search EDI for "Onyx River Lake Vanda discharge") | The gauge record begins in 1969. Units default to L/s (`discharge_units`). |
| `ice_thickness_csv` | MCM LTER lake ice thickness (search EDI for "lake ice thickness") | Optional; enables the lake-ice model. |

Cite each package with the DOI shown on its EDI landing page and follow the
[MCM LTER data use policy](https://mcm.lternet.edu/).

Older lake levels (before 1991) appear in the literature, for example Castendyk et al. 2016
and Hawes et al. 2013 (Fig. 1). If you digitise them, append them to the levels CSV and note
it in your README.

## Manual: Quantarctica (Norwegian Polar Institute)

Download the Quantarctica package or individual layers from the
[data catalog](https://sites.npolar.no/quantarctica/data-catalog/) and export the rasters as
GeoTIFF into `data/raw/quantarctica/`.

| Layer | Used for | Reference |
|---|---|---|
| 2 m temperature 1979–2022, van Wessem RACMO2.3p2-ERA5 | baseline for temperature deltas | doi:10.5281/zenodo.7845736; van Wessem et al. 2018, doi:10.5194/tc-12-1479-2018 |
| 2 m temperature 2025–2050 / 2051–2075 / 2076–2099 (SSP1-2.6, SSP2-4.5, SSP5-8.5), van Wessem RACMO2.3p2 | future temperature deltas | doi:10.5281/zenodo.6416973; doi:10.1038/s41558-022-01577-1 |
| Sublimation 1979–2022 and future periods, van Wessem RACMO2.3p2 | ablation ratio | as above |
| 10 m firn temperature, Veldhuijsen IMAU-FDM | DTS check | doi:10.5194/tc-17-1675-2023 |
| ASMA, ASPA polygons, Historic Sites and Monuments (ATS); building and ground disturbance footprints (Brooks) | flood intersection | see each catalogue entry |
| Ice surface flow speed (ITS_LIVE), ICESat-2 ATL15 elevation change | future work: Wright Lower Glacier | see catalogue |

## Manual: fibre-optic DTS

`dts.allan_hills_dir`: unzip `temp_data_sorted_by_borehole.zip` from
[USAP-DC 602025](https://www.usap-dc.org/view/dataset/602025) (reCAPTCHA). Manos & Shaya,
doi:10.15784/602025, CC BY 4.0.
