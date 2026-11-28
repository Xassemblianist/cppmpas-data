#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare two MPAS NetCDF files: format, dimensions, global and variable attributes, and the raw bytes
of every variable, all in file order and without masking, scaling or character conversion.

MPAS writes two global attributes that differ between identical runs (src/framework/mpas_stream_manager.F
and src/framework/mpas_bootstrapping.F): `file_id`, ten random characters from rand() seeded with the
wall-clock second, and `parent_id`, whose first line is the `file_id` of the file the run started from,
followed by that file's own `parent_id`. So a model output's `parent_id` starts with one random line for each
file of the chain the trial wrote (init, and static before it in the static cases). Each must have that form on
both sides; only the random characters themselves are not compared. ci/cases.py checks that the chain names the
trial's own files.
"""
import argparse
from itertools import product
from pathlib import Path
import re

import netCDF4 as nc
import numpy as np

RANDOM_ID = re.compile(r"[0-9a-z]{10}")
BLOCK_BYTES = 8 * 1024 * 1024


def signature(value):
    array = np.asarray(value)
    if array.dtype.hasobject:
        raise ValueError("Unsupported NetCDF attribute type")
    return array.dtype.str, array.shape, array.tobytes()


def global_attributes(dataset):
    result = []
    for name in dataset.ncattrs():
        value = dataset.getncattr(name)
        if name == "file_id":
            if not (isinstance(value, str) and RANDOM_ID.fullmatch(value)):
                raise ValueError(f"Unexpected file_id {value!r}")
            value = "<random>"
        elif name == "parent_id" and isinstance(value, str):
            lines = value.split("\n")
            for i, line in enumerate(lines[:-1]):
                if not RANDOM_ID.fullmatch(line):
                    break
                lines[i] = "<random>"
            value = "\n".join(lines)
        result.append((name, signature(value)))
    return result


def attributes(variable):
    return [(name, signature(variable.getncattr(name))) for name in variable.ncattrs()]


def blocks(shape, itemsize):
    remaining = max(1, BLOCK_BYTES // itemsize)
    widths = []
    for length in reversed(shape):
        width = max(1, min(length, remaining))
        widths.append(width)
        remaining = max(1, remaining // width)
    widths.reverse()
    for start in product(*(range(0, length, width) for length, width in zip(shape, widths))):
        yield tuple(slice(first, first + width) for first, width in zip(start, widths))


def compare(left, right):
    """Yield a description of every difference; nothing when the files match."""
    with nc.Dataset(left) as a, nc.Dataset(right) as b:
        for dataset in (a, b):
            dataset.set_auto_maskandscale(False)
            dataset.set_auto_chartostring(False)
            if dataset.groups:
                raise ValueError("Unexpected NetCDF groups in MPAS output")
        if a.data_model != b.data_model:
            yield f"format {a.data_model} | {b.data_model}"
        if [(k, len(v), v.isunlimited()) for k, v in a.dimensions.items()] != [
                (k, len(v), v.isunlimited()) for k, v in b.dimensions.items()]:
            yield "dimensions"
        ga, gb = global_attributes(a), global_attributes(b)
        if ga != gb:
            names = sorted({n for n, _ in ga} ^ {n for n, _ in gb} | {
                n for (n, x), (m, y) in zip(ga, gb) if n != m or x != y})
            yield f"global attributes {names}"

        av, bv = a.variables, b.variables
        if list(av) != list(bv):
            yield f"variable lists differ: {sorted(av.keys() ^ bv.keys())} (or their order)"
        for name in av:
            if name not in bv:
                continue
            x, y = av[name], bv[name]
            dtype = np.dtype(x.dtype)
            if dtype.kind not in "biufcS" or x.datatype is str or y.datatype is str:
                raise ValueError(f"Unsupported NetCDF type in {name}")
            if (dtype, x.shape, x.dimensions, x.endian()) != (
                    np.dtype(y.dtype), y.shape, y.dimensions, y.endian()):
                yield f"{name} dtype, shape, dimensions or byte order"
                continue
            if attributes(x) != attributes(y):
                yield f"{name} attributes"
            for block in blocks(x.shape, dtype.itemsize):
                if np.asarray(x[block]).tobytes() != np.asarray(y[block]).tobytes():
                    yield f"{name} value bytes differ in {block}"
                    break


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    args = parser.parse_args()
    differences = list(compare(args.left, args.right))
    for difference in differences:
        print(f"DATA-DIFF {difference}")
    if not differences:
        print("DATA-SAME")
    return 1 if differences else 0


if __name__ == "__main__":
    raise SystemExit(main())
