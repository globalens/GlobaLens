#!/bin/sh
# The entrypoint of the worker and edge images (apps/worker/Dockerfile).
#
# If PGPASSWORD_FILE names a file, its content becomes PGPASSWORD, which libpq (and so psycopg)
# reads. A database password then reaches the process from a Compose secret file and never
# through the container's configuration, where `docker inspect` would show it. The role guard
# does not pass PGPASSWORD on to the service it starts.
set -eu
if [ -n "${PGPASSWORD_FILE:-}" ]; then
	PGPASSWORD=$(cat -- "$PGPASSWORD_FILE")
	export PGPASSWORD
	unset PGPASSWORD_FILE
fi
exec "$@"
