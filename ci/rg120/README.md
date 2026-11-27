# RG120, RG120L: the RG case on the 120-km quasi-uniform mesh x1.40962

RG120 and RG120L are RG's recipe (`ci/rg/README.md`) on NCAR's 120-km quasi-uniform mesh (40962 cells, four times
RG's), with the same GFS first-guess file (2026-10-12 00 UTC) and the same `mesoscale_reference` physics suite.

- RG120, like RG: steps 0-10 with the bisection and initdump streams, then a forecast of 11 steps (2 h 12 min, the
  recipe's minimum when two history intervals are shorter than 11 steps) with hourly history and one restart one
  step after the midpoint.
- RG120L: a 48 h forecast (`ci/cases.py` `LONG_CASES`), history and diag every 3 h, one restart one step after 24 h,
  plus the steps phase as RG24 has.

## Inputs

- `x1.40962_static.tar.gz`, NCAR's archive (`x1.40962.static.nc`, `x1.40962.graph.info`), from the `inputs`
  release, pinned in `ci/upstream.tsv` and `ci/upstream.sha256`. The static file holds the subgrid-orography fields
  (`var2d`, `con`, `oa1`-`oa4`, `ol1`-`ol4`) and the Noah-MP soil fields; its `nominalMinDc` is 120000 m.
- `rg-gfs-20261012T00.wps`, RG's first-guess file.

## Changes from ci/rg

- Every `x1.10242` file name in the streams and in `config_block_decomp_file_prefix` is `x1.40962`.
- `namelist.atmosphere`: `config_dt = 720.0` (RG: 600.0), MPAS's default time step, which is for this mesh (six times
  the 120-km grid distance), and `config_len_disp = 120000.0` (RG: 240000.0), the static file's `nominalMinDc`.

`ci/cases.py` changes only `config_run_duration` and the stream intervals, as for RG.
