"""Tests for the Mattermost cleanup logic in the reset CLI command."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import click
import pytest
from click.testing import CliRunner

from embiggenator.cli import cli
from embiggenator.output.mattermost_client import MattermostAPIError


def _invoke_reset(runner: CliRunner, *, mm_url: str = "http://mm:8065", pat: str = "tok", extra: list[str] | None = None):
    """Invoke the reset command with Mattermost options, auto-confirming."""
    args = ["reset", "--yes", "--mattermost-url", mm_url, "--pat", pat]
    if extra:
        args.extend(extra)
    return runner.invoke(cli, args, catch_exceptions=False)


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def mock_ldap():
    with patch("embiggenator.output.ldap_writer.reset_ldap") as m:
        yield m


@pytest.fixture()
def mock_client():
    """Patch MattermostClient so reset_cmd gets a controllable mock instance."""
    with patch("embiggenator.output.mattermost_client.MattermostClient") as cls:
        client = MagicMock()
        cls.return_value = client
        # Defaults: valid PAT, deletion enabled, no users/teams
        client.get_me.return_value = {"id": "admin1", "username": "admin", "roles": "system_admin"}
        client.get_config.return_value = {
            "ServiceSettings": {
                "EnableAPIUserDeletion": True,
                "EnableAPITeamDeletion": True,
            },
        }
        client.get_all_users.return_value = []
        client.get_all_teams.return_value = []
        client.get_or_create_team.return_value = "new-team-id"
        yield client


class TestResetMattermostPATValidation:
    def test_missing_pat_errors(self, runner, mock_ldap):
        result = runner.invoke(cli, ["reset", "--yes", "--mattermost-url", "http://mm:8065"])
        assert result.exit_code != 0
        assert "--pat is required" in result.output

    def test_invalid_pat_errors(self, runner, mock_ldap, mock_client):
        mock_client.get_me.side_effect = MattermostAPIError(401, "Unauthorized", "/users/me")
        result = runner.invoke(cli, ["reset", "--yes", "--mattermost-url", "http://mm:8065", "--pat", "bad"])
        assert result.exit_code != 0
        assert "Invalid or expired PAT" in result.output


class TestResetMattermostPreflight:
    def test_deletion_not_enabled_errors(self, runner, mock_ldap, mock_client):
        mock_client.get_config.return_value = {
            "ServiceSettings": {"EnableAPIUserDeletion": False, "EnableAPITeamDeletion": False},
        }
        result = runner.invoke(cli, ["reset", "--yes", "--mattermost-url", "http://mm:8065", "--pat", "tok"])
        assert result.exit_code != 0
        assert "EnableAPIUserDeletion" in result.output
        assert "EnableAPITeamDeletion" in result.output

    def test_config_403_warns_and_continues(self, runner, mock_ldap, mock_client):
        mock_client.get_config.side_effect = MattermostAPIError(403, "forbidden", "/config")
        result = _invoke_reset(runner)
        assert result.exit_code == 0
        assert "Warning: cannot read server config" in result.output


class TestResetMattermostUserDeletion:
    def test_deletes_normal_users(self, runner, mock_ldap, mock_client):
        mock_client.get_all_users.return_value = [
            {"id": "u1", "username": "alice", "roles": "system_user"},
            {"id": "u2", "username": "bob", "roles": "system_user"},
        ]
        result = _invoke_reset(runner)
        assert result.exit_code == 0
        assert mock_client.delete_user.call_count == 2
        mock_client.delete_user.assert_any_call("u1", permanent=True)
        mock_client.delete_user.assert_any_call("u2", permanent=True)
        assert "2 users deleted" in result.output

    def test_skips_bots_and_admins(self, runner, mock_ldap, mock_client):
        mock_client.get_all_users.return_value = [
            {"id": "u1", "username": "admin", "roles": "system_admin system_user"},
            {"id": "u2", "username": "bot", "roles": "system_user", "is_bot": True},
            {"id": "u3", "username": "alice", "roles": "system_user"},
        ]
        result = _invoke_reset(runner)
        assert result.exit_code == 0
        mock_client.delete_user.assert_called_once_with("u3", permanent=True)
        assert "1 users deleted, 2 skipped (bots/admins)" in result.output

    def test_suppresses_errors_after_three(self, runner, mock_ldap, mock_client):
        users = [{"id": f"u{i}", "username": f"user{i}", "roles": "system_user"} for i in range(6)]
        mock_client.get_all_users.return_value = users
        mock_client.delete_user.side_effect = MattermostAPIError(500, "fail", "/users")
        result = _invoke_reset(runner)
        assert result.exit_code == 0
        # First 3 errors shown, 4th prints suppression message
        assert result.output.count("Warning: failed to delete user") == 3
        assert "suppressing further deletion errors" in result.output
        assert "0 users deleted" in result.output
        assert "6 errors" in result.output


class TestResetMattermostTeamDeletion:
    def test_deletes_all_teams(self, runner, mock_ldap, mock_client):
        mock_client.get_all_teams.return_value = [
            {"id": "t1", "display_name": "Team A"},
            {"id": "t2", "display_name": "Team B"},
        ]
        result = _invoke_reset(runner)
        assert result.exit_code == 0
        assert mock_client.delete_team.call_count == 2
        mock_client.delete_team.assert_any_call("t1", permanent=True)
        mock_client.delete_team.assert_any_call("t2", permanent=True)
        assert "2 teams deleted" in result.output

    def test_team_deletion_errors_suppressed(self, runner, mock_ldap, mock_client):
        teams = [{"id": f"t{i}", "display_name": f"Team {i}"} for i in range(5)]
        mock_client.get_all_teams.return_value = teams
        mock_client.delete_team.side_effect = MattermostAPIError(500, "fail", "/teams")
        result = _invoke_reset(runner)
        assert result.exit_code == 0
        assert result.output.count("Warning: failed to delete team") == 3
        assert "suppressing further team deletion errors" in result.output


class TestResetMattermostDefaultTeam:
    def test_creates_default_team_and_adds_admin(self, runner, mock_ldap, mock_client):
        result = _invoke_reset(runner)
        assert result.exit_code == 0
        mock_client.get_or_create_team.assert_called_once_with("default", "Default")
        mock_client.add_user_to_team.assert_called_once_with("new-team-id", "admin1")
        assert "Created default team 'Default'" in result.output

    def test_default_team_failure_does_not_abort(self, runner, mock_ldap, mock_client):
        mock_client.get_or_create_team.side_effect = MattermostAPIError(500, "fail", "/teams")
        result = _invoke_reset(runner)
        assert result.exit_code == 0
        assert "Warning: failed to create default team" in result.output


class TestResetWithoutMattermost:
    def test_ldap_only_reset(self, runner, mock_ldap):
        """reset without --mattermost-url should only do LDAP and succeed."""
        result = runner.invoke(cli, ["reset", "--yes"])
        assert result.exit_code == 0
        mock_ldap.assert_called_once()
