#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run each selected case twice on one MPI rank, require identical outputs, and stage /work/reference.

Runs inside the container started by ci/host.sh, with the verified build in /work/build and the
verified case packages in /work/downloads.
"""
import difflib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import resource
import shutil
import subprocess
import sys
import time

import cases
import nc_same

MPAS_COMMIT = "f34984b2c89353cf31c235b08d3b4acd96b37bb3"
CORES = ("init_atmosphere", "atmosphere")
# One rank needs only the self transport; this keeps UCX and the network out of MPI_Init.
MPI_ENV = {"OMPI_MCA_pml": "ob1", "OMPI_MCA_btl": "self"}
MPIEXEC = ("mpiexec", "--allow-run-as-root", "-n", "1")
WORK = Path("/work")
# glibc libmvec's SSE4 vector log and log10 take an approximate reciprocal (rcpps) whose bits the hardware defines,
# so physics loops gfortran vectorises give different last bits on Intel and AMD runners (rg-003 Intel vs rg-001/002
# AMD differed from the first step). As CPPWRF does for WRF's references, every MPAS run preloads CPPWRF's
# tests/phys/libmvec_intel.cpp (ci/mvec_intel, copied from CPPWRF 7fac5bf with its headers, SHA256SUMS there): those
# two functions as an Intel CPU computes them, on every x86-64 CPU. The idealized dycore cases are unaffected.
MVEC_PRELOAD = WORK / "libmvec_intel.so"


def build_preload():
    src = Path("/repo/ci/mvec_intel")
    subprocess.run(["sha256sum", "--quiet", "-c", "SHA256SUMS"], cwd=src, check=True)
    subprocess.run(["g++", "-std=c++20", "-O2", "-ffp-contract=off", "-fPIC", "-shared", "-I", str(src),
                    str(src / "tests" / "phys" / "libmvec_intel.cpp"), "-o", str(MVEC_PRELOAD)], check=True)


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def raise_stack_limit():
    # gfortran places automatic arrays on the stack; use the hard limit rather than the 8 MiB default.
    _, hard = resource.getrlimit(resource.RLIMIT_STACK)
    resource.setrlimit(resource.RLIMIT_STACK, (hard, hard))


def run_measured(args, **kwargs):
    """Run args to completion; return (exit status, peak resident set size in KiB). wait4's ru_maxrss is the
    largest of the child and every descendant it waited for, so under mpiexec it is the model process's peak."""
    process = subprocess.Popen(args, **kwargs)
    _, status, usage = os.wait4(process.pid, 0)
    process.returncode = os.waitstatus_to_exitcode(status)
    return process.returncode, usage.ru_maxrss


def launch(directory, binary):
    started = time.monotonic()
    with (directory / "mpiexec.log").open("wb") as log:
        returncode, peak_kib = run_measured(
            [*MPIEXEC, str(binary)], cwd=directory, stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, **MPI_ENV, "LD_PRELOAD": str(MVEC_PRELOAD)}, preexec_fn=raise_stack_limit)
    print(f"{directory.name}: {time.monotonic() - started:.1f} s, peak RSS {peak_kib} KiB", flush=True)
    logs = sorted(directory.glob("log.*.out"))
    errors = sorted(directory.glob("log.*.err"))
    # MPAS writes log.*.err only for error messages; a non-critical error (e.g. a stream that could not
    # be written) does not stop the model, so any .err file fails the run.
    if returncode or len(logs) != 1 or errors:
        for path in (directory / "mpiexec.log", *logs, *errors):
            tail = path.read_text(errors="replace").splitlines()[-80:]
            print(f"--- {path}", *tail, sep="\n", file=sys.stderr)
        raise RuntimeError(f"MPAS failed in {directory}: exit code {returncode}, "
                           f"{len(logs)} log files, {len(errors)} error logs")
    return round(time.monotonic() - started, 3), peak_kib


def build_tables(directory, binary):
    """MPAS's build_tables (src/core_atmosphere/utils/build_tables.F) in directory, as a user runs it: one serial
    process, no MPI launcher, with the run's libmvec preload and stack limit. It writes the four Thompson tables
    there. It reports a table it cannot create on stderr and still stops with status 0
    (atmphys_build_tables_thompson.F:45-49), so the tables and its closing message are checked here."""
    started = time.monotonic()
    with (directory / cases.TABLES_LOG).open("wb") as log:
        returncode, peak_kib = run_measured(
            [str(binary)], cwd=directory, stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, "LD_PRELOAD": str(MVEC_PRELOAD)}, preexec_fn=raise_stack_limit)
    text = (directory / cases.TABLES_LOG).read_text(errors="replace")
    missing = [name for name in cases.THOMPSON_TABLES if not (directory / name).is_file()]
    if returncode or missing or "Finished building all tables." not in text:
        print(f"--- {directory / cases.TABLES_LOG}", *text.splitlines()[-80:], sep="\n", file=sys.stderr)
        raise RuntimeError(f"build_tables failed in {directory}: exit code {returncode}, missing {missing}")
    return round(time.monotonic() - started, 3), peak_kib


