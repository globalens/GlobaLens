# The database images of a GlobaLens node. Built for linux/amd64 and linux/arm64 by
# docker-bake.hcl at the repository root; why these bases and pins: docs/adr/0013-node-images.md.
#
#   server   PostgreSQL 18 with this repository's configuration (postgresql.conf). Phase 1
#            needs no extension; each later one is added here, from a tagged tarball with its
#            checksum, by the task that needs it, with its ADR (plan §6).
#   migrate  The server image's client tools plus dbmate, db/roles.sql and db/migrations: the
#            one-shot migration step (migrate.sh). A separate image, so that a release that
#            only adds a migration does not restart the server.
#
# The build context is this folder (db/); Dockerfile.dockerignore keeps it to what is copied.

ARG TARGETARCH

# PostgreSQL 18.6 on Debian trixie, by the digest of its multi-platform index, the pin the SQL
# tests used since task 8 (docs/adr/0007-sql-tests-and-yaml.md). 18.7's current image build was
# pushed inside the 7-day cooldown; Renovate moves the pin once a build is old enough.
FROM postgres:18.6-trixie@sha256:e3d24f6906d0760bf4da0dae872415391ededefad23fd471c47dc53b0ddf3c42 AS server
COPY postgresql.conf /etc/postgresql/postgresql.conf
CMD ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]

# dbmate 2.37.0, the version mise pins for development (mise.toml): the release's static Linux
# binaries, checked against the SHA-256 of the files as GitHub served them on 2026-11-25.
FROM scratch AS dbmate-amd64
ADD --checksum=sha256:f855e99a0f0a81322014bf686b1cb820d2b4d8074e4eadafd64b851b80ecb15a --chmod=755 \
    https://github.com/amacneil/dbmate/releases/download/v2.37.0/dbmate-linux-amd64 /dbmate

FROM scratch AS dbmate-arm64
ADD --checksum=sha256:42de2bf27989192b9ca8db4cfaa0a9d6b4aee154a03abef30239b7186b1baf82 --chmod=755 \
    https://github.com/amacneil/dbmate/releases/download/v2.37.0/dbmate-linux-arm64 /dbmate

FROM dbmate-${TARGETARCH} AS dbmate

FROM server AS migrate
COPY --from=dbmate /dbmate /usr/local/bin/dbmate
COPY roles.sql /usr/share/globalens/db/roles.sql
COPY migrations/ /usr/share/globalens/db/migrations/
COPY --chmod=755 migrate.sh /usr/local/bin/globalens-migrate
USER postgres
ENTRYPOINT ["/usr/local/bin/globalens-migrate"]
CMD []
