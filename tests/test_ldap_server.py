"""Tests for the local LDAP server wrapper."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from pdftablesearch import ldap_server


class TestLdapServerConstants:
    """Verify the local LDAP server defaults and script locations."""

    def test_defaults_match_documented_local_server(self) -> None:
        assert ldap_server.DEFAULT_LDAP_PORT == 3890
        assert ldap_server.RUN_DIR_PREFIX == Path("/tmp/pdf-intelligence-portal-ldap")
        assert ldap_server.RUN_DIR == Path("/tmp/pdf-intelligence-portal-ldap-3890")
        assert ldap_server.ROOT_DN == "CN=admin,DC=hc,DC=com"
        assert ldap_server.ROOT_PASSWORD == "secret"
        assert ldap_server.BASE_DN == "OU=YourCompany,DC=hc,DC=com"

    def test_script_paths_are_repo_local(self) -> None:
        assert ldap_server.SCRIPTS_DIR == Path(__file__).resolve().parents[1] / "scripts" / "ldap"
        assert ldap_server.START_SCRIPT == ldap_server.SCRIPTS_DIR / "start.sh"
        assert ldap_server.STOP_SCRIPT == ldap_server.SCRIPTS_DIR / "stop.sh"
        assert ldap_server.START_SCRIPT.exists()
        assert ldap_server.STOP_SCRIPT.exists()

    def test_shell_scripts_have_valid_bash_syntax(self) -> None:
        for script_path in (ldap_server.START_SCRIPT, ldap_server.STOP_SCRIPT):
            subprocess.run(["bash", "-n", str(script_path)], check=True)

    def test_seeded_user_entries_expose_required_ldap_attributes(self) -> None:
        seed_ldif = (ldap_server.SCRIPTS_DIR / "seed.ldif").read_text(encoding="utf-8")
        required_fields = ("uid:", "cn:", "mail:", "departmentNumber:", "title:")
        user_entries = [
            entry
            for entry in seed_ldif.strip().split("\n\n")
            if "objectClass: inetOrgPerson" in entry
        ]

        assert len(user_entries) >= 2
        for entry in user_entries:
            for field in required_fields:
                assert field in entry


class TestLdapServerLifecycle:
    """Verify the wrapper dispatches to the shell scripts."""

    def test_start_runs_start_script(self) -> None:
        with patch.object(ldap_server.subprocess, "run") as mock_run:
            ldap_server.start()

        mock_run.assert_called_once_with(["bash", str(ldap_server.START_SCRIPT)], check=True)

    def test_stop_runs_stop_script(self) -> None:
        with patch.object(ldap_server.subprocess, "run") as mock_run:
            ldap_server.stop()

        mock_run.assert_called_once_with(["bash", str(ldap_server.STOP_SCRIPT)], check=True)
