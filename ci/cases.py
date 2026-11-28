#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare one trial of a reference case and validate the files that trial wrote.

A trial has three run directories: init (init_atmosphere_model), steps (atmosphere_model for ten
timesteps, writing the bisection stream after every step) and forecast (atmosphere_model for two
package history intervals, writing the package history and one restart checkpoint). The
convection_permitting cases have a fourth, tables, run first: MPAS's build_tables writes the Thompson
microphysics tables there, and both atmosphere runs read them. Only config_run_duration and the stream
intervals are changed; everything else is the case package.
"""
import argparse
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import re
import shutil
import tarfile
import xml.etree.ElementTree as ET

# ID: (config_init_case, package tarball, mesh file in the package)
CASES = {
    "JW": (2, "jw_baroclinic_wave.tar.gz", "x1.40962.grid.nc"),
    "SC": (5, "supercell.tar.gz", "supercell_grid.nc"),
    "MW": (6, "mountain_wave.tar.gz", "mtn_wave_grid.nc"),
    # Real data: NCAR's published 240-km static file (static fields precomputed, so no geographic data set) and one
    # GFS analysis as a WPS intermediate file; the namelists and streams are MPAS v8.4.2's generated defaults with
    # the changes in ci/rg/README.md.
    "RG": (7, "x1.10242_static.tar.gz", "x1.10242.static.nc"),
    # RG24: the same case and inputs, with a 24 h forecast (LONG_CASES: history every 3 h, one restart one step
    # after 12 h). RG's own forecast is two history intervals (2 h).
    "RG24": (7, "x1.10242_static.tar.gz", "x1.10242.static.nc"),
    # RGR: RG's forecast (the same init and 2 h forecast with its restart one step after 1 h), then a fourth phase,
    # restart: atmosphere_model restarted from that forecast's checkpoint (config_do_restart = true), with history,
    # diagnostics and one more restart (RESTART_CASES). It has no steps phase (RG has it).
    "RGR": (7, "x1.10242_static.tar.gz", "x1.10242.static.nc"),
    # RGR24: RG24's 24 h forecast (the same init, namelists and streams, so the same 12:10 checkpoint), then the
    # restart phase from that checkpoint to 24:00 (RESTART_CASES). No steps phase (RG24 has it).
    "RGR24": (7, "x1.10242_static.tar.gz", "x1.10242.static.nc"),
    # RGCP and RGCP24: RG and RG24 with config_physics_suite = 'convection_permitting' (ci/rgcp/README.md). A
    # fourth phase, tables, runs MPAS's build_tables before the init, and both model runs read its Thompson tables.
    "RGCP": (7, "x1.10242_static.tar.gz", "x1.10242.static.nc"),
    "RGCP24": (7, "x1.10242_static.tar.gz", "x1.10242.static.nc"),
    # RG60 and RG60L: RG's recipe on NCAR's 60-km quasi-uniform mesh x1.163842, from NCAR's published static file
    # (ci/rg60/README.md). RG60 is RG's short case; RG60L the long forecast.
    "RG60": (7, "x1.163842_static.tar.gz", "x1.163842.static.nc"),
    "RG60L": (7, "x1.163842_static.tar.gz", "x1.163842.static.nc"),
    # RGVR and RGVRL: RG's recipe on NCAR's 92-25 km variable-resolution mesh x4.163842 (ci/rgvr/README.md). NCAR
    # publishes no static file for it, so a fifth phase, static, runs init_atmosphere's static and GWDO stages on the
    # grid file with WPS geographic data first, and the init reads that trial's static file.
    # Its two trials do not fit in one standard runner job (8.4 h estimated from measured steps; ci/rgvr/README.md).
    "RGVR": (7, "x4.163842.tar.gz", "x4.163842.grid.nc"),
    "RGVRL": (7, "x4.163842.tar.gz", "x4.163842.grid.nc"),
    # RG120 and RG120L: RG's recipe on NCAR's 120-km quasi-uniform mesh x1.40962 (ci/rg120/README.md); RGV48 and
    # RGV48L: on NCAR's 240-48 km variable-resolution mesh x5.30210, with the static phase of RGVR (ci/rgv48/README.md).
    "RG120": (7, "x1.40962_static.tar.gz", "x1.40962.static.nc"),
    "RG120L": (7, "x1.40962_static.tar.gz", "x1.40962.static.nc"),
    "RGV48": (7, "x5.30210.tar.gz", "x5.30210.grid.nc"),
    "RGV48L": (7, "x5.30210.tar.gz", "x5.30210.grid.nc"),
    # RGDEF: MPAS's own generated default namelist.atmosphere and streams (namelist_gen and streams_gen, as the core
    # Makefile's core_input_gen makes them) on x1.40962, the mesh of the default config_dt = 720 s, changed only in
    # the start time (the GFS analysis) and a 24 h run (ci/rgdef/README.md): config_len_disp left out (0.0: MPAS
    # takes the mesh's nominalMinDc), history every 6 h, diagnostics every 3 h and the restart at 1 day, all as
    # generated. RGDT: the same with config_dt = 480 s and a 09 UTC start, a 6 h forecast (ci/rgdt/README.md).
    "RGDEF": (7, "x1.40962_static.tar.gz", "x1.40962.static.nc"),
    "RGDT": (7, "x1.40962_static.tar.gz", "x1.40962.static.nc"),
}
RG_CASES = ("RG", "RG24", "RGR", "RGR24", "RGCP", "RGCP24", "RG60", "RG60L", "RGVR", "RGVRL", "RG120", "RG120L", "RGV48", "RGV48L",
            "RGDEF", "RGDT")
CP_CASES = ("RGCP", "RGCP24")
STATIC_CASES = ("RGVR", "RGVRL", "RGV48", "RGV48L")
# Long cases: (forecast seconds, history interval seconds); one restart one step after the midpoint.
LONG_CASES = {
    "RG24": (86400, 3 * 3600),
    "RGR24": (86400, 3 * 3600),
    "RGCP24": (86400, 3 * 3600),
    "RG60L": (3 * 3600, 3 * 3600),
    "RGVRL": (3 * 3600, 3 * 3600),
    "RG120L": (48 * 3600, 3 * 3600),
    "RGV48L": (12 * 3600, 3 * 3600),
    "RGDEF": (86400, 6 * 3600),
    "RGDT": (6 * 3600, 6 * 3600),
}
# Cases whose forecast runs the package's streams.atmosphere unchanged (the generated defaults): no stream interval
# is set, and the restart is the package's own (RGDEF: output_interval 1_00:00:00, written at the end of the 24 h).
DEFAULT_STREAM_CASES = ("RGDEF",)
# Long cases on the 163842-cell meshes run no 10-step bisection phase (their short case has it), so that the two
# trials' forecasts fit in one runner job.
NO_STEPS_CASES = ("RG60L", "RGVRL", "RGV48L", "RGR", "RGR24")
# Restart cases: (restart run seconds, output interval seconds of its history and diagnostics streams, seconds of its
# checkpoint after the restart, or None for one step after the midpoint). The restart phase starts at the forecast's
# checkpoint. MPAS anchors every output alarm and the physics alarms at the clock's
# start time, which on a restart is the checkpoint (xml_stream_parser.c:1291-1296 reference_time 'initial_time';
# mpas_atmphys_manager.F:466-650), and does not write history or diagnostics at that time (mpas_atm_core.F:669-673).
# RGR restarts at 01:10 and writes every 50 min, so its first history is at 02:00, a time of the forecast's own
# history; its checkpoint is one step after the midpoint, as in the forecast (02:10).
# RGR24 restarts at 12:10 and runs to 24:00 (11 h 50 min, 71 steps: 71 is prime, so no interval longer than one step
# both divides the run and ends at 24:00). Its history and diagnostics write every 3 h after the restart (15:10, 18:10,
# 21:10), none a time of the forecast's history, and its checkpoint is written at the end, 24:00, so the final state
# is in the reference; continuity.txt compares that checkpoint with the forecast's 24:00 history.
RESTART_CASES = {"RGR": (6000, 3000, None), "RGR24": (42600, 3 * 3600, 42600)}
RESTART_PHASE = "restart"
# One-rank atmosphere_model on a 163842-cell mesh needs more than a standard runner's 16 GB of memory (rg60-001
# attempt, run 46066643405: killed at 15.25 GB resident, before the first step), so ci/host.sh adds a swap file of this
# many GiB on the runner disk for these cases. Swap changes where pages live, not a computed value.
SWAP_GIB = {case: 40 for case in ("RG60", "RG60L", "RGVR", "RGVRL")}
# The GWDO stage holds the global 30-arc-second terrain and land use in memory: the static phase on x5.30210 reached
# 14195472 KiB resident (run 46076927558) on a 16 GB runner, so RGV48 gets swap too.
SWAP_GIB.update({case: 16 for case in ("RGV48", "RGV48L")})
# Each real-data case's ci/ package directory and the graph file kept from its mesh archive.
RG_PACKAGES = {case: ("rg", "x1.10242.graph.info") for case in ("RG", "RG24", "RGR", "RGR24", "RGCP", "RGCP24")}
RG_PACKAGES.update({case: ("rg60", "x1.163842.graph.info") for case in ("RG60", "RG60L")})
RG_PACKAGES.update({case: ("rgvr", "x4.163842.graph.info") for case in ("RGVR", "RGVRL")})
RG_PACKAGES.update({case: ("rg120", "x1.40962.graph.info") for case in ("RG120", "RG120L")})
RG_PACKAGES.update({case: ("rgv48", "x5.30210.graph.info") for case in ("RGV48", "RGV48L")})
RG_PACKAGES.update({"RGDEF": ("rgdef", "x1.40962.graph.info"), "RGDT": ("rgdt", "x1.40962.graph.info")})
# The WPS geographic data sets the static stage reads (mpas_init_atm_static.F, mpas_init_atm_gwd.F, for the default
# config_*_data options): each tarball holds one top-level directory of that name, extracted under GEOG_DIR, which
# namelist.init_atmosphere.static names as config_geog_data_path.
GEOG_DATASETS = ("topo_gmted2010_30s", "modis_landuse_20class_30s", "soiltype_top_30s", "soiltemp_1deg",
                 "greenfrac_fpar_modis", "albedo_modis", "maxsnowalb_modis", "soilgrids", "landuse_30s")
GEOG_DIR = Path("/work/geog")
STATIC_SUFFIX = ".static"  # namelist.init_atmosphere.static and streams.init_atmosphere.static
# The namelist.atmosphere options the convection_permitting cases change in RG's package.
CP_NAMELIST = {"config_physics_suite": "'convection_permitting'"}
# The look-up tables that thompson_init reads with status='OLD' (module_mp_thompson.F:862-965) and build_tables
# writes in its working directory (src/core_atmosphere/utils/atmphys_build_tables_thompson.F:40-110).
THOMPSON_TABLES = ("MP_THOMPSON_QRacrQG_DATA.DBL", "MP_THOMPSON_QRacrQS_DATA.DBL",
                   "MP_THOMPSON_freezeH2O_DATA.DBL", "MP_THOMPSON_QIautQS_DATA.DBL")
TABLES_LOG = "build_tables.log"
# RG's first-guess file: the release-safe name in `inputs`, and the name init_atmosphere reads (config_met_prefix
# 'FILE' and config_start_time).
RG_MET = ("rg-gfs-20261012T00.wps", "FILE:2026-10-12_00")
# RGDT starts at 09 UTC: its init (config_start_time 2026-10-12_09:00:00) reads FILE:2026-10-12_09, which is RG's
# 00 UTC analysis staged under that name. init_atmosphere opens the file by the start time's name and does not
# compare the hdate inside it (mpas_init_atm_cases.F:3462, mpas_init_atm_read_met.F:119-130), so the initial state is
# RG120's fields valid at 09 UTC: a configuration test of the start time (solar geometry, julian day, alarms), not a
# meteorological analysis.
RG_MET_NAMES = {"RGDT": "FILE:2026-10-12_09"}


def met_name(case):
    return RG_MET_NAMES.get(case, RG_MET[1])
CI_DIR = Path(__file__).resolve().parent
STEPS = 10
STAMP = "$Y-$M-$D_$h.$m.$s"
BISECTION_TEMPLATE = f"step.{STAMP}.nc"
# Prognostic state (u, w, rho_zz, theta_m, scalars) and the diagnosed rho, theta and pressure_p.
BISECTION_FIELDS = ("xtime", "Time", "u", "w", "rho_zz", "theta_m", "rho", "theta", "pressure_p")
# Fields that atm_mpas_init_block (src/core_atmosphere/mpas_atm_core.F:366-617) computes before the first step and
# that no package stream writes: written once, at the initial time (the first stream write of atm_core_run,
# mpas_atm_core.F:701, after the init block), by the short run's "initdump" stream. Mesh-pool fields are
# time-invariant; the diag and state fields are those of time level 1 after the init block and the initial
# atm_compute_solve_diagnostics / mpas_reconstruct (mpas_atm_core.F:507-563). The stream only reads memory: it
# changes no computed value, and every other output of the run is unchanged.
INITDUMP_TEMPLATE = "initdump.nc"
INITDUMP_FIELDS = (
    "xtime",
    # atm_compute_signs, inverses, atm_adv_coef_compression, atm_couple_coef_3rd_order
    "invAreaCell", "invDvEdge", "invDcEdge", "invAreaTriangle", "edgesOnCell_sign", "edgesOnVertex_sign",
    "zb_cell", "zb3_cell", "kiteForCell", "advCellsForEdge", "nAdvCellsForEdge", "adv_coefs", "adv_coefs_3rd",
    # atm_initialize_deformation_weights, atm_compute_mesh_scaling, atm_compute_damping_coefs, bdy masks
    "deformation_coef_c2", "deformation_coef_s2", "deformation_coef_cs", "deformation_coef_c", "deformation_coef_s",
    "meshScalingDel2", "meshScalingDel4", "meshScalingRegionalCell", "meshScalingRegionalEdge",
    "etp", "etm", "ewp", "ewm", "specZoneMaskCell", "specZoneMaskEdge", "specZoneMaskVertex", "nearestRelaxationCell",
    # atm_init_coupled_diagnostics
    "theta_m", "rho_zz", "ru", "rw", "rho_p", "rtheta_base", "rtheta_p", "exner", "exner_base", "pressure_p",
    "pressure_base",
    # initial atm_compute_solve_diagnostics and mpas_reconstruct
    "v", "rho_edge", "vorticity", "divergence", "ke", "pv_edge", "pv_vertex", "pv_cell", "gradPVt", "gradPVn",
    "uReconstructX", "uReconstructY", "uReconstructZ", "uReconstructZonal", "uReconstructMeridional",
)
PHASES = ("init", "steps", "forecast")
CP_PHASES = ("tables",) + PHASES
STATIC_PHASES = ("static",) + PHASES
INIT_CORE_PHASES = ("static", "init")  # run by init_atmosphere_model


def plan_phases(plan):
    """The run directories of a trial in run order (plans without "phases" have the three of PHASES)."""
    return tuple(plan.get("phases", PHASES))
PACKAGE_PREFIXES = ("namelist.", "streams.", "stream_list.")


def stream(root, name):
    items = [item for item in root if isinstance(item.tag, str) and item.get("name") == name]
    if len(items) != 1:
        raise ValueError(f"Expected one {name} stream, got {len(items)}")
    return items[0]


def interval(value):
    """MPAS interval '[D_]h:m:s' in seconds."""
    days, sep, rest = value.strip().rpartition("_")
    h, m, s = (int(field) for field in rest.split(":"))
    return ((int(days) if sep else 0) * 24 + h) * 3600 + m * 60 + s


def duration(seconds):
    minutes, s = divmod(seconds, 60)
    hours, m = divmod(minutes, 60)
    days, h = divmod(hours, 24)
    return f"{days}_{h:02}:{m:02}:{s:02}"


def assignment(text, key):
    matches = list(re.finditer(rf"(?im)^([ \t]*{key}[ \t]*=[ \t]*)([^!,\r\n]+)", text))
    if len(matches) > 1:
        raise ValueError(f"{key} is set more than once")
    return matches[0] if matches else None


def nml_value(text, key):
    match = assignment(text, key)
    if not match:
        raise ValueError(f"Missing {key}")
    return match[2].strip().strip("'\"")


def set_nml(text, key, value):
    match = assignment(text, key)
    if not match:
        raise ValueError(f"Missing {key}")
    old = match[2].rstrip()
    return text[:match.start(2)] + value + text[match.start(2) + len(old):]


def flat_name(path):
    if not path or Path(path).name != path or path in {".", ".."}:
        raise ValueError(f"Expected a file name without directories, got {path!r}")
    return path


def extract_geog(downloads):
    """Extract the geographic data sets once per run under GEOG_DIR (both trials read the same files)."""
    marker = GEOG_DIR / ".complete"
    if marker.is_file():
        return
    GEOG_DIR.mkdir(parents=True)
    for name in GEOG_DATASETS:
        with tarfile.open(downloads / f"{name}.tar.bz2", "r:bz2") as source:
            members = source.getmembers()
            tops = {Path(m.name).parts[0] for m in members if Path(m.name).parts}
            if tops != {name}:
                raise ValueError(f"{name}.tar.bz2 holds {sorted(tops)}, expected one directory {name}")
            source.extractall(GEOG_DIR, members=members, filter="data")
    marker.write_text("\n".join(GEOG_DATASETS) + "\n")


def stage_rg(case, downloads, package):
    """RG cases: the static (or grid) file and its graph partition file from NCAR's archive, the met file, and the
    case's ci/ package directory."""
    _, archive, mesh = CASES[case]
    directory, graph = RG_PACKAGES[case]
    with tarfile.open(downloads / archive, "r:gz") as source:
        for member in source.getmembers():
            name = Path(member.name).name
            if member.isfile() and name in {mesh, graph}:
                with source.extractfile(member) as data, (package / flat_name(name)).open("xb") as out:
                    shutil.copyfileobj(data, out)
    if not (package / mesh).is_file():
        raise ValueError(f"{archive} lacks the static file {mesh}")
    shutil.copyfile(downloads / RG_MET[0], package / flat_name(met_name(case)))
    for item in sorted((CI_DIR / directory).iterdir()):
        if item.name.startswith(PACKAGE_PREFIXES):
            shutil.copyfile(item, package / item.name)
    if case in CP_CASES:
        path = package / "namelist.atmosphere"
        text = path.read_text()
        for key, value in CP_NAMELIST.items():
            text = set_nml(text, key, value)
        path.write_text(text)


