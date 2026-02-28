"""Group generation with membership assignment."""

from __future__ import annotations

from faker import Faker

from embiggenator.config import Config
from embiggenator.models import GeneratedGroup, GeneratedUser


def generate_groups(
    config: Config,
    users: list[GeneratedUser],
) -> list[GeneratedGroup]:
    """Generate groups and assign random user memberships."""
    fake = Faker()
    if config.seed is not None:
        Faker.seed(config.seed + 1000)  # Offset to avoid same sequence as users

    groups: list[GeneratedGroup] = []
    seen_cns: set[str] = set()

    for i in range(config.groups):
        # Generate a group name
        group_name = _generate_group_name(fake, seen_cns, i)
        seen_cns.add(group_name.lower())

        # Pick random members
        num_members = fake.random_int(min=config.members_min, max=config.members_max)
        num_members = min(num_members, len(users))

        if num_members > 0:
            members = fake.random_elements(
                elements=users,
                length=num_members,
                unique=True,
            )
            member_dns = [u.dn for u in members]
        else:
            # groupOfNames requires at least one member
            member_dns = [users[0].dn] if users else []

        group = GeneratedGroup(
            cn=group_name,
            description=f"Generated test group: {group_name}",
            member_dns=member_dns,
            base_dn=config.base_dn,
            group_ou=config.group_ou,
        )
        groups.append(group)

    return groups


# Word pools for group name generation
_PREFIXES = [
    "Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Theta", "Sigma",
    "Omega", "Nova", "Quantum", "Stellar", "Nebula", "Cosmic", "Solar",
    "Lunar", "Astro", "Cyber", "Digital", "Matrix",
]

_SUFFIXES = [
    "Team", "Squad", "Division", "Unit", "Corps", "Crew", "Force",
    "Group", "Alliance", "Council", "Guild", "League", "Network", "Hub",
    "Lab", "Ops", "Core", "Edge", "Prime", "Works",
]


def _generate_group_name(fake: Faker, seen: set[str], index: int) -> str:
    """Generate a unique group name."""
    attempts = 0
    while attempts < 100:
        prefix = fake.random_element(_PREFIXES)
        suffix = fake.random_element(_SUFFIXES)
        name = f"{prefix} {suffix}"
        if name.lower() not in seen:
            return name
        attempts += 1

    # Fallback with index
    return f"Group {index + 1}"
