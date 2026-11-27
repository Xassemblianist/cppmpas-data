# RGV48, RGV48L: the RG case on the 240-48 km variable-resolution mesh x5.30210

RGV48 and RGV48L are RG's recipe (`ci/rg/README.md`) on NCAR's 240-48 km variable-resolution mesh x5.30210 (30210
cells; the refinement is centred on 0° N, 0° E, as NCAR publishes it), the mesh of the MPAS tutorial's
variable-resolution exercise, with the same GFS first-guess file (2026-10-12 00 UTC) and the same
`mesoscale_reference` physics suite.

- RGV48, like RG: steps 0-10 with the bisection and initdump streams, then a 2 h forecast with hourly history and
  one restart one step after 1 h.
- RGV48L: a 12 h forecast (`ci/cases.py` `LONG_CASES`), history and diag every 3 h, one restart one step after 6 h,
  and no steps phase (`NO_STEPS_CASES`; RGV48 has it): with two static phases of about 40 minutes each, a 24 h
  forecast (360 steps of 240 s, about 25 s each) twice does not fit in the 6-hour job.

## Why this mesh

NCAR's variable-resolution meshes on its mesh page start at 163842 cells (92-25 km x4.163842, ci/rgvr). One-rank
`atmosphere_model` on 163842 cells needs more than a standard GitHub runner's 16 GB (the measurements are in
ci/rg60/README.md and the top-level README), so this case uses the largest NCAR variable-resolution mesh that fits:
x5.30210, which NCAR serves from the same mesh directory
(`https://www2.mmm.ucar.edu/projects/mpas/atmosphere_meshes/x5.30210.tar.gz`) and uses in its tutorial.

## Static fields

NCAR publishes only the grid for its variable-resolution meshes (`x5.30210.tar.gz`: `x5.30210.grid.nc`, the
graph file and its partitions), no static file. So these cases have a fifth phase, `static`, run before `init` in
each trial: `init_atmosphere_model` (one rank, as every run) with the static and GWDO stages on the grid file, which
writes `x5.30210.static.nc`; the trial's `init` then reads that file with RG's init namelist (static stages off,
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

## Changes from ci/rgvr

The files here are ci/rgvr's, with these changes only:

- Every `x4.163842` file name is `x5.30210`, in the streams, the static streams and `config_block_decomp_file_prefix`.
- `namelist.atmosphere`: `config_dt = 240.0` (the value the MPAS tutorial gives for this mesh: "a value of 240
  seconds is reasonable") and `config_len_disp = 48000.0`, the grid's `nominalMinDc` (48.0 km on MPAS's
  6371.229-km sphere). As in RGVR, `config_h_ScaleWithMesh` keeps its default, true.

`ci/cases.py` changes only `config_run_duration` and the stream intervals, as for RG.
