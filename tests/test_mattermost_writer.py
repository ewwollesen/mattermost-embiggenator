"""Tests for create_local_users (local Mattermost account creation)."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from embiggenator.models import GeneratedUser
from embiggenator.output.mattermost_client import MattermostAPIError, MattermostClient
from embiggenator.output.mattermost_writer import create_local_users


def _make_user(uid: str) -> GeneratedUser:
    """Create a minimal GeneratedUser for testing."""
    return GeneratedUser(
        uid=uid,
        cn=f"Test {uid}",
        sn="Test",
        given_name=uid.capitalize(),
        display_name=f"Test {uid}",
        mail=f"{uid}@example.com",
        password_hash="hash",
        base_dn="dc=example,dc=com",
        people_ou="people",
        employee_number="1000",
    )


@pytest.fixture()
def mock_client():
    client = MagicMock(spec=MattermostClient)
    # Default: create_user returns a user dict, login_user returns (dict, token)
    client.create_user.side_effect = lambda username, email, password, **kw: {
        "id": f"mm_{username}",
        "username": username,
    }
    client.login_user.side_effect = lambda login_id, password: (
        {"id": f"mm_{login_id}", "username": login_id},
        f"token_{login_id}",
    )
    return client


class TestCreateLocalUsers:
    def test_creates_and_logs_in_all(self, mock_client):
        users = [_make_user(f"user{i}") for i in range(5)]
        user_map = create_local_users(users, mock_client, "password")
        assert len(user_map) == 5
        assert user_map["user0"] == ("mm_user0", "token_user0")
        assert user_map["user4"] == ("mm_user4", "token_user4")
        assert mock_client.create_user.call_count == 5
        assert mock_client.login_user.call_count == 5

    def test_handles_existing_users(self, mock_client):
        """Users that already exist (409) should be looked up and logged in."""
        mock_client.create_user.side_effect = MattermostAPIError(
            409, "already exists", "http://localhost/api/v4/users"
        )
        mock_client.get_user_by_username.return_value = {
            "id": "existing_id", "username": "alice",
        }
        mock_client.login_user.return_value = (
            {"id": "existing_id", "username": "alice"},
            "token_alice",
        )

        users = [_make_user("alice")]
        user_map = create_local_users(users, mock_client, "password")
        assert len(user_map) == 1
        assert user_map["alice"] == ("existing_id", "token_alice")
        mock_client.get_user_by_username.assert_called_once_with("alice")

    def test_aborts_after_consecutive_failures(self, mock_client):
        """If first 5 all fail, should abort early."""
        mock_client.create_user.side_effect = MattermostAPIError(
            500, "server error", "http://localhost/api/v4/users"
        )

        users = [_make_user(f"user{i}") for i in range(20)]
        user_map = create_local_users(users, mock_client, "password")
        assert len(user_map) == 0
        # Should stop after max_consecutive_failures (5)
        assert mock_client.create_user.call_count == 5

    def test_no_abort_when_some_succeed(self, mock_client):
        """If some succeed, don't abort on later failures."""
        succeed_count = {"n": 0}
        original_side_effect = mock_client.create_user.side_effect

        def _mixed_side_effect(username, email, password, **kw):
            succeed_count["n"] += 1
            if succeed_count["n"] > 3:
                raise MattermostAPIError(500, "error", "http://localhost/api/v4/users")
            return {"id": f"mm_{username}", "username": username}

        mock_client.create_user.side_effect = _mixed_side_effect

        users = [_make_user(f"user{i}") for i in range(10)]
        user_map = create_local_users(users, mock_client, "password")
        assert len(user_map) == 3
        # Should try all 10 since some succeeded
        assert mock_client.create_user.call_count == 10

    def test_empty_user_list(self, mock_client):
        user_map = create_local_users([], mock_client, "password")
        assert user_map == {}
        assert mock_client.create_user.call_count == 0

    def test_login_failure_still_counts_as_created(self, mock_client):
        """If login fails after creation, user is created but not in user_map."""
        mock_client.login_user.side_effect = MattermostAPIError(
            401, "invalid", "http://localhost/api/v4/users/login"
        )
        users = [_make_user("alice")]
        user_map = create_local_users(users, mock_client, "password")
        # User was created but login failed, so no session token
        assert len(user_map) == 0
        assert mock_client.create_user.call_count == 1

    def test_passes_user_details(self, mock_client):
        """Verify first_name and last_name are passed to create_user."""
        users = [_make_user("alice")]
        users[0].given_name = "Alice"
        users[0].sn = "Smith"
        create_local_users(users, mock_client, "password")
        mock_client.create_user.assert_called_once_with(
            username="alice",
            email="alice@example.com",
            password="password",
            first_name="Alice",
            last_name="Smith",
        )
