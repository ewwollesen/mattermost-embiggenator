"""Live LDAP writer via ldap3 — populates a running LDAP server directly."""

from __future__ import annotations

import base64
import json
import urllib.request
import urllib.error
from pathlib import Path

import click
from ldap3 import ALL, MODIFY_REPLACE, SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPEntryAlreadyExistsResult, LDAPException
from ldap3.utils.conv import escape_filter_chars

from embiggenator.models import GeneratedGroup, GeneratedUser, _escape_dn_value


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
    with Connection(server, user=bind_dn, password=bind_password, auto_bind=True, raise_exceptions=True) as conn:
        # Add users first (groups reference them)
        added_users = 0
        skipped_users = 0
        for user in users:
            attrs = _attrs_to_dict(user.to_ldif_attrs())
            try:
                conn.add(user.dn, attributes=attrs)
                added_users += 1
                if added_users % 25 == 0:
                    click.echo(f"  Added {added_users} users...")
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


def login_mattermost_users(
    users: list[GeneratedUser],
    mattermost_url: str,
    password: str,
) -> dict[str, tuple[str, str]]:
    """Log in each user to Mattermost via the API to trigger account creation.

    Returns a mapping of uid -> (mm_user_id, session_token) for successfully
    logged-in users. The session token can be used to post as that user.
    """
    url = mattermost_url.rstrip("/") + "/api/v4/users/login"

    logged_in = 0
    failed = 0
    user_map: dict[str, tuple[str, str]] = {}

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
                    if logged_in % 25 == 0:
                        click.echo(f"  Logged in {logged_in} users...")
                    token = resp.headers.get("Token", "")
                    body = json.loads(resp.read().decode("utf-8"))
                    mm_user_id = body.get("id", "")
                    if mm_user_id and token:
                        user_map[user.uid] = (mm_user_id, token)
        except urllib.error.HTTPError as e:
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
    return user_map


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
    people_dn = f"ou={people_ou},{base_dn}"

    with Connection(server, user=bind_dn, password=bind_password, auto_bind=True, raise_exceptions=True) as conn:
        # Search for all entries under the people OU
        conn.search(people_dn, "(objectClass=*)", search_scope=SUBTREE)
        entries = [entry.entry_dn for entry in conn.entries]

        # Delete children first (deepest DNs first — sort by comma count descending)
        entries_to_delete = [dn for dn in entries if dn != people_dn]
        entries_to_delete.sort(key=lambda dn: dn.count(","), reverse=True)

        deleted = 0
        for dn in entries_to_delete:
            try:
                conn.delete(dn)
                deleted += 1
            except LDAPException:
                pass

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
        if line.startswith("#"):
            continue  # Skip comments without affecting entry boundaries
        if not line:
            # Blank line = end of entry
            if current_dn is not None:
                entries.append((current_dn, current_attrs))
                current_dn = None
                current_attrs = {}
            continue

        colon_idx = line.find(":")
        if colon_idx < 1:
            continue  # Malformed line
        if line[colon_idx:colon_idx + 3] == ":: ":
            # Base64-encoded value
            attr_name = line[:colon_idx]
            b64_value = line[colon_idx + 3:]
            value = base64.b64decode(b64_value)
            if attr_name.lower() == "dn":
                current_dn = value.decode("utf-8")
            else:
                current_attrs.setdefault(attr_name, []).append(value)
        elif line[colon_idx:colon_idx + 2] == ": ":
            attr_name = line[:colon_idx]
            value = line[colon_idx + 2:]
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


def _find_user_by_uid(conn: Connection, people_dn: str, uid: str) -> str | None:
    """Search LDAP for a user by uid. Returns the entry DN or None."""
    safe_uid = escape_filter_chars(uid)
    conn.search(people_dn, f"(uid={safe_uid})", search_scope=SUBTREE)
    if conn.entries:
        return conn.entries[0].entry_dn
    return None


def disable_ldap_user(
    username: str,
    base_dn: str = "dc=planetexpress,dc=com",
    people_ou: str = "people",
    host: str = "localhost",
    port: int = 10389,
    bind_dn: str = "cn=admin,dc=planetexpress,dc=com",
    bind_password: str = "GoodNewsEveryone",
    use_ssl: bool = False,
) -> None:
    """Mark a user as disabled by setting description=DISABLED."""
    server = Server(host, port=port, use_ssl=use_ssl, get_info=ALL)
    people_dn = f"ou={people_ou},{base_dn}"

    # raise_exceptions=True ensures conn.modify raises on failure
    with Connection(server, user=bind_dn, password=bind_password, auto_bind=True, raise_exceptions=True) as conn:
        dn = _find_user_by_uid(conn, people_dn, username)
        if dn is None:
            raise click.ClickException(f"User '{username}' not found in LDAP under {people_dn}")

        conn.modify(dn, {"description": [(MODIFY_REPLACE, ["DISABLED"])]})
        click.echo(f"Disabled user '{username}' (set description=DISABLED on {dn})")


def update_ldap_user(
    username: str,
    changes: dict[str, str],
    base_dn: str = "dc=planetexpress,dc=com",
    people_ou: str = "people",
    host: str = "localhost",
    port: int = 10389,
    bind_dn: str = "cn=admin,dc=planetexpress,dc=com",
    bind_password: str = "GoodNewsEveryone",
    use_ssl: bool = False,
) -> None:
    """Modify LDAP attributes for a user. If 'cn' is changed, the DN is renamed."""
    server = Server(host, port=port, use_ssl=use_ssl, get_info=ALL)
    people_dn = f"ou={people_ou},{base_dn}"

    # raise_exceptions=True ensures conn.modify/modify_dn raise on failure
    with Connection(server, user=bind_dn, password=bind_password, auto_bind=True, raise_exceptions=True) as conn:
        dn = _find_user_by_uid(conn, people_dn, username)
        if dn is None:
            raise click.ClickException(f"User '{username}' not found in LDAP under {people_dn}")

        # Separate cn from other attributes — cn requires a DN rename
        new_cn = changes.get("cn")
        non_cn_changes = {attr: [(MODIFY_REPLACE, [val])] for attr, val in changes.items() if attr != "cn"}

        # Apply non-cn attribute changes first (on the current DN)
        if non_cn_changes:
            conn.modify(dn, non_cn_changes)
            click.echo(f"Updated attributes on '{username}': {', '.join(non_cn_changes)}")

        # Rename DN if cn changed
        if new_cn is not None:
            escaped_cn = _escape_dn_value(new_cn)
            conn.modify_dn(dn, f"cn={escaped_cn}")
            click.echo(f"Renamed DN for '{username}': cn={new_cn}")
