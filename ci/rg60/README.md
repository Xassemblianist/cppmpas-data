# RG60, RG60L: the RG case on the 60-km quasi-uniform mesh x1.163842

RG60 and RG60L are RG's recipe (`ci/rg/README.md`) on NCAR's 60-km quasi-uniform mesh (163842 cells, 491520 edges,
327680 vertices), with the same GFS first-guess file (`rg-gfs-20261012T00.wps`, 2026-10-12 00 UTC) and the same
`mesoscale_reference` physics suite.

- RG60, like RG: steps 0-10 with the bisection and initdump streams, then a 2 h forecast with hourly history and one
  restart one step after 1 h.
- RG60L: a longer forecast (`ci/cases.py` `LONG_CASES`), history and diag every 3 h, one restart one step after the
  midpoint. It has no steps phase (`NO_STEPS_CASES`): RG60 has the bisection files, and leaving them out lets both
  trials' forecasts fit in one runner job.

## Inputs

- `x1.163842_static.tar.gz`, NCAR's archive (`x1.163842.static.nc`, `x1.163842.graph.info`), from the `inputs`
  release, pinned in `ci/upstream.tsv` and `ci/upstream.sha256`. Like `x1.10242.static.nc`, the static file already
  holds the subgrid-orography fields `var2d`, `con`, `oa1`-`oa4`, `ol1`-`ol4`, and its `nominalMinDc` is 60000 m.
- `rg-gfs-20261012T00.wps`, RG's first-guess file.

## Changes from ci/rg

The files here are ci/rg's, with these changes only:

- Every `x1.10242` file name in the streams and in `config_block_decomp_file_prefix` is `x1.163842` (unused on one
  rank).
- `namelist.atmosphere`: `config_dt = 360.0` (RG: 600.0) and `config_len_disp = 60000.0` (RG: 240000.0).
  The time step follows NCAR's rule of thumb, "roughly six times the minimum grid distance in km" (MPAS tutorial,
  regional exercise, which uses `config_dt = 360.0` on a subset of this mesh); the length scale is the mesh's grid
  distance, which is also the static file's `nominalMinDc`. 360 s divides the 30-min radiation interval (5 steps),
  the 1-h history interval of RG60 and the 3-h one of RG60L.

`ci/cases.py` changes only `config_run_duration` and the stream intervals, as for RG.

## Memory and time

One-rank `atmosphere_model` on this mesh needs more than the 16 GB of a standard GitHub runner: the first attempt
(run 46066643405, Intel Xeon 6975P-C, MemTotal 16078396 kB, no swap) was killed by the kernel at a peak resident set
of 15251176 KiB, 8 s into the steps run, before its first time step (`init_atmosphere_model` peaked at 6404936 KiB).
`ci/host.sh` therefore adds a swap file (`ci/cases.py` `SWAP_GIB`, 40 GiB) on the runner disk for RG60, RG60L, RGVR
and RGVRL, caps the container's memory 3 GiB below the runner's so that the model's pages, not the runner agent's,
go to swap (without the cap the runner lost contact with GitHub: runs 46070002759, 46070005979), and prints the
peak of used memory plus swap. Swap moves pages, not values: the run is the same one-rank run.

With the swap file, RG60's two trials ran in run 46076631636 (Intel Xeon 6975P-C, 4 CPUs) and matched in all 18
NetCDF files:

| Phase | Trial A | Trial B | Peak resident set |
| --- | --- | --- | --- |
| init | 53.1 s | 54.7 s | 6405040 KiB |
| steps (10 steps) | 1999.7 s | 2157.0 s | 12929188 KiB |
| forecast (2 h, 20 steps) | 4210.4 s | 4051.6 s | 12916172 KiB |

Used memory plus swap peaked at 39102264 KiB (14872336 KiB of memory, 24229928 KiB of swap). About 200 s per step,
paging included, sets RG60L's length: a 3 h forecast (30 steps, about 6300 s per trial) is the longest whose two
trials and packing fit in the job's 355-min limit with room for a slower runner; 6 h would need about 7 h.
