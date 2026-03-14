"""Content orchestrator — creates teams, channels, posts, threads, reactions, DMs."""

from __future__ import annotations

import random

import click

from embiggenator.config import ChannelConfig, ContentConfig, TeamConfig
from embiggenator.generators.content import PassageBank
from embiggenator.models_mattermost import ContentGenerationResult
from embiggenator.output.mattermost_client import MattermostClient, MattermostAPIError

# Emoji pool for reactions
REACTION_EMOJIS = [
    "thumbsup", "thumbsdown", "heart", "smile", "laughing",
    "tada", "thinking", "eyes", "+1", "-1",
    "wave", "fire", "rocket", "100", "clap",
    "slightly_smiling_face", "grinning", "white_check_mark",
]

# Word pools for auto-generated channel names (Mattermost requires lowercase alphanum + hyphens)
_CHANNEL_PREFIXES = [
    "general", "random", "project", "dev", "ops", "design", "qa", "security",
    "infra", "data", "mobile", "web", "api", "docs", "support", "sales",
    "marketing", "finance", "hr", "legal", "product", "platform", "cloud",
    "backend", "frontend", "devops", "sre", "ml", "analytics", "research",
    "testing", "staging", "release", "onboarding", "training", "team",
    "alerts", "incidents", "reviews", "planning", "strategy", "growth",
]
_CHANNEL_SUFFIXES = [
    "chat", "discussion", "updates", "announcements", "help", "reviews",
    "planning", "standup", "alerts", "builds", "deploys", "bugs", "features",
    "requests", "feedback", "ideas", "notes", "watercooler", "social",
    "wins", "kudos", "releases", "oncall", "triage", "escalations",
    "retro", "demos", "questions", "tips", "resources", "links",
]


def generate_channel_configs(
    rng: random.Random,
    count: int,
    private_probability: float,
    existing_names: set[str] | None = None,
) -> list[ChannelConfig]:
    """Generate random channel configs with unique Mattermost-valid names."""
    used = set(existing_names) if existing_names else set()
    channels: list[ChannelConfig] = []

    # Build a shuffled pool of all prefix-suffix combos
    combos = [(p, s) for p in _CHANNEL_PREFIXES for s in _CHANNEL_SUFFIXES]
    rng.shuffle(combos)
    combo_iter = iter(combos)

    for _ in range(count):
        # Try prefix-suffix combos first
        name = None
        for prefix, suffix in combo_iter:
            candidate = f"{prefix}-{suffix}"
            if candidate not in used:
                name = candidate
                break

        # Fall back to numbered names if combos exhausted
        if name is None:
            i = len(used) + 1
            while f"channel-{i}" in used:
                i += 1
            name = f"channel-{i}"

        used.add(name)
        ch_type = "private" if rng.random() < private_probability else "public"
        channels.append(ChannelConfig(name=name, type=ch_type))

    return channels


