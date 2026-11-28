# RGVR, RGVRL: the RG case on the 92-25 km variable-resolution mesh x4.163842

RGVR and RGVRL are RG's recipe (`ci/rg/README.md`) on NCAR's 92-25 km variable-resolution mesh x4.163842 (163842
cells; the refinement is centred on 0° N, 0° E, as NCAR publishes it, not rotated), with the same GFS first-guess
file (2026-10-12 00 UTC) and the same `mesoscale_reference` physics suite.

- RGVR, like RG: steps 0-10 with the bisection and initdump streams, then a 2 h forecast with hourly history and one
  restart one step after 1 h.
- RGVRL: a longer forecast (`ci/cases.py` `LONG_CASES`), history and diag every 3 h, one restart one step after the
  midpoint, and no steps phase (`NO_STEPS_CASES`), as RG60L.

## It does not fit in a GitHub runner job

x4.163842 is the smallest of NCAR's published variable-resolution meshes. Its two one-rank trials do not fit in one
job of a standard GitHub runner (ubuntu-24.04: 4 CPUs, 16 GB of memory, the workflow's 355-min limit), so no RGVR or
RGVRL reference is published and ci/rgv48 (x5.30210) is the variable-resolution case. The numbers:

1. Memory. One-rank `atmosphere_model` on 163842 cells has a resident set of 12.9 GB on top of a 6.4 GB
   initialisation, over 15.25 GB at its peak (RG60 without swap, run 46066643405, killed before its first step).
   With the 40 GiB swap file and the capped container (`ci/host.sh`), RG60 runs, using up to 15.1 GB of memory
   plus 24.4 GB of swap (run 46098059159).
2. Time per step. Paging makes a step on 163842 cells take about 190-210 s (RG60: 10 steps in 1930-2157 s,
   20 steps in 3815-4210 s). RGVR's step is 150 s, not RG60's 360 s, because its finest cells are 25 km.
3. The static phase. On x4.163842 it took 3427 s at 15456988 KiB resident (run 46074272693, AMD EPYC 9V74),
   before the GWDO stage stopped on a missing data set (fixed since).
4. So one RGVR trial needs about 3427 + 60 + 10 × 200 (steps) + 48 × 200 (the 2 h forecast) ≈ 15100 s, and the
   two trials about 30200 s (8.4 h) against 21300 s; RGVRL (3 h, no steps) would need about 2 × (3427 + 60 +
   72 × 200) ≈ 35800 s. Even one trial of the short case would take more than 4 hours.

A larger runner or several MPI ranks would change that; neither is used here (references are one-rank runs on
standard runners). The package files stay so that the case can be run where it fits.

## Static fields

NCAR publishes only the grid for its variable-resolution meshes (`x4.163842.tar.gz`: `x4.163842.grid.nc`, the
graph file and its partitions), no static file. So these cases have a fifth phase, `static`, run before `init` in
each trial: `init_atmosphere_model` (one rank, as every run) with the static and GWDO stages on the grid file, which
writes `x4.163842.static.nc`; the trial's `init` then reads that file with RG's init namelist (static stages off,
vertical grid and first-guess interpolation on). Both trials' static files are compared like every other output and
the published one is in `static/`.

The static stage reads the WPS geographic data sets that MPAS 8.4.2 uses for the default `config_*_data` options
(`mpas_init_atm_static.F`, `mpas_init_atm_gwd.F`), each NCAR's WPS tarball, from the `inputs` release (pinned in
`ci/upstream.tsv` and `ci/upstream.sha256`):

| Data set | Used for |
| --- | --- |
| `topo_gmted2010_30s` | terrain (`config_topo_data = 'GMTED2010'`) and the GWDO fields |
| `modis_landuse_20class_30s` | land use (`MODIFIED_IGBP_MODIS_NOAH`) |
| `soiltype_top_30s` | soil category (`STATSGO`) |
| `soiltemp_1deg` | deep soil temperature |
| `greenfrac_fpar_modis` | vegetation fraction (`MODIS`) |
| `albedo_modis` | monthly albedo (`MODIS`) |
| `maxsnowalb_modis` | maximum snow albedo (`MODIS`) |
| `soilgrids` | `soilcomp` and the soil texture layers `soilcl1`-`soilcl4`, read because `config_noahmp_static` is true by default (`mpas_init_atm_static.F:1199`); NCAR's static files hold them too |
| `landuse_30s` | land use for the GWDO statistics, a path fixed in `mpas_init_atm_gwd.F:635` whatever `config_landuse_data` is |

`ci/cases.py` extracts them once per run under `/work/geog/` (each tarball must hold one directory of its name);
the receipt lists their SHA-256 (`cases.<ID>.geog_sha256`).

## Changes from ci/rg

The files here are ci/rg's, with these changes only:

- Every `x1.10242` file name in the streams and in `config_block_decomp_file_prefix` is `x4.163842` (unused on one
  rank). `streams.init_atmosphere` reads `x4.163842.static.nc`, the static phase's output.
- `namelist.atmosphere`: `config_dt = 150.0` (RG: 600.0) and `config_len_disp = 25000.0` (RG: 240000.0). The step
  is chosen for the finest cells, "roughly six times the minimum grid distance in km" (MPAS tutorial); 25 km is the
  grid's `nominalMinDc` (0.0039239 on the unit sphere, 25.0 km on MPAS's 6371.229-km sphere) and the length scale.
  `config_h_ScaleWithMesh` is not set, so its default, true, scales the horizontal eddy viscosities with the grid's
  `meshDensity`. 150 s divides the 30-min radiation interval (12 steps) and both history intervals.
- `namelist.init_atmosphere.static` and `streams.init_atmosphere.static` (new; the static phase's namelist and
  streams): `namelist.init_atmosphere` with `config_static_interp = true`, `config_native_gwd_static = true`,
  `config_vertical_grid = false`, `config_met_interp = false`, `config_frac_seaice = false` (the static step of the
  MPAS Users' Guide) and `config_geog_data_path = '/work/geog/'`; the streams read `x4.163842.grid.nc` and write
  `x4.163842.static.nc`. `config_native_gwd_gsl_static` stays false, as for RG.

`ci/cases.py` changes only `config_run_duration` and the stream intervals, as for RG.
