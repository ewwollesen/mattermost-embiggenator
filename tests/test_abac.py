"""Tests for ABAC attribute assignment."""

from __future__ import annotations

from faker import Faker

from embiggenator.config import AbacAttribute
from embiggenator.generators.abac import assign_abac_attributes, _weighted_choice


class TestAssignAbacAttributes:
    def test_uniform_selection(self):
        """Without weights, values are picked uniformly."""
        fake = Faker()
        fake.seed_instance(42)
        attrs = [AbacAttribute(name="dept", values=["Eng", "Sales", "HR"])]
        result = assign_abac_attributes(attrs, fake)
        assert result["dept"] in ["Eng", "Sales", "HR"]

    def test_weighted_selection(self):
        """With weights, values are picked according to weight distribution."""
        fake = Faker()
        fake.seed_instance(42)
        attrs = [
            AbacAttribute(
                name="level",
                values=["IL4", "IL5", "IL6"],
                weights=[50, 35, 15],
            ),
        ]
        result = assign_abac_attributes(attrs, fake)
        assert result["level"] in ["IL4", "IL5", "IL6"]

    def test_multiple_attributes(self):
        """Multiple attributes are all assigned."""
        fake = Faker()
        fake.seed_instance(42)
        attrs = [
            AbacAttribute(name="dept", values=["Eng", "Sales"]),
            AbacAttribute(name="type", values=["FT", "Contractor"]),
            AbacAttribute(name="level", values=["A", "B", "C"], weights=[60, 30, 10]),
        ]
        result = assign_abac_attributes(attrs, fake)
        assert len(result) == 3
        assert "dept" in result
        assert "type" in result
        assert "level" in result

    def test_deterministic_with_seed(self):
        """Same seed produces same assignments."""
        attrs = [
            AbacAttribute(name="dept", values=["Eng", "Sales", "HR"]),
            AbacAttribute(name="level", values=["A", "B"], weights=[80, 20]),
        ]
        fake1 = Faker()
        fake1.seed_instance(99)
        result1 = assign_abac_attributes(attrs, fake1)

        fake2 = Faker()
        fake2.seed_instance(99)
        result2 = assign_abac_attributes(attrs, fake2)

        assert result1 == result2

    def test_single_value(self):
        """Attribute with one value always returns that value."""
        fake = Faker()
        fake.seed_instance(42)
        attrs = [AbacAttribute(name="env", values=["Production"])]
        result = assign_abac_attributes(attrs, fake)
        assert result["env"] == "Production"

    def test_single_value_weighted(self):
        """Attribute with one value and weight always returns that value."""
        fake = Faker()
        fake.seed_instance(42)
        attrs = [AbacAttribute(name="env", values=["Prod"], weights=[100])]
        result = assign_abac_attributes(attrs, fake)
        assert result["env"] == "Prod"


class TestWeightedChoice:
    def test_heavily_weighted_first(self):
        """With extreme weight on first value, it should dominate."""
        fake = Faker()
        fake.seed_instance(42)
        counts = {"A": 0, "B": 0}
        for _ in range(200):
            val = _weighted_choice(["A", "B"], [99, 1], fake)
            counts[val] += 1
        assert counts["A"] > counts["B"]

    def test_all_values_reachable(self):
        """Over many trials, all values should appear at least once."""
        fake = Faker()
        fake.seed_instance(42)
        seen = set()
        for _ in range(500):
            val = _weighted_choice(["X", "Y", "Z"], [10, 10, 10], fake)
            seen.add(val)
        assert seen == {"X", "Y", "Z"}

    def test_single_option(self):
        """Single value always returned."""
        fake = Faker()
        fake.seed_instance(42)
        assert _weighted_choice(["Only"], [1], fake) == "Only"
