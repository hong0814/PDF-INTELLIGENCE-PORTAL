#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${LDAP_PORT:-3890}"
RUN_DIR="${LDAP_RUN_DIR:-/tmp/pdf-intelligence-portal-ldap-${PORT}}"
ROOT_DN="cn=admin,dc=pdfportal,dc=local"
ROOT_PW="admin"
BASE_DN="dc=pdfportal,dc=local"
LDAP_URL="ldap://localhost:${PORT}"

is_numeric_pid() {
    case "${1:-}" in
        ""|*[!0-9]*)
            return 1
            ;;
        *)
            return 0
            ;;
    esac
}

find_executable() {
    for candidate in "$@"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

SLAPD="$(find_executable \
    "$(command -v slapd 2>/dev/null || true)" \
    /opt/homebrew/opt/openldap/libexec/slapd \
    /usr/local/opt/openldap/libexec/slapd)"
[ -n "$SLAPD" ] || {
    echo "slapd not found. Install openldap first: brew install openldap" >&2
    exit 1
}

LDAPADD="$(find_executable \
    "$(command -v ldapadd 2>/dev/null || true)" \
    /opt/homebrew/opt/openldap/bin/ldapadd \
    /usr/local/opt/openldap/bin/ldapadd)"
[ -n "$LDAPADD" ] || {
    echo "ldapadd not found. Install openldap first: brew install openldap" >&2
    exit 1
}

SCHEMA_DIR=""
for candidate in \
    /opt/homebrew/etc/openldap/schema \
    /usr/local/etc/openldap/schema; do
    if [ -f "$candidate/core.schema" ]; then
        SCHEMA_DIR="$candidate"
        break
    fi
done
[ -n "$SCHEMA_DIR" ] || {
    echo "OpenLDAP schema directory not found. Install openldap first: brew install openldap" >&2
    exit 1
}

PID_FILE="$RUN_DIR/slapd.pid"
if [ -f "$PID_FILE" ]; then
    EXISTING_PID="$(tr -d '[:space:]' < "$PID_FILE")"
    if is_numeric_pid "$EXISTING_PID"; then
        kill "$EXISTING_PID" 2>/dev/null || true
        sleep 0.5
    else
        echo "Ignoring stale invalid PID file at $PID_FILE: ${EXISTING_PID:-<empty>}"
        rm -f "$PID_FILE"
    fi
fi

if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$PORT" -sTCP:LISTEN -nP >/dev/null 2>&1; then
    echo "Port ${PORT} is already in use. Set LDAP_PORT to another port or stop the existing listener." >&2
    exit 1
fi

rm -rf "$RUN_DIR"
mkdir -p "$RUN_DIR/data"
chmod 700 "$RUN_DIR" "$RUN_DIR/data"

cat > "$RUN_DIR/slapd.conf" <<EOF
include ${SCHEMA_DIR}/core.schema
include ${SCHEMA_DIR}/cosine.schema
include ${SCHEMA_DIR}/inetorgperson.schema

loglevel 0
pidfile  ${RUN_DIR}/slapd.pid
argsfile ${RUN_DIR}/slapd.args

database  mdb
suffix    "dc=pdfportal,dc=local"
rootdn    "${ROOT_DN}"
rootpw    ${ROOT_PW}
directory ${RUN_DIR}/data
maxsize   1073741824
EOF

ulimit -n 4096 2>/dev/null || true
"$SLAPD" -f "$RUN_DIR/slapd.conf" -h "$LDAP_URL"
sleep 2

if ! [ -f "$RUN_DIR/slapd.pid" ]; then
    echo "ERROR: slapd failed to start" >&2
    exit 1
fi

if ! "$LDAPADD" -x -H "$LDAP_URL" -D "$ROOT_DN" -w "$ROOT_PW" \
    -f "$SCRIPT_DIR/seed.ldif" 2>&1; then
    echo "ERROR: ldapadd failed" >&2
    exit 1
fi

echo ""
echo "LDAP server running on $LDAP_URL"
echo "  rootdn : $ROOT_DN"
echo "  rootpw : $ROOT_PW"
echo "  basedn : $BASE_DN"
echo ""
echo "Seeded users (uid / password):"
echo "  123456 / 1234   (title: user)"
echo "  admin  / admin  (title: admin)"
