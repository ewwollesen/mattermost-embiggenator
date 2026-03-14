"""Dataclasses for Mattermost content generation planning."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChannelPlan:
    """Plan for a single channel's content."""

    channel_id: str
    channel_name: str
    team_id: str
    member_uids: list[str]  # UIDs of users who are members


@dataclass
class PostPlan:
    """Plan for a single post or reply."""

    channel_id: str
    author_uid: str
    message: str
    root_id: str = ""  # non-empty for threaded replies


@dataclass
class ReactionPlan:
    """Plan for a single emoji reaction."""

    post_id: str
    user_uid: str
    emoji_name: str


@dataclass
class DMConversation:
    """Plan for a direct message conversation between two users."""

    user_uid_1: str
    user_uid_2: str
    messages: list[tuple[str, str]]  # list of (author_uid, message_text)


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
    dm_conversations: int = 0
    dm_messages: int = 0
