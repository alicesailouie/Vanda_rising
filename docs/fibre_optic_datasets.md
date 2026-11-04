# Public Antarctic fibre-optic sensing datasets

Survey made on 2026-11-04 with web searches across Zenodo, USAP-DC, the UK Polar Data Centre
and the literature. It is not exhaustive. Contributions are welcome.

| Dataset | Type | Where | Access | Used here? |
|---|---|---|---|---|
| Manos & Shaya, *Borehole temperature measurements using distributed temperature sensing in Allan Hills, Antarctica (2022–2024)*, [USAP-DC 602025](https://www.usap-dc.org/view/dataset/602025), doi:10.15784/602025 | DTS, 7 boreholes (ALHIC1901–ALHIC2401), Dec 2022 to Jan 2025 | Allan Hills, southern Victoria Land, ~100 km NW of Lake Vanda | CC BY 4.0, 17.3 MB zip, reCAPTCHA download | **Yes.** The 10–20 m borehole temperature approximates mean annual surface temperature and is compared with RACMO 2 m T and IMAU-FDM 10 m firn T (`vanda dts-check`). |
| Hudson et al., *Rutford Ice Stream DAS dataset*, [Zenodo 4778368](https://zenodo.org/records/4778368) | DAS on buried and surface fibre, icequake catalogues | Rutford Ice Stream, West Antarctica | CC BY 4.0, 253 MB (MATLAB `.m` files) | No: ice-stream seismology, not lake hydrology. Good material for a separate icequake-detection ML project. |
| *Ambient seismic recordings and DAS: imaging the firn on Rutford Ice Stream*, [Zenodo 5927541](https://zenodo.org/records/5927541) | DAS, 7 h continuous at 100 Hz | Rutford Ice Stream | Listed as restricted | No |
| Downhole DAS seismic profiling at SkyTrain Ice Rise ([*The Cryosphere* 15, 3443, 2021](https://tc.copernicus.org/articles/15/3443/2021/)); data at the UK Polar Data Centre | DAS walkaway VSP in a borehole | SkyTrain Ice Rise, West Antarctica | UK PDC | No |
| South Pole fibre DAS project ([USAP-DC project p0010214](https://www.usap-dc.org/view/project/p0010214)) | DAS on existing telecom fibre | Amundsen-Scott South Pole Station | No public dataset found | No |
| McMurdo Ice Shelf DTS mooring ([*GRL* 41, 6779, 2014](https://ui.adsabs.harvard.edu/abs/2014GeoRL..41.6779K/abstract)) and Amery Ice Shelf borehole DTS | DTS through ice shelf into the cavity | Ross / Amery ice shelves | Papers found; archived data not confirmed | No |

**Dry Valleys:** no fibre-optic deployment in the McMurdo Dry Valleys lakes or streams was
found. A DTS cable through Vanda's ice and upper water column would directly constrain the
basal heat flux `F` that `lakeice.py` currently has to calibrate. That's a concrete use case
for anyone planning field work.