def outputs(directory):
    return {path.name: path for path in directory.glob("*.nc") if path.is_file() and not path.is_symlink()}


def compare_trials(first, second, receipt, phases):
    """Write every comparison to the receipt and raise if anything differs."""
    failures = files = 0
    with receipt.open("w") as log:
        def report(line):
            print(line, file=log, flush=True)

        for phase in phases:
            left, right = outputs(first / phase), outputs(second / phase)
            for name in sorted(left.keys() ^ right.keys()):
                report(f"DATA-DIFF {phase}/{name} written by one trial only")
                failures += 1
            for name in sorted(left.keys() & right.keys()):
                differences = list(nc_same.compare(left[name], right[name]))
                for difference in differences:
                    report(f"DATA-DIFF {phase}/{name} {difference}")
                report(f"DATA-SAME {phase}/{name}" if not differences else f"DATA-DIFF {phase}/{name}")
                failures += bool(differences)
                files += 1
            def texts(trial):
                return {p.name: p.read_bytes() for p in (trial / phase).iterdir() if p.is_file()
                        and not p.is_symlink() and not p.name.endswith(".nc") and not p.name.startswith(
                            ("log.", "mpiexec.log"))}
            left_text, right_text = texts(first), texts(second)
            for name in sorted(left_text.keys() | right_text.keys()):
                if left_text.get(name) != right_text.get(name):
                    report(f"TEXT-DIFF {phase}/{name}")
                    failures += 1
        report(f"{files} NetCDF files compared, {failures} differences")
    if failures or not files:
        raise RuntimeError(f"The two trials differ; see {receipt}")


def stage_trial(trial, target):
    package = trial / "package"
    shutil.copyfile(trial / "plan.json", target / "plan.json")
    (target / "package").mkdir()
    plan = json.loads((trial / "plan.json").read_text())
    for path in sorted(package.iterdir()):
        if path.name != plan["mesh"]:
            shutil.copyfile(path, target / "package" / path.name)
    patches = []
    for phase in cases.plan_phases(plan):
        directory = target / phase
        directory.mkdir()
        for path in sorted((trial / phase).iterdir()):
            if path.is_file() and not path.is_symlink():
                os.link(path, directory / path.name)
                original = package / path.name
                if path.name.startswith(cases.PACKAGE_PREFIXES) and original.is_file():
                    patches.extend(difflib.unified_diff(
                        original.read_text().splitlines(keepends=True), path.read_text().splitlines(keepends=True),
                        f"package/{path.name}", f"{phase}/{path.name}"))
    (target / "configuration.diff").write_text("".join(patches))


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def apt_snapshot():
    text = Path("/repo/ci/Dockerfile").read_text()
    snapshot = re.search(r"snapshot\.debian\.org/archive/debian/(\w+)/", text)
    release = re.search(r"\b([0-9a-f]{64})\s+/var/lib/apt/lists/\S+_InRelease", text)
    return {"snapshot": snapshot[1], "inrelease_sha256": release[1]}


