#!/usr/bin/env bash
# Local Postgres 16 cluster for development, no Docker required.
# Usage: scripts/dev_db.sh start|stop|status
set -euo pipefail

PG_BIN="${PG_BIN:-/usr/lib/postgresql/16/bin}"
PGDATA_DIR="${PGDATA_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/pgdata}"
SOCKET_DIR="$PGDATA_DIR/sockets"

start() {
  mkdir -p "$SOCKET_DIR"
  if [ ! -f "$PGDATA_DIR/PG_VERSION" ]; then
    echo "Initializing Postgres cluster at $PGDATA_DIR ..."
    "$PG_BIN/initdb" -D "$PGDATA_DIR" -U postgres --auth=trust --no-locale --encoding=UTF8 >/dev/null
  fi
  "$PG_BIN/pg_ctl" -D "$PGDATA_DIR" -l "$PGDATA_DIR/postgres.log" \
    -o "-k $SOCKET_DIR -c listen_addresses='127.0.0.1' -p 5432" start
  export PGHOST="$SOCKET_DIR"
  "$PG_BIN/createdb" -h "$SOCKET_DIR" -U postgres ham_dev 2>/dev/null || true
  "$PG_BIN/createdb" -h "$SOCKET_DIR" -U postgres ham_test 2>/dev/null || true
  "$PG_BIN/psql" -h "$SOCKET_DIR" -U postgres -c \
    "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ham') THEN \
     CREATE ROLE ham LOGIN PASSWORD 'ham' SUPERUSER; END IF; END \$\$;" >/dev/null
  echo "Postgres is up. DATABASE_URL=postgresql://ham:ham@127.0.0.1:5432/ham_dev"
}

stop() {
  "$PG_BIN/pg_ctl" -D "$PGDATA_DIR" stop -m fast || true
}

status() {
  "$PG_BIN/pg_ctl" -D "$PGDATA_DIR" status
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) echo "Usage: $0 {start|stop|status}"; exit 1 ;;
esac
