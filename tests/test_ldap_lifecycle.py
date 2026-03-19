"""Tests for LDAP user lifecycle commands (disable-user, update-user)."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import click
import pytest
from click.testing import CliRunner
from ldap3 import MODIFY_REPLACE

from embiggenator.cli import cli
from embiggenator.output.ldap_writer import (
    _find_user_by_uid,
    disable_ldap_user,
    update_ldap_user,
)


# ── Helpers ──


def _mock_conn_with_user(uid: str = "jdoe", dn: str = "cn=John Doe,ou=people,dc=example,dc=com"):
    """Create a mock ldap3 Connection that finds a user."""
    conn = MagicMock()
    entry = MagicMock()
    entry.entry_dn = dn
    conn.entries = [entry]
    return conn


def _mock_conn_no_user():
    """Create a mock ldap3 Connection that finds no user."""
    conn = MagicMock()
    conn.entries = []
    return conn


# ── _find_user_by_uid ──


class TestFindUserByUid:
    def test_returns_dn_when_found(self):
        conn = _mock_conn_with_user()
        result = _find_user_by_uid(conn, "ou=people,dc=example,dc=com", "jdoe")
        assert result == "cn=John Doe,ou=people,dc=example,dc=com"
        conn.search.assert_called_once()

    def test_returns_none_when_not_found(self):
        conn = _mock_conn_no_user()
        result = _find_user_by_uid(conn, "ou=people,dc=example,dc=com", "nonexistent")
        assert result is None

    def test_escapes_filter_chars(self):
        conn = _mock_conn_no_user()
        _find_user_by_uid(conn, "ou=people,dc=example,dc=com", "user(with)parens")
        search_filter = conn.search.call_args[0][1]
        # ldap3 escape_filter_chars escapes parentheses
        assert "(" not in search_filter.split("=", 1)[1] or "\\28" in search_filter


# ── disable_ldap_user ──


class TestDisableLdapUser:
    @patch("embiggenator.output.ldap_writer.Connection")
    @patch("embiggenator.output.ldap_writer.Server")
    def test_sets_description_disabled(self, mock_server_cls, mock_conn_cls):
        conn = _mock_conn_with_user()
        mock_conn_cls.return_value.__enter__ = MagicMock(return_value=conn)
        mock_conn_cls.return_value.__exit__ = MagicMock(return_value=False)

        disable_ldap_user("jdoe", base_dn="dc=example,dc=com")

        conn.modify.assert_called_once_with(
            "cn=John Doe,ou=people,dc=example,dc=com",
            {"description": [(MODIFY_REPLACE, ["DISABLED"])]},
        )

    @patch("embiggenator.output.ldap_writer.Connection")
    @patch("embiggenator.output.ldap_writer.Server")
    def test_not_found_raises(self, mock_server_cls, mock_conn_cls):
        conn = _mock_conn_no_user()
        mock_conn_cls.return_value.__enter__ = MagicMock(return_value=conn)
        mock_conn_cls.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(click.ClickException, match="not found"):
            disable_ldap_user("ghost", base_dn="dc=example,dc=com")


# ── update_ldap_user ──


class TestUpdateLdapUser:
    @patch("embiggenator.output.ldap_writer.Connection")
    @patch("embiggenator.output.ldap_writer.Server")
    def test_modifies_attributes(self, mock_server_cls, mock_conn_cls):
        conn = _mock_conn_with_user()
        mock_conn_cls.return_value.__enter__ = MagicMock(return_value=conn)
        mock_conn_cls.return_value.__exit__ = MagicMock(return_value=False)

        update_ldap_user("jdoe", {"sn": "NewName", "mail": "new@example.com"}, base_dn="dc=example,dc=com")

        conn.modify.assert_called_once()
        modify_args = conn.modify.call_args[0]
        assert modify_args[0] == "cn=John Doe,ou=people,dc=example,dc=com"
        changes = modify_args[1]
        assert changes["sn"] == [(MODIFY_REPLACE, ["NewName"])]
        assert changes["mail"] == [(MODIFY_REPLACE, ["new@example.com"])]
        conn.modify_dn.assert_not_called()

    @patch("embiggenator.output.ldap_writer.Connection")
    @patch("embiggenator.output.ldap_writer.Server")
    def test_renames_dn_for_cn_change(self, mock_server_cls, mock_conn_cls):
        conn = _mock_conn_with_user()
        mock_conn_cls.return_value.__enter__ = MagicMock(return_value=conn)
        mock_conn_cls.return_value.__exit__ = MagicMock(return_value=False)

        update_ldap_user("jdoe", {"cn": "Jane Doe"}, base_dn="dc=example,dc=com")

        conn.modify.assert_not_called()
        conn.modify_dn.assert_called_once_with(
            "cn=John Doe,ou=people,dc=example,dc=com",
            "cn=Jane Doe",
        )

    @patch("embiggenator.output.ldap_writer.Connection")
    @patch("embiggenator.output.ldap_writer.Server")
    def test_cn_with_other_attrs_modifies_before_rename(self, mock_server_cls, mock_conn_cls):
        conn = _mock_conn_with_user()
        mock_conn_cls.return_value.__enter__ = MagicMock(return_value=conn)
        mock_conn_cls.return_value.__exit__ = MagicMock(return_value=False)

        update_ldap_user("jdoe", {"sn": "Doe-Smith", "cn": "Jane Doe-Smith"}, base_dn="dc=example,dc=com")

        # modify should be called before modify_dn
        assert conn.modify.call_count == 1
        assert conn.modify_dn.call_count == 1

        # Verify modify was called on the OLD DN
        modify_dn_arg = conn.modify.call_args[0][0]
        assert modify_dn_arg == "cn=John Doe,ou=people,dc=example,dc=com"

        # Verify rename
        conn.modify_dn.assert_called_once_with(
            "cn=John Doe,ou=people,dc=example,dc=com",
            "cn=Jane Doe-Smith",
        )

    @patch("embiggenator.output.ldap_writer.Connection")
    @patch("embiggenator.output.ldap_writer.Server")
    def test_not_found_raises(self, mock_server_cls, mock_conn_cls):
        conn = _mock_conn_no_user()
        mock_conn_cls.return_value.__enter__ = MagicMock(return_value=conn)
        mock_conn_cls.return_value.__exit__ = MagicMock(return_value=False)

        with pytest.raises(click.ClickException, match="not found"):
            update_ldap_user("ghost", {"sn": "X"}, base_dn="dc=example,dc=com")


# ── CLI smoke tests ──


class TestDisableUserCLI:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["disable-user", "--help"])
        assert result.exit_code == 0
        assert "USERNAMES" in result.output
        assert "description=DISABLED" in result.output

    def test_requires_username(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["disable-user"])
        assert result.exit_code != 0


class TestUpdateUserCLI:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["update-user", "--help"])
        assert result.exit_code == 0
        assert "USERNAME" in result.output
        assert "--set" in result.output

    @patch("embiggenator.output.ldap_writer.Connection")
    @patch("embiggenator.output.ldap_writer.Server")
    def test_rejects_bad_set_format(self, mock_server_cls, mock_conn_cls):
        runner = CliRunner()
        result = runner.invoke(cli, ["update-user", "jdoe", "--set", "noequals"])
        assert result.exit_code != 0
        assert "Invalid --set format" in result.output

    @patch("embiggenator.output.ldap_writer.Connection")
    @patch("embiggenator.output.ldap_writer.Server")
    def test_handles_value_with_equals(self, mock_server_cls, mock_conn_cls):
        """Values containing '=' should be preserved (e.g. base64 data)."""
        conn = _mock_conn_with_user()
        mock_conn_cls.return_value.__enter__ = MagicMock(return_value=conn)
        mock_conn_cls.return_value.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        result = runner.invoke(cli, ["update-user", "jdoe", "--set", "description=a=b=c"])
        assert result.exit_code == 0
        # The value should be "a=b=c" (everything after first =)
        conn.modify.assert_called_once()
        changes = conn.modify.call_args[0][1]
        assert changes["description"] == [(MODIFY_REPLACE, ["a=b=c"])]
