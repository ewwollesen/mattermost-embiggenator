"""Click CLI commands: generate-ldif, populate, show-config."""

from __future__ import annotations

import json

import click

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


def _build_config_and_generate(
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
        config_file, users, groups, members_per_group, base_dn, email_domain,
        default_password, password_scheme, seed, abac_inline, abac_profile,
        no_defaults=no_defaults,
    )

    write_ldif_files(generated_users, generated_groups, output_dir, cfg.include_defaults)
    click.echo(f"LDIF files written to {output_dir}/")
    if cfg.include_defaults:
        click.echo("Includes bundled default LDIF files (use --no-defaults to skip)")


@cli.command("populate")
@_add_common_options
@click.option("--host", type=str, default="localhost", show_default=True, help="LDAP server host")
@click.option("--port", type=int, default=10389, show_default=True, help="LDAP server port")
@click.option("--bind-dn", type=str, default=None, help="Bind DN (default: cn=admin,dc=planetexpress,dc=com)")
@click.option("--bind-password", type=str, default=None, help="Bind password (default: GoodNewsEveryone)")
@click.option("--use-ssl", is_flag=True, default=False, help="Use SSL/TLS connection")
def populate_cmd(
    host, port, bind_dn, bind_password, use_ssl,
    config_file, users, groups, members_per_group, base_dn, email_domain,
    default_password, password_scheme, seed, abac_inline, abac_profile,
) -> None:
    """Populate a running LDAP server with generated entries."""
    from embiggenator.output.ldap_writer import populate_ldap

    cfg, generated_users, generated_groups = _build_config_and_generate(
        config_file, users, groups, members_per_group, base_dn, email_domain,
        default_password, password_scheme, seed, abac_inline, abac_profile,
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


@cli.command("reset")
@click.option("--host", type=str, default="localhost", show_default=True, help="LDAP server host")
@click.option("--port", type=int, default=10389, show_default=True, help="LDAP server port")
@click.option("--bind-dn", type=str, default=None, help="Bind DN (default: cn=admin,dc=planetexpress,dc=com)")
@click.option("--bind-password", type=str, default=None, help="Bind password (default: GoodNewsEveryone)")
@click.option("--use-ssl", is_flag=True, default=False, help="Use SSL/TLS connection")
@click.option("--base-dn", type=str, default="dc=planetexpress,dc=com", show_default=True, help="Base DN")
@click.option("--no-restore", is_flag=True, default=False, help="Don't restore built-in default entries after clearing")
@click.confirmation_option(prompt="This will delete ALL entries under ou=people. Continue?")
def reset_cmd(host, port, bind_dn, bind_password, use_ssl, base_dn, no_restore) -> None:
    """Delete all entries and optionally restore built-in defaults."""
    from embiggenator.output.ldap_writer import reset_ldap

    reset_ldap(
        base_dn=base_dn,
        host=host,
        port=port,
        bind_dn=bind_dn or f"cn=admin,{base_dn}",
        bind_password=bind_password or "GoodNewsEveryone",
        use_ssl=use_ssl,
        restore_defaults=not no_restore,
    )


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