def generate_mattermost_content(
    client: MattermostClient,
    content_config: ContentConfig,
    user_map: dict[str, tuple[str, str]],
    seed: int | None = None,
    passage_bank: PassageBank | None = None,
) -> ContentGenerationResult:
    """Generate Mattermost content: teams, channels, posts, threads, reactions, DMs.

    Args:
        client: Authenticated Mattermost API client.
        content_config: Content generation parameters.
        user_map: Mapping of uid -> (mm_user_id, session_token).
        seed: Optional random seed for reproducibility.
        passage_bank: Optional pre-loaded passage bank (creates default if None).
    """
    rng = random.Random(seed)
    bank = passage_bank or PassageBank()
    result = ContentGenerationResult()

    if not user_map:
        click.echo("Warning: no users available, skipping content generation")
        return result

    uids = list(user_map.keys())

    # ── Step 1: Create teams and channels ──
    channel_plans: list[_ChannelInfo] = []

    # Pre-compute per-team channel targets
    team_channel_targets = _compute_channel_targets(rng, content_config)

    for team_idx, team_cfg in enumerate(content_config.teams):
        try:
            team_id = client.get_or_create_team(team_cfg.name, team_cfg.display_name)
        except MattermostAPIError as e:
            click.echo(f"  Error creating team '{team_cfg.name}': {e}")
            click.echo(f"  Skipping team and its channels")
            continue
        result.teams_created += 1
        click.echo(f"  Team: {team_cfg.display_name} ({team_id[:8]}...)")

        # Add all users to the team
        for uid in uids:
            mm_user_id, _ = user_map[uid]
            try:
                client.add_user_to_team(team_id, mm_user_id)
                result.users_added_to_teams += 1
            except MattermostAPIError:
                pass  # already a member

        # Build channel list: explicit channels + auto-generated to fill the target
        all_channels = list(team_cfg.channels)
        target = team_channel_targets[team_idx]
        n_to_generate = max(0, target - len(all_channels))
        if n_to_generate > 0:
            existing_names = {ch.name for ch in all_channels}
            all_channels.extend(generate_channel_configs(
                rng, n_to_generate, content_config.private_channel_probability, existing_names,
            ))

        # Create channels
        for ch_cfg in all_channels:
            ch_type = "P" if ch_cfg.type == "private" else "O"
            try:
                channel_id = client.get_or_create_channel(
                    team_id, ch_cfg.name, ch_cfg.display_name, ch_type,
                )
            except MattermostAPIError as e:
                click.echo(f"    Error creating channel '{ch_cfg.name}': {e}")
                continue
            result.channels_created += 1

            # Assign a random subset of users as channel members
            n_members = rng.randint(
                content_config.members_per_channel_min,
                content_config.members_per_channel_max,
            )
            n_members = max(2, min(n_members, len(uids)))
            member_uids = rng.sample(uids, n_members)

            for uid in member_uids:
                mm_user_id, _ = user_map[uid]
                try:
                    client.add_user_to_channel(channel_id, mm_user_id)
                    result.users_added_to_channels += 1
                except MattermostAPIError:
                    pass  # already a member

            channel_plans.append(_ChannelInfo(
                channel_id=channel_id,
                channel_name=ch_cfg.name,
                team_id=team_id,
                member_uids=member_uids,
            ))
            click.echo(f"    Channel: {ch_cfg.display_name} ({len(member_uids)} members)")

    # ── Step 2: Generate posts ──
    all_post_ids: list[tuple[str, str, str]] = []  # (post_id, channel_id, author_uid)

    for ch_info in channel_plans:
        n_posts = rng.randint(
            content_config.posts_per_channel_min,
            content_config.posts_per_channel_max,
        )
        for _ in range(n_posts):
            author_uid = rng.choice(ch_info.member_uids)
            _, token = user_map[author_uid]
            message = bank.get_passage(rng)

            try:
                post_id = client.create_post(
                    ch_info.channel_id, message, token_override=token,
                )
                result.posts_created += 1
                all_post_ids.append((post_id, ch_info.channel_id, author_uid))
            except MattermostAPIError as e:
                click.echo(f"    Warning: failed to create post in {ch_info.channel_name}: {e}")

    click.echo(f"  Posts created: {result.posts_created}")

    # ── Step 3: Generate threaded replies ──
    for post_id, channel_id, original_uid in all_post_ids:
        if rng.random() >= content_config.reply_probability:
            continue
        # Find which channel this post is in to get member list
        ch_info = _find_channel(channel_plans, channel_id)
        if not ch_info:
            continue

        n_replies = rng.randint(
            content_config.replies_per_thread_min,
            content_config.replies_per_thread_max,
        )
        for _ in range(n_replies):
            reply_uid = rng.choice(ch_info.member_uids)
            _, token = user_map[reply_uid]
            reply_text = bank.get_short_reply(rng)

            try:
                client.create_post(
                    channel_id, reply_text, root_id=post_id, token_override=token,
                )
                result.replies_created += 1
            except MattermostAPIError:
                pass

    click.echo(f"  Replies created: {result.replies_created}")

    # ── Step 4: Generate reactions ──
    for post_id, channel_id, _ in all_post_ids:
        if rng.random() >= content_config.reaction_probability:
            continue
        ch_info = _find_channel(channel_plans, channel_id)
        if not ch_info:
            continue

        n_reactions = rng.randint(
            content_config.reactions_per_post_min,
            content_config.reactions_per_post_max,
        )
        reactors = rng.sample(
            ch_info.member_uids, min(n_reactions, len(ch_info.member_uids)),
        )
        for uid in reactors:
            mm_user_id, token = user_map[uid]
            emoji = rng.choice(REACTION_EMOJIS)
            try:
                client.add_reaction(post_id, mm_user_id, emoji, token_override=token)
                result.reactions_added += 1
            except MattermostAPIError:
                pass

    click.echo(f"  Reactions added: {result.reactions_added}")

    # ── Step 5: Generate DMs ──
    n_dm_convos = rng.randint(
        content_config.direct_messages_min,
        content_config.direct_messages_max,
    )
    # Don't try more conversations than we have user pairs
    max_pairs = len(uids) * (len(uids) - 1) // 2
    n_dm_convos = min(n_dm_convos, max_pairs)

    dm_pairs: set[tuple[str, str]] = set()
    attempts = 0
    while len(dm_pairs) < n_dm_convos and attempts < n_dm_convos * 3:
        u1, u2 = rng.sample(uids, 2)
        pair = (min(u1, u2), max(u1, u2))
        dm_pairs.add(pair)
        attempts += 1

    for uid1, uid2 in dm_pairs:
        mm_id1, token1 = user_map[uid1]
        mm_id2, token2 = user_map[uid2]

        try:
            dm_channel_id = client.create_direct_channel(mm_id1, mm_id2)
        except MattermostAPIError:
            continue

        result.dm_conversations += 1
        n_messages = rng.randint(
            content_config.dms_per_conversation_min,
            content_config.dms_per_conversation_max,
        )

        for _ in range(n_messages):
            # Alternate between the two users
            if rng.random() < 0.5:
                author_uid, token = uid1, token1
            else:
                author_uid, token = uid2, token2

            message = bank.get_short_reply(rng)
            try:
                client.create_post(dm_channel_id, message, token_override=token)
                result.dm_messages += 1
            except MattermostAPIError:
                pass

    click.echo(f"  DM conversations: {result.dm_conversations} ({result.dm_messages} messages)")

    return result


