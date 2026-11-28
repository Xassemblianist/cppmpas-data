# CPPMPAS reference data

Recipes and release assets for the MPAS-Atmosphere 8.4.2 references that define "correct" for CPPMPAS.
The source is MPAS-Model commit `f34984b2c89353cf31c235b08d3b4acd96b37bb3`
([v8.4.2](https://github.com/MPAS-Dev/MPAS-Model/releases/tag/v8.4.2)), built with GNU Fortran 14.2,
glibc 2.41, Open MPI 5.0.7, netCDF and PnetCDF from a dated Debian 13 snapshot, with MPAS's bundled SMIOL
for I/O (every file is CDF-5).

| ID | Case | Package |
| --- | --- | --- |
| JW | Jablonowski–Williamson baroclinic wave, `config_init_case = 2` | x1.40962 mesh (about 120 km), 26 levels |
| SC | Supercell with Kessler microphysics, `config_init_case = 5` | doubly periodic supercell mesh, 40 levels |
| MW | Mountain wave, `config_init_case = 6` | mountain-wave mesh, 70 levels |

The packages are the [NCAR idealized test cases](https://www2.mmm.ucar.edu/projects/mpas/site/downloads/idealized.html).

## What a reference is

Every model launch is `mpiexec -n 1` (no OpenMP, no OpenACC), in the same container image the executables
were built in. glibc selects its FMA/AVX2 libm variants; the workflow refuses a runner CPU without AVX2, FMA
and SSE4.1 and records the CPU. Each case runs as two independent trials (initialisation, short run, long
run), and the reference is published only when the two trials match.

Cases: JW (Jablonowski-Williamson baroclinic wave), SC (supercell, Kessler), MW (mountain wave) from NCAR's
idealized test-case packages, and RG: a real-data forecast on the 240-km x1.10242 mesh with the mesoscale_reference
physics suite from one GFS analysis (inputs and changes in ci/rg/README.md), with RG24 its 24 h forecast, RGR its
restart run and RGR24 the restart of RG24 (below); and RGCP
and RGCP24: the same two runs with the convection_permitting suite (Thompson, Grell-Freitas, MYNN), whose Thompson
tables MPAS's build_tables writes in each trial (ci/rgcp/README.md); RG60 and RG60L: RG's recipe on NCAR's 60-km
quasi-uniform mesh x1.163842 (ci/rg60/README.md); RG120 and RG120L: on the 120-km x1.40962 (ci/rg120/README.md);
RGV48 and RGV48L: on NCAR's 240-48 km variable-resolution mesh x5.30210, whose static fields MPAS's init_atmosphere
computes in each trial from WPS geographic data (ci/rgv48/README.md). RGDEF: MPAS's own generated default namelist and streams on x1.40962
(dt 720 s, config_len_disp from the mesh, 6 h history, 3 h diagnostics, daily restart) for 24 h, changed only in the
start time (ci/rgdef/README.md); RGDT: the same with dt 480 s and a 09 UTC start, 6 h (ci/rgdt/README.md). RGVR and RGVRL, the same on the 92-25 km
x4.163842, are defined but do not fit in a runner job (ci/rgvr/README.md). Every run preloads CPPWRF's Intel libmvec log/log10
(ci/mvec_intel, see ci/ref.py), because the physics' vectorised logs differ in the last bits between Intel and AMD
CPUs; with it the references are the same on any runner.

Per case directory:

- `init/`: the initial conditions written by `init_atmosphere_model`, with its namelist, streams and logs.
- `steps/`: `step.*.nc`, the state after steps 0 to 10 in double precision (`u`, `w`, `rho_zz`, `theta_m`,
  the `scalars` array, and the diagnosed `rho`, `theta`, `pressure_p`), written by a 10-step run in which
  every other output stream is off. The same run writes `initdump.nc`: one record at the initial time with the
  fields `atm_mpas_init_block` computes before the first step and no package stream writes (mesh coefficients,
  `atm_init_coupled_diagnostics`, the initial solve diagnostics and reconstruction; list in `ci/cases.py`
  `INITDUMP_FIELDS`). It is an ordinary MPAS output stream (`output_interval="initial_only"`), so the
  executables are unchanged and the stream changes no computed value.
- `forecast/`: a run of two package history intervals (at least 11 steps) with the package history stream
  unchanged and one restart checkpoint, written one step after the midpoint, with its `restart_timestamp`.
- `static/` (RGV48, RGV48L, RGVR, RGVRL only): the mesh's `static.nc`, written by `init_atmosphere_model`'s static
  and GWDO stages from the grid file and the geographic data sets; the trial's `init/` reads it. RG60L, RGV48L and
  RGVRL have no `steps/`.
- `tables/` (RGCP, RGCP24 only): the four `MP_THOMPSON_*_DATA.DBL` tables that `build_tables` wrote in that trial,
  and its output (`build_tables.log`); both atmosphere runs read them.
- `package/`: the case's namelists, streams, stream lists, tables and README as published (without the mesh,
  whose SHA-256 is in `provenance.json`); `configuration.diff` shows every edit made for the runs.
- `plan.json`: timestep, history interval, run lengths and restart time; `determinism.txt`: the comparison.

The top level holds `provenance.json` (build asset and recipe hashes, make commands and options, link lines,
executable hashes, Debian snapshot and package versions, container base digest, runner CPU and image, MPI
settings, input and mesh hashes, timings), `build-metadata/` (toolchain versions, compressed build logs,
`ldd` output, package list, the build's own `SHA256SUMS`), `recipe/` (the `ci/` scripts and workflows of the
commit that made it) and `SHA256SUMS`.

Before publishing, every trial is checked: the expected step, history and restart times; every floating-point
variable is 8 bytes and finite; every model output descends from that trial's own initial file; no `log.*.err`
was written. The two trials must then have the same NetCDF files with the same format, dimensions, variables,
variable attributes, global attributes and raw value bytes, all in the same order, and the same text files.
The only exception is in two global attributes that MPAS fills with random characters from `rand()` seeded
by the wall clock: `file_id` (compared only as ten characters from `[0-9a-z]`) and the leading lines of
`parent_id` that have that form (the `file_id` of the run's input file, then that file's own `parent_id`: init's,
and in the static cases the static file's); the rest of `parent_id` is compared, and each trial's chain must name
its own files.

## Releases

- `inputs`: the pinned upstream tarballs and files, listed with their origin in [ci/upstream.tsv](ci/upstream.tsv)
  and checked against [ci/upstream.sha256](ci/upstream.sha256). The workflows download inputs only from here,
  because GitHub's generated source archives are not guaranteed to be byte-stable.
- `mpas-build`: `mpas-8.4.2-<flavour>-<recipe>.tar.zst`, where `<recipe>` is the SHA-256 of the image recipe,
  `ci/build.sh` and the four source tarball hashes. Each holds both executables, the physics tables, licenses
  and metadata.
- one release per reference tag: `<tag>.tar.zst.part00`, `.part01`, … (release assets must be under 2 GiB) and
  `<tag>.sha256` with the hashes of every part and of the joined archive.

Build assets from commit 8739add on also hold `bin/build_tables` (built by `make atmosphere` with the same compiler
and flags). `mpas-build` with `verify=true` builds the published asset of the current recipe a second time and
fails unless `bin/`, `tables/` and `licenses/` are bit-identical; `refcompare` fetches two reference releases,
checks their hashes and compares every case file (NetCDF as above, every other file byte for byte, MPAS's own
logs excepted), printing each side's runner CPU.

## Restart reference

RGR is RG's init and 2 h forecast (the same namelists and streams, so the same 01:10 checkpoint) followed by a fourth
phase, `restart/`: `atmosphere_model` with `config_do_restart = true` and `config_start_time = '2026-10-12_01:10:00'`,
reading the forecast's `restart.2026-10-12_01.10.00.nc`, for 1 h 40 min (to 02:50). RGR has no `steps/`.

MPAS starts every output alarm and the physics alarms (radiation, the physics diagnostics, ...) at the clock's start
time, which on a restart is the checkpoint (`xml_stream_parser.c` reference_time `initial_time`,
`mpas_atmphys_manager.F` physics_run_init), and it writes no history or diagnostics at that time
(`mpas_atm_core.F:669-673`). So the restart run's history and diagnostics streams write every 50 min (02:00 and
02:50): 02:00 is a history time of the forecast. Its own checkpoint is one step after the midpoint, as in the other
cases: `restart.2026-10-12_02.10.00.nc`, with `restart_timestamp`. Each trial's restart outputs must descend from
that trial's checkpoint and init file (`parent_id`).

`RGR/continuity.txt` records MPAS against itself: the restart run's history at 02:00 against the uninterrupted
forecast's, variable by variable (ci/cases.py `continuity`). A difference there is recorded, not an error.

RGR24 is the long restart: RG24's init and 24 h forecast (the same namelists and streams, so the same 12:10
checkpoint), then `restart/` from `restart.2026-10-12_12.10.00.nc` with `config_start_time = '2026-10-12_12:10:00'`
to 24:00 (11 h 50 min, 71 steps). Its history and diagnostics streams write every 3 h after the restart (15:10,
18:10, 21:10) and its checkpoint is written at the end, `restart.2026-10-13_00.00.00.nc`, so the final state is in
the reference. 71 is prime: no output interval longer than one step both divides the run and ends at 24:00, and no
restart-run output falls on a 3-hourly history time of the forecast. `RGR24/continuity.txt` therefore compares the
24:00 checkpoint with the forecast's 24:00 history in the variables both hold. RGR24 has no `steps/`.

| Tag | Case | Run | Runner CPU | Size | Archive SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `mpas842-dbl-rgr-001` | RGR | 46131461178 | Intel Xeon 6975P-C | 1352722570 B (1 part) | `c4720917afbbfed2e2080187fb2378eb07196c1d42562ac2c426f342debc8264` |
| `mpas842-dbl-rgr-003` | RGR | 46135179230 | AMD EPYC 9V45 | 1352722492 B (1 part) | `e0f34e7519c1c63828aea8b48bed6d6754e310a0a22f88e0819e84e9a99a9eb7` |
| `mpas842-dbl-rgr24-001` | RGR24 | 46150240751 | Intel Xeon 6975P-C | 2040511681 B (2 parts) | `6025cb8ae7b3a1881ef01d05fc5bf9bff38a073ffd0519bca7ad2ec241a45d33` |
| `mpas842-dbl-rgr24-002` | RGR24 | 46150243641 | AMD EPYC 9V74 | 2040511671 B (2 parts) | `f32203c03189fb233c655ab4d106175da91c06155e856fe8a3ff0b869b7e7a1c` |

Both from build asset `mpas-8.4.2-double-7be24aab….tar.zst`; each run's two trials were identical, and rgr-001 =
rgr-003 (`refcompare` run 46135943408: 129 files, 11 NetCDF, 0 differences). (`mpas842-dbl-rgr-002` does not exist:
its dispatches with `cpu_vendor=AuthenticAMD` drew Intel runners and stopped before any work.) RGR's forecast
equals rg-004's in every variable. MPAS's restarted run does not continue its uninterrupted forecast bit for bit: at
02:00, 45 of the 99 history variables differ (`continuity.txt`), among them the state (u, w, theta, rho, the
moist species), the surface and soil fields and the accumulated rain; the alarms that start again at 01:10 are one
cause (radiation at 01:10 and 01:40 instead of 01:30).

rgr24-001 = rgr24-002 (`refcompare` run 46155516685: 145 files, 27 NetCDF, 0 differences); each run's two trials
were identical, and RGR24's 12:10 checkpoint equals rg24-001's in every variable (only parent_id, whose first line is
the random file_id of the trial's init file, differs). At 24:00 the restart run's checkpoint and the uninterrupted
forecast's history differ in 38 of the 90 variables both hold (`RGR24/continuity.txt`): the moist species, u, w, rho,
theta, surface pressure, the accumulated rain, the PBL and surface fields and the soil state.

## convection_permitting references

| Tag | Case | Run | Runner CPU | Size | Archive SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `mpas842-dbl-rgcp-001` | RGCP | 46013527381 | Intel Xeon 6975P-C | 1873269384 B (1 part) | `3abb3d828df91f7e631a68279a3b0052d0254c1413afb0a4e4faa9e73275afbb` |
| `mpas842-dbl-rgcp24-001` | RGCP24 | 46032373796 | Intel Xeon 6975P-C | 2482191079 B (2 parts) | `e82ed02ee318c231f99a75d2d5e2dad26f6680d7a895893ffba4c3c1a9633e99` |

Both come from build asset `mpas-8.4.2-double-7be24aab….tar.zst` (SHA-256 `40313ccf…66c4`), whose
`atmosphere_model` and `init_atmosphere_model` are bit-identical to those of the earlier asset that made the RG
references; a second build (mpas-build verify, run 46013523007) gave a byte-identical archive. Each run's two
trials were identical, tables included. Cross-checks, compared with `refcompare` (0 differences in every case file):

- rgcp-001 = rgcp-002 (Intel, run 46018881505); rgcp-003 (Intel) also passed its own two-trial check;
- rgcp-001 = rgcp-004 (AMD EPYC 9V74, run 46022359710);
- rgcp24-001 = rgcp24-003 (AMD EPYC 7763, run 46040434563).

So with the Intel log/log10 preload, Intel and AMD runners give the same convection_permitting references; no other
libmvec function needed replacing (ci/rgcp/README.md). The Thompson tables are also attached to
`mpas842-dbl-rgcp-001` as separate assets with `mpas842-dbl-rgcp-001.tables.sha256`.

## Larger-mesh references

RG's recipe (one GFS analysis, 2026-10-12 00 UTC, mesoscale_reference suite) on larger NCAR meshes, every run on one
MPI rank of a standard ubuntu-24.04 runner (4 CPUs, 16 GB). Namelist changes, inputs and the measured times and
memory are in each case's README.

| Tag | Case | Run | Runner CPU | Size | Archive SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `mpas842-dbl-rg60-001` | RG60 | 46098059159 | Intel Xeon 6975P-C | 21420550594 B (11 parts) | `d20f2e7f0009dfaf1837bdf60490b0a4364906da0950ee5b7d12b1fb6d2f1013` |
| `mpas842-dbl-rg60-002` | RG60 | 46097673427 | AMD EPYC 9V45 | 21420550645 B (11 parts) | `28cd16b173d2c6b976464d5e31a476c5ab51046c38490b7307729084ad2dd887` |
| `mpas842-dbl-rg60l-001` | RG60L (3 h) | 46097281302 | Intel Xeon 6975P-C | 8959612967 B (5 parts) | `78c9275d8dd352364e55b44a5da44d14b7facdd43754c9d273fb92a56035dd11` |
| `mpas842-dbl-rg120-001` | RG120 | 46076914266 | Intel Xeon 6975P-C | 5583976721 B (3 parts) | `057e2fe53c3acdeafb143b2b0338ea3452f6259dfee7f8ad4e8397fcbe4e316f` |
| `mpas842-dbl-rg120-002` | RG120 | 46100210828 | AMD EPYC 9V45 | 5583977854 B (3 parts) | `84eb6d294b9e738dedfb3250558d045da69620e946dd7cd87cd7877e0f5c3767` |
| `mpas842-dbl-rg120l-001` | RG120L (48 h) | 46076917966 | AMD EPYC 7763 | 10950679913 B (6 parts) | `22e68c364dc8e72a914ec75c1db4fff9576cdc1763c2bc7e864cb67fd56c2159` |
| `mpas842-dbl-rg120l-002` | RG120L (48 h) | 46106335744 | Intel Xeon 6975P-C | 10950681339 B (6 parts) | `22f5b4fac3fa608408710d5afc69f0a812eca24957e070705cfb3f7d64817a23` |
| `mpas842-dbl-rgv48-001` | RGV48 | 46097754964 | Intel Xeon Platinum 8573C | 4709097135 B (3 parts) | `9ebc35a80ef8a8f39faae7d524af6dcf75a68dbdfcbdf2d0de2f32091f068266` |
| `mpas842-dbl-rgv48-002` | RGV48 | 46097588796 | AMD EPYC 7763 | 4709097157 B (3 parts) | `6257415c757717915959a19ad7709691179d3be0120b694c0d5130a16e4488ab` |
| `mpas842-dbl-rgv48l-001` | RGV48L (12 h) | 46097228289 | Intel Xeon 6975P-C | 3561986876 B (2 parts) | `14d9f2e0071604ff273722488c9fd59b96e2b2dfa4d7c5ad737e31abc9ee5cfa` |
| `mpas842-dbl-rgv48l-002` | RGV48L (12 h) | 46097618523 | AMD EPYC 9V74 | 3561986895 B (2 parts) | `a79433c633a33bcfcdcf6a58c34fb169a4b346f59eed974322f51937e912f445` |

All come from build asset `mpas-8.4.2-double-7be24aab….tar.zst`; each run's two trials were identical. Intel and AMD,
compared with `refcompare` (0 differences in every case file):

- rg60-001 = rg60-002 (run 46120393807, 134 files);
- rg120-001 = rg120-002 (run 46102277946, 134 files);
- rgv48-001 = rgv48-002 (run 46111045041, 139 files);
- rgv48l-001 = rgv48l-002 (run 46114186647, 127 files);
- rg120l-001 = rg120l-002 (run 46128266028, 164 files).

The 60-km mesh (163842 cells) needs more memory than the runner has: one-rank `atmosphere_model` is killed at
15.25 GB resident without swap, so RG60 and RG60L run with a 40 GiB swap file and a capped container
(`ci/host.sh`, ci/rg60/README.md), which makes a step take about 200 s. With that, NCAR's smallest
variable-resolution mesh, 92-25 km x4.163842 (163842 cells, a 150 s step), would need about 8.4 h for its two
trials, beyond the job limit (ci/rgvr/README.md), so the variable-resolution references use the 240-48 km
x5.30210 of the MPAS tutorial.

## Dispatch

`mpas-build` must exist as a release before the first build. Dispatch the references from the same commit
as the build so that the recipe hash matches; one case per tag.

```bash
repo=Xassemblianist/cppmpas-data
gh workflow run mpas-build.yml -R "$repo" --ref main -f flavour=double
gh workflow run mpasref.yml -R "$repo" --ref main -f tag=mpas842-dbl-jw-001 -f flavour=double -f cases=JW
gh workflow run mpas-build.yml -R "$repo" --ref main -f flavour=double -f verify=true
gh workflow run refcompare.yml -R "$repo" --ref main -f left=mpas842-dbl-rgcp-001 -f right=mpas842-dbl-rgcp-002
```

## Fetch a reference

```bash
repo=Xassemblianist/cppmpas-data
tag=mpas842-dbl-jw-001
gh release download "$tag" -R "$repo" --dir "$tag.download"
cd "$tag.download"
sha256sum -c --ignore-missing "$tag.sha256"
cat "$tag".tar.zst.part* > "$tag.tar.zst"
sha256sum -c "$tag.sha256"
mkdir "../$tag"
zstd -dc "$tag.tar.zst" | tar -xf - -C "../$tag"
(cd "../$tag" && sha256sum -c SHA256SUMS)
```

To restart from the checkpoint, use the restart file and `restart_timestamp` from `forecast/`, the
case's `forecast/` namelist and streams, and the tables of the recorded build asset (case-local `.TBL`
files in the run directories take precedence).

Repository recipes are GPL-3.0-or-later. MPAS, its dependencies and the upstream datasets have their own terms.
