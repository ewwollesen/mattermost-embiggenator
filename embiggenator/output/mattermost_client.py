"""Mattermost REST API client — urllib-based, no extra dependencies."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


class MattermostAPIError(Exception):
    """Raised when the Mattermost API returns an error."""

    def __init__(self, status: int, message: str, url: str) -> None:
        self.status = status
        self.url = url
        super().__init__(f"HTTP {status} from {url}: {message}")


class MattermostClient:
    """Minimal Mattermost REST API client using urllib.

    Auth is via a Personal Access Token (PAT) passed as a Bearer token.
    Includes simple retry with exponential backoff on HTTP 429 (rate limit).
    """

    MAX_RETRIES = 3
    BACKOFF_BASE = 1.0  # seconds
    MAX_RETRY_WAIT = 30.0  # cap Retry-After to avoid unbounded sleep

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _request(
        self,
        method: str,
        path: str,
        body: dict | list | None = None,
        token_override: str | None = None,
    ) -> Any:
        """Make an API request with retry on 429."""
        url = f"{self.base_url}/api/v4{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        token = token_override or self.token

        for attempt in range(self.MAX_RETRIES + 1):
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method=method,
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    resp_body = resp.read().decode("utf-8")
                    if resp_body:
                        return json.loads(resp_body)
                    return None
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < self.MAX_RETRIES:
                    retry_after = float(e.headers.get("Retry-After", self.BACKOFF_BASE * (2 ** attempt)))
                    retry_after = min(retry_after, self.MAX_RETRY_WAIT)
                    time.sleep(retry_after)
                    continue
                body_text = e.read().decode("utf-8", errors="replace")
                raise MattermostAPIError(e.code, body_text, url) from e
        # Should not reach here, but just in case
        raise MattermostAPIError(429, "Rate limit exceeded after retries", url)

    # ── Teams ──

    def create_team(self, name: str, display_name: str, team_type: str = "O") -> str:
        """Create a team. Returns team_id. type: 'O' (open) or 'I' (invite-only)."""
        result = self._request("POST", "/teams", {
            "name": name,
            "display_name": display_name,
            "type": team_type,
        })
        return result["id"]

    def get_all_teams(self, per_page: int = 200) -> list[dict]:
        """Fetch all teams via paginated API calls. Returns list of team dicts."""
        all_teams: list[dict] = []
        page = 0
        while True:
            batch = self._request("GET", f"/teams?page={page}&per_page={per_page}")
            if not batch:
                break
            all_teams.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return all_teams

    def delete_team(self, team_id: str, permanent: bool = True) -> None:
        """Delete a team. Permanent deletion cascades to channels."""
        params = "?permanent=true" if permanent else ""
        self._request("DELETE", f"/teams/{team_id}{params}")

    def get_team_by_name(self, name: str) -> dict | None:
        """Get a team by name. Returns team dict or None if not found."""
        try:
            return self._request("GET", f"/teams/name/{name}")
        except MattermostAPIError as e:
            if e.status == 404:
                return None
            raise

    def get_or_create_team(self, name: str, display_name: str, team_type: str = "O") -> str:
        """Get existing team or create one. Returns team_id."""
        existing = self.get_team_by_name(name)
        if existing:
            return existing["id"]
        try:
            return self.create_team(name, display_name, team_type)
        except MattermostAPIError as e:
            # Handle race: another process created it between our GET and POST
            if e.status == 409:
                existing = self.get_team_by_name(name)
                if existing:
                    return existing["id"]
            raise

    # ── Channels ──

    def create_channel(
        self, team_id: str, name: str, display_name: str, channel_type: str = "O",
    ) -> str:
        """Create a channel. type: 'O' (public) or 'P' (private). Returns channel_id."""
        result = self._request("POST", "/channels", {
            "team_id": team_id,
            "name": name,
            "display_name": display_name,
            "type": channel_type,
        })
        return result["id"]

    def get_channel_by_name(self, team_id: str, name: str) -> dict | None:
        """Get a channel by team ID and name. Returns channel dict or None."""
        try:
            return self._request("GET", f"/teams/{team_id}/channels/name/{name}")
        except MattermostAPIError as e:
            if e.status == 404:
                return None
            raise

    def get_or_create_channel(
        self, team_id: str, name: str, display_name: str, channel_type: str = "O",
    ) -> str:
        """Get existing channel or create one. Returns channel_id."""
        existing = self.get_channel_by_name(team_id, name)
        if existing:
            return existing["id"]
        try:
            return self.create_channel(team_id, name, display_name, channel_type)
        except MattermostAPIError as e:
            # Handle race: another process created it between our GET and POST
            if e.status == 409:
                existing = self.get_channel_by_name(team_id, name)
                if existing:
                    return existing["id"]
            raise

    def create_direct_channel(self, user_id_1: str, user_id_2: str) -> str:
        """Create (or get) a direct message channel between two users. Returns channel_id."""
        result = self._request("POST", "/channels/direct", [user_id_1, user_id_2])
        return result["id"]

    # ── Team/Channel membership ──

    def add_user_to_team(self, team_id: str, user_id: str) -> None:
        """Add a user to a team."""
        self._request("POST", f"/teams/{team_id}/members", {
            "team_id": team_id,
            "user_id": user_id,
        })

    def add_user_to_channel(self, channel_id: str, user_id: str) -> None:
        """Add a user to a channel."""
        self._request("POST", f"/channels/{channel_id}/members", {
            "user_id": user_id,
        })

    # ── Posts ──

    def create_post(
        self,
        channel_id: str,
        message: str,
        root_id: str = "",
        *,
        token_override: str | None = None,
    ) -> str:
        """Create a post. If root_id is set, creates a threaded reply. Returns post_id.

        Use token_override to post as a specific user (using their session token).
        """
        result = self._request(
            "POST",
            "/posts",
            {
                "channel_id": channel_id,
                "message": message,
                "root_id": root_id,
            },
            token_override=token_override,
        )
        return result["id"]

    # ── Reactions ──

    def add_reaction(
        self,
        post_id: str,
        user_id: str,
        emoji_name: str,
        *,
        token_override: str | None = None,
    ) -> None:
        """Add an emoji reaction to a post."""
        self._request(
            "POST",
            "/reactions",
            {
                "user_id": user_id,
                "post_id": post_id,
                "emoji_name": emoji_name,
            },
            token_override=token_override,
        )

    # ── Current user ──

    def get_me(self) -> dict:
        """Get the authenticated user's profile. Returns user dict."""
        return self._request("GET", "/users/me")

    # ── Config ──

    def get_config(self) -> dict:
        """Get the full server configuration. Requires system admin permissions."""
        return self._request("GET", "/config")

    def patch_config(self, config_patch: dict) -> dict:
        """Partially update the server configuration. Requires system admin permissions."""
        return self._request("PUT", "/config/patch", config_patch)

    # ── Users ──

    def get_user_by_username(self, username: str) -> dict | None:
        """Get a user by username. Returns user dict or None."""
        try:
            return self._request("GET", f"/users/username/{username}")
        except MattermostAPIError as e:
            if e.status == 404:
                return None
            raise

    def get_users_by_usernames(self, usernames: list[str]) -> list[dict]:
        """Batch lookup users by username. Returns list of user dicts for found users."""
        if not usernames:
            return []
        result = self._request("POST", "/users/usernames", usernames)
        return result or []

    def delete_user(self, user_id: str, permanent: bool = True) -> None:
        """Delete a user. Requires ServiceSettings.EnableAPIUserDeletion=true on the server."""
        params = "?permanent=true" if permanent else ""
        self._request("DELETE", f"/users/{user_id}{params}")

    def get_all_users(self, per_page: int = 200) -> list[dict]:
        """Fetch all users via paginated API calls. Returns list of user dicts."""
        all_users: list[dict] = []
        page = 0
        while True:
            batch = self._request("GET", f"/users?page={page}&per_page={per_page}")
            if not batch:
                break
            all_users.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return all_users
