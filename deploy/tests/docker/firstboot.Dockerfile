# The machine deploy/tests/docker/test_firstboot.py boots: Debian 13 with what the first boot uses
# (python3, nftables, util-linux's unshare, systemctl for the units) and what the test's network
# lab uses (iproute2 for the namespaces, openssl for a throwaway certificate authority). Run
# privileged, so that nft and the namespaces act on the container's own network stack only.
# Packages come from Debian's archive at build time, as they do on a node.
FROM debian:trixie-20261104-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 nftables openssl python3 systemd \
    && rm -rf /var/lib/apt/lists/*
