#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Runner side of both workflows: ci/host.sh build|refs, configured by the workflow environment
# (FLAVOUR; for build optionally VERIFY=true, which rebuilds the published asset and compares it; for refs also
# REF_TAG and CASE_LIST; for compare LEFT_TAG and RIGHT_TAG). Everything is written under .ci-work.
set -euo pipefail
shopt -s inherit_errexit
cd "$(dirname "$0")/.."
repo=$PWD
work=$repo/.ci-work
mode=${1:?use build, refs or compare}
flavour=${FLAVOUR:?missing FLAVOUR}
slug=${GITHUB_REPOSITORY:?}
[[ "$mode" == build || "$mode" == refs || "$mode" == compare ]] || { echo "Unknown mode $mode" >&2; exit 2; }
[[ "$flavour" == double || "$flavour" == single ]] || { echo "Unknown flavour $flavour" >&2; exit 2; }
mkdir "$work" "$work/downloads" "$work/logs"

# The build asset is addressed by everything that determines it: image recipe, build script and the
# four source tarballs. Reference-only files (host.sh, ref.py, cases.py, ...) are not part of it.
recipe=$({
    sha256sum .dockerignore ci/Dockerfile ci/debian-packages.txt ci/build.sh
    grep -E '  (mpas-v8|mmm-physics|ugwp-|mpas-data-)[^ ]*\.tar\.gz$' ci/upstream.sha256
} | sha256sum | cut -d' ' -f1)
asset=mpas-8.4.2-$flavour-$recipe.tar.zst
echo "Build asset: $asset"

build_image() {
    docker build --platform linux/amd64 --progress plain --iidfile "$work/image-id" --file ci/Dockerfile .
    IMAGE_ID=$(< "$work/image-id")
}

if [[ "$mode" == build ]]; then
    if ! assets=$(gh release view mpas-build --repo "$slug" --json assets --jq '.assets[].name'); then
        echo "Create the mpas-build release first (see README.md)" >&2
        exit 1
    fi
    published=false
    if grep -Fxq "$asset" <<< "$assets"; then
        published=true
        if [[ "${VERIFY:-false}" != true ]]; then
            echo "mpas-build already has $asset"
            exit 0
        fi
    elif [[ "${VERIFY:-false}" == true ]]; then
        echo "VERIFY rebuilds a published asset, and mpas-build has no $asset" >&2
        exit 1
    fi
    bash ci/inputs.sh build "$work/downloads"
    build_image
    docker run --rm --network none --platform linux/amd64 -v "$repo:/repo:ro" -v "$work:/work" \
        "$IMAGE_ID" bash /repo/ci/build.sh "$flavour" "$asset"
    sha256sum "$work/$asset"
    if [[ "$published" == false ]]; then
        gh release upload mpas-build "$work/$asset" --repo "$slug"
        exit 0
    fi
    # VERIFY: a second, independent build must give the published executables, tables and licenses bit for bit.
    mkdir "$work/published" "$work/rebuilt"
    gh release download mpas-build --repo "$slug" --pattern "$asset" --dir "$work/published"
    sha256sum "$work/published/$asset"
    zstd -q -dc "$work/published/$asset" | tar -xf - -C "$work/published"
    zstd -q -dc "$work/$asset" | tar -xf - -C "$work/rebuilt"
    grep -E '  \./(bin|tables|licenses)/' "$work/published/build/SHA256SUMS" > "$work/published.sums"
    grep -E '  \./(bin|tables|licenses)/' "$work/rebuilt/build/SHA256SUMS" > "$work/rebuilt.sums"
    cat "$work/rebuilt.sums"
    (cd "$work/published/build" && sha256sum --quiet -c SHA256SUMS)
    if ! diff "$work/published.sums" "$work/rebuilt.sums"; then
        echo "The rebuild differs from the published $asset" >&2
        exit 1
    fi
    echo "Rebuild identical to the published $asset in bin/, tables/ and licenses/" \
        "($(wc -l < "$work/rebuilt.sums") files)"
    if cmp -s "$work/published/$asset" "$work/$asset"; then
        echo "The rebuilt archive is byte-identical to the published one"
    else
        echo "Metadata files that differ (not part of the comparison):"
        diff <(grep -v -E '  \./(bin|tables|licenses)/' "$work/published/build/SHA256SUMS") \
            <(grep -v -E '  \./(bin|tables|licenses)/' "$work/rebuilt/build/SHA256SUMS") || true
    fi
    exit 0
fi

if [[ "$mode" == compare ]]; then
    # Two published references, fetched and checked as README.md describes, compared file by file by ci/compare.py.
    for side in left right; do
        if [[ "$side" == left ]]; then tag=${LEFT_TAG:?}; else tag=${RIGHT_TAG:?}; fi
        mkdir "$work/$side.download" "$work/$side"
        gh release download "$tag" --repo "$slug" --dir "$work/$side.download"
        (
            cd "$work/$side.download"
            sha256sum -c --ignore-missing "$tag.sha256"
            cat "$tag".tar.zst.part* > "$tag.tar.zst"
            rm "$tag".tar.zst.part*
            sha256sum -c --ignore-missing "$tag.sha256"
            zstd -q -dc "$tag.tar.zst" | tar -xf - -C "$work/$side"
        )
        rm -r "$work/$side.download"
        (cd "$work/$side" && sha256sum --quiet -c SHA256SUMS)
        df -h "$work"
    done
    build_image
    docker run --rm --network none --platform linux/amd64 -v "$repo:/repo:ro" -v "$work:/work:ro" \
        "$IMAGE_ID" python3 /repo/ci/compare.py /work/left /work/right
    exit 0
