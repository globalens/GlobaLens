# The worker's images. Built for linux/amd64 and linux/arm64 by docker-bake.hcl at the
# repository root; why these bases and pins: docs/adr/0013-node-images.md.
#
#   worker   python -m worker: the poller, the tier-1 workers and (with task 11) the publisher.
#            One image, one service per role in Compose.
#   edge     cloudflared behind the role guard (python -m worker.guard). The guard is the
#            entrypoint, so a Compose `command:` can change cloudflared's arguments but cannot
#            start it without the guard's checks.
#
# The build context is the repository root (the uv workspace and its lockfile);
# Dockerfile.dockerignore beside this file keeps it to what is copied.

# Python 3.13 on Debian trixie, slim. 3.13.17 is the newest build pushed before the 7-day
# cooldown (3.13.18's current build was pushed on 2026-11-24).
FROM python:3.13.17-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS python

# uv 0.13.7, the version mise pins (mise.toml), so the image installs exactly what uv.lock says.
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

# cloudflared 2026.11.1 (released 2026-11-17). Its binary is built with CGO off, so it runs in
# the Debian image as it does in Cloudflare's own.
FROM cloudflare/cloudflared:2026.11.1@sha256:e613aadbc2d9511785d2e67a86b0c8ac18dd63a3f9af0d06faf04cbfdcb35f2d AS cloudflared

FROM python AS build
COPY --from=uv /uv /usr/local/bin/uv
# The environment goes to /app; the image's own Python, never a downloaded one; byte-code
# compiled now, because the running containers have a read-only file system.
ENV UV_PROJECT_ENVIRONMENT=/app \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /src
# The lockfile and the manifests first: a change to the code alone reuses the dependency layer.
COPY pyproject.toml uv.lock ./
COPY apps/worker/pyproject.toml apps/worker/
COPY packages/gdelt/pyproject.toml packages/gdelt/
COPY packages/glcore/pyproject.toml packages/glcore/
RUN uv sync --locked --no-dev --package globalens-worker --no-install-workspace \
        --python-preference only-system --python /usr/local/bin/python3
COPY apps/worker/src apps/worker/src
COPY packages/gdelt/src packages/gdelt/src
COPY packages/glcore/src packages/glcore/src
RUN uv sync --locked --no-dev --package globalens-worker --no-editable \
        --python-preference only-system --python /usr/local/bin/python3

FROM python AS worker
# One unprivileged user, the same number in every image of ours (10001), which owns the
# object-store folder that a fresh Compose volume copies from the image.
RUN groupadd --system --gid 10001 globalens \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent --no-create-home \
        --shell /usr/sbin/nologin globalens \
    && install -d -o 10001 -g 10001 -m 0750 /data/store
COPY --from=build /app /app
COPY --chmod=755 apps/worker/entrypoint.sh /usr/local/bin/globalens-entrypoint
ENV PATH=/app/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10001:10001
ENTRYPOINT ["globalens-entrypoint", "python", "-m", "worker"]

FROM worker AS edge
COPY --from=cloudflared /usr/local/bin/cloudflared /usr/local/bin/cloudflared
ENTRYPOINT ["globalens-entrypoint", "python", "-m", "worker.guard", "cloudflared", "--"]
CMD ["cloudflared", "tunnel", "--no-autoupdate", "run"]
