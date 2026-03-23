"""Create email/password Mattermost users via the REST API (no LDAP required)."""

from __future__ import annotations

import click

from embiggenator.models import GeneratedUser
from embiggenator.output.mattermost_client import MattermostAPIError, MattermostClient


def create_local_users(
    users: list[GeneratedUser],
    client: MattermostClient,
    password: str,
) -> dict[str, tuple[str, str]]:
    """Create email/password Mattermost accounts and log them in.

    For each generated user, creates an account via ``POST /api/v4/users``
    (using the admin PAT), then logs the user in to capture an individual
    session token.

    Returns a mapping of uid -> (mm_user_id, session_token).
    """
    created = 0
    skipped = 0
    failed = 0
    consecutive_failures = 0
    max_consecutive_failures = 5
    user_map: dict[str, tuple[str, str]] = {}

    for user in users:
        mm_user_id: str | None = None

        # Step 1: Create the user via the admin API
        try:
            result = client.create_user(
                username=user.uid,
                email=user.mail,
                password=password,
                first_name=user.given_name,
                last_name=user.sn,
            )
            mm_user_id = result["id"]
            created += 1
            consecutive_failures = 0
        except MattermostAPIError as e:
            if e.status == 409:
                # User already exists — look them up
                existing = client.get_user_by_username(user.uid)
                if existing:
                    mm_user_id = existing["id"]
                    skipped += 1
                    consecutive_failures = 0
                else:
                    failed += 1
                    consecutive_failures += 1
            else:
                failed += 1
                consecutive_failures += 1
                if failed <= 3:
                    click.echo(f"  Failed to create {user.uid}: {e}")
                elif failed == 4:
                    click.echo("  (suppressing further creation errors)")

        if mm_user_id is None:
            if consecutive_failures >= max_consecutive_failures and not user_map:
                click.echo(
                    f"  Aborting: first {consecutive_failures} attempts all failed. "
                    "Check Mattermost connectivity and permissions."
                )
                break
            continue

        # Step 2: Log the user in to get a session token
        try:
            body, token = client.login_user(user.uid, password)
            if token:
                user_map[user.uid] = (mm_user_id, token)
        except MattermostAPIError:
            # User was created but login failed — still count as created,
            # but they won't have a session token for per-user actions
            pass

        total = created + skipped
        if total % 25 == 0:
            click.echo(f"  Processed {total} users...")

    click.echo(
        f"Local users: {created} created, {skipped} already existed, {failed} failed"
    )
    click.echo(f"Logged in {len(user_map)} users with session tokens")
    return user_map
