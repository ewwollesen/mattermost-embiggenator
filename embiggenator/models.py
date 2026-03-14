"""Data models for generated LDAP entries."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GeneratedUser:
    """A generated LDAP user entry."""

    uid: str
    cn: str
    sn: str
    given_name: str
    display_name: str
    mail: str
    password_hash: str
    base_dn: str
    people_ou: str = "people"
    employee_number: str | None = None
    extra_attributes: dict[str, str] = field(default_factory=dict)

    @property
    def dn(self) -> str:
        return f"cn={_escape_dn_value(self.cn)},ou={self.people_ou},{self.base_dn}"

    def to_ldif_attrs(self) -> list[tuple[str, str]]:
        """Return attribute tuples for LDIF output."""
        attrs = [
            ("dn", self.dn),
            ("objectClass", "inetOrgPerson"),
            ("uid", self.uid),
            ("cn", self.cn),
            ("sn", self.sn),
            ("givenName", self.given_name),
            ("displayName", self.display_name),
            ("mail", self.mail),
            ("userPassword", self.password_hash),
        ]
        if self.employee_number:
            attrs.append(("employeeNumber", self.employee_number))
        for attr_name, attr_value in sorted(self.extra_attributes.items()):
            attrs.append((attr_name, attr_value))
        return attrs


@dataclass
class GeneratedGroup:
    """A generated LDAP group entry."""

    cn: str
    description: str
    member_dns: list[str]
    base_dn: str
    group_ou: str = "people"

    @property
    def dn(self) -> str:
        return f"cn={_escape_dn_value(self.cn)},ou={self.group_ou},{self.base_dn}"

    def to_ldif_attrs(self, live: bool = False) -> list[tuple[str, str]]:
        """Return attribute tuples for LDIF/LDAP output.

        Args:
            live: If True, use groupOfNames (for ldap3 populate against a running
                  server). If False, use Group (for LDIF bootstrap which skips
                  schema validation).
        """
        if live:
            attrs = [
                ("dn", self.dn),
                ("objectClass", "groupOfNames"),
                ("cn", self.cn),
                ("description", self.description),
            ]
        else:
            attrs = [
                ("dn", self.dn),
                ("objectClass", "Group"),
                ("objectClass", "top"),
                ("groupType", "2147483650"),
                ("cn", self.cn),
                ("description", self.description),
            ]
        for member_dn in self.member_dns:
            attrs.append(("member", member_dn))
        return attrs


def _escape_dn_value(value: str) -> str:
    """Escape special characters in a DN attribute value (RFC 4514)."""
    # Characters that must be escaped in DN values
    result = value.replace("\\", "\\\\")
    # NUL character (RFC 4514)
    result = result.replace("\x00", "\\00")
    result = result.replace(",", "\\,")
    result = result.replace("+", "\\+")
    result = result.replace('"', '\\"')
    result = result.replace("<", "\\<")
    result = result.replace(">", "\\>")
    result = result.replace(";", "\\;")
    if result.startswith(" ") or result.startswith("#"):
        result = "\\" + result
    if result.endswith(" "):
        result = result[:-1] + "\\ "
    return result
