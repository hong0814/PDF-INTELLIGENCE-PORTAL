"""Entry points for the local OpenLDAP development server."""

from __future__ import annotations

import subprocess
from pathlib import Path

DEFAULT_LDAP_PORT = 3890
RUN_DIR_PREFIX = Path("/tmp/pdf-intelligence-portal-ldap")
RUN_DIR = Path(f"{RUN_DIR_PREFIX}-{DEFAULT_LDAP_PORT}")
ROOT_DN = "CN=admin,DC=hc,DC=com"
ROOT_PASSWORD = "secret"
BASE_DN = "OU=YourCompany,DC=hc,DC=com"
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "ldap"
START_SCRIPT = SCRIPTS_DIR / "start.sh"
STOP_SCRIPT = SCRIPTS_DIR / "stop.sh"


def start() -> None:
    """Start the local OpenLDAP development server."""
    subprocess.run(["bash", str(START_SCRIPT)], check=True)


def stop() -> None:
    """Stop the local OpenLDAP development server."""
    subprocess.run(["bash", str(STOP_SCRIPT)], check=True)
