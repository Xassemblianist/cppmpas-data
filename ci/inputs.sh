#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# ci/inputs.sh build DEST | ci/inputs.sh cases DEST ID...
# Downloads the pinned tarballs of the given role(s) from this repository's `inputs` release into DEST
# and checks each against ci/upstream.sha256. ci/upstream.tsv records where each tarball came from;
# the workflows never fetch from those URLs because GitHub's generated archives are not byte-stable.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
mode=${1:?use build or cases}
dest=${2:?download directory required}
shift 2
case "$mode" in
    build) roles=(build) ;;
    cases) roles=("$@") ;;
    *) echo "Unknown mode $mode" >&2; exit 2 ;;
esac
(( ${#roles[@]} > 0 )) || { echo "No case IDs given" >&2; exit 2; }
mkdir -p "$dest"
fetched=()
while IFS=$'\t' read -r -u 3 role file _url; do
    [[ -z "$role" || "$role" == \#* ]] && continue
    [[ " ${roles[*]} " == *" $role "* ]] || continue
    digest=$(awk -v f="$file" '$2 == f && NF == 2 {print $1}' "$root/ci/upstream.sha256")
    if [[ ! "$digest" =~ ^[0-9a-f]{64}$ ]]; then
        echo "Missing or invalid SHA-256 for $file in ci/upstream.sha256" >&2
        exit 1
    fi
    gh release download inputs --repo "${GITHUB_REPOSITORY:?}" --pattern "$file" --dir "$dest" < /dev/null
    printf '%s  %s\n' "$digest" "$dest/$file" | sha256sum -c -
    fetched+=("$role")
done 3< "$root/ci/upstream.tsv"
# one tarball per role, except RG (static archive and first-guess file) and build (four tarballs)
expected=$(awk -F'\t' -v r=" ${roles[*]} " '$1 !~ /^#/ && $1 != "" && index(r, " " $1 " ") {n++} END {print n + 0}' \
    "$root/ci/upstream.tsv")
if (( ${#fetched[@]} != expected )); then
    echo "Fetched ${#fetched[@]} tarballs for ${roles[*]}, expected $expected" >&2
    exit 1
fi
