"""Tests for the avatar JPEG palette."""

from embiggenator.generators.avatar import _PALETTE, generate_avatar


class TestPalette:
    def test_has_16_colors(self):
        assert len(_PALETTE) == 16

    def test_all_valid_jpeg(self):
        for i, jpg in enumerate(_PALETTE):
            assert jpg[:2] == b"\xff\xd8", f"Color {i}: missing SOI marker"
            assert jpg[-2:] == b"\xff\xd9", f"Color {i}: missing EOI marker"

    def test_all_different(self):
        unique = set(_PALETTE)
        assert len(unique) == 16

    def test_reasonable_size(self):
        for i, jpg in enumerate(_PALETTE):
            assert 400 < len(jpg) < 1000, f"Color {i}: unexpected size {len(jpg)}"


class TestGenerateAvatar:
    def test_returns_bytes(self):
        result = generate_avatar(0)
        assert isinstance(result, bytes)

    def test_valid_jpeg(self):
        result = generate_avatar(5)
        assert result[:2] == b"\xff\xd8"
        assert result[-2:] == b"\xff\xd9"

    def test_wraps_around(self):
        assert generate_avatar(0) == generate_avatar(16)
        assert generate_avatar(3) == generate_avatar(19)

    def test_different_indices_different_images(self):
        assert generate_avatar(0) != generate_avatar(1)

    def test_deterministic(self):
        assert generate_avatar(7) == generate_avatar(7)
