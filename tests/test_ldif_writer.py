"""Tests for LDIF writer output."""

import pytest

from embiggenator.config import Config
from embiggenator.generators.groups import generate_groups
from embiggenator.generators.users import generate_users
from embiggenator.output.ldif_writer import write_ldif_files
from embiggenator.utils import base64_encode_value, hash_password, needs_base64


class TestPasswordHashing:
    def test_ssha(self):
        h = hash_password("test", "{SSHA}")
        assert h.startswith("{SSHA}")

    def test_sha(self):
        h = hash_password("test", "{SHA}")
        assert h.startswith("{SHA}")

    def test_plain(self):
        h = hash_password("test", "{PLAIN}")
        assert h == "test"

    def test_unsupported(self):
        with pytest.raises(ValueError, match="Unsupported"):
            hash_password("test", "{MD5}")


class TestBase64:
    def test_needs_base64_normal(self):
        assert needs_base64("hello") is False

    def test_needs_base64_colon_start(self):
        assert needs_base64(":value") is True

    def test_needs_base64_space_start(self):
        assert needs_base64(" value") is True

    def test_needs_base64_non_ascii(self):
        assert needs_base64("héllo") is True

    def test_encode(self):
        encoded = base64_encode_value("hello")
        assert encoded == "aGVsbG8="


class TestLdifWriter:
    def test_writes_user_and_group_files(self, tmp_path):
        cfg = Config(users=5, groups=2, members_min=2, members_max=3, seed=42)
        users = generate_users(cfg)
        groups = generate_groups(cfg, users)

        write_ldif_files(users, groups, tmp_path, include_defaults=False)

        users_file = tmp_path / "50_a_users.ldif"
        groups_file = tmp_path / "50_b_groups.ldif"

        assert users_file.exists()
        assert groups_file.exists()

        users_content = users_file.read_text()
        groups_content = groups_file.read_text()

        # Should have 5 user entries separated by blank lines
        assert users_content.count("objectClass: inetOrgPerson") == 5
        # Should have 2 group entries
        assert groups_content.count("objectClass: Group") == 2

    def test_copies_defaults(self, tmp_path):
        cfg = Config(users=1, groups=0, seed=42)
        users = generate_users(cfg)

        write_ldif_files(users, [], tmp_path, include_defaults=True)

        # Should have default files
        assert (tmp_path / "00_people.ldif").exists()
        assert (tmp_path / "30_groups_admin.ldif").exists()
        # Plus generated files
        assert (tmp_path / "50_a_users.ldif").exists()

    def test_no_defaults(self, tmp_path):
        cfg = Config(users=1, groups=0, seed=42)
        users = generate_users(cfg)

        write_ldif_files(users, [], tmp_path, include_defaults=False)

        assert not (tmp_path / "00_people.ldif").exists()
        assert (tmp_path / "50_a_users.ldif").exists()

    def test_jpeg_photo_base64_encoded(self, tmp_path):
        cfg = Config(users=1, groups=0, seed=42, avatar_probability=1.0)
        users = generate_users(cfg)
        assert users[0].jpeg_photo is not None

        write_ldif_files(users, [], tmp_path, include_defaults=False)

        content = (tmp_path / "50_a_users.ldif").read_text()
        # jpegPhoto should appear with :: (base64 encoding)
        assert "jpegPhoto:: " in content
        # Should NOT contain raw binary
        assert b"\xff\xd8" not in content.encode("utf-8")

    def test_no_jpeg_photo_when_none(self, tmp_path):
        cfg = Config(users=1, groups=0, seed=42, avatar_probability=0.0)
        users = generate_users(cfg)

        write_ldif_files(users, [], tmp_path, include_defaults=False)

        content = (tmp_path / "50_a_users.ldif").read_text()
        assert "jpegPhoto" not in content

    def test_ldif_dn_format(self, tmp_path):
        cfg = Config(users=1, groups=0, seed=42)
        users = generate_users(cfg)

        write_ldif_files(users, [], tmp_path, include_defaults=False)

        content = (tmp_path / "50_a_users.ldif").read_text()
        lines = content.strip().split("\n")
        # First line should be a dn: line
        assert lines[0].startswith("dn: cn=")
