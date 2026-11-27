# RGCP, RGCP24: the RG case with the convection_permitting suite

RGCP and RGCP24 are RG and RG24 (`ci/rg/README.md`) with MPAS's other physics suite. They use RG's inputs
(`x1.10242_static.tar.gz`, `rg-gfs-20261012T00.wps`), RG's `namelist.init_atmosphere` and init streams, so the
initial file is RG's, and RG's atmosphere streams and stream lists.

- RGCP, like RG: steps 0-10 with the bisection and initdump streams, then a 2 h forecast with hourly history,
  the 3-hourly diag stream at 0 h, and one restart at 01:10.
- RGCP24, like RG24: a 24 h forecast, history and diag every 3 h, one restart at 12:10.

## Changes from RG

`namelist.atmosphere`: one change, made by `ci/cases.py` (`CP_NAMELIST`) when it stages the package:

- `config_physics_suite = 'convection_permitting'` instead of `'mesoscale_reference'`.

No other option has to change for MPAS to run this suite on this case. `mpas_atmphys_control.F:145-153` resolves
every scheme option left at `'suite'` (RG's namelist sets none of them) to:

| Option | convection_permitting | (RG: mesoscale_reference) |
| --- | --- | --- |
| `config_microp_scheme` | `mp_thompson` | `mp_wsm6` |
| `config_convection_scheme` | `cu_grell_freitas` | `cu_ntiedtke` |
| `config_pbl_scheme` | `bl_mynn` | `bl_ysu` |
| `config_gwdo_scheme` | `bl_ysu_gwdo` | `bl_ysu_gwdo` |
| `config_radt_lw_scheme`, `config_radt_sw_scheme` | `rrtmg_lw`, `rrtmg_sw` | same |
| `config_radt_cld_scheme` | `cld_fraction` | same |
| `config_sfclayer_scheme` | `sf_mynn` | `sf_monin_obukhov_rev` |
| `config_lsm_scheme` | `sf_noah` | same |

The packaged `namelist.atmosphere` in each reference's `package/` holds the change; `configuration.diff` lists
only the run edits made on top of it (run duration, stream intervals, bisection and initdump streams), as for RG.

## Thompson tables

`thompson_init` opens `MP_THOMPSON_QRacrQG_DATA.DBL`, `MP_THOMPSON_QRacrQS_DATA.DBL`,
`MP_THOMPSON_freezeH2O_DATA.DBL` and `MP_THOMPSON_QIautQS_DATA.DBL` in the run directory with `status='OLD'`
(`module_mp_thompson.F:862-965`). Neither MPAS nor MPAS-Data ships them; MPAS's `build_tables` utility writes them.

- **Build:** `make atmosphere` builds `build_tables` (`src/core_atmosphere/Makefile` target `utilities`,
  `src/core_atmosphere/utils/Makefile`) from `build_tables.F` and `atmphys_build_tables_thompson.F` with the
  same `mpif90`, flags (`-O3 ... -fconvert=big-endian -fdefault-real-8 -fdefault-double-8`) and the same
  `libphys` objects as `atmosphere_model`, and moves it to the top directory. `ci/build.sh` keeps it in the build
  asset's `bin/`, with its link line and `ldd` in `metadata/`.
- **Run:** every RGCP trial first runs `build_tables` in its own `tables/` directory (`ci/ref.py`
  `build_tables`): one serial process, without `mpiexec`, with the same Intel libmvec preload and stack limit as
  the model runs. Its output goes to `tables/build_tables.log`. The `steps/` and `forecast/` directories link the
  four tables from `../tables/`.
- **Checks:** `build_tables` opens each table with `status='new'` and, if it cannot, prints a message and
  returns with exit status 0 (`atmphys_build_tables_thompson.F:45-49` and the three blocks after it), so
  `ci/ref.py` requires exit status 0, the four files and its closing "Finished building all tables." line;
  `ci/cases.py validate` requires exactly the four tables and the log in `tables/`, and that both model runs
  read them. The two trials' tables are compared byte for byte (`determinism.txt`, `TEXT-DIFF` on a difference).
- **Published:** `RGCP/tables/` (or `RGCP24/tables/`) of the reference archive holds the four tables and the log;
  their SHA-256 are in `SHA256SUMS` and in `provenance.json` (`cases.<ID>.thompson_tables_sha256`). The files are
  big-endian Fortran unformatted sequential records, as `-fconvert=big-endian` writes them.

MPAS's own check that the tables exist never fires. `physics_tables_init` (`mpas_atmphys_control.F:410-411`)
returns early when

```fortran
if(config_microp_scheme /= "mp_thompson" .or. &
   config_microp_scheme /= "mp_thompson_aerosols") return
```

which is true for every value, so the `inquire` calls and the "run build_tables first" error below it are never
reached. A run without the tables stops instead in `thompson_init`, at the first `open`
(`module_mp_thompson.F:862-866`), with `physics_error_fatal('... failure opening MP_THOMPSON_QRacrQG.DBL')`.

## libmvec

`atmosphere_model` calls glibc's 2-lane SSE vector functions `_ZGVbN2v_{atan,cos,exp,log,log10,sin}` and
`_ZGVbN2vv_pow`. In the convection_permitting schemes, gfortran vectorised (from the reference executable's
disassembly):

- `exp`: `thompson_init`, `qr_acr_qg`, `qr_acr_qs`, `bl_mynn_run`, `mym_turbulence`;
- `pow`: `mp_thompson`, `freezeh2o`, `qr_acr_qg`, `qr_acr_qs`, `table_dropevap`, `bl_mynn_run`, `dmp_mf`,
  `topdown_cloudrad`, `sf_mynn_run`;
- `atan`, `log`: `sf_mynn_init`; `log10`: `calc_refl10cm`.

Of glibc 2.41's SSE4 variants of these, only `log` and `log10` take `rcpps` (`rsqrtps` none); `exp`, `pow`, `atan`,
`sin` and `cos` use no instruction whose result the hardware defines. `log` and `log10` are already the Intel ones
on every runner (`ci/mvec_intel`), so the preload is not extended. Whether an Intel and an AMD runner give the same
references is checked by running the case on both and comparing them with the `refcompare` workflow; the result
is in the top-level README.
