#!/bin/sh
# Runs inside the Postgres container on first initialisation only
# (docker-entrypoint-initdb.d is executed when the data directory is empty).
# POSTGRES_DB is already created by the entrypoint; this script ensures
# the "stryng" database exists in case POSTGRES_DB was overridden or the
# volume was partially initialised.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE stryng'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'stryng')\gexec
EOSQL
