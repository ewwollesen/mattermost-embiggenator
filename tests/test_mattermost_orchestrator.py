"""Tests for the Mattermost content orchestrator."""

from __future__ import annotations

import random
from unittest.mock import MagicMock, patch

import click
import pytest

from embiggenator.config import ChannelConfig, ContentConfig, TeamConfig
from embiggenator.generators.content import PassageBank
from embiggenator.generators.mattermost import (
    _compute_channel_targets,
    generate_channel_configs,
    generate_mattermost_content,
    preflight_check_max_users_per_team,
)
from embiggenator.output.mattermost_client import MattermostClient, MattermostAPIError


@pytest.fixture()
def passage_bank(tmp_path):
    """Create a small passage bank for testing."""
    f = tmp_path / "test.txt"
    paragraphs = [
        f"This is test paragraph number {i} with enough text for the minimum length filter."
        for i in range(100)
    ]
    f.write_text("\n\n".join(paragraphs))
    return PassageBank(text_dir=tmp_path)


@pytest.fixture()
def user_map():
    """Fake user map with 10 users."""
    return {
        f"user{i}": (f"mm_id_{i}", f"token_{i}")
        for i in range(10)
    }


@pytest.fixture()
def mock_client():
    """Create a mock MattermostClient."""
    client = MagicMock(spec=MattermostClient)
    client.get_or_create_team.return_value = "team_001"
    client.get_or_create_channel.return_value = "ch_001"
    client.create_post.return_value = "post_001"
    client.create_direct_channel.return_value = "dm_001"
    return client


@pytest.fixture()
def small_content_config():
    """Content config with small numbers for fast testing.

    Uses 2 explicit channels and channels_per_team=2 so no auto-generation happens.
    """
    return ContentConfig(
        teams=[
            TeamConfig(
                name="test-team",
                display_name="Test Team",
                channels=[
                    ChannelConfig(name="general", display_name="General"),
                    ChannelConfig(name="private", display_name="Private", type="private"),
                ],
                channels_per_team_min=2,
                channels_per_team_max=2,
            ),
        ],
        channels_per_team_min=5,
        channels_per_team_max=10,
        posts_per_channel_min=3,
        posts_per_channel_max=5,
        reply_probability=0.5,
        replies_per_thread_min=1,
        replies_per_thread_max=2,
        reaction_probability=0.5,
        reactions_per_post_min=1,
        reactions_per_post_max=2,
        direct_messages_min=2,
        direct_messages_max=3,
        dms_per_conversation_min=2,
        dms_per_conversation_max=3,
    )


