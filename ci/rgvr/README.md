# RGVR, RGVRL: the RG case on the 92-25 km variable-resolution mesh x4.163842

RGVR and RGVRL are RG's recipe (`ci/rg/README.md`) on NCAR's 92-25 km variable-resolution mesh x4.163842 (163842
cells; the refinement is centred on 0° N, 0° E, as NCAR publishes it, not rotated), with the same GFS first-guess
file (2026-10-12 00 UTC) and the same `mesoscale_reference` physics suite.

- RGVR, like RG: steps 0-10 with the bisection and initdump streams, then a 2 h forecast with hourly history and one
  restart one step after 1 h.
- RGVRL: a longer forecast (`ci/cases.py` `LONG_CASES`), history and diag every 3 h, one restart one step after the
  midpoint, and no steps phase (`NO_STEPS_CASES`), as RG60L.

## Why this mesh

It is the largest of NCAR's variable-resolution meshes whose two one-rank trials fit in one GitHub runner job
(ubuntu-24.04: 4 CPUs, 16 GB of memory, 6-h job limit). The next one, 60-15 km x4.535554, has 535554 cells (3.3
times as many) and needs a 90 s step (six times 15 km) instead of 150 s: about 8 times the work per simulated hour.
The numbers measured on the runner are in the top-level README.

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
