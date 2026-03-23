"""Configuration dataclass with YAML loading and CLI/file/default merging."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AbacAttribute:
    """A single ABAC attribute definition."""

    name: str
    values: list[str]
    weights: list[int] | None = None

    def __post_init__(self) -> None:
        if self.weights is not None and len(self.weights) != len(self.values):
            raise ValueError(
                f"ABAC attribute '{self.name}': "
                f"weights length ({len(self.weights)}) != values length ({len(self.values)})"
            )
        if self.weights is not None and sum(self.weights) <= 0:
            raise ValueError(
                f"ABAC attribute '{self.name}': weights must sum to > 0"
            )


@dataclass
class ChannelConfig:
    """A channel to create inside a team."""

    name: str
    display_name: str = ""
    type: str = "public"  # "public" or "private"

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.name.replace("-", " ").replace("_", " ").title()


@dataclass
class TeamConfig:
    """A team to create with its channels."""

    name: str
    display_name: str = ""
    channels: list[ChannelConfig] = field(default_factory=list)
    channels_per_team_min: int | None = None  # per-team override (None = use global)
    channels_per_team_max: int | None = None

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.name.replace("-", " ").replace("_", " ").title()


@dataclass
class MattermostConfig:
    """Mattermost server connection settings."""

    url: str = "http://localhost:8065"
    pat: str = ""


@dataclass
class ContentConfig:
    """Content generation parameters."""

    teams: list[TeamConfig] = field(default_factory=list)
    channels_min: int | None = None  # total channels distributed across teams
    channels_max: int | None = None
    channels_per_team_min: int = 5   # fallback if channels not set
    channels_per_team_max: int = 10
    private_channel_probability: float = 0.2
    members_per_channel_min: int = 5
    members_per_channel_max: int = 50
    posts_per_channel_min: int = 20
    posts_per_channel_max: int = 50
    reply_probability: float = 0.3
    replies_per_thread_min: int = 1
    replies_per_thread_max: int = 5
    reaction_probability: float = 0.2
    reactions_per_post_min: int = 1
    reactions_per_post_max: int = 3
    attachment_probability: float = 0.0
    attachment_size_min: int = 1024  # 1 KB
    attachment_size_max: int = 5 * 1024 * 1024  # 5 MB
    direct_messages_min: int = 10
    direct_messages_max: int = 30
    dms_per_conversation_min: int = 3
    dms_per_conversation_max: int = 10
    group_messages_min: int = 5
    group_messages_max: int = 15
    group_message_members_min: int = 3
    group_message_members_max: int = 7
    group_messages_per_conversation_min: int = 5
    group_messages_per_conversation_max: int = 15
    pin_probability: float = 0.05
    status_probability: float = 0.6

    def __post_init__(self) -> None:
        if (self.channels_min is None) != (self.channels_max is None):
            raise ValueError(
                "channels_min and channels_max must both be set or both be None"
            )
        for name in ("reply_probability", "reaction_probability", "private_channel_probability", "attachment_probability", "pin_probability", "status_probability"):
            val = getattr(self, name)
            if not 0.0 <= val <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0, got {val}")
        # Validate all min/max range pairs
        _range_pairs = [
            ("channels_per_team_min", "channels_per_team_max"),
            ("members_per_channel_min", "members_per_channel_max"),
            ("posts_per_channel_min", "posts_per_channel_max"),
            ("replies_per_thread_min", "replies_per_thread_max"),
            ("reactions_per_post_min", "reactions_per_post_max"),
            ("attachment_size_min", "attachment_size_max"),
            ("direct_messages_min", "direct_messages_max"),
            ("dms_per_conversation_min", "dms_per_conversation_max"),
            ("group_messages_min", "group_messages_max"),
            ("group_message_members_min", "group_message_members_max"),
            ("group_messages_per_conversation_min", "group_messages_per_conversation_max"),
        ]
        if self.channels_min is not None:
            _range_pairs.append(("channels_min", "channels_max"))
        for min_name, max_name in _range_pairs:
            lo, hi = getattr(self, min_name), getattr(self, max_name)
            if lo > hi:
                label = min_name.removesuffix("_min")
                raise ValueError(f"{label}: min ({lo}) > max ({hi})")


DEFAULT_ABAC_ATTRIBUTES = [
    AbacAttribute(
        name="businessCategory",
        values=["IL4", "IL5", "IL6"],
        weights=[50, 35, 15],
    ),
    AbacAttribute(
        name="departmentNumber",
        values=["Engineering", "Sales", "Support", "Finance", "HR"],
    ),
    AbacAttribute(
        name="employeeType",
        values=["Full-Time", "Contractor", "Intern"],
        weights=[70, 20, 10],
    ),
]


@dataclass
class Config:
    """Resolved configuration for a generation run."""

    users: int = 100
    groups: int = 10
    members_min: int = 5
    members_max: int = 20
    base_dn: str = "dc=planetexpress,dc=com"
    people_ou: str = "people"
    group_ou: str = "people"
    email_domain: str = "planetexpress.com"
    default_password: str = "password"
    password_scheme: str = "{SSHA}"
    seed: int | None = None
    abac_attributes: list[AbacAttribute] = field(default_factory=list)
    include_defaults: bool = True
    avatar_probability: float = 0.0
    mattermost: MattermostConfig = field(default_factory=MattermostConfig)
    content: ContentConfig = field(default_factory=ContentConfig)

    def __post_init__(self) -> None:
        if not 0.0 <= self.avatar_probability <= 1.0:
            raise ValueError(
                f"avatar_probability must be between 0.0 and 1.0, got {self.avatar_probability}"
            )

    @property
    def people_dn(self) -> str:
        return f"ou={self.people_ou},{self.base_dn}"

    @property
    def group_dn(self) -> str:
        return f"ou={self.group_ou},{self.base_dn}"


_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def expand_env_vars(value: str) -> str:
    """Expand ${VAR} references in a string using environment variables.

    Unset variables expand to empty string.
    """
    def _replace(match: re.Match) -> str:
        return os.environ.get(match.group(1), "")
    return _ENV_VAR_RE.sub(_replace, value)


def parse_range(value: str | int | float) -> tuple[int, int]:
    """Parse a range value like '10', '5-20', or a bare integer.

    Handles negative numbers correctly: '-5' is a single value,
    '5-20' is a range, '-5-20' is -5 to 20.
    """
    if isinstance(value, (int, float)):
        n = int(value)
        return n, n
    s = str(value).strip()
    # Find the range separator: a hyphen that is NOT at position 0 (negative sign)
    sep_idx = s.find("-", 1)
    if sep_idx > 0:
        lo, hi = int(s[:sep_idx]), int(s[sep_idx + 1:])
        if lo > hi:
            raise ValueError(f"Invalid range: {lo} > {hi}")
        return lo, hi
    n = int(s)
    return n, n


# Backwards-compatible alias
parse_members_range = parse_range


def parse_abac_inline(abac_str: str) -> list[AbacAttribute]:
    """Parse inline ABAC like 'departmentNumber=Eng,Sales;businessCategory=Public,Secret'."""
    attrs = []
    for part in abac_str.split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, vals = part.partition("=")
        if not vals:
            raise ValueError(f"Invalid ABAC spec: {part}")
        attrs.append(AbacAttribute(name=name.strip(), values=[v.strip() for v in vals.split(",")]))
    return attrs


def load_abac_from_yaml(data: dict[str, Any]) -> list[AbacAttribute]:
    """Extract ABAC attributes from a YAML config dict."""
    abac_section = data.get("abac", {})
    attrs_list = abac_section.get("attributes", [])
    result = []
    for item in attrs_list:
        result.append(
            AbacAttribute(
                name=item["name"],
                values=item["values"],
                weights=item.get("weights"),
            )
        )
    return result


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config file."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _load_mattermost_from_yaml(data: dict[str, Any]) -> MattermostConfig:
    """Extract Mattermost connection config from YAML."""
    mm = data.get("mattermost", {})
    if not mm:
        return MattermostConfig()
    url = mm.get("url", "http://localhost:8065")
    pat = expand_env_vars(str(mm.get("pat", "")))
    return MattermostConfig(url=url, pat=pat)


def _load_content_from_yaml(data: dict[str, Any]) -> ContentConfig:
    """Extract content generation config from YAML."""
    ct = data.get("content", {})
    if not ct:
        return ContentConfig()

    cfg = ContentConfig()

    if "channels" in ct:
        lo, hi = parse_range(ct["channels"])
        cfg.channels_min = lo
        cfg.channels_max = hi

    if "channels_per_team" in ct:
        lo, hi = parse_range(ct["channels_per_team"])
        cfg.channels_per_team_min = lo
        cfg.channels_per_team_max = hi

    if "private_channel_probability" in ct:
        cfg.private_channel_probability = float(ct["private_channel_probability"])

    if "members_per_channel" in ct:
        lo, hi = parse_range(ct["members_per_channel"])
        cfg.members_per_channel_min = lo
        cfg.members_per_channel_max = hi

    # Teams
    for team_data in ct.get("teams", []):
        channels = []
        for ch in team_data.get("channels", []):
            if isinstance(ch, str):
                channels.append(ChannelConfig(name=ch))
            else:
                channels.append(ChannelConfig(
                    name=ch["name"],
                    display_name=ch.get("display_name", ""),
                    type=ch.get("type", "public"),
                ))
        team_ch_min: int | None = None
        team_ch_max: int | None = None
        if "channels_per_team" in team_data:
            team_ch_min, team_ch_max = parse_range(team_data["channels_per_team"])
        cfg.teams.append(TeamConfig(
            name=team_data["name"],
            display_name=team_data.get("display_name", ""),
            channels=channels,
            channels_per_team_min=team_ch_min,
            channels_per_team_max=team_ch_max,
        ))

    if "posts_per_channel" in ct:
        lo, hi = parse_range(ct["posts_per_channel"])
        cfg.posts_per_channel_min = lo
        cfg.posts_per_channel_max = hi

    if "reply_probability" in ct:
        cfg.reply_probability = float(ct["reply_probability"])

    if "replies_per_thread" in ct:
        lo, hi = parse_range(ct["replies_per_thread"])
        cfg.replies_per_thread_min = lo
        cfg.replies_per_thread_max = hi

    if "reaction_probability" in ct:
        cfg.reaction_probability = float(ct["reaction_probability"])

    if "reactions_per_post" in ct:
        lo, hi = parse_range(ct["reactions_per_post"])
        cfg.reactions_per_post_min = lo
        cfg.reactions_per_post_max = hi

    if "attachment_probability" in ct:
        cfg.attachment_probability = float(ct["attachment_probability"])

    if "attachment_size" in ct:
        lo, hi = parse_range(ct["attachment_size"])
        cfg.attachment_size_min = lo
        cfg.attachment_size_max = hi

    if "direct_messages" in ct:
        lo, hi = parse_range(ct["direct_messages"])
        cfg.direct_messages_min = lo
        cfg.direct_messages_max = hi

    if "dms_per_conversation" in ct:
        lo, hi = parse_range(ct["dms_per_conversation"])
        cfg.dms_per_conversation_min = lo
        cfg.dms_per_conversation_max = hi

    if "group_messages" in ct:
        lo, hi = parse_range(ct["group_messages"])
        cfg.group_messages_min = lo
        cfg.group_messages_max = hi

    if "group_message_members" in ct:
        lo, hi = parse_range(ct["group_message_members"])
        cfg.group_message_members_min = lo
        cfg.group_message_members_max = hi

    if "group_messages_per_conversation" in ct:
        lo, hi = parse_range(ct["group_messages_per_conversation"])
        cfg.group_messages_per_conversation_min = lo
        cfg.group_messages_per_conversation_max = hi

    if "pin_probability" in ct:
        cfg.pin_probability = float(ct["pin_probability"])

    if "status_probability" in ct:
        cfg.status_probability = float(ct["status_probability"])

    return cfg


def build_config(
    *,
    config_file: str | None = None,
    users: int | None = None,
    groups: int | None = None,
    members_per_group: str | None = None,
    base_dn: str | None = None,
    email_domain: str | None = None,
    default_password: str | None = None,
    password_scheme: str | None = None,
    seed: int | None = None,
    abac_inline: str | None = None,
    abac_profile: str | None = None,
    no_defaults: bool = False,
    pat: str | None = None,
) -> Config:
    """Build a Config by merging defaults < YAML file < CLI overrides."""
    cfg = Config()

    # Layer 1: YAML file
    yaml_data: dict[str, Any] = {}
    if config_file:
        yaml_data = load_yaml_config(config_file)
        if "users" in yaml_data:
            cfg.users = int(yaml_data["users"])
        if "groups" in yaml_data:
            cfg.groups = int(yaml_data["groups"])
        if "members_per_group" in yaml_data:
            lo, hi = parse_members_range(str(yaml_data["members_per_group"]))
            cfg.members_min = lo
            cfg.members_max = hi
        if "base_dn" in yaml_data:
            cfg.base_dn = yaml_data["base_dn"]
        if "people_ou" in yaml_data:
            cfg.people_ou = yaml_data["people_ou"]
        if "group_ou" in yaml_data:
            cfg.group_ou = yaml_data["group_ou"]
        if "email_domain" in yaml_data:
            cfg.email_domain = yaml_data["email_domain"]
        if "default_password" in yaml_data:
            cfg.default_password = yaml_data["default_password"]
        if "password_scheme" in yaml_data:
            cfg.password_scheme = yaml_data["password_scheme"]
        if "seed" in yaml_data:
            cfg.seed = int(yaml_data["seed"])
        if "include_defaults" in yaml_data:
            cfg.include_defaults = bool(yaml_data["include_defaults"])
        if "avatar_probability" in yaml_data:
            cfg.avatar_probability = float(yaml_data["avatar_probability"])
        cfg.abac_attributes.extend(load_abac_from_yaml(yaml_data))

        # New v2 sections
        cfg.mattermost = _load_mattermost_from_yaml(yaml_data)
        cfg.content = _load_content_from_yaml(yaml_data)

    # Layer 2: CLI overrides
    if users is not None:
        cfg.users = users
    if groups is not None:
        cfg.groups = groups
    if members_per_group is not None:
        lo, hi = parse_members_range(members_per_group)
        cfg.members_min = lo
        cfg.members_max = hi
    if base_dn is not None:
        cfg.base_dn = base_dn
    if email_domain is not None:
        cfg.email_domain = email_domain
    if default_password is not None:
        cfg.default_password = default_password
    if password_scheme is not None:
        cfg.password_scheme = password_scheme
    if seed is not None:
        cfg.seed = seed
    if no_defaults:
        cfg.include_defaults = False
    if pat is not None:
        cfg.mattermost.pat = pat

    # ABAC: use custom attributes if any are specified, otherwise use defaults
    custom_abac: list[AbacAttribute] = []

    if abac_profile:
        profile_data = load_yaml_config(abac_profile)
        custom_abac.extend(load_abac_from_yaml(profile_data))

    if abac_inline:
        custom_abac.extend(parse_abac_inline(abac_inline))

    if custom_abac or cfg.abac_attributes:
        # User specified custom ABAC — use those (YAML + profile + inline)
        cfg.abac_attributes.extend(custom_abac)
    else:
        # No custom ABAC — use built-in defaults
        cfg.abac_attributes = list(DEFAULT_ABAC_ATTRIBUTES)

    return cfg
