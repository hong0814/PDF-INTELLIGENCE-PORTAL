#!/usr/bin/env bash
set -euo pipefail

PORT="${LDAP_PORT:-3890}"
RUN_DIR="${LDAP_RUN_DIR:-/tmp/pdf-intelligence-portal-ldap-${PORT}}"
PID_FILE="$RUN_DIR/slapd.pid"

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

if [ -f "$PID_FILE" ]; then
    PID="$(tr -d '[:space:]' < "$PID_FILE")"
    if is_numeric_pid "$PID"; then
        kill "$PID" 2>/dev/null && echo "LDAP server stopped." || echo "Process already gone for PID $PID."
    else
        echo "Ignoring stale invalid PID file at $PID_FILE: ${PID:-<empty>}"
    fi
    rm -f "$PID_FILE"
else
    echo "LDAP server is not running (no PID file found at $PID_FILE)."
fi