def stage_package(case, downloads, package):
    """Copy the case configuration, tables and mesh from the top directory of the package."""
    if case in RG_CASES:
        stage_rg(case, downloads, package)
        return
    _, archive, mesh = CASES[case]
    with tarfile.open(downloads / archive, "r:gz") as source:
        members = source.getmembers()
        roots = {Path(m.name).parent for m in members if m.isfile() and Path(m.name).name == "namelist.atmosphere"}
        if len(roots) != 1:
            raise ValueError(f"{archive} must have one namelist.atmosphere")
        root = roots.pop()
        for member in members:
            path = Path(member.name)
            if not member.isfile() or path.parent != root:
                continue
            if (path.name == mesh or path.name.startswith(PACKAGE_PREFIXES) or path.name.endswith(".TBL")
                    or path.name.lower().startswith("readme")):
                with source.extractfile(member) as data, (package / flat_name(path.name)).open("xb") as out:
                    shutil.copyfileobj(data, out)
    if not (package / mesh).is_file():
        raise ValueError(f"{archive} lacks the mesh {mesh}")


def prepare(case, downloads, build, trial):
    init_case, _, mesh = CASES[case]
    package = trial / "package"
    package.mkdir(parents=True)
    stage_package(case, downloads, package)

    init = trial / "init"
    init.mkdir()
    init_input = mesh
    if case in STATIC_CASES:
        # static: init_atmosphere's static and GWDO stages on the grid file; the init then reads its static file.
        static = trial / "static"
        static.mkdir()
        (static / mesh).symlink_to(Path("..") / "package" / mesh)
        static_text = (package / ("namelist.init_atmosphere" + STATIC_SUFFIX)).read_text()
        for key, value in (("config_static_interp", "true"), ("config_native_gwd_static", "true"),
                           ("config_vertical_grid", "false"), ("config_met_interp", "false"),
                           ("config_geog_data_path", str(GEOG_DIR) + "/")):
            found = nml_value(static_text, key)
            if (found if key == "config_geog_data_path" else found.lower().strip(".")) != value:
                raise ValueError(f"{case} static namelist must set {key} = {value}")
        for name in ("namelist.init_atmosphere", "streams.init_atmosphere"):
            shutil.copyfile(package / (name + STATIC_SUFFIX), static / name)
        static_streams = ET.parse(static / "streams.init_atmosphere").getroot()
        if flat_name(stream(static_streams, "input").get("filename_template")) != mesh:
            raise ValueError(f"{case} static input is not {mesh}")
        init_input = flat_name(stream(static_streams, "output").get("filename_template"))
        (init / init_input).symlink_to(Path("..") / "static" / init_input)
        extract_geog(downloads)
    else:
        (init / mesh).symlink_to(Path("..") / "package" / mesh)
    init_text = (package / "namelist.init_atmosphere").read_text()
    if int(nml_value(init_text, "config_init_case")) != init_case:
        raise ValueError(f"{case} package does not select init case {init_case}")
    for name in ("namelist.init_atmosphere", "streams.init_atmosphere"):
        shutil.copyfile(package / name, init / name)
    if case in RG_CASES:
        (init / met_name(case)).symlink_to(Path("..") / "package" / met_name(case))
        if nml_value(init_text, "config_met_prefix") + ":" + nml_value(init_text, "config_start_time")[:13] \
                != met_name(case):
            raise ValueError("RG init namelist does not read " + met_name(case))
    init_streams = ET.parse(init / "streams.init_atmosphere").getroot()
    if flat_name(stream(init_streams, "input").get("filename_template")) != init_input:
        raise ValueError(f"{case} init input is not {init_input}")
    init_file = flat_name(stream(init_streams, "output").get("filename_template"))

    atm_text = (package / "namelist.atmosphere").read_text()
    if case == "SC" and nml_value(atm_text, "config_microp_scheme") != "mp_kessler":
        raise ValueError("SC requires the package's Kessler microphysics")
    suite = nml_value(atm_text, "config_physics_suite") if case in RG_CASES else None
    if suite is not None and suite != ("convection_permitting" if case in CP_CASES else "mesoscale_reference"):
        raise ValueError(f"{case} namelist selects the physics suite {suite!r}")
    if assignment(atm_text, "config_stop_time") or assignment(atm_text, "config_do_restart") is None \
            or nml_value(atm_text, "config_do_restart").lower().strip(".") not in {"false", "f"}:
        raise ValueError(f"{case} namelist must be a cold start that ends by config_run_duration")
    dt = Decimal(nml_value(atm_text, "config_dt").lower().replace("d", "e"))
    if dt <= 0 or dt != dt.to_integral_value():
        raise ValueError(f"{case} requires a positive whole-second config_dt")
    dt = int(dt)
    timestamp_file = "restart_timestamp"
    if assignment(atm_text, "config_restart_timestamp_name"):
        timestamp_file = flat_name(nml_value(atm_text, "config_restart_timestamp_name"))

    package_streams = ET.parse(package / "streams.atmosphere").getroot()
    if flat_name(stream(package_streams, "input").get("filename_template")) != init_file:
        raise ValueError(f"{case} atmosphere input is not the init output {init_file}")
    history = stream(package_streams, "output")
    flat_name(history.get("filename_template"))
    history_seconds = interval(history.get("output_interval"))
    if history_seconds <= 0 or history_seconds % dt:
        raise ValueError(f"{case} history interval {history_seconds} s is not a multiple of {dt} s")
    restart_template = stream(package_streams, "restart").get("filename_template")
    if any(token not in restart_template for token in STAMP.split(".")) or flat_name(restart_template) in {
            history.get("filename_template"), BISECTION_TEMPLATE}:
        raise ValueError(f"{case} restart template {restart_template!r} must be timestamped and distinct")
    # Two history intervals; one checkpoint, one step after the midpoint, so it is not at a history time.
    forecast_seconds = max(2 * history_seconds, (STEPS + 1) * dt)
    if case in LONG_CASES:
        forecast_seconds, history_seconds = LONG_CASES[case]
        if forecast_seconds % history_seconds or history_seconds % dt:
            raise ValueError(f"{case} forecast {forecast_seconds} s, history {history_seconds} s, dt {dt} s disagree")
    restart_seconds = (forecast_seconds // (2 * dt) + 1) * dt
    if case in DEFAULT_STREAM_CASES:
        restart_seconds = interval(stream(package_streams, "restart").get("output_interval"))
        if restart_seconds % dt or not 0 < restart_seconds <= forecast_seconds \
                or interval(history.get("output_interval")) != history_seconds:
            raise ValueError(f"{case} package restart {restart_seconds} s or history does not fit the forecast")
        if nml_value(atm_text, "config_run_duration") != duration(forecast_seconds):
            raise ValueError(f"{case} package config_run_duration is not the {forecast_seconds} s forecast")
    plan = {
        "case": case, "init_case": init_case, "mesh": mesh, "init_file": init_file, "dt_seconds": dt,
        "bisection_steps": STEPS, "bisection_template": BISECTION_TEMPLATE,
        "bisection_fields": list(BISECTION_FIELDS) + ["scalars"],
        "initdump_template": INITDUMP_TEMPLATE, "initdump_fields": list(INITDUMP_FIELDS),
        "history_template": history.get("filename_template"), "history_interval_seconds": history_seconds,
        "forecast_seconds": forecast_seconds, "forecast_steps": forecast_seconds // dt,
        "restart_template": restart_template, "restart_seconds": restart_seconds,
        "restart_timestamp_file": timestamp_file,
    }
    if case in CP_CASES:
        plan.update(phases=list(CP_PHASES), thompson_tables=list(THOMPSON_TABLES))
        (trial / "tables").mkdir()
    if case in STATIC_CASES:
        plan.update(phases=list(STATIC_PHASES), static_file=init_input,
                    geog_datasets=list(GEOG_DATASETS), geog_data_path=str(GEOG_DIR) + "/")
    diagnostics = stream(package_streams, "diagnostics") if case in RESTART_CASES else None
    if case in RESTART_CASES:
        run_seconds, every, checkpoint_seconds = RESTART_CASES[case]
        if checkpoint_seconds is None:
            checkpoint_seconds = (run_seconds // (2 * dt) + 1) * dt
        if (every > run_seconds or every % dt or run_seconds % dt or checkpoint_seconds % dt
                or not 0 < checkpoint_seconds <= run_seconds):
            raise ValueError(f"{case} restart run {run_seconds} s, output {every} s, dt {dt} s disagree")
        if forecast_seconds < restart_seconds:
            raise ValueError(f"{case} forecast ends before its checkpoint")
        start_stamp = nml_value(atm_text, "config_start_time")
        restart_start = datetime.strptime(start_stamp, "%Y-%m-%d_%H:%M:%S") + timedelta(seconds=restart_seconds)
        plan.update(phases=list(plan_phases(plan)) + [RESTART_PHASE],
                    restart_run={"start_seconds": restart_seconds, "run_seconds": run_seconds,
                                 "output_interval_seconds": every,
                                 "restart_seconds": checkpoint_seconds,
                                 "diagnostics_template": flat_name(diagnostics.get("filename_template")),
                                 "start_time": stamp_of(restart_start),
                                 "input_restart": expand(restart_template, restart_start)})
    if case in NO_STEPS_CASES:
        plan.update(phases=[phase for phase in plan_phases(plan) if phase != "steps"])
        for key in ("bisection_steps", "bisection_template", "bisection_fields", "initdump_template",
                    "initdump_fields"):
            del plan[key]

    restart_run = plan.get("restart_run")
    for phase, seconds in (("steps", STEPS * dt), ("forecast", forecast_seconds),
                           (RESTART_PHASE, restart_run and restart_run["run_seconds"])):
        if phase not in plan_phases(plan):
            continue
        run = trial / phase
        run.mkdir()
        (run / init_file).symlink_to(Path("..") / "init" / init_file)
        if phase == RESTART_PHASE:
            # The restart stream reads the forecast's checkpoint (mpas_atm_core.F:129-149); a restart run does not
            # read the input stream, whose file is linked as in the other phases.
            (run / restart_run["input_restart"]).symlink_to(Path("..") / "forecast" / restart_run["input_restart"])
        for table in sorted((build / "tables").iterdir()):
            (run / table.name).symlink_to(table.resolve())
        for name in plan.get("thompson_tables", []):
            # build_tables writes them in this trial's tables/ before the model runs.
            (run / name).symlink_to(Path("..") / "tables" / name)
        for item in sorted(package.iterdir()):
            if item.name.endswith(".TBL") or item.name.startswith("stream_list.atmosphere."):
                (run / item.name).unlink(missing_ok=True)
                shutil.copyfile(item, run / item.name)
        text = set_nml(atm_text, "config_run_duration", f"'{duration(seconds)}'")
        if phase == RESTART_PHASE:
            text = set_nml(text, "config_do_restart", "true")
            text = set_nml(text, "config_start_time", f"'{restart_run['start_time']}'")
        (run / "namelist.atmosphere").write_text(text)

        tree = ET.parse(package / "streams.atmosphere",
                        parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
        root = tree.getroot()
        restart = stream(root, "restart")
        if phase == "forecast":
            restart.set("output_interval", duration(restart_seconds))
            if case in LONG_CASES:
                stream(root, "output").set("output_interval", duration(history_seconds))
        elif phase == RESTART_PHASE:
            restart.set("output_interval", duration(restart_run["restart_seconds"]))
            for name in ("output", "diagnostics"):
                stream(root, name).set("output_interval", duration(restart_run["output_interval_seconds"]))
        else:
            restart.set("output_interval", "none")
            # The forecast writes the package history; the short run writes only the bisection stream.
            for item in root:
                if (isinstance(item.tag, str) and item.get("name") != "restart"
                        and "output" in item.get("type", "").split(";")):
                    item.set("output_interval", "none")
            bisection = ET.SubElement(root, "stream", {
                "name": "bisection", "type": "output", "filename_template": BISECTION_TEMPLATE,
                "filename_interval": "output_interval", "output_interval": duration(dt),
                "precision": "double",
            })
            for field in BISECTION_FIELDS:
                ET.SubElement(bisection, "var", {"name": field})
            ET.SubElement(bisection, "var_array", {"name": "scalars"})
            initdump = ET.SubElement(root, "stream", {
                "name": "initdump", "type": "output", "filename_template": INITDUMP_TEMPLATE,
                "output_interval": "initial_only", "precision": "double",
            })
            for field in INITDUMP_FIELDS:
                ET.SubElement(initdump, "var", {"name": field})
        if phase == "forecast" and case in DEFAULT_STREAM_CASES:
            shutil.copyfile(package / "streams.atmosphere", run / "streams.atmosphere")  # as generated
            continue
        tree.write(run / "streams.atmosphere", encoding="unicode")
    (trial / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")


def stamp_of(moment):
    """An MPAS time string of a real-data case (year >= 1000, so no calendar shift)."""
    return moment.strftime("%Y-%m-%d_%H:%M:%S")


def expand(template, moment):
    """filename_template with $Y $M $D $h $m $s of a real-data time (mpas_expand_string)."""
    for token, value in (("$Y", f"{moment.year:04}"), ("$M", f"{moment.month:02}"), ("$D", f"{moment.day:02}"),
                         ("$h", f"{moment.hour:02}"), ("$m", f"{moment.minute:02}"), ("$s", f"{moment.second:02}")):
        template = template.replace(token, value)
    return flat_name(template)


def files_at(directory, template):
    pattern = re.escape(template)
    for token in ("Y", "M", "D", "h", "m", "s"):
        pattern = pattern.replace(re.escape("$" + token), r"[0-9]+")
    return [path for path in sorted(directory.iterdir())
            if path.is_file() and not path.is_symlink() and re.fullmatch(pattern, path.name)]


def time_value(stamp):
    # The idealized cases start in year 0; a 400-year shift keeps the Gregorian calendar.
    return datetime.strptime(f"{int(stamp[:4]) + 400:04}" + stamp[4:], "%Y-%m-%d_%H:%M:%S")


def records(path):
    import netCDF4 as nc

    with nc.Dataset(path) as data:
        xtime = data.variables["xtime"]
        xtime.set_auto_chartostring(False)
        xtime.set_auto_maskandscale(False)
        return [record.tobytes().decode("ascii").rstrip(" \0") for record in xtime[:]]


def offsets(paths, start):
    return [time_value(stamp) - start for path in paths for stamp in records(path)]


def validate(trial):
    """Check the files of one finished trial against its plan. Raises ValueError on any mismatch."""
    import netCDF4 as nc

    plan = json.loads((trial / "plan.json").read_text())
    dt = plan["dt_seconds"]
    if plan.get("thompson_tables"):
        tables = trial / "tables"
        written = sorted(path.name for path in tables.iterdir())
        if written != sorted(plan["thompson_tables"] + [TABLES_LOG]):
            raise ValueError(f"tables/ holds {written}, expected the Thompson tables and {TABLES_LOG}")
        for name in plan["thompson_tables"]:
            if (tables / name).is_symlink() or not (tables / name).stat().st_size:
                raise ValueError(f"tables/{name} is empty or a link")
            for phase in ("steps", "forecast"):
                if (trial / phase / name).resolve() != (tables / name).resolve():
                    raise ValueError(f"{phase}/{name} does not read tables/{name}")
    if plan.get("static_file"):
        static = trial / "static"
        written = sorted(p.name for p in static.glob("*.nc") if p.is_file() and not p.is_symlink())
        if written != [plan["static_file"]]:
            raise ValueError(f"static/ wrote {written}, expected {plan['static_file']}")
        if (trial / "init" / plan["static_file"]).resolve() != (static / plan["static_file"]).resolve():
            raise ValueError(f"init/ does not read static/{plan['static_file']}")
        with nc.Dataset(static / plan["static_file"]) as data:
            static_id = data.getncattr("file_id")
            missing = [f for f in ("ter", "ivgtyp", "isltyp", "var2d", "con", "oa1", "ol1", "albedo12m",
                                   "greenfrac", "soiltemp", "soilcomp", "soilcl1") if f not in data.variables]
        if missing:
            raise ValueError(f"static/{plan['static_file']} lacks {missing}")
    init_path = trial / "init" / plan["init_file"]
    with nc.Dataset(init_path) as data:
        init_id = data.getncattr("file_id")
        init_parent = data.getncattr("parent_id").split("\n")
    start_stamps = records(init_path)
    # In the static cases the init file descends from the trial's static file, so its parent_id starts with
    # that file's file_id, and every model output's parent_id with init's file_id and then the static one.
    chain = [init_id]
    if "static" in plan_phases(plan):
        if init_parent[0].strip() != static_id:
            raise ValueError(f"{plan['init_file']} does not descend from static/{plan['static_file']}")
        chain.append(static_id)
    if len(start_stamps) != 1:
        raise ValueError(f"Init file has {len(start_stamps)} records")
    start = time_value(start_stamps[0])

    has_steps = "steps" in plan_phases(plan)
    if not has_steps and (trial / "steps").exists():
        raise ValueError("A case without the steps phase has a steps directory")
    if has_steps:
        steps = files_at(trial / "steps", plan["bisection_template"])
        expected = [timedelta(seconds=n * dt) for n in range(plan["bisection_steps"] + 1)]
        if offsets(steps, start) != expected or len(steps) != len(expected):
            raise ValueError(
                f"Bisection files {[p.name for p in steps]} do not hold steps 0..{plan['bisection_steps']}")

        dump = trial / "steps" / plan["initdump_template"]
        if not dump.is_file() or offsets([dump], start) != [timedelta(0)]:
            raise ValueError(f"steps/{plan['initdump_template']} must hold one record at the initial time")
        with nc.Dataset(dump) as data:
            missing = [f for f in plan["initdump_fields"] if f not in data.variables]
        if missing:
            raise ValueError(f"steps/{plan['initdump_template']} lacks {missing}")

    forecast = trial / "forecast"
    history = files_at(forecast, plan["history_template"])
    every = plan["history_interval_seconds"]
    if offsets(history, start) != [timedelta(seconds=s) for s in range(0, plan["forecast_seconds"] + 1, every)]:
        raise ValueError(f"History {[p.name for p in history]} does not hold every {every} s")
    restarts = files_at(forecast, plan["restart_template"])
    checkpoint = timedelta(seconds=plan["restart_seconds"])
    marker = (forecast / plan["restart_timestamp_file"]).read_text().strip()
    if (len(restarts) != 1 or offsets(restarts, start) != [checkpoint]
            or time_value(marker) - start != checkpoint):
        raise ValueError(f"Expected one restart at +{checkpoint}, found {[p.name for p in restarts]}, {marker!r}")
    if has_steps and files_at(trial / "steps", plan["restart_template"]):
        raise ValueError("The short run wrote a restart file")

    restart_run = plan.get("restart_run")
    restart_chain = None
    if restart_run:
        # The restart run: history and diagnostics every output interval after its start (none at the start), one
        # checkpoint and its restart_timestamp; every output descends from the forecast's checkpoint, then init.
        run = trial / RESTART_PHASE
        source = run / restart_run["input_restart"]
        if not source.is_symlink() or source.resolve() != (forecast / restart_run["input_restart"]).resolve():
            raise ValueError(f"{RESTART_PHASE}/ does not read forecast/{restart_run['input_restart']}")
        if offsets([source], start) != [checkpoint]:
            raise ValueError(f"{restart_run['input_restart']} is not the forecast's checkpoint")
        first, every = restart_run["start_seconds"], restart_run["output_interval_seconds"]
        expected = [timedelta(seconds=first + s) for s in range(every, restart_run["run_seconds"] + 1, every)]
        for template in (plan["history_template"], restart_run["diagnostics_template"]):
            found = files_at(run, template)
            if offsets(found, start) != expected or len(found) != len(expected):
                raise ValueError(f"{RESTART_PHASE}/ {[p.name for p in found]} do not hold every {every} s after "
                                 f"the restart")
        restarts = files_at(run, plan["restart_template"])
        again = timedelta(seconds=first + restart_run["restart_seconds"])
        marker = (run / plan["restart_timestamp_file"]).read_text().strip()
        if len(restarts) != 1 or offsets(restarts, start) != [again] or time_value(marker) - start != again:
            raise ValueError(f"Expected one restart at +{again} in {RESTART_PHASE}/, found "
                             f"{[p.name for p in restarts]}, {marker!r}")
        with nc.Dataset(source) as data:
            restart_chain = [data.getncattr("file_id")] + chain

    # Every float written by the double-precision build is 8 bytes and finite, and every model output
    # names the trial's own initial file as its parent.
    import numpy as np

    for phase in plan_phases(plan):
        if any(path.is_dir() for path in (trial / phase).iterdir()):
            raise ValueError(f"{phase} holds a subdirectory; outputs must be flat")
        for path in sorted((trial / phase).glob("*.nc")):
            if path.is_symlink():
                continue
            with nc.Dataset(path) as data:
                data.set_auto_maskandscale(False)
                for name, variable in data.variables.items():
                    if variable.dtype.kind != "f":
                        continue
                    if variable.dtype.itemsize != 8:
                        raise ValueError(f"{phase}/{path.name} {name} is {variable.dtype}, not double")
                    if variable.size and not np.isfinite(variable[...]).all():
                        raise ValueError(f"{phase}/{path.name} {name} holds NaN or infinity")
                parent = [line.strip() for line in data.getncattr("parent_id").split("\n")]
                expected_chain = restart_chain if phase == RESTART_PHASE else chain
                if phase not in INIT_CORE_PHASES and parent[:len(expected_chain)] != expected_chain:
                    raise ValueError(f"{phase}/{path.name} does not descend from {plan['init_file']}"
                                     + (" through the forecast's checkpoint" if phase == RESTART_PHASE else ""))


def continuity(trial):
    """Restart cases: the restart run's history against the forecast's (the run without the restart) at every time
    both wrote, and its checkpoint against the forecast's history at the checkpoint's time, as lines for
    continuity.txt. A difference is recorded, not an error: MPAS's restart need not continue the uninterrupted run bit
    for bit (its alarms start again at the checkpoint, RESTART_CASES)."""
    import netCDF4 as nc
    import nc_same
    import numpy as np

    plan = json.loads((trial / "plan.json").read_text())
    lines = []
    restart_files = {p.name: p for p in files_at(trial / RESTART_PHASE, plan["history_template"])}
    for path in files_at(trial / "forecast", plan["history_template"]):
        if path.name not in restart_files:
            continue
        differences = list(nc_same.compare(path, restart_files[path.name]))
        lines += [f"DIFF forecast/{path.name} vs {RESTART_PHASE}/{path.name}: {d}" for d in differences]
        # The global attributes always differ (the namelist options config_do_restart, config_start_time and
        # config_run_duration, and parent_id's extra file of the chain); the verdict is on the variables.
        variables = [d for d in differences if not d.startswith("global attributes")]
        with nc.Dataset(path) as data:
            total = len(data.variables)
        lines.append(f"{'SAME' if not variables else 'DIFFERENT'} forecast/{path.name} vs {RESTART_PHASE}/{path.name}: "
                     f"{len(variables)} of {total} variables differ")
    # The restart run's checkpoint against the forecast's history at the same time (RGR24's at 24:00), in the
    # variables both files hold: their raw values, type and shape.
    history_files = {p.name: p for p in files_at(trial / "forecast", plan["history_template"])}
    for path in files_at(trial / RESTART_PHASE, plan["restart_template"]):
        moment = re.fullmatch(r".*?([0-9]{4})-([0-9]{2})-([0-9]{2})_([0-9]{2})\.([0-9]{2})\.([0-9]{2}).*", path.name)
        if not moment:
            continue
        name = expand(plan["history_template"], datetime(*(int(x) for x in moment.groups())))
        if name not in history_files:
            continue
        with nc.Dataset(history_files[name]) as left, nc.Dataset(path) as right:
            for data in (left, right):
                data.set_auto_maskandscale(False)
                data.set_auto_chartostring(False)
            common = [v for v in left.variables if v in right.variables]
            differ = [v for v in common
                      if left[v].dtype != right[v].dtype or left[v].shape != right[v].shape
                      or np.asarray(left[v][...]).tobytes() != np.asarray(right[v][...]).tobytes()]
        lines += [f"DIFF forecast/{name} vs {RESTART_PHASE}/{path.name}: variable {v}" for v in differ]
        lines.append(f"{'SAME' if not differ else 'DIFFERENT'} forecast/{name} vs {RESTART_PHASE}/{path.name}: "
                     f"{len(differ)} of {len(common)} common variables differ")
    if not lines:
        raise ValueError("The restart run wrote no history or checkpoint at a time of the forecast's history")
    return lines


def parse_cases(value):
    cases = [x for x in re.split(r"[\s,]+", value.strip()) if x]
    if not cases or len(cases) != len(set(cases)) or set(cases) - CASES.keys():
        raise ValueError(f"Expected distinct case IDs from {', '.join(CASES)}, got {value!r}")
    return cases


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    select = cli.add_subparsers(dest="mode", required=True)
    select.add_parser("list").add_argument("cases")
    select.add_parser("swap").add_argument("cases")
    prep = select.add_parser("prepare")
    prep.add_argument("case", choices=CASES)
    prep.add_argument("downloads", type=Path)
    prep.add_argument("build", type=Path)
    prep.add_argument("trial", type=Path)
    select.add_parser("validate").add_argument("trial", type=Path)
    args = cli.parse_args()
    if args.mode == "list":
        print(" ".join(parse_cases(args.cases)))
    elif args.mode == "swap":
        print(max(SWAP_GIB.get(case, 0) for case in parse_cases(args.cases)))
    elif args.mode == "prepare":
        prepare(args.case, args.downloads, args.build, args.trial)
    else:
        validate(args.trial)
