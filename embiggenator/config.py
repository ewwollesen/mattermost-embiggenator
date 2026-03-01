"""Configuration dataclass with YAML loading and CLI/file/default merging."""

from __future__ import annotations

import os
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
        if self.weights and len(self.weights) != len(self.values):
            raise ValueError(
                f"ABAC attribute '{self.name}': "
                f"weights length ({len(self.weights)}) != values length ({len(self.values)})"
            )


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

    @property
    def people_dn(self) -> str:
        return f"ou={self.people_ou},{self.base_dn}"

    @property
    def group_dn(self) -> str:
        return f"ou={self.group_ou},{self.base_dn}"


def parse_members_range(value: str) -> tuple[int, int]:
    """Parse a members-per-group value like '10' or '5-20'."""
    if "-" in str(value):
        parts = str(value).split("-", 1)
        lo, hi = int(parts[0]), int(parts[1])
        if lo > hi:
            raise ValueError(f"Invalid range: {lo} > {hi}")
        return lo, hi
    n = int(value)
    return n, n


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
        cfg.abac_attributes.extend(load_abac_from_yaml(yaml_data))

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
