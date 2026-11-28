# RGDT: the default configuration with another time step and start time

RGDT is RGDEF (`ci/rgdef/README.md`) with two more changes. It shows that a time step and a start time other than
the defaults run as well.

- `namelist.atmosphere`: `config_dt = 480.0` and `config_start_time = '2026-10-12_09:00:00'`. Neither the default
  3 h diagnostics interval nor the 30 min radiation interval is a whole number of 480 s steps, so their alarms
  ring at the first step past each time. `config_run_duration = '0_06:00:00'`.
- `namelist.init_atmosphere`: `config_start_time` and `config_stop_time` = `2026-10-12_09:00:00`.
- The first-guess file is RG's 00 UTC GFS analysis, staged as `FILE:2026-10-12_09`. `init_atmosphere` opens the
  file named after the start time and does not compare the date written inside it (`mpas_init_atm_cases.F:3462`).
  The initial state is therefore the 00 UTC fields valid at 09 UTC. This is a test of the configuration (the solar
  geometry, the clock and the alarms), not a meteorological analysis.

`ci/cases.py` sets the 6 h forecast's history to every 6 h (`LONG_CASES`), as generated. It sets one restart one step
after the midpoint (03:04 after the start, 12:04 UTC), because the generated daily restart is not written in 6 h.
The diagnostics stream is unchanged.
