"""Live LDAP writer via ldap3 — populates a running LDAP server directly."""

from __future__ import annotations

import click
from ldap3 import ALL, Connection, Server
from ldap3.core.exceptions import LDAPEntryAlreadyExistsResult

from embiggenator.models import GeneratedGroup, GeneratedUser


def populate_ldap(
    users: list[GeneratedUser],
    groups: list[GeneratedGroup],
    host: str = "localhost",
    port: int = 10389,
    bind_dn: str = "cn=admin,dc=planetexpress,dc=com",
    bind_password: str = "GoodNewsEveryone",
    use_ssl: bool = False,
) -> None:
    """Connect to a running LDAP server and add generated entries."""
    server = Server(host, port=port, use_ssl=use_ssl, get_info=ALL)
    conn = Connection(server, user=bind_dn, password=bind_password, auto_bind=True)

    try:
        # Add users first (groups reference them)
        added_users = 0
        skipped_users = 0
        for user in users:
            attrs = _attrs_to_dict(user.to_ldif_attrs())
            try:
                conn.add(user.dn, attributes=attrs)
                added_users += 1
            except LDAPEntryAlreadyExistsResult:
                skipped_users += 1

        click.echo(f"Users: {added_users} added, {skipped_users} skipped (already exist)")

        # Add groups
        added_groups = 0
        skipped_groups = 0
        for group in groups:
            attrs = _attrs_to_dict(group.to_ldif_attrs())
            try:
                conn.add(group.dn, attributes=attrs)
                added_groups += 1
            except LDAPEntryAlreadyExistsResult:
                skipped_groups += 1

        click.echo(f"Groups: {added_groups} added, {skipped_groups} skipped (already exist)")

    finally:
        conn.unbind()


def _attrs_to_dict(attr_tuples: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Convert attribute tuples to a dict suitable for ldap3, skipping 'dn'."""
    result: dict[str, list[str]] = {}
    for name, value in attr_tuples:
        if name == "dn":
            continue
        result.setdefault(name, []).append(value)
    return result
