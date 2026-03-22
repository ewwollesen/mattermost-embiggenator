"""Tests for login_mattermost_users including early abort on consecutive failures."""

from __future__ import annotations

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

import pytest

from embiggenator.models import GeneratedUser
from embiggenator.output.ldap_writer import login_mattermost_users


def _make_user(uid: str) -> GeneratedUser:
    """Create a minimal GeneratedUser for login testing."""
    return GeneratedUser(
        uid=uid,
        cn=f"Test {uid}",
        sn="Test",
        given_name=uid,
        display_name=f"Test {uid}",
        mail=f"{uid}@example.com",
        password_hash="hash",
        base_dn="dc=example,dc=com",
        people_ou="people",
        employee_number="1000",
    )


class _LoginHandler(BaseHTTPRequestHandler):
    """HTTP handler that simulates Mattermost login responses."""

    # Class-level state, reset per test
    call_count: int = 0
    fail_count: int = 0  # how many to fail before succeeding (0 = all succeed)
    fail_all: bool = False

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}
        _LoginHandler.call_count += 1

        if _LoginHandler.fail_all or _LoginHandler.call_count <= _LoginHandler.fail_count:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "id": "api.user.login.invalid_credentials_email_username",
                "message": "invalid credentials",
                "status_code": 401,
            }).encode())
            return

        # Success
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Token", f"token_{body.get('login_id', 'unknown')}")
        self.end_headers()
        self.wfile.write(json.dumps({
            "id": f"mm_{body.get('login_id', 'unknown')}",
            "username": body.get("login_id", "unknown"),
        }).encode())

    def log_message(self, format, *args):
        pass


@pytest.fixture()
def login_server():
    """Start a local HTTP server simulating Mattermost login."""
    _LoginHandler.call_count = 0
    _LoginHandler.fail_count = 0
    _LoginHandler.fail_all = False
    server = HTTPServer(("127.0.0.1", 0), _LoginHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


class TestLoginMattermostUsers:
    def test_all_succeed(self, login_server):
        users = [_make_user(f"user{i}") for i in range(5)]
        user_map = login_mattermost_users(users, login_server, "password")
        assert len(user_map) == 5
        assert "user0" in user_map
        assert user_map["user0"][0] == "mm_user0"

    def test_aborts_after_consecutive_failures(self, login_server):
        """If first 5 all fail, should abort early instead of trying all users."""
        _LoginHandler.fail_all = True
        users = [_make_user(f"user{i}") for i in range(50)]
        user_map = login_mattermost_users(users, login_server, "password")
        assert len(user_map) == 0
        # Should have stopped after 5 (max_consecutive_failures), not tried all 50
        assert _LoginHandler.call_count == 5

    def test_no_abort_when_some_succeed(self, login_server):
        """If some logins succeed, don't abort even if there are failures."""
        # First 3 fail, then rest succeed
        _LoginHandler.fail_count = 3
        users = [_make_user(f"user{i}") for i in range(10)]
        user_map = login_mattermost_users(users, login_server, "password")
        # 10 total - 3 failed = 7 succeeded
        assert len(user_map) == 7
        assert _LoginHandler.call_count == 10  # tried all of them

    def test_unreachable_server_aborts_immediately(self):
        """URLError (can't connect) should abort after first failure."""
        users = [_make_user(f"user{i}") for i in range(10)]
        user_map = login_mattermost_users(users, "http://127.0.0.1:1", "password")
        assert len(user_map) == 0

    def test_empty_user_list(self, login_server):
        user_map = login_mattermost_users([], login_server, "password")
        assert user_map == {}
        assert _LoginHandler.call_count == 0

    def test_returns_tokens(self, login_server):
        """Verify the user_map contains (mm_user_id, token) tuples."""
        users = [_make_user("alice")]
        user_map = login_mattermost_users(users, login_server, "password")
        assert "alice" in user_map
        mm_id, token = user_map["alice"]
        assert mm_id == "mm_alice"
        assert token == "token_alice"