fi

[[ "$flavour" == double ]] || { echo "Only double-precision references are produced" >&2; exit 2; }
tag=${REF_TAG:?}
if [[ ! "$tag" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ || "$tag" == mpas-build || "$tag" == inputs ]]; then
    echo "Invalid reference tag $tag" >&2
    exit 2
fi
git check-ref-format "refs/tags/$tag"
if gh release view "$tag" --repo "$slug" > /dev/null 2>&1 || git ls-remote --exit-code --tags origin "refs/tags/$tag" > /dev/null; then
    echo "Tag or release $tag already exists. Choose a new tag." >&2
    exit 2
fi
selected=$(python3 ci/cases.py list "${CASE_LIST:?}")
read -ra case_ids <<< "$selected"

python3 - "$work/cpu.json" <<'PY'
import json
from pathlib import Path
import sys

blocks = [b for b in Path("/proc/cpuinfo").read_text().split("\n\n") if b.strip()]
wanted = {"vendor_id", "cpu family", "model", "model name", "stepping", "microcode"}
cpu, flags = {}, None
for block in blocks:
    for line in block.splitlines():
        key, _, value = (part.strip() for part in line.partition(":"))
        if key in wanted:
            cpu.setdefault(key, value)
        elif key == "flags":
            flags = set(value.split()) if flags is None else flags & set(value.split())
cpu["logical_cpus"] = len(blocks)
cpu["flags_on_all_cpus"] = " ".join(sorted(flags or ()))
Path(sys.argv[1]).write_text(json.dumps(cpu, sort_keys=True, indent=1) + "\n")
print(cpu.get("model name", "unknown CPU"))
# glibc's libm ifuncs select the FMA variants with AVX2+FMA; libmvec and the rounding functions use SSE4.1.
missing = {"avx2", "fma", "sse4_1"} - (flags or set())
if missing:
    sys.exit(f"The runner CPU lacks {sorted(missing)}, so glibc would select other libm variants")
PY

bash ci/inputs.sh cases "$work/downloads" "${case_ids[@]}"
gh release download mpas-build --repo "$slug" --pattern "$asset" --dir "$work"
BUILD_SHA256=$(sha256sum "$work/$asset" | cut -d' ' -f1)
zstd -q -dc "$work/$asset" | tar -xf - -C "$work"
(cd "$work/build" && sha256sum --quiet -c SHA256SUMS)
build_image

BASE_IMAGE=$(awk '/^FROM / {print $2}' ci/Dockerfile)
DOCKER_SERVER=$(docker version --format '{{.Server.Version}}')
export REF_TAG=$tag BUILD_ASSET=$asset BUILD_SHA256 RECIPE_SHA256=$recipe IMAGE_ID BASE_IMAGE DOCKER_SERVER
docker run --rm --platform linux/amd64 --shm-size 1g -v "$repo:/repo:ro" -v "$work:/work" \
    -e CASE_LIST -e REF_TAG -e BUILD_ASSET -e BUILD_SHA256 -e RECIPE_SHA256 -e BASE_IMAGE -e IMAGE_ID \
    -e DOCKER_SERVER -e RUNNER_ENVIRONMENT -e RUNNER_OS -e RUNNER_ARCH -e ImageOS -e ImageVersion \
    -e GITHUB_REPOSITORY -e GITHUB_SHA -e GITHUB_RUN_ID -e GITHUB_RUN_ATTEMPT \
    "$IMAGE_ID" bash -euo pipefail -c '
        # The image must hold exactly the packages the executables were built against.
        cmp /opt/mpas-packages.tsv /work/build/metadata/packages.tsv
        python3 /repo/ci/ref.py
        tar --sort=name --mtime=@1788553670 --owner=0 --group=0 --numeric-owner -C /work/reference -cf - . \
            | zstd -q -T2 -10 -o "/work/$REF_TAG.tar.zst"
    '

# A release asset must be smaller than 2 GiB, so the archive is published in parts of 1900 MiB.
cd "$work"
archive=$tag.tar.zst
split -b 1900M -d -a 2 "$archive" "$archive.part"
sha256sum "$archive" "$archive".part* > "$tag.sha256"
cat "$tag.sha256"
rm "$archive"
gh release create "$tag" "$archive".part* "$tag.sha256" --repo "$slug" --target "$GITHUB_SHA" --title "$tag" \
    --notes "MPAS-Atmosphere 8.4.2 double-precision references for ${case_ids[*]} (workflow run $GITHUB_RUN_ID). See README.md to fetch and check them."
