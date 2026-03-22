"""Dataclasses for Mattermost content generation results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContentGenerationResult:
    """Summary of what was created."""

    teams_created: int = 0
    channels_created: int = 0
    users_added_to_teams: int = 0
    users_added_to_channels: int = 0
    posts_created: int = 0
    replies_created: int = 0
    reactions_added: int = 0
    attachments_uploaded: int = 0
    dm_conversations: int = 0
    dm_messages: int = 0
    group_conversations: int = 0
    group_messages: int = 0
    posts_pinned: int = 0
    statuses_set: int = 0
