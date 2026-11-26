# RG: real-data case inputs

The namelists, streams and stream lists here are MPAS v8.4.2's generated defaults: `namelist_gen` and `streams_gen`
from `src/tools/input_gen`, run on `Registry.xml` preprocessed with the reference build's own `cpp` flags, as
`core_input_gen` does in the core Makefiles. The only changes from those defaults are listed below.

`namelist.init_atmosphere` (init case 7, already the default):
- `config_start_time`, `config_stop_time` = `2026-10-12_00:00:00`, the time of the GFS analysis.
- `config_met_prefix = 'FILE'`, so the first-guess file is staged as `FILE:2026-10-12_00`.
- `config_static_interp = false`, `config_native_gwd_static = false`, `config_native_gwd_gsl_static = false`:
  NCAR's published `x1.10242.static.nc` already holds the static fields, including the subgrid-orography fields
  `var2d`, `con`, `oa1`–`oa4` and `ol1`–`ol4`, so no geographic data set is needed.
- `config_vertical_grid = true`, `config_met_interp = true`, `config_input_sst = false`,
  `config_frac_seaice = true`. These are the defaults, stated explicitly.
- `config_block_decomp_file_prefix = 'x1.10242.graph.info.part.'`. It is unused on one rank.

`namelist.atmosphere` (`config_physics_suite = 'mesoscale_reference'`, the default):
- `config_dt = 600.0`, `config_len_disp = 240000.0` (the mesh's 240-km spacing), and `config_start_time`.
- `config_run_duration` is set by `ci/cases.py`.
- `config_block_decomp_file_prefix` as above.

Streams: the file names are `x1.10242.*` instead of the template's `x1.40962.*`, and the history (`output`) stream
writes every hour.

Inputs, from the `inputs` release:
- `x1.10242_static.tar.gz`, NCAR's archive.
- `rg-gfs-20261012T00.wps`, the WPS 4.6.0 intermediate file of the NCEP GFS 0.25° analysis at 2026-10-12 00 UTC,
  with 33 pressure levels plus the surface.
