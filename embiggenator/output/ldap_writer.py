"""Live LDAP writer via ldap3 — populates a running LDAP server directly."""

from __future__ import annotations

import base64
import json
import urllib.request
import urllib.error
from pathlib import Path

import click
from ldap3 import ALL, SUBTREE, Connection, Server
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
            attrs = _attrs_to_dict(group.to_ldif_attrs(live=True))
            try:
                conn.add(group.dn, attributes=attrs)
                added_groups += 1
            except LDAPEntryAlreadyExistsResult:
                skipped_groups += 1

        click.echo(f"Groups: {added_groups} added, {skipped_groups} skipped (already exist)")

    finally:
        conn.unbind()


def login_mattermost_users(
    users: list[GeneratedUser],
    mattermost_url: str,
    password: str,
) -> None:
    """Log in each user to Mattermost via the API to trigger account creation."""
    url = mattermost_url.rstrip("/") + "/api/v4/users/login"

    logged_in = 0
    already_existed = 0
    failed = 0

    for user in users:
        payload = json.dumps({"login_id": user.uid, "password": password}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status == 200:
                    logged_in += 1
        except urllib.error.HTTPError as e:
            if e.code == 200:
                logged_in += 1
            else:
                failed += 1
                if failed <= 3:
                    body = e.read().decode("utf-8", errors="replace")
                    click.echo(f"  Login failed for {user.uid}: HTTP {e.code} — {body}")
                elif failed == 4:
                    click.echo("  (suppressing further login errors)")
        except urllib.error.URLError as e:
            failed += 1
            if failed == 1:
                click.echo(f"  Cannot reach Mattermost at {mattermost_url}: {e.reason}")
                click.echo("  Skipping remaining logins")
                break

    click.echo(f"Mattermost logins: {logged_in} activated, {failed} failed")


def reset_ldap(
    base_dn: str = "dc=planetexpress,dc=com",
    people_ou: str = "people",
    host: str = "localhost",
    port: int = 10389,
    bind_dn: str = "cn=admin,dc=planetexpress,dc=com",
    bind_password: str = "GoodNewsEveryone",
    use_ssl: bool = False,
    restore_defaults: bool = True,
) -> None:
    """Delete all entries under the people OU, then optionally restore built-in defaults."""
    server = Server(host, port=port, use_ssl=use_ssl, get_info=ALL)
    conn = Connection(server, user=bind_dn, password=bind_password, auto_bind=True)

    people_dn = f"ou={people_ou},{base_dn}"

    try:
        # Search for all entries under the people OU
        conn.search(people_dn, "(objectClass=*)", search_scope=SUBTREE)
        entries = [entry.entry_dn for entry in conn.entries]

        # Delete children first (deepest DNs first — sort by comma count descending)
        entries_to_delete = [dn for dn in entries if dn != people_dn]
        entries_to_delete.sort(key=lambda dn: dn.count(","), reverse=True)

        deleted = 0
        for dn in entries_to_delete:
            conn.delete(dn)
            if conn.result["result"] == 0:
                deleted += 1

        click.echo(f"Deleted {deleted} entries from {people_dn}")

        # Restore built-in defaults
        if restore_defaults:
            defaults_dir = Path(__file__).parent.parent / "data" / "defaults"
            if not defaults_dir.is_dir():
                click.echo("Warning: bundled defaults directory not found, skipping restore")
                return

            restored = 0
            for ldif_file in sorted(defaults_dir.glob("*.ldif")):
                for entry_dn, attrs in _parse_ldif_file(ldif_file):
                    # Convert AD-style Group objectClass to groupOfNames
                    # for live LDAP (bootstrap LDIF skips schema validation,
                    # but ldap3 add does not)
                    attrs = _fixup_group_objectclass(attrs)
                    try:
                        conn.add(entry_dn, attributes=attrs)
                        if conn.result["result"] == 0:
                            restored += 1
                    except LDAPEntryAlreadyExistsResult:
                        pass

            click.echo(f"Restored {restored} built-in entries")

    finally:
        conn.unbind()


def _parse_ldif_file(path: Path) -> list[tuple[str, dict[str, list[str | bytes]]]]:
    """Parse a simple LDIF file into (dn, attributes) tuples."""
    entries: list[tuple[str, dict[str, list[str | bytes]]]] = []
    current_dn: str | None = None
    current_attrs: dict[str, list[str | bytes]] = {}

    lines = path.read_text(encoding="utf-8").splitlines()

    # Unfold continuation lines (lines starting with a single space)
    unfolded: list[str] = []
    for line in lines:
        if line.startswith(" ") and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    for line in unfolded:
        line = line.strip()
        if not line or line.startswith("#"):
            # Blank line = end of entry
            if current_dn is not None:
                entries.append((current_dn, current_attrs))
                current_dn = None
                current_attrs = {}
            continue

        if ":: " in line:
            # Base64-encoded value
            attr_name, _, b64_value = line.partition(":: ")
            value = base64.b64decode(b64_value)
            if attr_name.lower() == "dn":
                current_dn = value.decode("utf-8")
            else:
                current_attrs.setdefault(attr_name, []).append(value)
        elif ": " in line:
            attr_name, _, value = line.partition(": ")
            if attr_name.lower() == "dn":
                current_dn = value
            else:
                current_attrs.setdefault(attr_name, []).append(value)

    # Don't forget the last entry if file doesn't end with a blank line
    if current_dn is not None:
        entries.append((current_dn, current_attrs))

    return entries


def _fixup_group_objectclass(attrs: dict[str, list]) -> dict[str, list]:
    """Convert AD-style Group objectClass to groupOfNames for live LDAP."""
    oc_key = None
    for key in attrs:
        if key.lower() == "objectclass":
            oc_key = key
            break

    if oc_key is None:
        return attrs

    oc_values = [v if isinstance(v, str) else v.decode("utf-8") for v in attrs[oc_key]]
    oc_lower = [v.lower() for v in oc_values]

    if "group" in oc_lower:
        attrs[oc_key] = ["groupOfNames"]
        # Remove groupType since it's AD-specific and not in the groupOfNames schema
        attrs.pop("groupType", None)

    return attrs


def _attrs_to_dict(attr_tuples: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Convert attribute tuples to a dict suitable for ldap3, skipping 'dn'."""
    result: dict[str, list[str]] = {}
    for name, value in attr_tuples:
        if name == "dn":
            continue
        result.setdefault(name, []).append(value)
    return result
