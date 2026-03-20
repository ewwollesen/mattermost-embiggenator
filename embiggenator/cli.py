"""Click CLI commands: generate-ldif, populate, content, run-all, show-config."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from embiggenator.output.mattermost_client import MattermostClient

from embiggenator.config import Config, build_config
from embiggenator.generators.groups import generate_groups
from embiggenator.generators.users import generate_users
from embiggenator.models import GeneratedGroup, GeneratedUser
from embiggenator.output.ldif_writer import write_ldif_files


@click.group()
@click.version_option(package_name="embiggenator")
def cli() -> None:
    """Embiggenator: LDAP test data generator for Mattermost testing."""


# Shared options for generate-ldif and populate
_common_options = [
    click.option("-u", "--users", type=int, default=None, help="Number of users to generate"),
    click.option("-g", "--groups", type=int, default=None, help="Number of groups to generate"),
    click.option(
        "-m",
        "--members-per-group",
        type=str,
        default=None,
        help="Members per group: integer or 'min-max' range",
    ),
    click.option("-c", "--config", "config_file", type=click.Path(exists=True), default=None, help="YAML config file"),
    click.option("--base-dn", type=str, default=None, help="Base DN (default: dc=planetexpress,dc=com)"),
    click.option("--email-domain", type=str, default=None, help="Email domain for generated users"),
    click.option("--default-password", type=str, default=None, help="Default password for all users"),
    click.option(
        "--password-scheme",
        type=click.Choice(["{SSHA}", "{SHA}", "{PLAIN}"], case_sensitive=False),
        default=None,
        help="Password hashing scheme",
    ),
    click.option("--seed", type=int, default=None, help="Random seed for reproducible output"),
    click.option("--abac", "abac_inline", type=str, default=None, help="Inline ABAC: 'attr=val1,val2;attr2=val3,val4'"),
    click.option("--abac-profile", type=click.Path(exists=True), default=None, help="ABAC profile YAML file"),
]


def _add_common_options(func):
    """Apply shared options to a command."""
    for option in reversed(_common_options):
        func = option(func)
    return func


# Shared LDAP connection options (used by populate, reset, disable-user, update-user, run-all)
# Note: --base-dn is NOT included here because _common_options already defines it for
# populate/run-all. Commands that don't use _common_options add --base-dn explicitly.
_ldap_connection_options = [
    click.option("--host", type=str, default="localhost", show_default=True, help="LDAP server host"),
    click.option("--port", type=int, default=10389, show_default=True, help="LDAP server port"),
    click.option("--bind-dn", type=str, default=None, help="Bind DN (default: cn=admin,dc=planetexpress,dc=com)"),
    click.option("--bind-password", type=str, default=None, help="Bind password (default: GoodNewsEveryone)"),
    click.option("--use-ssl", is_flag=True, default=False, help="Use SSL/TLS connection"),
]


def _add_ldap_options(func):
    """Apply shared LDAP connection options to a command."""
    for option in reversed(_ldap_connection_options):
        func = option(func)
    return func


def _build_config_and_generate(
    *,
    config_file, users, groups, members_per_group, base_dn, email_domain,
    default_password, password_scheme, seed, abac_inline, abac_profile,
    no_defaults=False,
) -> tuple[Config, list[GeneratedUser], list[GeneratedGroup]]:
    """Build config and run generation (shared by generate-ldif and populate)."""
    cfg = build_config(
        config_file=config_file,
        users=users,
        groups=groups,
        members_per_group=members_per_group,
        base_dn=base_dn,
        email_domain=email_domain,
        default_password=default_password,
        password_scheme=password_scheme,
        seed=seed,
        abac_inline=abac_inline,
        abac_profile=abac_profile,
        no_defaults=no_defaults,
    )

    click.echo(f"Generating {cfg.users} users and {cfg.groups} groups...")
    generated_users = generate_users(cfg)
    generated_groups = generate_groups(cfg, generated_users)
    click.echo(f"Generated {len(generated_users)} users and {len(generated_groups)} groups")

    return cfg, generated_users, generated_groups


@cli.command("generate-ldif")
@_add_common_options
@click.option(
    "-o",
    "--output",
    "output_dir",
    type=click.Path(),
    default="./embiggenator-data",
    show_default=True,
    help="Output directory for LDIF files",
)
@click.option("--no-defaults", is_flag=True, default=False, help="Skip bundled default LDIF files")
def generate_ldif_cmd(
    output_dir, no_defaults, config_file, users, groups, members_per_group,
    base_dn, email_domain, default_password, password_scheme, seed,
    abac_inline, abac_profile,
) -> None:
    """Generate LDIF files to mount into the OpenLDAP container."""
    cfg, generated_users, generated_groups = _build_config_and_generate(
        config_file=config_file, users=users, groups=groups,
        members_per_group=members_per_group, base_dn=base_dn, email_domain=email_domain,
        default_password=default_password, password_scheme=password_scheme,
        seed=seed, abac_inline=abac_inline, abac_profile=abac_profile,
        no_defaults=no_defaults,
    )

    write_ldif_files(generated_users, generated_groups, output_dir, cfg.include_defaults)
    click.echo(f"LDIF files written to {output_dir}/")
    if cfg.include_defaults:
        click.echo("Includes bundled default LDIF files (use --no-defaults to skip)")


@cli.command("populate")
@_add_common_options
@_add_ldap_options
@click.option("--mattermost-url", type=str, default=None, help="Mattermost server URL to log users in and activate accounts")
@click.option("--nologin", is_flag=True, default=False, help="Skip Mattermost login (only populate LDAP)")
def populate_cmd(
    host, port, bind_dn, bind_password, use_ssl,
    mattermost_url, nologin,
    config_file, users, groups, members_per_group, base_dn, email_domain,
    default_password, password_scheme, seed, abac_inline, abac_profile,
) -> None:
    """Populate a running LDAP server with generated entries."""
    from embiggenator.output.ldap_writer import login_mattermost_users, populate_ldap

    cfg, generated_users, generated_groups = _build_config_and_generate(
        config_file=config_file, users=users, groups=groups,
        members_per_group=members_per_group, base_dn=base_dn, email_domain=email_domain,
        default_password=default_password, password_scheme=password_scheme,
        seed=seed, abac_inline=abac_inline, abac_profile=abac_profile,
    )

    populate_ldap(
        generated_users,
        generated_groups,
        host=host,
        port=port,
        bind_dn=bind_dn or f"cn=admin,{cfg.base_dn}",
        bind_password=bind_password or "GoodNewsEveryone",
        use_ssl=use_ssl,
    )

    if mattermost_url and not nologin:
        click.echo(f"Logging users into Mattermost at {mattermost_url}...")
        login_mattermost_users(generated_users, mattermost_url, cfg.default_password)


@cli.command("reset")
@_add_ldap_options
@click.option("--base-dn", type=str, default="dc=planetexpress,dc=com", show_default=True, help="Base DN")
@click.option("--no-restore", is_flag=True, default=False, help="Don't restore built-in default entries after clearing")
@click.option("--mattermost-url", type=str, default=None, help="Mattermost URL — also delete all non-admin users from Mattermost")
@click.option("--pat", type=str, default=None, help="Mattermost Personal Access Token (required with --mattermost-url)")
@click.option("--skip-verify-ssl", is_flag=True, default=False, help="Skip TLS certificate verification (for self-signed certs)")
@click.confirmation_option(prompt="This will delete ALL entries under ou=people. Continue?")
def reset_cmd(host, port, bind_dn, bind_password, use_ssl, base_dn, no_restore, mattermost_url, pat, skip_verify_ssl) -> None:
    """Delete all entries and optionally restore built-in defaults.

    If --mattermost-url and --pat are provided, also permanently deletes all
    non-bot, non-admin users from Mattermost. Requires
    ServiceSettings.EnableAPIUserDeletion=true on the server.
    """
    from embiggenator.output.ldap_writer import reset_ldap

    # Validate Mattermost options BEFORE touching LDAP so a bad PAT or missing
    # server config doesn't leave LDAP wiped with Mattermost untouched.
    client = None
    if mattermost_url and not pat:
        raise click.ClickException("--pat is required when using --mattermost-url with reset")

    if mattermost_url and pat:
        import urllib.error

        from embiggenator.output.mattermost_client import MattermostAPIError, MattermostClient

        client = MattermostClient(mattermost_url, pat, verify_ssl=not skip_verify_ssl)
        _validate_pat(client)

        # Preflight: check that API user/team deletion is enabled
        try:
            config = client.get_config()
            service_settings = config.get("ServiceSettings", {})
            api_user_deletion = service_settings.get("EnableAPIUserDeletion", False)
            api_team_deletion = service_settings.get("EnableAPITeamDeletion", False)
            missing = []
            if not api_user_deletion:
                missing.append("EnableAPIUserDeletion")
            if not api_team_deletion:
                missing.append("EnableAPITeamDeletion")
            if missing:
                raise click.ClickException(
                    f"ServiceSettings.{' and '.join(missing)} must be enabled on the Mattermost server. "
                    "Enable in the System Console or config.json before using --mattermost-url with reset."
                )
        except MattermostAPIError as e:
            if e.status == 403:
                click.echo("  Warning: cannot read server config (403 Forbidden). "
                           "Ensure ServiceSettings.EnableAPIUserDeletion=true and "
                           "EnableAPITeamDeletion=true or deletion will fail.")
            else:
                raise
        except urllib.error.URLError as e:
            raise click.ClickException(f"Cannot reach Mattermost at {mattermost_url}: {e.reason}") from None

    reset_ldap(
        base_dn=base_dn,
        host=host,
        port=port,
        bind_dn=bind_dn or f"cn=admin,{base_dn}",
        bind_password=bind_password or "GoodNewsEveryone",
        use_ssl=use_ssl,
        restore_defaults=not no_restore,
    )

    if client is not None:
        import urllib.error

        from embiggenator.output.mattermost_client import MattermostAPIError

        click.echo(f"\nDeleting Mattermost users at {mattermost_url}...")

        try:
            all_users = client.get_all_users()
        except urllib.error.URLError as e:
            raise click.ClickException(f"Cannot reach Mattermost at {mattermost_url}: {e.reason}") from None

        deleted = 0
        skipped = 0
        errors = 0
        for user in all_users:
            if user.get("is_bot"):
                skipped += 1
                continue
            roles = user.get("roles", "")
            if "system_admin" in roles.split():
                skipped += 1
                continue
            try:
                client.delete_user(user["id"], permanent=True)
                deleted += 1
                if deleted % 25 == 0:
                    click.echo(f"  Deleted {deleted} users...")
            except MattermostAPIError as e:
                errors += 1
                if errors <= 3:
                    click.echo(f"  Warning: failed to delete user '{user.get('username', user['id'])}': {e}")
                elif errors == 4:
                    click.echo("  (suppressing further deletion errors)")

        click.echo(f"Mattermost: {deleted} users deleted, {skipped} skipped (bots/admins), {errors} errors")

        # Delete all teams (cascades to channels)
        click.echo("Deleting Mattermost teams...")
        all_teams = client.get_all_teams()
        teams_deleted = 0
        teams_errors = 0
        for team in all_teams:
            try:
                client.delete_team(team["id"], permanent=True)
                teams_deleted += 1
                if teams_deleted % 25 == 0:
                    click.echo(f"  Deleted {teams_deleted} teams...")
            except MattermostAPIError as e:
                teams_errors += 1
                if teams_errors <= 3:
                    click.echo(f"  Warning: failed to delete team '{team.get('display_name', team['id'])}': {e}")
                elif teams_errors == 4:
                    click.echo("  (suppressing further team deletion errors)")

        click.echo(f"Mattermost: {teams_deleted} teams deleted, {teams_errors} errors")

        # Create a default team so the server isn't left in a broken state
        try:
            team_id = client.get_or_create_team("default", "Default")
            me = client.get_me()
            client.add_user_to_team(team_id, me["id"])
            click.echo("Created default team 'Default' with Town Square and Off-Topic channels")
        except MattermostAPIError as e:
            click.echo(f"  Warning: failed to create default team: {e}")


@cli.command("disable-user")
@_add_ldap_options
@click.option("--base-dn", type=str, default="dc=planetexpress,dc=com", show_default=True, help="Base DN")
@click.argument("usernames", nargs=-1, required=True)
def disable_user_cmd(host, port, bind_dn, bind_password, use_ssl, base_dn, usernames) -> None:
    """Disable one or more LDAP users by setting description=DISABLED.

    Configure Mattermost with LdapSettings.UserFilter=(!(description=DISABLED))
    to exclude disabled users during sync.
    """
    from embiggenator.output.ldap_writer import disable_ldap_user

    failures = 0
    for username in usernames:
        try:
            disable_ldap_user(
                username,
                base_dn=base_dn,
                host=host,
                port=port,
                bind_dn=bind_dn or f"cn=admin,{base_dn}",
                bind_password=bind_password or "GoodNewsEveryone",
                use_ssl=use_ssl,
            )
        except click.ClickException as e:
            click.echo(f"Error: {e.message}", err=True)
            failures += 1
    if failures:
        raise SystemExit(1)


@cli.command("update-user")
@_add_ldap_options
@click.option("--base-dn", type=str, default="dc=planetexpress,dc=com", show_default=True, help="Base DN")
@click.argument("username")
@click.option("--set", "attrs", multiple=True, required=True, help="Attribute to set (ATTR=VALUE)")
def update_user_cmd(host, port, bind_dn, bind_password, use_ssl, base_dn, username, attrs) -> None:
    """Modify LDAP attributes for a user.

    Use --set ATTR=VALUE to change attributes. If cn is changed, the entry DN
    is renamed. Multiple --set flags can be provided.

    Examples:

        embiggenator update-user jdoe --set sn=NewLastName

        embiggenator update-user jdoe --set mail=new@example.com --set sn=Smith
    """
    from embiggenator.output.ldap_writer import update_ldap_user

    changes: dict[str, str] = {}
    for attr_spec in attrs:
        name, sep, value = attr_spec.partition("=")
        if not sep or not name:
            raise click.ClickException(f"Invalid --set format: '{attr_spec}' (expected ATTR=VALUE)")
        changes[name] = value

    update_ldap_user(
        username,
        changes,
        base_dn=base_dn,
        host=host,
        port=port,
        bind_dn=bind_dn or f"cn=admin,{base_dn}",
        bind_password=bind_password or "GoodNewsEveryone",
        use_ssl=use_ssl,
    )


@cli.command("content")
@click.option("-c", "--config", "config_file", type=click.Path(exists=True), default=None, help="YAML config file")
@click.option("--pat", type=str, default=None, help="Mattermost Personal Access Token (overrides config/env)")
@click.option("--mattermost-url", type=str, default=None, help="Mattermost server URL (overrides config)")
@click.option("--seed", type=int, default=None, help="Random seed for reproducible output")
@click.option("-y", "--yes", "auto_yes", is_flag=True, default=False, help="Auto-confirm prompts (e.g. config changes)")
@click.option("--skip-verify-ssl", is_flag=True, default=False, help="Skip TLS certificate verification (for self-signed certs)")
def content_cmd(config_file, pat, mattermost_url, seed, auto_yes, skip_verify_ssl) -> None:
    """Generate Mattermost content (teams, channels, posts, threads, reactions, DMs).

    Requires a running Mattermost server with LDAP users already logged in.
    Uses the PAT (Personal Access Token) for API authentication.

    Note: All API actions are performed using the admin PAT, so Mattermost will
    attribute posts/reactions to the PAT owner. For realistic per-user authorship,
    use 'run-all' which captures individual session tokens during login.
    """
    from embiggenator.generators.content import PassageBank
    from embiggenator.generators.mattermost import generate_mattermost_content, preflight_check_max_users_per_team
    from embiggenator.output.mattermost_client import MattermostClient

    cfg = build_config(config_file=config_file, pat=pat, seed=seed)

    if mattermost_url:
        cfg.mattermost.url = mattermost_url

    if not cfg.mattermost.pat:
        raise click.ClickException(
            "Mattermost PAT is required. Set it via --pat, config YAML (mattermost.pat), "
            "or the MM_PAT environment variable."
        )

    if not cfg.content.teams and cfg.content.direct_messages_min == 0:
        raise click.ClickException("No content to generate. Define teams or DMs in your config.")

    click.echo(f"Connecting to Mattermost at {cfg.mattermost.url}...")
    client = MattermostClient(cfg.mattermost.url, cfg.mattermost.pat, verify_ssl=not skip_verify_ssl)
    _validate_pat(client)

    # Build user map by fetching all users from Mattermost
    click.echo("Fetching users from Mattermost...")
    user_map = _build_user_map_from_pat(client)
    click.echo(f"Found {len(user_map)} users on Mattermost")

    if not user_map:
        raise click.ClickException(
            "No users found on Mattermost. Run 'populate' with --mattermost-url first."
        )

    if cfg.content.teams:
        preflight_check_max_users_per_team(client, len(user_map), auto_yes=auto_yes)

    click.echo("Generating content...")
    bank = PassageBank()
    result = generate_mattermost_content(
        client, cfg.content, user_map, seed=cfg.seed, passage_bank=bank,
    )

    click.echo("Content generation complete:")
    click.echo(f"  Teams: {result.teams_created}")
    click.echo(f"  Channels: {result.channels_created}")
    click.echo(f"  Posts: {result.posts_created}")
    click.echo(f"  Attachments: {result.attachments_uploaded}")
    click.echo(f"  Replies: {result.replies_created}")
    click.echo(f"  Reactions: {result.reactions_added}")
    click.echo(f"  DM conversations: {result.dm_conversations} ({result.dm_messages} messages)")


@cli.command("run-all")
@_add_common_options
@_add_ldap_options
@click.option("--mattermost-url", type=str, default=None, help="Mattermost server URL (overrides config)")
@click.option("--pat", type=str, default=None, help="Mattermost Personal Access Token (overrides config/env)")
@click.option("-y", "--yes", "auto_yes", is_flag=True, default=False, help="Auto-confirm prompts (e.g. config changes)")
@click.option("--skip-verify-ssl", is_flag=True, default=False, help="Skip TLS certificate verification (for self-signed certs)")
def run_all_cmd(
    host, port, bind_dn, bind_password, use_ssl,
    mattermost_url, pat, auto_yes, skip_verify_ssl,
    config_file, users, groups, members_per_group, base_dn, email_domain,
    default_password, password_scheme, seed, abac_inline, abac_profile,
) -> None:
    """Run everything: populate LDAP, login users, generate Mattermost content.

    This is the all-in-one command for setting up a complete test environment.
    """
    from embiggenator.generators.content import PassageBank
    from embiggenator.generators.mattermost import generate_mattermost_content, preflight_check_max_users_per_team
    from embiggenator.output.ldap_writer import login_mattermost_users, populate_ldap
    from embiggenator.output.mattermost_client import MattermostClient

    cfg, generated_users, generated_groups = _build_config_and_generate(
        config_file=config_file, users=users, groups=groups,
        members_per_group=members_per_group, base_dn=base_dn, email_domain=email_domain,
        default_password=default_password, password_scheme=password_scheme,
        seed=seed, abac_inline=abac_inline, abac_profile=abac_profile,
    )

    if pat:
        cfg.mattermost.pat = pat
    if mattermost_url:
        cfg.mattermost.url = mattermost_url

    # Step 1: Populate LDAP
    click.echo("\n=== Step 1: Populate LDAP ===")
    populate_ldap(
        generated_users,
        generated_groups,
        host=host,
        port=port,
        bind_dn=bind_dn or f"cn=admin,{cfg.base_dn}",
        bind_password=bind_password or "GoodNewsEveryone",
        use_ssl=use_ssl,
    )

    # Step 2: Login users to Mattermost
    mm_url = cfg.mattermost.url
    click.echo(f"\n=== Step 2: Login users to Mattermost at {mm_url} ===")
    user_map = login_mattermost_users(generated_users, mm_url, cfg.default_password)

    if not user_map:
        click.echo("Warning: no users were logged in. Skipping content generation.")
        return

    # Step 3: Generate content
    if not cfg.mattermost.pat:
        click.echo("Warning: no PAT configured. Skipping content generation.")
        click.echo("Set PAT via --pat, config YAML, or MM_PAT env var to enable content generation.")
        return

    click.echo("\n=== Step 3: Generate Mattermost content ===")
    client = MattermostClient(mm_url, cfg.mattermost.pat, verify_ssl=not skip_verify_ssl)
    _validate_pat(client)

    if cfg.content.teams:
        preflight_check_max_users_per_team(client, len(user_map), auto_yes=auto_yes)

    bank = PassageBank()
    result = generate_mattermost_content(
        client, cfg.content, user_map, seed=cfg.seed, passage_bank=bank,
    )

    click.echo("\nAll done! Summary:")
    click.echo(f"  Teams: {result.teams_created}")
    click.echo(f"  Channels: {result.channels_created}")
    click.echo(f"  Posts: {result.posts_created}")
    click.echo(f"  Attachments: {result.attachments_uploaded}")
    click.echo(f"  Replies: {result.replies_created}")
    click.echo(f"  Reactions: {result.reactions_added}")
    click.echo(f"  DM conversations: {result.dm_conversations} ({result.dm_messages} messages)")


def _validate_pat(client: MattermostClient) -> None:
    """Verify the PAT is valid by calling /users/me. Raises ClickException on 401."""
    import urllib.error

    from embiggenator.output.mattermost_client import MattermostAPIError

    try:
        client.get_me()
    except MattermostAPIError as e:
        if e.status == 401:
            raise click.ClickException(
                "Invalid or expired PAT. Check your token and try again."
            ) from None
        raise
    except urllib.error.URLError as e:
        raise click.ClickException(
            f"Cannot reach Mattermost at {client.base_url}: {e.reason}"
        ) from None


def _build_user_map_from_pat(
    client: MattermostClient,
) -> dict[str, tuple[str, str]]:
    """Build a user map by fetching all users from Mattermost via the PAT.

    Fetches users in batch via the paginated API. Excludes bot accounts and
    deactivated users. Each entry maps username -> (mm_user_id, pat_token)
    where pat_token is the admin PAT (used for all operations).
    """
    user_map: dict[str, tuple[str, str]] = {}
    for mm_user in client.get_all_users():
        # Skip bots and deactivated users
        if mm_user.get("is_bot") or mm_user.get("delete_at", 0) > 0:
            continue
        username = mm_user.get("username", "")
        if username:
            user_map[username] = (mm_user["id"], client.token)
    return user_map


@cli.command("show-config")
@click.option("-c", "--config", "config_file", type=click.Path(exists=True), default=None, help="YAML config file")
def show_config_cmd(config_file) -> None:
    """Show the resolved configuration."""
    cfg = build_config(config_file=config_file)
    click.echo("Resolved configuration:")
    click.echo(f"  users:            {cfg.users}")
    click.echo(f"  groups:           {cfg.groups}")
    click.echo(f"  members_per_group: {cfg.members_min}-{cfg.members_max}")
    click.echo(f"  base_dn:          {cfg.base_dn}")
    click.echo(f"  people_ou:        {cfg.people_ou}")
    click.echo(f"  group_ou:         {cfg.group_ou}")
    click.echo(f"  email_domain:     {cfg.email_domain}")
    click.echo(f"  default_password: {cfg.default_password}")
    click.echo(f"  password_scheme:  {cfg.password_scheme}")
    click.echo(f"  seed:             {cfg.seed}")
    click.echo(f"  include_defaults: {cfg.include_defaults}")
    if cfg.abac_attributes:
        click.echo("  abac_attributes:")
        for attr in cfg.abac_attributes:
            weights = f" (weights: {attr.weights})" if attr.weights else ""
            click.echo(f"    - {attr.name}: {attr.values}{weights}")
    # Mattermost section
    click.echo("  mattermost:")
    click.echo(f"    url:            {cfg.mattermost.url}")
    click.echo(f"    pat:            {'***' if cfg.mattermost.pat else '(not set)'}")
    # Content section
    click.echo("  content:")
    if cfg.content.channels_min is not None:
        click.echo(f"    channels: {cfg.content.channels_min}-{cfg.content.channels_max} (distributed across teams)")
    else:
        click.echo(f"    channels_per_team: {cfg.content.channels_per_team_min}-{cfg.content.channels_per_team_max}")
    click.echo(f"    private_channel_probability: {cfg.content.private_channel_probability}")
    click.echo(f"    members_per_channel: {cfg.content.members_per_channel_min}-{cfg.content.members_per_channel_max}")
    click.echo(f"    posts_per_channel: {cfg.content.posts_per_channel_min}-{cfg.content.posts_per_channel_max}")
    click.echo(f"    reply_probability: {cfg.content.reply_probability}")
    click.echo(f"    replies_per_thread: {cfg.content.replies_per_thread_min}-{cfg.content.replies_per_thread_max}")
    click.echo(f"    reaction_probability: {cfg.content.reaction_probability}")
    click.echo(f"    reactions_per_post: {cfg.content.reactions_per_post_min}-{cfg.content.reactions_per_post_max}")
    click.echo(f"    attachment_probability: {cfg.content.attachment_probability}")
    click.echo(f"    attachment_size: {cfg.content.attachment_size_min}-{cfg.content.attachment_size_max}")
    click.echo(f"    direct_messages: {cfg.content.direct_messages_min}-{cfg.content.direct_messages_max}")
    click.echo(f"    dms_per_conversation: {cfg.content.dms_per_conversation_min}-{cfg.content.dms_per_conversation_max}")
    if cfg.content.teams:
        click.echo("    teams:")
        for team in cfg.content.teams:
            override = ""
            if team.channels_per_team_min is not None:
                override = f", channels_per_team: {team.channels_per_team_min}-{team.channels_per_team_max}"
            explicit = f", {len(team.channels)} explicit" if team.channels else ""
            click.echo(f"      - {team.display_name} ({team.name}{override}{explicit})")
    else:
        click.echo("    teams: (none configured)")
