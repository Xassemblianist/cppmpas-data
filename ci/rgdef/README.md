# RGDEF: MPAS-Atmosphere's own default configuration on x1.40962

RGDEF runs `atmosphere_model` with the namelist and streams MPAS v8.4.2 generates for itself, changed only where a
real-data run must be. The mesh is NCAR's 120-km quasi-uniform x1.40962, which is the mesh the defaults name. Its
init and inputs are RG120's (`ci/rg120/README.md`): the same static file and the same GFS first guess
(2026-10-12 00 UTC).

## How the files were made

`namelist.atmosphere`, `streams.atmosphere` and the four `stream_list.atmosphere.*` files are the output of
`src/tools/input_gen/namelist_gen` and `streams_gen` at MPAS commit f34984b. They were run as the core Makefile's
`core_input_gen` runs them:

    cpp -P -traditional -D_MPI -DCORE_ATMOSPHERE -DMPAS_NAMELIST_SUFFIX=atmosphere -DMPAS_EXE_NAME=atmosphere_model \
        -DMPAS_NATIVE_TIMERS -DMPAS_GIT_VERSION=v8.4.2 -DMPAS_BUILD_TARGET=gfortran -DMPAS_SMIOL_SUPPORT \
        -DMPAS_USE_MPI_F08 -DDO_PHYSICS -DDO_CHEMISTRY Registry.xml > Registry_processed.xml
    namelist_gen Registry_processed.xml namelist.atmosphere in_defaults=true
    streams_gen Registry_processed.xml streams.atmosphere stream_list.atmosphere. listed in_defaults=true

The flags are those of the reference build's log (`build-metadata/atmosphere.build.log.zst`). The generated
stream lists and `streams.atmosphere` are used byte for byte.

## Changes from the generated files

`namelist.atmosphere`:
- `config_start_time = '2026-10-12_00:00:00'`, the time of the GFS analysis (generated: `2010-10-23_00:00:00`).
- `config_run_duration = '1_00:00:00'`, a 24 h forecast that fits a runner job (generated: `5_00:00:00`).

Everything else is as generated:
- `config_dt = 720.0`.
- No `config_len_disp` line. The Registry has `in_defaults="false"`, so the value is 0.0 and MPAS takes the input
  file's `nominalMinDc`, 120000 m (`mpas_atm_core.F:170-195`).
- History every 6 h, diagnostics every 3 h, and the restart every day, which writes one checkpoint at the end of the
  24 h.

`ci/cases.py` (`DEFAULT_STREAM_CASES`) gives the forecast the package's streams unchanged. The steps phase (10
steps with the bisection and initdump streams) is RG's.

The init files (`namelist.init_atmosphere`, `streams.init_atmosphere`) are RG120's.
