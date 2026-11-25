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

Per case directory:

- `init/`: the initial conditions written by `init_atmosphere_model`, with its namelist, streams and logs.
- `steps/`: `step.*.nc`, the state after steps 0 to 10 in double precision (`u`, `w`, `rho_zz`, `theta_m`,
  the `scalars` array, and the diagnosed `rho`, `theta`, `pressure_p`), written by a 10-step run in which
  every other output stream is off.
- `forecast/`: a run of two package history intervals (at least 11 steps) with the package history stream
  unchanged and one restart checkpoint, written one step after the midpoint, with its `restart_timestamp`.
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

## Dispatch

`mpas-build` must exist as a release before the first build. Dispatch the references from the same commit
as the build so that the recipe hash matches; one case per tag.

```bash
repo=Xassemblianist/cppmpas-data
gh workflow run mpas-build.yml -R "$repo" --ref main -f flavour=double
gh workflow run mpasref.yml -R "$repo" --ref main -f tag=mpas842-dbl-jw-001 -f flavour=double -f cases=JW
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