class TestGenerateMattermostContent:
    def test_creates_teams_and_channels(self, mock_client, small_content_config, user_map, passage_bank):
        result = generate_mattermost_content(
            mock_client, small_content_config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.teams_created == 1
        assert result.channels_created == 2
        mock_client.get_or_create_team.assert_called_once_with("test-team", "Test Team")
        assert mock_client.get_or_create_channel.call_count == 2

    def test_adds_users_to_teams(self, mock_client, small_content_config, user_map, passage_bank):
        result = generate_mattermost_content(
            mock_client, small_content_config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.users_added_to_teams == 10  # all users added to one team

    def test_creates_posts(self, mock_client, small_content_config, user_map, passage_bank):
        result = generate_mattermost_content(
            mock_client, small_content_config, user_map, seed=42, passage_bank=passage_bank,
        )
        # Should have created posts in both channels (3-5 each)
        assert result.posts_created >= 6  # 2 channels * 3 min
        assert result.posts_created <= 10  # 2 channels * 5 max

    def test_creates_replies(self, mock_client, small_content_config, user_map, passage_bank):
        result = generate_mattermost_content(
            mock_client, small_content_config, user_map, seed=42, passage_bank=passage_bank,
        )
        # With 50% reply probability and 6-10 posts, should have some replies
        assert result.replies_created > 0

    def test_creates_reactions(self, mock_client, small_content_config, user_map, passage_bank):
        result = generate_mattermost_content(
            mock_client, small_content_config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.reactions_added > 0

    def test_creates_dms(self, mock_client, small_content_config, user_map, passage_bank):
        result = generate_mattermost_content(
            mock_client, small_content_config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.dm_conversations >= 2
        assert result.dm_messages > 0

    def test_deterministic_with_seed(self, mock_client, small_content_config, user_map, passage_bank):
        # Reset mock between runs
        result1 = generate_mattermost_content(
            mock_client, small_content_config, user_map, seed=99, passage_bank=passage_bank,
        )
        mock_client.reset_mock()
        mock_client.get_or_create_team.return_value = "team_001"
        mock_client.get_or_create_channel.return_value = "ch_001"
        mock_client.create_post.return_value = "post_001"
        mock_client.create_direct_channel.return_value = "dm_001"

        result2 = generate_mattermost_content(
            mock_client, small_content_config, user_map, seed=99, passage_bank=passage_bank,
        )
        assert result1.posts_created == result2.posts_created
        assert result1.dm_conversations == result2.dm_conversations

    def test_empty_user_map(self, mock_client, small_content_config, passage_bank):
        result = generate_mattermost_content(
            mock_client, small_content_config, {}, seed=42, passage_bank=passage_bank,
        )
        assert result.posts_created == 0
        assert result.teams_created == 0

    def test_single_user(self, mock_client, passage_bank):
        """Single user should not crash — channels get 1 member, DMs skipped."""
        single_user_map = {"user0": ("mm_id_0", "token_0")}
        config = ContentConfig(
            teams=[TeamConfig(name="t", channels_per_team_min=2, channels_per_team_max=2)],
            channels_per_team_min=2,
            channels_per_team_max=2,
            members_per_channel_min=5,
            members_per_channel_max=10,
            posts_per_channel_min=1,
            posts_per_channel_max=2,
            direct_messages_min=1,
            direct_messages_max=3,
            dms_per_conversation_min=1,
            dms_per_conversation_max=2,
        )
        result = generate_mattermost_content(
            mock_client, config, single_user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.channels_created == 2
        assert result.posts_created >= 2
        assert result.dm_conversations == 0  # need >= 2 users for DMs

    def test_private_channel_type(self, mock_client, small_content_config, user_map, passage_bank):
        generate_mattermost_content(
            mock_client, small_content_config, user_map, seed=42, passage_bank=passage_bank,
        )
        # Second channel should be private
        calls = mock_client.get_or_create_channel.call_args_list
        assert calls[1][0][3] == "P"  # channel_type arg
        assert calls[0][0][3] == "O"  # first channel is public

    def test_no_teams_config(self, mock_client, user_map, passage_bank):
        config = ContentConfig(
            direct_messages_min=1,
            direct_messages_max=2,
            dms_per_conversation_min=1,
            dms_per_conversation_max=2,
        )
        result = generate_mattermost_content(
            mock_client, config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.teams_created == 0
        assert result.channels_created == 0
        assert result.dm_conversations >= 1

    def test_auto_generates_channels(self, mock_client, user_map, passage_bank):
        """Team with no explicit channels gets auto-generated ones."""
        config = ContentConfig(
            teams=[
                TeamConfig(name="auto-team", display_name="Auto Team"),
            ],
            channels_per_team_min=8,
            channels_per_team_max=8,
            posts_per_channel_min=1,
            posts_per_channel_max=1,
            direct_messages_min=0,
            direct_messages_max=0,
        )
        result = generate_mattermost_content(
            mock_client, config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.channels_created == 8

    def test_auto_generates_channels_supplements_explicit(self, mock_client, user_map, passage_bank):
        """Auto-generation fills up to channels_per_team, keeping explicit channels."""
        config = ContentConfig(
            teams=[
                TeamConfig(
                    name="mixed-team",
                    display_name="Mixed Team",
                    channels=[ChannelConfig(name="important", type="private")],
                ),
            ],
            channels_per_team_min=5,
            channels_per_team_max=5,
            posts_per_channel_min=1,
            posts_per_channel_max=1,
            direct_messages_min=0,
            direct_messages_max=0,
        )
        result = generate_mattermost_content(
            mock_client, config, user_map, seed=42, passage_bank=passage_bank,
        )
        # 1 explicit + 4 auto-generated = 5 total
        assert result.channels_created == 5
        # First channel call should be the explicit "important" one
        first_call = mock_client.get_or_create_channel.call_args_list[0]
        assert first_call[0][1] == "important"
        assert first_call[0][3] == "P"

    def test_creates_attachments(self, mock_client, user_map, passage_bank):
        """With attachment_probability=1.0, every post gets an attachment."""
        config = ContentConfig(
            teams=[
                TeamConfig(
                    name="t",
                    channels=[ChannelConfig(name="ch")],
                    channels_per_team_min=1,
                    channels_per_team_max=1,
                ),
            ],
            posts_per_channel_min=5,
            posts_per_channel_max=5,
            attachment_probability=1.0,
            attachment_size_min=512,
            attachment_size_max=1024,
            direct_messages_min=0,
            direct_messages_max=0,
            group_messages_min=0,
            group_messages_max=0,
            reply_probability=0.0,
            reaction_probability=0.0,
            pin_probability=0.0,
            status_probability=0.0,
        )
        mock_client.upload_file.return_value = "file_001"
        result = generate_mattermost_content(
            mock_client, config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.attachments_uploaded == 5
        assert mock_client.upload_file.call_count == 5
        # Verify file_ids were passed to every create_post (only channel posts, no replies/group msgs)
        for call in mock_client.create_post.call_args_list:
            assert call.kwargs.get("file_ids") == ["file_001"] or call[1].get("file_ids") == ["file_001"]

    def test_no_attachments_when_probability_zero(self, mock_client, small_content_config, user_map, passage_bank):
        """Default attachment_probability=0.0 means no uploads."""
        result = generate_mattermost_content(
            mock_client, small_content_config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.attachments_uploaded == 0
        mock_client.upload_file.assert_not_called()

    def test_per_team_channel_count_override(self, mock_client, user_map, passage_bank):
        """Per-team channels_per_team overrides the global default."""
        config = ContentConfig(
            teams=[
                TeamConfig(
                    name="big-team",
                    display_name="Big Team",
                    channels_per_team_min=15,
                    channels_per_team_max=15,
                ),
            ],
            channels_per_team_min=3,
            channels_per_team_max=3,
            posts_per_channel_min=1,
            posts_per_channel_max=1,
            direct_messages_min=0,
            direct_messages_max=0,
        )
        result = generate_mattermost_content(
            mock_client, config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.channels_created == 15  # per-team override, not global 3


    def test_creates_group_messages(self, mock_client, user_map, passage_bank):
        """Group messages should create group channels and post messages."""
        config = ContentConfig(
            teams=[],
            direct_messages_min=0,
            direct_messages_max=0,
            group_messages_min=3,
            group_messages_max=3,
            group_message_members_min=3,
            group_message_members_max=5,
            group_messages_per_conversation_min=4,
            group_messages_per_conversation_max=4,
            status_probability=0.0,
        )
        mock_client.create_group_channel.return_value = "gm_001"
        result = generate_mattermost_content(
            mock_client, config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.group_conversations == 3
        assert result.group_messages == 12  # 3 convos * 4 messages
        assert mock_client.create_group_channel.call_count == 3
        # Verify each group channel call has 3-5 user IDs
        for call in mock_client.create_group_channel.call_args_list:
            user_ids = call[0][0]
            assert 3 <= len(user_ids) <= 5

    def test_no_group_messages_with_fewer_than_3_users(self, mock_client, passage_bank):
        """Group messages require at least 3 users."""
        two_user_map = {
            "user0": ("mm_id_0", "token_0"),
            "user1": ("mm_id_1", "token_1"),
        }
        config = ContentConfig(
            teams=[],
            direct_messages_min=0,
            direct_messages_max=0,
            group_messages_min=5,
            group_messages_max=5,
            status_probability=0.0,
        )
        result = generate_mattermost_content(
            mock_client, config, two_user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.group_conversations == 0
        assert result.group_messages == 0

    def test_no_group_messages_when_zero(self, mock_client, user_map, passage_bank):
        """group_messages=0 means no group channels created."""
        config = ContentConfig(
            teams=[],
            direct_messages_min=0,
            direct_messages_max=0,
            group_messages_min=0,
            group_messages_max=0,
            status_probability=0.0,
        )
        result = generate_mattermost_content(
            mock_client, config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.group_conversations == 0
        mock_client.create_group_channel.assert_not_called()

    def test_pins_posts(self, mock_client, user_map, passage_bank):
        """With pin_probability=1.0, every post should be pinned."""
        config = ContentConfig(
            teams=[
                TeamConfig(
                    name="t",
                    channels=[ChannelConfig(name="ch")],
                    channels_per_team_min=1,
                    channels_per_team_max=1,
                ),
            ],
            posts_per_channel_min=5,
            posts_per_channel_max=5,
            pin_probability=1.0,
            reply_probability=0.0,
            reaction_probability=0.0,
            direct_messages_min=0,
            direct_messages_max=0,
            group_messages_min=0,
            group_messages_max=0,
            status_probability=0.0,
        )
        result = generate_mattermost_content(
            mock_client, config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.posts_pinned == 5
        assert mock_client.pin_post.call_count == 5

    def test_no_pins_when_probability_zero(self, mock_client, small_content_config, user_map, passage_bank):
        """Default pin_probability=0.05 — set to 0 to verify no pins."""
        small_content_config.pin_probability = 0.0
        result = generate_mattermost_content(
            mock_client, small_content_config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.posts_pinned == 0
        mock_client.pin_post.assert_not_called()

    def test_sets_custom_statuses(self, mock_client, user_map, passage_bank):
        """With status_probability=1.0, every user gets a status."""
        config = ContentConfig(
            teams=[],
            direct_messages_min=0,
            direct_messages_max=0,
            group_messages_min=0,
            group_messages_max=0,
            status_probability=1.0,
        )
        result = generate_mattermost_content(
            mock_client, config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.statuses_set == 10  # all 10 users
        assert mock_client.set_custom_status.call_count == 10

    def test_no_statuses_when_probability_zero(self, mock_client, user_map, passage_bank):
        """status_probability=0.0 means no statuses set."""
        config = ContentConfig(
            teams=[],
            direct_messages_min=0,
            direct_messages_max=0,
            group_messages_min=0,
            group_messages_max=0,
            status_probability=0.0,
        )
        result = generate_mattermost_content(
            mock_client, config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.statuses_set == 0
        mock_client.set_custom_status.assert_not_called()


class TestGenerateChannelConfigs:
    def test_generates_correct_count(self):
        rng = random.Random(42)
        channels = generate_channel_configs(rng, 10, 0.2)
        assert len(channels) == 10

    def test_unique_names(self):
        rng = random.Random(42)
        channels = generate_channel_configs(rng, 50, 0.0)
        names = [ch.name for ch in channels]
        assert len(names) == len(set(names))

    def test_respects_existing_names(self):
        rng = random.Random(42)
        existing = {"general-chat", "random-discussion"}
        channels = generate_channel_configs(rng, 5, 0.0, existing)
        generated_names = {ch.name for ch in channels}
        assert not generated_names.intersection(existing)

    def test_mattermost_valid_names(self):
        rng = random.Random(42)
        channels = generate_channel_configs(rng, 30, 0.0)
        for ch in channels:
            assert ch.name == ch.name.lower(), f"Name not lowercase: {ch.name}"
            assert all(c.isalnum() or c == "-" for c in ch.name), f"Invalid chars: {ch.name}"
            assert len(ch.name) >= 2, f"Name too short: {ch.name}"

    def test_private_probability(self):
        rng = random.Random(42)
        channels = generate_channel_configs(rng, 200, 1.0)
        assert all(ch.type == "private" for ch in channels)

        channels = generate_channel_configs(rng, 200, 0.0)
        assert all(ch.type == "public" for ch in channels)

    def test_handles_large_count(self):
        """Should handle more channels than prefix-suffix combos via fallback."""
        rng = random.Random(42)
        channels = generate_channel_configs(rng, 2000, 0.1)
        assert len(channels) == 2000
        names = [ch.name for ch in channels]
        assert len(names) == len(set(names))


class TestComputeChannelTargets:
    def test_total_channels_distributed_evenly(self):
        config = ContentConfig(
            teams=[TeamConfig(name="a"), TeamConfig(name="b")],
            channels_min=200,
            channels_max=200,
        )
        rng = random.Random(42)
        targets = _compute_channel_targets(rng, config)
        assert sum(targets) == 200
        assert len(targets) == 2
        # Should be roughly 100 each
        assert all(90 <= t <= 110 for t in targets)

    def test_total_channels_with_per_team_override(self):
        config = ContentConfig(
            teams=[
                TeamConfig(name="small", channels_per_team_min=20, channels_per_team_max=20),
                TeamConfig(name="rest"),
            ],
            channels_min=200,
            channels_max=200,
        )
        rng = random.Random(42)
        targets = _compute_channel_targets(rng, config)
        assert targets[0] == 20   # per-team override
        assert targets[1] == 180  # remainder goes here
        assert sum(targets) == 200

    def test_total_channels_three_teams(self):
        config = ContentConfig(
            teams=[TeamConfig(name="a"), TeamConfig(name="b"), TeamConfig(name="c")],
            channels_min=90,
            channels_max=90,
        )
        rng = random.Random(42)
        targets = _compute_channel_targets(rng, config)
        assert sum(targets) == 90
        assert len(targets) == 3
        assert all(t == 30 for t in targets)

    def test_falls_back_to_channels_per_team(self):
        config = ContentConfig(
            teams=[TeamConfig(name="a"), TeamConfig(name="b")],
            channels_per_team_min=7,
            channels_per_team_max=7,
        )
        rng = random.Random(42)
        targets = _compute_channel_targets(rng, config)
        assert targets == [7, 7]

    def test_no_teams(self):
        config = ContentConfig(teams=[])
        rng = random.Random(42)
        targets = _compute_channel_targets(rng, config)
        assert targets == []

    def test_single_team_gets_all(self):
        config = ContentConfig(
            teams=[TeamConfig(name="only")],
            channels_min=150,
            channels_max=150,
        )
        rng = random.Random(42)
        targets = _compute_channel_targets(rng, config)
        assert targets == [150]

    def test_total_channels_orchestration(self, mock_client, user_map, passage_bank):  # noqa: PT019
        """End-to-end: total channels distributed across 2 teams."""
        config = ContentConfig(
            teams=[TeamConfig(name="a"), TeamConfig(name="b")],
            channels_min=20,
            channels_max=20,
            posts_per_channel_min=1,
            posts_per_channel_max=1,
            direct_messages_min=0,
            direct_messages_max=0,
        )
        result = generate_mattermost_content(
            mock_client, config, user_map, seed=42, passage_bank=passage_bank,
        )
        assert result.channels_created == 20


class TestPreflightMaxUsersPerTeam:
    @pytest.fixture()
    def mock_client(self):
        client = MagicMock(spec=MattermostClient)
        return client

    def test_limit_sufficient(self, mock_client):
        mock_client.get_config.return_value = {"TeamSettings": {"MaxUsersPerTeam": 100}}
        preflight_check_max_users_per_team(mock_client, 50)
        mock_client.patch_config.assert_not_called()

    def test_limit_exceeded_confirm(self, mock_client):
        mock_client.get_config.return_value = {"TeamSettings": {"MaxUsersPerTeam": 10}}
        mock_client.patch_config.return_value = {"TeamSettings": {"MaxUsersPerTeam": 50}}
        with patch("embiggenator.generators.mattermost.click.confirm"):
            preflight_check_max_users_per_team(mock_client, 50)
        mock_client.patch_config.assert_called_once_with({"TeamSettings": {"MaxUsersPerTeam": 50}})

    def test_auto_yes_patches_without_prompting(self, mock_client):
        mock_client.get_config.return_value = {"TeamSettings": {"MaxUsersPerTeam": 10}}
        mock_client.patch_config.return_value = {"TeamSettings": {"MaxUsersPerTeam": 50}}
        with patch("embiggenator.generators.mattermost.click.confirm") as mock_confirm:
            preflight_check_max_users_per_team(mock_client, 50, auto_yes=True)
        mock_confirm.assert_not_called()
        mock_client.patch_config.assert_called_once_with({"TeamSettings": {"MaxUsersPerTeam": 50}})

    def test_get_config_403_warns_and_continues(self, mock_client):
        mock_client.get_config.side_effect = MattermostAPIError(403, "forbidden", "/config")
        # Should not raise
        preflight_check_max_users_per_team(mock_client, 50)
        mock_client.patch_config.assert_not_called()

    def test_get_config_500_reraises(self, mock_client):
        mock_client.get_config.side_effect = MattermostAPIError(500, "server error", "/config")
        with pytest.raises(MattermostAPIError) as exc_info:
            preflight_check_max_users_per_team(mock_client, 50)
        assert exc_info.value.status == 500

    def test_user_declines_aborts(self, mock_client):
        mock_client.get_config.return_value = {"TeamSettings": {"MaxUsersPerTeam": 10}}
        with patch("embiggenator.generators.mattermost.click.confirm", side_effect=click.Abort):
            with pytest.raises(click.Abort):
                preflight_check_max_users_per_team(mock_client, 50)
        mock_client.patch_config.assert_not_called()

    def test_patch_config_403_raises_click_exception(self, mock_client):
        mock_client.get_config.return_value = {"TeamSettings": {"MaxUsersPerTeam": 10}}
        mock_client.patch_config.side_effect = MattermostAPIError(403, "forbidden", "/config/patch")
        with pytest.raises(click.ClickException, match="Unable to update MaxUsersPerTeam"):
            preflight_check_max_users_per_team(mock_client, 50, auto_yes=True)