class _ChannelInfo:
    """Internal tracking for a channel during orchestration."""

    __slots__ = ("channel_id", "channel_name", "team_id", "member_uids")

    def __init__(self, channel_id: str, channel_name: str, team_id: str, member_uids: list[str]) -> None:
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.team_id = team_id
        self.member_uids = member_uids


def _find_channel(channels: list[_ChannelInfo], channel_id: str) -> _ChannelInfo | None:
    for ch in channels:
        if ch.channel_id == channel_id:
            return ch
    return None


def _compute_channel_targets(rng: random.Random, config: ContentConfig) -> list[int]:
    """Compute channel count for each team.

    Priority:
    1. Per-team channels_per_team override
    2. Top-level channels (total) — distributed across teams without overrides
    3. Top-level channels_per_team — used per-team as fallback
    """
    n_teams = len(config.teams)
    if n_teams == 0:
        return []

    targets: list[int | None] = [None] * n_teams

    # Apply per-team overrides first
    for i, team in enumerate(config.teams):
        if team.channels_per_team_min is not None:
            targets[i] = rng.randint(team.channels_per_team_min, team.channels_per_team_max)

    # If top-level `channels` is set, distribute remaining across non-overridden teams
    if config.channels_min is not None:
        total = rng.randint(config.channels_min, config.channels_max)

        # Subtract what's already allocated by per-team overrides
        override_total = sum(t for t in targets if t is not None)
        remaining = max(0, total - override_total)

        # Find teams that need allocation
        unset_indices = [i for i, t in enumerate(targets) if t is None]

        if unset_indices:
            # Distribute remaining roughly evenly with some randomness
            per_team_base = remaining // len(unset_indices)
            leftover = remaining - per_team_base * len(unset_indices)

            for i in unset_indices:
                targets[i] = per_team_base

            # Distribute leftover one-per-team randomly
            if leftover > 0:
                bonus_teams = rng.sample(unset_indices, min(leftover, len(unset_indices)))
                for i in bonus_teams:
                    targets[i] += 1
    else:
        # No total channels — use channels_per_team for any remaining
        for i in range(n_teams):
            if targets[i] is None:
                targets[i] = rng.randint(
                    config.channels_per_team_min, config.channels_per_team_max,
                )

    return targets
