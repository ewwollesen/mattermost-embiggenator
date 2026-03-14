"""Faker-based user generation with uid/cn uniqueness."""

from __future__ import annotations

from faker import Faker

from embiggenator.config import Config
from embiggenator.generators.abac import assign_abac_attributes
from embiggenator.models import GeneratedUser
from embiggenator.utils import hash_password


def generate_users(config: Config) -> list[GeneratedUser]:
    """Generate the requested number of unique LDAP users."""
    fake = Faker()
    if config.seed is not None:
        fake.seed_instance(config.seed)

    users: list[GeneratedUser] = []
    seen_uids: set[str] = set()
    seen_cns: set[str] = set()

    attempts = 0
    max_attempts = config.users * 10

    while len(users) < config.users and attempts < max_attempts:
        attempts += 1

        first = fake.first_name()
        last = fake.last_name()

        # Build uid: first initial + last name, lowercase
        uid_base = (first[0] + last).lower()
        uid = _make_unique(uid_base, seen_uids)

        # Build cn: "First Last"
        cn_base = f"{first} {last}"
        cn = _make_unique_cn(cn_base, seen_cns)

        # Derive names from the final cn in case we appended a number
        display_name = cn
        mail = f"{uid}@{config.email_domain}"
        password_hash = hash_password(config.default_password, config.password_scheme)
        employee_number = str(1000 + len(users))

        user = GeneratedUser(
            uid=uid,
            cn=cn,
            sn=last,
            given_name=first,
            display_name=display_name,
            mail=mail,
            password_hash=password_hash,
            base_dn=config.base_dn,
            people_ou=config.people_ou,
            employee_number=employee_number,
        )

        # Assign ABAC attributes
        if config.abac_attributes:
            user.extra_attributes = assign_abac_attributes(config.abac_attributes, fake)

        seen_uids.add(uid)
        seen_cns.add(cn.lower())
        users.append(user)

    if len(users) < config.users:
        raise RuntimeError(
            f"Could only generate {len(users)}/{config.users} unique users "
            f"after {max_attempts} attempts"
        )

    return users


def _make_unique(base: str, seen: set[str]) -> str:
    """Ensure a uid is unique by appending a numeric suffix if needed."""
    # Strip non-alphanumeric chars
    base = "".join(c for c in base if c.isalnum())
    if not base:
        base = "user"
    candidate = base
    counter = 2
    while candidate in seen:
        candidate = f"{base}{counter}"
        counter += 1
    return candidate


def _make_unique_cn(base: str, seen: set[str]) -> str:
    """Ensure a cn is unique (case-insensitive) by appending a suffix."""
    candidate = base
    counter = 2
    while candidate.lower() in seen:
        candidate = f"{base} {counter}"
        counter += 1
    return candidate
