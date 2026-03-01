"""Tests for config loading and merging."""

import tempfile
from pathlib import Path

import pytest
import yaml

from embiggenator.config import (
    DEFAULT_ABAC_ATTRIBUTES,
    AbacAttribute,
    Config,
    build_config,
    parse_abac_inline,
    parse_members_range,
)


class TestParseMembers:
    def test_single_value(self):
        assert parse_members_range("10") == (10, 10)

    def test_range(self):
        assert parse_members_range("5-20") == (5, 20)

    def test_invalid_range(self):
        with pytest.raises(ValueError, match="Invalid range"):
            parse_members_range("20-5")


class TestParseAbacInline:
    def test_single_attr(self):
        attrs = parse_abac_inline("departmentNumber=Eng,Sales,Support")
        assert len(attrs) == 1
        assert attrs[0].name == "departmentNumber"
        assert attrs[0].values == ["Eng", "Sales", "Support"]
        assert attrs[0].weights is None

    def test_multiple_attrs(self):
        attrs = parse_abac_inline("dept=A,B;cat=X,Y,Z")
        assert len(attrs) == 2
        assert attrs[0].name == "dept"
        assert attrs[1].name == "cat"
        assert attrs[1].values == ["X", "Y", "Z"]

    def test_invalid_spec(self):
        with pytest.raises(ValueError, match="Invalid ABAC spec"):
            parse_abac_inline("noequals")


class TestAbacAttribute:
    def test_weight_length_mismatch(self):
        with pytest.raises(ValueError, match="weights length"):
            AbacAttribute(name="test", values=["a", "b"], weights=[1])


class TestConfigDefaults:
    def test_defaults(self):
        cfg = Config()
        assert cfg.users == 100
        assert cfg.groups == 10
        assert cfg.base_dn == "dc=planetexpress,dc=com"
        assert cfg.include_defaults is True

    def test_people_dn(self):
        cfg = Config()
        assert cfg.people_dn == "ou=people,dc=planetexpress,dc=com"


class TestBuildConfig:
    def test_cli_overrides(self):
        cfg = build_config(users=50, groups=5, members_per_group="3-10", seed=42)
        assert cfg.users == 50
        assert cfg.groups == 5
        assert cfg.members_min == 3
        assert cfg.members_max == 10
        assert cfg.seed == 42

    def test_yaml_config(self, tmp_path):
        config_data = {
            "users": 200,
            "groups": 15,
            "email_domain": "test.com",
            "abac": {
                "attributes": [
                    {"name": "dept", "values": ["A", "B"]},
                ]
            },
        }
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file))
        assert cfg.users == 200
        assert cfg.groups == 15
        assert cfg.email_domain == "test.com"
        assert len(cfg.abac_attributes) == 1
        assert cfg.abac_attributes[0].name == "dept"

    def test_cli_overrides_yaml(self, tmp_path):
        config_data = {"users": 200, "groups": 15}
        config_file = tmp_path / "test.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = build_config(config_file=str(config_file), users=50)
        assert cfg.users == 50  # CLI wins
        assert cfg.groups == 15  # YAML value kept

    def test_no_defaults_flag(self):
        cfg = build_config(no_defaults=True)
        assert cfg.include_defaults is False

    def test_abac_inline(self):
        cfg = build_config(abac_inline="dept=A,B;cat=X,Y")
        assert len(cfg.abac_attributes) == 2

    def test_default_abac_attributes(self):
        cfg = build_config()
        assert len(cfg.abac_attributes) == 3
        names = [a.name for a in cfg.abac_attributes]
        assert "businessCategory" in names
        assert "departmentNumber" in names
        assert "employeeType" in names

    def test_custom_abac_replaces_defaults(self):
        cfg = build_config(abac_inline="custom=X,Y")
        assert len(cfg.abac_attributes) == 1
        assert cfg.abac_attributes[0].name == "custom"
