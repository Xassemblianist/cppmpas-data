#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare one trial of an NCAR idealized case and validate the files that trial wrote.

A trial has three run directories: init (init_atmosphere_model), steps (atmosphere_model for ten
timesteps, writing the bisection stream after every step) and forecast (atmosphere_model for two
package history intervals, writing the package history and one restart checkpoint). Only
config_run_duration and the stream intervals are changed; everything else is the NCAR package.
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
}
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


def stage_package(case, downloads, package):
    """Copy the case configuration, tables and mesh from the top directory of the package."""
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
    (init / mesh).symlink_to(Path("..") / "package" / mesh)
    init_text = (package / "namelist.init_atmosphere").read_text()
    if int(nml_value(init_text, "config_init_case")) != init_case:
        raise ValueError(f"{case} package does not select init case {init_case}")
    for name in ("namelist.init_atmosphere", "streams.init_atmosphere"):
        shutil.copyfile(package / name, init / name)
    init_streams = ET.parse(init / "streams.init_atmosphere").getroot()
    if flat_name(stream(init_streams, "input").get("filename_template")) != mesh:
        raise ValueError(f"{case} init input is not {mesh}")
    init_file = flat_name(stream(init_streams, "output").get("filename_template"))

    atm_text = (package / "namelist.atmosphere").read_text()
    if case == "SC" and nml_value(atm_text, "config_microp_scheme") != "mp_kessler":
        raise ValueError("SC requires the package's Kessler microphysics")
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
    restart_seconds = (forecast_seconds // (2 * dt) + 1) * dt
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

    for phase, seconds in (("steps", STEPS * dt), ("forecast", forecast_seconds)):
        run = trial / phase
        run.mkdir()
        (run / init_file).symlink_to(Path("..") / "init" / init_file)
        for table in sorted((build / "tables").iterdir()):
            (run / table.name).symlink_to(table.resolve())
        for item in sorted(package.iterdir()):
            if item.name.endswith(".TBL") or item.name.startswith("stream_list.atmosphere."):
                (run / item.name).unlink(missing_ok=True)
                shutil.copyfile(item, run / item.name)
        (run / "namelist.atmosphere").write_text(
            set_nml(atm_text, "config_run_duration", f"'{duration(seconds)}'"))

        tree = ET.parse(package / "streams.atmosphere",
                        parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
        root = tree.getroot()
        restart = stream(root, "restart")
        if phase == "forecast":
            restart.set("output_interval", duration(restart_seconds))
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
        tree.write(run / "streams.atmosphere", encoding="unicode")
    (trial / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")


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
    init_path = trial / "init" / plan["init_file"]
    with nc.Dataset(init_path) as data:
        init_id = data.getncattr("file_id")
        start_stamps = records(init_path)
    if len(start_stamps) != 1:
        raise ValueError(f"Init file has {len(start_stamps)} records")
    start = time_value(start_stamps[0])

    steps = files_at(trial / "steps", plan["bisection_template"])
    expected = [timedelta(seconds=n * dt) for n in range(plan["bisection_steps"] + 1)]
    if offsets(steps, start) != expected or len(steps) != len(expected):
        raise ValueError(f"Bisection files {[p.name for p in steps]} do not hold steps 0..{plan['bisection_steps']}")

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
    if files_at(trial / "steps", plan["restart_template"]):
        raise ValueError("The short run wrote a restart file")

    # Every float written by the double-precision build is 8 bytes and finite, and every model output
    # names the trial's own initial file as its parent.
    import numpy as np

    for phase in PHASES:
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
                if phase != "init" and data.getncattr("parent_id").split("\n", 1)[0].strip() != init_id:
                    raise ValueError(f"{phase}/{path.name} does not descend from {plan['init_file']}")


def parse_cases(value):
    cases = [x for x in re.split(r"[\s,]+", value.strip()) if x]
    if not cases or len(cases) != len(set(cases)) or set(cases) - CASES.keys():
        raise ValueError(f"Expected distinct case IDs from {', '.join(CASES)}, got {value!r}")
    return cases


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    select = cli.add_subparsers(dest="mode", required=True)
    select.add_parser("list").add_argument("cases")
    prep = select.add_parser("prepare")
    prep.add_argument("case", choices=CASES)
    prep.add_argument("downloads", type=Path)
    prep.add_argument("build", type=Path)
    prep.add_argument("trial", type=Path)
    select.add_parser("validate").add_argument("trial", type=Path)
    args = cli.parse_args()
    if args.mode == "list":
        print(" ".join(parse_cases(args.cases)))
    elif args.mode == "prepare":
        prepare(args.case, args.downloads, args.build, args.trial)
    else:
        validate(args.trial)
