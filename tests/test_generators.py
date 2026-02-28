"""Tests for user and group generators."""

import pytest

from embiggenator.config import AbacAttribute, Config
from embiggenator.generators.groups import generate_groups
from embiggenator.generators.users import generate_users


class TestGenerateUsers:
    def test_generates_correct_count(self):
        cfg = Config(users=10, seed=42)
        users = generate_users(cfg)
        assert len(users) == 10

    def test_unique_uids(self):
        cfg = Config(users=50, seed=42)
        users = generate_users(cfg)
        uids = [u.uid for u in users]
        assert len(uids) == len(set(uids))

    def test_unique_cns(self):
        cfg = Config(users=50, seed=42)
        users = generate_users(cfg)
        cns = [u.cn.lower() for u in users]
        assert len(cns) == len(set(cns))

    def test_dn_format(self):
        cfg = Config(users=1, seed=42)
        users = generate_users(cfg)
        assert users[0].dn.startswith("cn=")
        assert users[0].dn.endswith(",ou=people,dc=planetexpress,dc=com")

    def test_email_domain(self):
        cfg = Config(users=5, seed=42, email_domain="example.com")
        users = generate_users(cfg)
        for u in users:
            assert u.mail.endswith("@example.com")

    def test_reproducible_with_seed(self):
        cfg1 = Config(users=10, seed=99)
        cfg2 = Config(users=10, seed=99)
        users1 = generate_users(cfg1)
        users2 = generate_users(cfg2)
        assert [u.uid for u in users1] == [u.uid for u in users2]

    def test_abac_attributes_assigned(self):
        cfg = Config(
            users=10,
            seed=42,
            abac_attributes=[
                AbacAttribute(name="departmentNumber", values=["Eng", "Sales"]),
            ],
        )
        users = generate_users(cfg)
        for u in users:
            assert "departmentNumber" in u.extra_attributes
            assert u.extra_attributes["departmentNumber"] in ["Eng", "Sales"]


class TestGenerateGroups:
    def test_generates_correct_count(self):
        cfg = Config(users=20, groups=5, seed=42)
        users = generate_users(cfg)
        groups = generate_groups(cfg, users)
        assert len(groups) == 5

    def test_unique_group_cns(self):
        cfg = Config(users=20, groups=10, seed=42)
        users = generate_users(cfg)
        groups = generate_groups(cfg, users)
        cns = [g.cn.lower() for g in groups]
        assert len(cns) == len(set(cns))

    def test_member_count_in_range(self):
        cfg = Config(users=50, groups=5, members_min=3, members_max=10, seed=42)
        users = generate_users(cfg)
        groups = generate_groups(cfg, users)
        for g in groups:
            assert 3 <= len(g.member_dns) <= 10

    def test_members_are_valid_dns(self):
        cfg = Config(users=20, groups=3, seed=42)
        users = generate_users(cfg)
        groups = generate_groups(cfg, users)
        user_dns = {u.dn for u in users}
        for g in groups:
            for member_dn in g.member_dns:
                assert member_dn in user_dns

    def test_group_dn_format(self):
        cfg = Config(users=10, groups=1, seed=42)
        users = generate_users(cfg)
        groups = generate_groups(cfg, users)
        assert groups[0].dn.startswith("cn=")
        assert groups[0].dn.endswith(",ou=people,dc=planetexpress,dc=com")
