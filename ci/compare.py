#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare two extracted reference archives file by file: ci/compare.py LEFT RIGHT.

Every file of every case directory must be on both sides and the same: NetCDF files by ci/nc_same.py (format,
dimensions, attributes and raw value bytes; only MPAS's random file_id characters are not compared), every
other file byte for byte. MPAS's own logs (log.*, mpiexec.log) hold timings and are not compared. The two
archives must come from the same build asset; provenance.json is not compared (it records the runner), but
the runner CPU, commit and build of each side are printed. recipe/ (the ci/ scripts and workflows of the
commit that made the reference) is compared too, but a difference there is only reported: two references
dispatched from different commits with the same build may differ in it. Exits 1 on any other difference.
"""
import argparse
import json
from pathlib import Path

import nc_same

SKIPPED_TOP = {"provenance.json", "SHA256SUMS"}


def compared(path):
    return not (path.name.startswith("log.") or path.name == "mpiexec.log")


def files(root):
    return {path.relative_to(root).as_posix(): path for path in root.rglob("*")
            if path.is_file() and compared(path)}


def main():
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("left", type=Path)
    cli.add_argument("right", type=Path)
    args = cli.parse_args()
    receipts = [json.loads((side / "provenance.json").read_text()) for side in (args.left, args.right)]
    for side, receipt in zip((args.left, args.right), receipts):
        cpu = receipt["environment"]["cpu"]
        print(f"{side.name}: {receipt['tag']}, run {receipt['workflow']['GITHUB_RUN_ID']}, "
              f"{cpu.get('vendor_id')} {cpu.get('model name')}, commit {receipt['workflow'].get('GITHUB_SHA')}, "
              f"build {receipt['build']['asset_sha256']}")
    failures = 0
    if receipts[0]["build"]["asset_sha256"] != receipts[1]["build"]["asset_sha256"]:
        print("BUILD-DIFF the two references come from different build assets")
        failures += 1
    left, right = files(args.left), files(args.right)
    names = sorted((left.keys() | right.keys()) - SKIPPED_TOP)
    nc_files = 0
    for name in names:
        if name not in left or name not in right:
            print(f"MISSING {name} only in {'left' if name in left else 'right'}")
            failures += 1
        elif name.endswith(".nc"):
            differences = list(nc_same.compare(left[name], right[name]))
            for difference in differences:
                print(f"DATA-DIFF {name} {difference}")
            failures += bool(differences)
            nc_files += 1
        elif left[name].read_bytes() != right[name].read_bytes():
            if name.startswith("recipe/"):
                print(f"RECIPE-DIFF {name} (reported, not a failure)")
            else:
                print(f"FILE-DIFF {name}")
                failures += 1
    print(f"{len(names)} files compared ({nc_files} NetCDF), "
          f"{failures} differences")
    return 1 if failures or not nc_files else 0


if __name__ == "__main__":
    raise SystemExit(main())
