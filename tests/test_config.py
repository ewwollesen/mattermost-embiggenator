"""Tests for config loading and merging."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from embiggenator.config import (
    DEFAULT_ABAC_ATTRIBUTES,
    AbacAttribute,
    ChannelConfig,
    Config,
    ContentConfig,
    MattermostConfig,
    TeamConfig,
    build_config,
    expand_env_vars,
    parse_abac_inline,
    parse_members_range,
    parse_range,
)


class TestParseMembers:
    def test_single_value(self):
        assert parse_members_range("10") == (10, 10)

    def test_range(self):
        assert parse_members_range("5-20") == (5, 20)

    def test_invalid_range(self):
        with pytest.raises(ValueError, match="Invalid range"):
            parse_members_range("20-5")


class TestParseAbacInline:
    def test_single_attr(self):
        attrs = parse_abac_inline("departmentNumber=Eng,Sales,Support")
        assert len(attrs) == 1
        assert attrs[0].name == "departmentNumber"
        assert attrs[0].values == ["Eng", "Sales", "Support"]
        assert attrs[0].weights is None

    def test_multiple_attrs(self):
        attrs = parse_abac_inline("dept=A,B;cat=X,Y,Z")
        assert len(attrs) == 2
        assert attrs[0].name == "dept"
        assert attrs[1].name == "cat"
        assert attrs[1].values == ["X", "Y", "Z"]

    def test_invalid_spec(self):
        with pytest.raises(ValueError, match="Invalid ABAC spec"):
            parse_abac_inline("noequals")


class TestAbacAttribute:
    def test_weight_length_mismatch(self):
        with pytest.raises(ValueError, match="weights length"):
            AbacAttribute(name="test", values=["a", "b"], weights=[1])


class TestConfigDefaults:
    def test_defaults(self):
        cfg = Config()
        assert cfg.users == 100
        assert cfg.groups == 10
        assert cfg.base_dn == "dc=planetexpress,dc=com"
        assert cfg.include_defaults is True

    def test_people_dn(self):
        cfg = Config()
        assert cfg.people_dn == "ou=people,dc=planetexpress,dc=com"


class TestBuildConfig:
    def test_cli_overrides(self):
        cfg = build_config(users=50, groups=5, members_per_group="3-10", seed=42)
        assert cfg.users == 50
        assert cfg.groups == 5
        assert cfg.members_min == 3
        assert cfg.members_max == 10
        assert cfg.seed == 42

    def test_cli_overrides_all_fields(self):
        cfg = build_config(
            base_dn="dc=cli,dc=test",
            email_domain="cli.test",
            default_password="clipass",
            password_scheme="{SHA}",
        )
        assert cfg.base_dn == "dc=cli,dc=test"
        assert cfg.email_domain == "cli.test"
        assert cfg.default_password == "clipass"
        assert cfg.password_scheme == "{SHA}"

    def test_yaml_config(self, tmp_path):
        config_data = {
            "users": 200,
            "groups": 15,
            "email_domain": "test.com",
            "abac": {
                "attributes": [
                    {"name": "dept", "values": ["A", "B"]},
                ]
            },
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file))
        assert cfg.users == 200
        assert cfg.groups == 15
        assert cfg.email_domain == "test.com"
        assert len(cfg.abac_attributes) == 1
        assert cfg.abac_attributes[0].name == "dept"

    def test_cli_overrides_yaml(self, tmp_path):
        config_data = {"users": 200, "groups": 15}
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file), users=50)
        assert cfg.users == 50  # CLI wins
        assert cfg.groups == 15  # YAML value kept

    def test_no_defaults_flag(self):
        cfg = build_config(no_defaults=True)
        assert cfg.include_defaults is False

    def test_abac_inline(self):
        cfg = build_config(abac_inline="dept=A,B;cat=X,Y")
        assert len(cfg.abac_attributes) == 2

    def test_default_abac_attributes(self):
        cfg = build_config()
        assert len(cfg.abac_attributes) == 3
        names = [a.name for a in cfg.abac_attributes]
        assert "businessCategory" in names
        assert "departmentNumber" in names
        assert "employeeType" in names

    def test_custom_abac_replaces_defaults(self):
        cfg = build_config(abac_inline="custom=X,Y")
        assert len(cfg.abac_attributes) == 1
        assert cfg.abac_attributes[0].name == "custom"


class TestParseRange:
    def test_single_value(self):
        assert parse_range("10") == (10, 10)

    def test_range_string(self):
        assert parse_range("5-20") == (5, 20)

    def test_integer_input(self):
        assert parse_range(10) == (10, 10)

    def test_invalid_range(self):
        with pytest.raises(ValueError, match="Invalid range"):
            parse_range("20-5")

    def test_negative_single_value(self):
        assert parse_range("-5") == (-5, -5)

    def test_negative_to_positive_range(self):
        assert parse_range("-5-20") == (-5, 20)

    def test_float_input(self):
        assert parse_range(10.7) == (10, 10)


class TestExpandEnvVars:
    def test_expand_set_var(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret123")
        assert expand_env_vars("${MY_TOKEN}") == "secret123"

    def test_expand_unset_var(self, monkeypatch):
        monkeypatch.delenv("UNSET_VAR", raising=False)
        assert expand_env_vars("${UNSET_VAR}") == ""

    def test_expand_in_url(self, monkeypatch):
        monkeypatch.setenv("MY_PAT", "tok_abc")
        assert expand_env_vars("Bearer ${MY_PAT}") == "Bearer tok_abc"

    def test_no_expansion_needed(self):
        assert expand_env_vars("plain string") == "plain string"

    def test_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("A", "1")
        monkeypatch.setenv("B", "2")
        assert expand_env_vars("${A}-${B}") == "1-2"


class TestChannelConfig:
    def test_auto_display_name(self):
        ch = ChannelConfig(name="my-channel")
        assert ch.display_name == "My Channel"

    def test_explicit_display_name(self):
        ch = ChannelConfig(name="foo", display_name="Custom Name")
        assert ch.display_name == "Custom Name"

    def test_default_type(self):
        ch = ChannelConfig(name="test")
        assert ch.type == "public"


class TestTeamConfig:
    def test_auto_display_name(self):
        t = TeamConfig(name="engineering")
        assert t.display_name == "Engineering"

    def test_explicit_display_name(self):
        t = TeamConfig(name="eng", display_name="Engineering Team")
        assert t.display_name == "Engineering Team"


class TestMattermostConfig:
    def test_defaults(self):
        mm = MattermostConfig()
        assert mm.url == "http://localhost:8065"
        assert mm.pat == ""


class TestContentConfig:
    def test_defaults(self):
        cc = ContentConfig()
        assert cc.channels_min is None
        assert cc.channels_max is None
        assert cc.channels_per_team_min == 5
        assert cc.channels_per_team_max == 10
        assert cc.private_channel_probability == 0.2
        assert cc.posts_per_channel_min == 20
        assert cc.posts_per_channel_max == 50
        assert cc.reply_probability == 0.3
        assert cc.reaction_probability == 0.2

    def test_asymmetric_channels_min_max_raises(self):
        with pytest.raises(ValueError, match="channels_min and channels_max"):
            ContentConfig(channels_min=10, channels_max=None)

    def test_asymmetric_channels_max_only_raises(self):
        with pytest.raises(ValueError, match="channels_min and channels_max"):
            ContentConfig(channels_min=None, channels_max=20)

    def test_reply_probability_too_high(self):
        with pytest.raises(ValueError, match="reply_probability"):
            ContentConfig(reply_probability=1.5)

    def test_reaction_probability_negative(self):
        with pytest.raises(ValueError, match="reaction_probability"):
            ContentConfig(reaction_probability=-0.1)

    def test_private_channel_probability_too_high(self):
        with pytest.raises(ValueError, match="private_channel_probability"):
            ContentConfig(private_channel_probability=2.0)

    def test_boundary_probabilities_valid(self):
        cc = ContentConfig(reply_probability=0.0, reaction_probability=1.0)
        assert cc.reply_probability == 0.0
        assert cc.reaction_probability == 1.0

    def test_attachment_defaults(self):
        cc = ContentConfig()
        assert cc.attachment_probability == 0.0
        assert cc.attachment_size_min == 1024
        assert cc.attachment_size_max == 5 * 1024 * 1024

    def test_attachment_probability_too_high(self):
        with pytest.raises(ValueError, match="attachment_probability"):
            ContentConfig(attachment_probability=1.5)

    def test_attachment_size_inverted_raises(self):
        with pytest.raises(ValueError, match="attachment_size"):
            ContentConfig(attachment_size_min=5000, attachment_size_max=1000)

    def test_group_messages_defaults(self):
        cc = ContentConfig()
        assert cc.group_messages_min == 5
        assert cc.group_messages_max == 15
        assert cc.group_message_members_min == 3
        assert cc.group_message_members_max == 7
        assert cc.group_messages_per_conversation_min == 5
        assert cc.group_messages_per_conversation_max == 15

    def test_group_messages_inverted_raises(self):
        with pytest.raises(ValueError, match="group_messages"):
            ContentConfig(group_messages_min=20, group_messages_max=5)

    def test_group_message_members_inverted_raises(self):
        with pytest.raises(ValueError, match="group_message_members"):
            ContentConfig(group_message_members_min=10, group_message_members_max=3)

    def test_pin_probability_defaults(self):
        cc = ContentConfig()
        assert cc.pin_probability == 0.05

    def test_pin_probability_too_high(self):
        with pytest.raises(ValueError, match="pin_probability"):
            ContentConfig(pin_probability=1.5)

    def test_status_probability_defaults(self):
        cc = ContentConfig()
        assert cc.status_probability == 0.6

    def test_status_probability_negative(self):
        with pytest.raises(ValueError, match="status_probability"):
            ContentConfig(status_probability=-0.1)


class TestBuildConfigV2:
    def test_mattermost_from_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MM_PAT", "test_pat_value")
        config_data = {
            "users": 10,
            "mattermost": {
                "url": "http://mm:8065",
                "pat": "${MM_PAT}",
            },
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file))
        assert cfg.mattermost.url == "http://mm:8065"
        assert cfg.mattermost.pat == "test_pat_value"

    def test_content_from_yaml(self, tmp_path):
        config_data = {
            "users": 10,
            "content": {
                "teams": [
                    {
                        "name": "engineering",
                        "display_name": "Engineering",
                        "channels": [
                            {"name": "general"},
                            {"name": "backend", "type": "private"},
                        ],
                    }
                ],
                "channels_per_team": "8-15",
                "private_channel_probability": 0.3,
                "posts_per_channel": "20-50",
                "reply_probability": 0.4,
                "replies_per_thread": "1-3",
                "reaction_probability": 0.15,
                "reactions_per_post": "1-2",
                "direct_messages": "5-15",
                "dms_per_conversation": "2-8",
            },
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file))
        assert len(cfg.content.teams) == 1
        assert cfg.content.teams[0].name == "engineering"
        assert len(cfg.content.teams[0].channels) == 2
        assert cfg.content.teams[0].channels[1].type == "private"
        assert cfg.content.channels_per_team_min == 8
        assert cfg.content.channels_per_team_max == 15
        assert cfg.content.private_channel_probability == 0.3
        assert cfg.content.posts_per_channel_min == 20
        assert cfg.content.posts_per_channel_max == 50
        assert cfg.content.reply_probability == 0.4
        assert cfg.content.replies_per_thread_min == 1
        assert cfg.content.replies_per_thread_max == 3
        assert cfg.content.direct_messages_min == 5
        assert cfg.content.direct_messages_max == 15

    def test_total_channels_from_yaml(self, tmp_path):
        config_data = {
            "content": {
                "channels": "100-200",
                "teams": [{"name": "engineering"}, {"name": "support"}],
            },
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file))
        assert cfg.content.channels_min == 100
        assert cfg.content.channels_max == 200

    def test_per_team_channels_per_team(self, tmp_path):
        config_data = {
            "content": {
                "channels_per_team": 5,
                "teams": [
                    {"name": "small", "channels_per_team": 3},
                    {"name": "big", "channels_per_team": "20-30"},
                    {"name": "default"},
                ],
            },
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file))
        assert cfg.content.channels_per_team_min == 5
        assert cfg.content.channels_per_team_max == 5

        assert cfg.content.teams[0].channels_per_team_min == 3
        assert cfg.content.teams[0].channels_per_team_max == 3
        assert cfg.content.teams[1].channels_per_team_min == 20
        assert cfg.content.teams[1].channels_per_team_max == 30
        assert cfg.content.teams[2].channels_per_team_min is None  # uses global

    def test_pat_cli_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MM_PAT", "yaml_pat")
        config_data = {
            "mattermost": {"pat": "${MM_PAT}"},
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file), pat="cli_pat")
        assert cfg.mattermost.pat == "cli_pat"

    def test_default_mattermost_and_content(self):
        cfg = build_config()
        assert cfg.mattermost.url == "http://localhost:8065"
        assert cfg.content.posts_per_channel_min == 20
        assert cfg.content.teams == []

    def test_attachment_config_from_yaml(self, tmp_path):
        config_data = {
            "content": {
                "attachment_probability": 0.15,
                "attachment_size": "2048-1048576",
                "teams": [{"name": "test"}],
            },
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file))
        assert cfg.content.attachment_probability == 0.15
        assert cfg.content.attachment_size_min == 2048
        assert cfg.content.attachment_size_max == 1048576

    def test_group_messages_from_yaml(self, tmp_path):
        config_data = {
            "content": {
                "group_messages": "10-25",
                "group_message_members": "3-8",
                "group_messages_per_conversation": "4-12",
                "teams": [{"name": "test"}],
            },
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file))
        assert cfg.content.group_messages_min == 10
        assert cfg.content.group_messages_max == 25
        assert cfg.content.group_message_members_min == 3
        assert cfg.content.group_message_members_max == 8
        assert cfg.content.group_messages_per_conversation_min == 4
        assert cfg.content.group_messages_per_conversation_max == 12

    def test_pin_and_status_from_yaml(self, tmp_path):
        config_data = {
            "content": {
                "pin_probability": 0.1,
                "status_probability": 0.8,
                "teams": [{"name": "test"}],
            },
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file))
        assert cfg.content.pin_probability == 0.1
        assert cfg.content.status_probability == 0.8

    def test_all_yaml_top_level_fields(self, tmp_path):
        """Cover all top-level YAML fields that map to Config."""
        config_data = {
            "users": 200,
            "groups": 15,
            "members_per_group": "8-25",
            "base_dn": "dc=test,dc=org",
            "people_ou": "users",
            "group_ou": "groups",
            "email_domain": "test.org",
            "default_password": "secret123",
            "password_scheme": "{SHA}",
            "seed": 77,
            "include_defaults": False,
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file))
        assert cfg.users == 200
        assert cfg.groups == 15
        assert cfg.members_min == 8
        assert cfg.members_max == 25
        assert cfg.base_dn == "dc=test,dc=org"
        assert cfg.people_ou == "users"
        assert cfg.group_ou == "groups"
        assert cfg.email_domain == "test.org"
        assert cfg.default_password == "secret123"
        assert cfg.password_scheme == "{SHA}"
        assert cfg.seed == 77
        assert cfg.include_defaults is False

    def test_string_channel_shorthand_in_yaml(self, tmp_path):
        """Channels can be specified as plain strings instead of dicts."""
        config_data = {
            "content": {
                "teams": [
                    {
                        "name": "test-team",
                        "channels": ["general", "random", "off-topic"],
                    }
                ],
            },
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file))
        channels = cfg.content.teams[0].channels
        assert len(channels) == 3
        assert channels[0].name == "general"
        assert channels[0].display_name == "General"  # auto-derived
        assert channels[2].name == "off-topic"

    def test_members_per_channel_from_yaml(self, tmp_path):
        config_data = {
            "content": {
                "members_per_channel": "10-100",
                "teams": [{"name": "test"}],
            },
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file))
        assert cfg.content.members_per_channel_min == 10
        assert cfg.content.members_per_channel_max == 100

    def test_abac_profile_file(self, tmp_path):
        """ABAC attributes loaded from a separate profile file."""
        profile_data = {
            "abac": {
                "attributes": [
                    {"name": "clearance", "values": ["Public", "Secret", "TopSecret"]},
                ],
            },
        }
        profile_file = tmp_path / "abac_profile.yaml"
        profile_file.write_text(yaml.dump(profile_data))

        cfg = build_config(abac_profile=str(profile_file))
        attr_names = [a.name for a in cfg.abac_attributes]
        assert "clearance" in attr_names

    def test_group_dn_property(self):
        cfg = Config(group_ou="groups", base_dn="dc=test,dc=org")
        assert cfg.group_dn == "ou=groups,dc=test,dc=org"


class TestConfigAvatarProbability:
    def test_default_zero(self):
        cfg = Config()
        assert cfg.avatar_probability == 0.0

    def test_valid_value(self):
        cfg = Config(avatar_probability=0.8)
        assert cfg.avatar_probability == 0.8

    def test_too_high_raises(self):
        with pytest.raises(ValueError, match="avatar_probability"):
            Config(avatar_probability=1.5)

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="avatar_probability"):
            Config(avatar_probability=-0.1)

    def test_from_yaml(self, tmp_path):
        config_data = {"users": 10, "avatar_probability": 0.75}
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))
        cfg = build_config(config_file=str(config_file))
        assert cfg.avatar_probability == 0.75


class TestAbacAttributeValidation:
    def test_weights_sum_to_zero_raises(self):
        with pytest.raises(ValueError, match="weights must sum to > 0"):
            AbacAttribute(name="bad", values=["A", "B"], weights=[0, 0])

    def test_weights_all_zero_raises(self):
        with pytest.raises(ValueError, match="weights must sum to > 0"):
            AbacAttribute(name="bad", values=["X"], weights=[0])


class TestParseAbacInlineEdgeCases:
    def test_trailing_semicolons_ignored(self):
        """Trailing semicolons produce empty parts that should be skipped."""
        result = parse_abac_inline("dept=Eng,Sales;")
        assert len(result) == 1
        assert result[0].name == "dept"

    def test_whitespace_handling(self):
        result = parse_abac_inline("  dept = Eng , Sales ; level = A , B  ")
        assert len(result) == 2
        assert result[0].values == ["Eng", "Sales"]
        assert result[1].values == ["A", "B"]
