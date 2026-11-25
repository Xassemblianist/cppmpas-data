#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Container side of the build: ci/build.sh double|single ASSET.
# Builds init_atmosphere_model and atmosphere_model from the verified tarballs in /work/downloads and
# writes /work/ASSET (tar.zst of /work/build: bin, tables, licenses, metadata, SHA256SUMS).
set -euo pipefail
shopt -s inherit_errexit
flavour=${1:?precision required}
asset=${2:?asset name required}
case "$flavour" in
    double) precision_message='MPAS was built with default double-precision reals.' ;;
    single) precision_message='MPAS was built with default single-precision reals.' ;;
    *) echo "Unknown precision $flavour" >&2; exit 2 ;;
esac
export SOURCE_DATE_EPOCH=1788553670
downloads=/work/downloads
source=/work/source
out=/work/build
metadata=$out/metadata
mkdir -p "$source" "$out"/{bin,tables,licenses,metadata} /work/logs /work/table-source

# MPAS expects $NETCDF and $PNETCDF to hold include/ and lib/; point them at Debian's directories.
prefix() {
    local dir=/work/prefix/$1 files header lib
    files=$(dpkg -L "$2")
    header=$(grep -m1 "/$3\$" <<< "$files")
    lib=$(grep -m1 "/$4\$" <<< "$files")
    mkdir -p "$dir"
    ln -s "$(dirname "$header")" "$dir/include"
    ln -s "$(dirname "$lib")" "$dir/lib"
    test -e "$dir/include/$3"
    test -e "$dir/lib/$4"
    echo "$dir"
}
NETCDF=$(prefix netcdf libnetcdf-dev netcdf.h libnetcdf.so)
PNETCDF=$(prefix pnetcdf libpnetcdf-dev pnetcdf.h libpnetcdf.so)
export NETCDF PNETCDF

tar -xzf "$downloads/mpas-v8.4.2-f34984b.tar.gz" -C "$source" --strip-components=1 --no-same-owner
physics=$source/src/core_atmosphere/physics
mkdir -p "$physics"/{physics_mmm,physics_noaa/UGWP,physics_wrf/files}
tar -xzf "$downloads/mmm-physics-a4baf7f.tar.gz" -C "$physics/physics_mmm" --strip-components=1 --no-same-owner
tar -xzf "$downloads/ugwp-c1c893e.tar.gz" -C "$physics/physics_noaa/UGWP" --strip-components=1 --no-same-owner
tar -xzf "$downloads/mpas-data-c57dbc7.tar.gz" -C /work/table-source --strip-components=1 --no-same-owner
cp /work/table-source/atmosphere/physics_wrf/files/* "$physics/physics_wrf/files/"
test -s "$physics/physics_mmm/Makefile.mpas"
test -s "$physics/physics_noaa/UGWP/Makefile"
grep -qx '8.2' "$physics/physics_wrf/files/COMPATIBILITY"
# The externals and tables are staged above; the recipe that would clone them must not run.
python3 - "$physics/Makefile" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
old = "\t./../tools/manage_externals/checkout_externals --externals ./../Externals.cfg\n"
if text.count(old) != 1:
    raise SystemExit("The physics Makefile no longer has the expected externals recipe")
path.write_text(text.replace(old, "\t@true\n"))
PY

cp /opt/mpas-packages.tsv "$metadata/packages.tsv"
cp /repo/ci/upstream.tsv /repo/ci/upstream.sha256 "$metadata/"
{
    echo "NETCDF=$NETCDF -> $(readlink "$NETCDF/include") $(readlink "$NETCDF/lib")"
    echo "PNETCDF=$PNETCDF -> $(readlink "$PNETCDF/include") $(readlink "$PNETCDF/lib")"
    gfortran --version
    gcc --version
    g++ --version
    ld --version
    getconf GNU_LIBC_VERSION
    ompi_info --version
    mpif90 --showme
    mpicc --showme
    mpicxx --showme
    nc-config --all
    nf-config --all
} > "$metadata/toolchain.txt"
cp "$source/LICENSE" "$out/licenses/MPAS-Model.txt"
cp "$physics/physics_mmm/LICENSE" "$out/licenses/MMM-physics.txt"
printf '%s\n' 'The pinned UGWP and MPAS-Data trees contain no license file; see their repositories.' \
    > "$out/licenses/NOTICE.txt"

cd "$source"
# Serial make; each core is built from a clean tree (make clean between the cores).
for core in init_atmosphere atmosphere; do
    command=(make -j1 gfortran "CORE=$core" "PRECISION=$flavour" OPENMP=false OPENACC=false
        OPENMP_OFFLOAD=false DEBUG=false PIO= VER=v8.4.2)
    printf '%s\n' "${command[*]}" > "$metadata/$core.command.txt"
    echo "Building $core: ${command[*]}"
    if ! "${command[@]}" > "/work/logs/$core.build.log" 2>&1; then
        tail -n 100 "/work/logs/$core.build.log" >&2
        exit 1
    fi
    grep -Fx 'Using the SMIOL library.' "/work/logs/$core.build.log"
    grep -Fx "$precision_message" "/work/logs/$core.build.log"
    test -x "${core}_model"
    cp "${core}_model" "$out/bin/"
    cp ".build_opts.$core" "$metadata/$core.rebuild-options.txt"
    cp "/work/logs/$core.build.log" "$metadata/"
    grep -E "^mpif90 .*-o ${core}_model " "/work/logs/$core.build.log" > "$metadata/$core.link.txt"
    ldd "${core}_model" | sed -E 's/ \(0x[0-9a-f]+\)$//' > "$metadata/$core.ldd.txt"
    if grep -F 'not found' "$metadata/$core.ldd.txt"; then
        exit 1
    fi
    if [[ "$core" == init_atmosphere ]]; then
        make -j1 clean CORE=init_atmosphere > /work/logs/init_atmosphere.clean.log 2>&1
    fi
done
# The atmosphere build links the WRF physics and Noah-MP tables into the top directory.
cp -L -- *TBL *DATA* "$out/tables/"

cd "$out"
find . -type f ! -name SHA256SUMS -print0 | LC_ALL=C sort -z | xargs -0 sha256sum > SHA256SUMS
tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner -C /work -cf - build \
    | zstd -q -T2 -10 -o "/work/$asset"
