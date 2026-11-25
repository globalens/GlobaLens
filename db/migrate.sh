#!/bin/sh
# The migration step: the migrate image's entrypoint (db/Dockerfile), run once per start.
#
# 1. db/roles.sql as the cluster's superuser. It is safe to run again (db/README.md, Roles).
# 2. Each role's password, from the node's secret files (docs/secrets.md).
# 3. dbmate up as `migrator`, the only role that runs DDL.
#
# Compose runs it before the services that need the schema (deploy/compose/node-paid); the
# pull deployer (task 16) runs the same image before it rolls out a release. Settings:
#
#   PGHOST, PGDATABASE      the server and the application database
#   /run/secrets/<role>_password   one file per role: postgres, migrator, worker, readonly
#
# No password is printed, passed on a command line or left in the server's log.
set -eu

: "${PGHOST:?PGHOST is not set}"
: "${PGDATABASE:?PGDATABASE is not set}"
SHARE=/usr/share/globalens/db

# A password is read from its secret file. The node's first boot writes them in this alphabet
# (base64url), which needs no quoting in SQL or in a URL; anything else is refused, not quoted.
secret() {
	value=$(cat "/run/secrets/$1_password") || exit 1
	case "$value" in
	"" | *[!A-Za-z0-9_-]*)
		echo "migrate: the $1 password is empty or has characters outside A-Z a-z 0-9 _ -" >&2
		exit 1
		;;
	esac
	printf '%s' "$value"
}

# Every password is read before anything is done, so a missing one stops the step at the start.
pw_postgres=$(secret postgres)
pw_migrator=$(secret migrator)
pw_worker=$(secret worker)
pw_readonly=$(secret readonly)
PGPASSWORD=$pw_postgres
export PGPASSWORD
psql="psql -X -q -v ON_ERROR_STOP=1 -U postgres -d $PGDATABASE"

echo "migrate: waiting for $PGHOST"
tries=0
until pg_isready -q -h "$PGHOST" -U postgres -d "$PGDATABASE"; do
	tries=$((tries + 1))
	if [ "$tries" -ge 60 ]; then
		echo "migrate: $PGHOST did not answer in 60 s" >&2
		exit 1
	fi
	sleep 1
done

echo "migrate: roles"
$psql -f "$SHARE/roles.sql"

# The passwords travel on stdin, and the session stops logging statement text first, so that
# a failing ALTER ROLE cannot write a password into the server's log.
echo "migrate: passwords"
{
	echo "set log_statement = 'none';"
	echo "set log_min_error_statement = 'panic';"
	echo "set log_min_duration_statement = -1;"
	echo "alter role migrator password '$pw_migrator';"
	echo "alter role worker password '$pw_worker';"
	echo "alter role readonly password '$pw_readonly';"
} | $psql
unset PGPASSWORD pw_postgres pw_worker pw_readonly

echo "migrate: dbmate up"
DATABASE_URL="postgres://migrator:$pw_migrator@$PGHOST:5432/$PGDATABASE?sslmode=disable"
export DATABASE_URL
exec dbmate --migrations-dir "$SHARE/migrations" --no-dump-schema --migration-lock up
