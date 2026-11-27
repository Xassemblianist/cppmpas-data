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
physics suite from one GFS analysis (inputs and changes in ci/rg/README.md), with RG24 its 24 h forecast; and RGCP
and RGCP24: the same two runs with the convection_permitting suite (Thompson, Grell-Freitas, MYNN), whose Thompson
tables MPAS's build_tables writes in each trial (ci/rgcp/README.md). Every run preloads CPPWRF's Intel libmvec log/log10
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
by the wall clock: `file_id` (compared only as ten characters from `[0-9a-z]`) and the first line of
`parent_id` (the `file_id` of the run's input file); the rest of `parent_id` is compared.

## Releases

- `inputs`: the seven pinned upstream tarballs, listed with their origin in [ci/upstream.tsv](ci/upstream.tsv)
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
