# SPDX-License-Identifier: GPL-3.0-or-later
# Debian 13 build and run image. The base is pinned by digest and APT reads a dated snapshot whose signed
# InRelease is pinned by SHA-256, so the package set below resolves to the same files on every build.
FROM docker.io/library/debian@sha256:ab3b3c8c5159eebfca4376430132d53c4d425f869c765ecbe47177a030da575d
COPY ci/debian-packages.txt /opt/debian-packages.txt
RUN set -eu; \
    export DEBIAN_FRONTEND=noninteractive; \
    rm -f /etc/apt/sources.list /etc/apt/sources.list.d/*; \
    echo 'deb [check-valid-until=no signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] http://snapshot.debian.org/archive/debian/20261123T000000Z/ trixie main' \
        > /etc/apt/sources.list; \
    printf '%s\n' 'Acquire::Languages "none";' 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/99snapshot; \
    apt-get -o APT::Update::Error-Mode=any update; \
    echo 'bfacad4ca61899ce20d4a0d439f29339f66541561b67506364efb88e27dee870  /var/lib/apt/lists/snapshot.debian.org_archive_debian_20261123T000000Z_dists_trixie_InRelease' \
        | sha256sum -c -; \
    xargs apt-get install -y --no-install-recommends < /opt/debian-packages.txt; \
    dpkg-query -W -f='${binary:Package}\t${Version}\n' | LC_ALL=C sort > /opt/mpas-packages.tsv; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*
# glibc's ifuncs pick the FMA/AVX2 libm variants; ci/host.sh refuses a runner CPU without both.
# The run scripts execute as root in the container, so Open MPI must be told that this is intended.
ENV LC_ALL=C TZ=UTC OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
    OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
