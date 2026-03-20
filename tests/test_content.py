"""Tests for the literary passage bank."""

import random
from pathlib import Path

import pytest

from embiggenator.generators.content import PassageBank, _parse_paragraphs


class TestParseParagraphs:
    def test_filters_short_fragments(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Short.\n\nThis is a long enough paragraph to pass the minimum length filter.")
        paras = _parse_paragraphs(f)
        assert len(paras) == 1
        assert "long enough" in paras[0]

    def test_filters_chapter_headings(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text(
            "Chapter I\n\n"
            "This is the first paragraph of the chapter, which is long enough to be kept."
        )
        paras = _parse_paragraphs(f)
        assert len(paras) == 1
        assert "first paragraph" in paras[0]

    def test_normalizes_whitespace(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("This   has   multiple\n   spaces   and  newlines  within  one  paragraph  block.")
        paras = _parse_paragraphs(f)
        assert len(paras) == 1
        assert "  " not in paras[0]


class TestPassageBank:
    @pytest.fixture()
    def bank(self, tmp_path):
        f = tmp_path / "sample.txt"
        paragraphs = [
            f"Paragraph number {i} with enough text to pass the minimum length filter easily."
            for i in range(50)
        ]
        f.write_text("\n\n".join(paragraphs))
        return PassageBank(text_dir=tmp_path)

    def test_loads_paragraphs(self, bank):
        assert bank.count == 50

    def test_get_passage_returns_string(self, bank):
        rng = random.Random(42)
        passage = bank.get_passage(rng)
        assert isinstance(passage, str)
        assert len(passage) > 0

    def test_get_passage_multi_paragraph(self, bank):
        rng = random.Random(42)
        passage = bank.get_passage(rng, min_paragraphs=2, max_paragraphs=3)
        # Multi-paragraph passages contain paragraph separators
        parts = passage.split("\n\n")
        assert 2 <= len(parts) <= 3

    def test_get_short_reply(self, bank):
        rng = random.Random(42)
        reply = bank.get_short_reply(rng)
        assert isinstance(reply, str)
        assert len(reply) > 0

    def test_deterministic_with_seed(self, bank):
        rng1 = random.Random(99)
        rng2 = random.Random(99)
        p1 = bank.get_passage(rng1)
        p2 = bank.get_passage(rng2)
        assert p1 == p2

    def test_no_texts_raises(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(RuntimeError, match="No usable paragraphs"):
            PassageBank(text_dir=empty_dir)

    def test_loads_bundled_texts(self):
        """Verify the real bundled text files can be loaded."""
        bank = PassageBank()
        # Should have thousands of paragraphs from all books
        assert bank.count > 1000

    def test_generate_attachment_returns_bytes(self, bank):
        rng = random.Random(42)
        filename, data = bank.generate_attachment(rng, 1024)
        assert isinstance(data, bytes)
        assert len(data) == 1024
        assert filename.endswith(".txt")

    def test_generate_attachment_respects_target_size(self, bank):
        rng = random.Random(42)
        for target in [512, 4096, 10_000]:
            _, data = bank.generate_attachment(rng, target)
            assert len(data) == target

    def test_generate_attachment_deterministic(self, bank):
        rng1 = random.Random(99)
        rng2 = random.Random(99)
        name1, data1 = bank.generate_attachment(rng1, 2048)
        name2, data2 = bank.generate_attachment(rng2, 2048)
        assert name1 == name2
        assert data1 == data2

    def test_generate_attachment_uses_frankenstein(self, tmp_path):
        """When a 'frankenstein' file exists, attachments draw from it."""
        frank = tmp_path / "frankenstein.txt"
        frank_paras = [
            f"Frankenstein paragraph {i} with enough text to pass the minimum length filter."
            for i in range(20)
        ]
        frank.write_text("\n\n".join(frank_paras))

        other = tmp_path / "other.txt"
        other_paras = [
            f"Other paragraph {i} with enough text to pass the minimum length filter easily."
            for i in range(20)
        ]
        other.write_text("\n\n".join(other_paras))

        bank = PassageBank(text_dir=tmp_path)
        rng = random.Random(42)
        _, data = bank.generate_attachment(rng, 2048)
        text = data.decode("utf-8", errors="replace")
        assert "Frankenstein paragraph" in text
        # Should NOT contain other book text
        assert "Other paragraph" not in text

    def test_generate_attachment_fallback_without_frankenstein(self, bank):
        """Without a frankenstein file, attachments use all paragraphs."""
        rng = random.Random(42)
        _, data = bank.generate_attachment(rng, 1024)
        assert len(data) == 1024
