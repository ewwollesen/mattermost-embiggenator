"""ABAC attribute generation with uniform and weighted distribution."""

from __future__ import annotations

from faker import Faker

from embiggenator.config import AbacAttribute


def assign_abac_attributes(
    abac_attrs: list[AbacAttribute],
    fake: Faker,
) -> dict[str, str]:
    """Assign ABAC attribute values to a user.

    Uses weighted random selection if weights are provided,
    otherwise uniform random selection.
    """
    result: dict[str, str] = {}
    for attr in abac_attrs:
        if attr.weights is not None:
            # Weighted selection using cumulative weights
            value = _weighted_choice(attr.values, attr.weights, fake)
        else:
            value = fake.random_element(attr.values)
        result[attr.name] = value
    return result


def _weighted_choice(values: list[str], weights: list[int], fake: Faker) -> str:
    """Select a value using weighted probability."""
    total = sum(weights)
    roll = fake.random_int(min=1, max=total)
    cumulative = 0
    for value, weight in zip(values, weights):
        cumulative += weight
        if roll <= cumulative:
            return value
    return values[-1]  # Fallback
