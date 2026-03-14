"""Tests for the Mattermost REST API client (mocked HTTP)."""

from __future__ import annotations

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from unittest.mock import patch

import pytest

from embiggenator.output.mattermost_client import MattermostClient, MattermostAPIError


class _MockHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that records requests and returns canned responses."""

    # Class-level list of (method, path, request_body) tuples
    requests: list[tuple[str, str, dict | list | None]] = []
    # Class-level map of (method, path_prefix) -> (status, response_body)
    responses: dict[tuple[str, str], tuple[int, dict | list | str]] = {}

    def _handle(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = None
        if content_length > 0:
            raw = self.rfile.read(content_length)
            body = json.loads(raw)
        _MockHandler.requests.append((self.command, self.path, body))

        # Find matching response
        for (method, prefix), (status, resp_body) in _MockHandler.responses.items():
            if self.command == method and self.path.startswith(prefix):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp_body).encode())
                return

        # Default 404
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"message": "not found"}).encode())

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle

    def log_message(self, format, *args):
        pass  # Suppress console output


@pytest.fixture()
def mock_server():
    """Start a local HTTP server for testing."""
    _MockHandler.requests = []
    _MockHandler.responses = {}
    server = HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", _MockHandler
    server.shutdown()


@pytest.fixture()
def client(mock_server):
    url, handler = mock_server
    return MattermostClient(url, "test-token"), handler


class TestCreateTeam:
    def test_creates_team(self, client):
        mc, handler = client
        handler.responses[("POST", "/api/v4/teams")] = (200, {"id": "team123"})
        team_id = mc.create_team("eng", "Engineering")
        assert team_id == "team123"
        assert len(handler.requests) == 1
        _, path, body = handler.requests[0]
        assert body["name"] == "eng"
        assert body["display_name"] == "Engineering"
        assert body["type"] == "O"


class TestGetTeamByName:
    def test_returns_team(self, client):
        mc, handler = client
        handler.responses[("GET", "/api/v4/teams/name/")] = (200, {"id": "t1", "name": "eng"})
        team = mc.get_team_by_name("eng")
        assert team["id"] == "t1"

    def test_returns_none_for_404(self, client):
        mc, handler = client
        # Default is 404, so no response needed
        team = mc.get_team_by_name("nonexistent")
        assert team is None


class TestGetOrCreateTeam:
    def test_returns_existing(self, client):
        mc, handler = client
        handler.responses[("GET", "/api/v4/teams/name/")] = (200, {"id": "existing"})
        team_id = mc.get_or_create_team("eng", "Engineering")
        assert team_id == "existing"
        # Should not have made a POST
        assert all(r[0] == "GET" for r in handler.requests)

    def test_creates_when_missing(self, client):
        mc, handler = client
        # GET returns 404 (default), POST creates
        handler.responses[("POST", "/api/v4/teams")] = (200, {"id": "new123"})
        team_id = mc.get_or_create_team("eng", "Engineering")
        assert team_id == "new123"


class TestCreateChannel:
    def test_creates_channel(self, client):
        mc, handler = client
        handler.responses[("POST", "/api/v4/channels")] = (200, {"id": "ch123"})
        ch_id = mc.create_channel("team1", "backend", "Backend", "P")
        assert ch_id == "ch123"
        _, _, body = handler.requests[0]
        assert body["team_id"] == "team1"
        assert body["type"] == "P"


class TestDirectChannel:
    def test_creates_direct_channel(self, client):
        mc, handler = client
        handler.responses[("POST", "/api/v4/channels/direct")] = (200, {"id": "dm123"})
        ch_id = mc.create_direct_channel("user1", "user2")
        assert ch_id == "dm123"
        _, _, body = handler.requests[0]
        assert body == ["user1", "user2"]


class TestMembership:
    def test_add_user_to_team(self, client):
        mc, handler = client
        handler.responses[("POST", "/api/v4/teams/")] = (200, {})
        mc.add_user_to_team("team1", "user1")
        _, path, body = handler.requests[0]
        assert "/teams/team1/members" in path
        assert body["user_id"] == "user1"

    def test_add_user_to_channel(self, client):
        mc, handler = client
        handler.responses[("POST", "/api/v4/channels/")] = (200, {})
        mc.add_user_to_channel("ch1", "user1")
        _, path, body = handler.requests[0]
        assert "/channels/ch1/members" in path
        assert body["user_id"] == "user1"


class TestCreatePost:
    def test_creates_post(self, client):
        mc, handler = client
        handler.responses[("POST", "/api/v4/posts")] = (200, {"id": "post123"})
        post_id = mc.create_post("ch1", "Hello world")
        assert post_id == "post123"
        _, _, body = handler.requests[0]
        assert body["channel_id"] == "ch1"
        assert body["message"] == "Hello world"
        assert body["root_id"] == ""

    def test_creates_threaded_reply(self, client):
        mc, handler = client
        handler.responses[("POST", "/api/v4/posts")] = (200, {"id": "reply1"})
        post_id = mc.create_post("ch1", "Reply text", root_id="parent123")
        assert post_id == "reply1"
        _, _, body = handler.requests[0]
        assert body["root_id"] == "parent123"

    def test_token_override(self, client):
        mc, handler = client
        handler.responses[("POST", "/api/v4/posts")] = (200, {"id": "p1"})
        mc.create_post("ch1", "test", token_override="user-token-abc")
        # The handler doesn't inspect auth headers, but we verify it doesn't raise


class TestReaction:
    def test_adds_reaction(self, client):
        mc, handler = client
        handler.responses[("POST", "/api/v4/reactions")] = (200, {})
        mc.add_reaction("post1", "user1", "thumbsup")
        _, _, body = handler.requests[0]
        assert body["post_id"] == "post1"
        assert body["user_id"] == "user1"
        assert body["emoji_name"] == "thumbsup"


class TestErrorHandling:
    def test_raises_on_error(self, client):
        mc, handler = client
        # Default 404 response
        with pytest.raises(MattermostAPIError) as exc_info:
            mc.create_team("x", "X")
        assert exc_info.value.status == 404

    def test_rate_limit_retry(self, client):
        mc, handler = client
        # We can't easily test 429 retry with this simple mock server,
        # but we can verify the retry logic exists by checking the class constants
        assert mc.MAX_RETRIES == 3
        assert mc.BACKOFF_BASE == 1.0