def main():
    downloads, build, target = WORK / "downloads", WORK / "build", WORK / "reference"
    target.mkdir()
    build_preload()
    selected = cases.parse_cases(os.environ["CASE_LIST"])
    meta = target / "build-metadata"
    shutil.copytree(build / "metadata", meta, ignore=shutil.ignore_patterns("*.build.log"))
    for core in CORES:
        subprocess.run(["zstd", "-q", "-19", str(build / "metadata" / f"{core}.build.log"),
                        "-o", str(meta / f"{core}.build.log.zst")], check=True)
    shutil.copyfile(build / "SHA256SUMS", meta / "build-SHA256SUMS")
    recipe = target / "recipe"
    shutil.copytree("/repo/ci", recipe / "ci", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree("/repo/.github/workflows", recipe / "workflows")
    packages = dict(line.split("\t", 1) for line in (meta / "packages.tsv").read_text().splitlines())
    receipt = {
        "tag": os.environ["REF_TAG"],
        "mpas": {"version": "8.4.2", "commit": MPAS_COMMIT, "precision": "double"},
        "build": {
            "asset": os.environ["BUILD_ASSET"], "asset_sha256": os.environ["BUILD_SHA256"],
            "recipe_sha256": os.environ["RECIPE_SHA256"],
            "make_commands": {core: (meta / f"{core}.command.txt").read_text().strip() for core in CORES},
            "make_options": {core: (meta / f"{core}.rebuild-options.txt").read_text() for core in CORES},
            "link_commands": {core: (meta / f"{core}.link.txt").read_text().strip() for core in CORES},
            "executables_sha256": {**{core: sha256(build / "bin" / f"{core}_model") for core in CORES},
                                   "build_tables": sha256(build / "bin" / "build_tables")},
        },
        "run": {
            "launcher": " ".join(MPIEXEC), "mpi_ranks": 1, "openmp": False, "openacc": False,
            "mpi_environment": MPI_ENV, "mpi_version": command("ompi_info", "--version"),
            "stack_limit": "raised to the hard limit",
            "ld_preload": {"library": "CPPWRF tests/phys/libmvec_intel.cpp (Intel's _ZGVbN2v_log, _ZGVbN2v_log10)",
                           "sources": "ci/mvec_intel (CPPWRF 7fac5bf)", "sha256": sha256(MVEC_PRELOAD)},
            "environment": {key: os.environ.get(key, "") for key in ("LC_ALL", "TZ", "OMP_NUM_THREADS")},
            "io": "SMIOL with PnetCDF (CDF-5)", "glibc_tunables": os.environ.get("GLIBC_TUNABLES", ""),
            "glibc": platform.libc_ver()[1],
        },
        "environment": {
            "container_base": os.environ["BASE_IMAGE"], "container_image_id": os.environ["IMAGE_ID"],
            "apt": apt_snapshot(), "package_versions": packages,
            "kernel": platform.release(), "docker_server": os.environ["DOCKER_SERVER"],
            "runner": {key: os.environ.get(key, "") for key in (
                "RUNNER_ENVIRONMENT", "RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion")},
            "cpu": json.loads((WORK / "cpu.json").read_text()),
        },
        "workflow": {key: os.environ[key] for key in (
            "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")},
        "comparison": {
            "trials": 2,
            "rule": "same NetCDF format, dimensions, variables, attributes and value bytes, in file order",
            "random_global_attributes": ["file_id", "parent_id (first line)"],
        },
        "cases": {},
    }
    for case in selected:
        case_path = target / case
        case_path.mkdir()
        replicas = WORK / "trials" / case
        timings, peaks = {}, {}
        for trial in ("A", "B"):
            trial_path = replicas / trial
            cases.prepare(case, downloads, build, trial_path)
            timings[trial], peaks[trial] = {}, {}
            phases = cases.plan_phases(json.loads((trial_path / "plan.json").read_text()))
            for phase in phases:
                if phase == "tables":
                    print(f"{case}/{trial}/{phase}: build_tables", flush=True)
                    timings[trial][phase], peaks[trial][phase] = build_tables(
                        trial_path / phase, build / "bin" / "build_tables")
                    continue
                core = "init_atmosphere" if phase in cases.INIT_CORE_PHASES else "atmosphere"
                print(f"{case}/{trial}/{phase} on one MPI rank", flush=True)
                timings[trial][phase], peaks[trial][phase] = launch(
                    trial_path / phase, build / "bin" / f"{core}_model")
            cases.validate(trial_path)

        compare_trials(replicas / "A", replicas / "B", case_path / "determinism.txt", phases)
        stage_trial(replicas / "A", case_path)
        plan = json.loads((case_path / "plan.json").read_text())
        input_asset = downloads / cases.CASES[case][1]
        receipt["cases"][case] = {
            "input_asset": input_asset.name, "input_sha256": sha256(input_asset),
            "mesh": plan["mesh"], "mesh_sha256": sha256(replicas / "A" / "package" / plan["mesh"]),
            "partition": "none (one rank reads no graph partition file)",
            "package_files_sha256": {p.name: sha256(p) for p in sorted((case_path / "package").iterdir())},
            "seconds": timings, "peak_rss_kib": peaks, "plan": plan,
        }
        if plan.get("geog_datasets"):
            receipt["cases"][case]["geog_sha256"] = {
                f"{name}.tar.bz2": sha256(downloads / f"{name}.tar.bz2") for name in plan["geog_datasets"]}
        if plan.get("thompson_tables"):
            receipt["cases"][case]["thompson_tables_sha256"] = {
                name: sha256(case_path / "tables" / name) for name in plan["thompson_tables"]}
        print((case_path / "determinism.txt").read_text().rstrip(), flush=True)
        shutil.rmtree(replicas)

    (target / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")
    with (target / "SHA256SUMS").open("w") as manifest:
        for path in sorted(target.rglob("*")):
            if path.is_file() and path.name != "SHA256SUMS":
                manifest.write(f"{sha256(path)}  {path.relative_to(target).as_posix()}\n")


if __name__ == "__main__":
    main()
