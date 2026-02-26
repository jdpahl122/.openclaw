"""Tests for URL normalisation and text utilities."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.text import clean_text, first_sentences, normalise_url, story_id, strip_html


class TestNormaliseUrl:
    def test_strips_utm_params(self):
        url = "https://www.wgrz.com/article?id=123&utm_source=twitter&utm_medium=social"
        result = normalise_url(url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "id=123" in result

    def test_strips_trailing_slash(self):
        assert normalise_url("https://example.com/path/") == normalise_url("https://example.com/path")

    def test_lowercases_host(self):
        result = normalise_url("https://WWW.WGRZ.COM/article")
        assert "www.wgrz.com" in result

    def test_drops_fragment(self):
        result = normalise_url("https://example.com/page#section2")
        assert "#" not in result

    def test_preserves_meaningful_params(self):
        url = "https://example.com/search?q=buffalo+bills&page=2"
        result = normalise_url(url)
        assert "q=buffalo" in result
        assert "page=2" in result

    def test_identical_urls_after_normalisation(self):
        a = "https://www.wkbw.com/news/local?utm_campaign=fb&fbclid=abc123"
        b = "https://www.wkbw.com/news/local"
        assert normalise_url(a) == normalise_url(b)


class TestStoryId:
    def test_deterministic(self):
        a = story_id("wgrz", "https://www.wgrz.com/article/123")
        b = story_id("wgrz", "https://www.wgrz.com/article/123")
        assert a == b

    def test_different_sources_different_ids(self):
        a = story_id("wgrz", "https://example.com/article")
        b = story_id("wkbw", "https://example.com/article")
        assert a != b


class TestCleanText:
    def test_collapses_whitespace(self):
        assert clean_text("hello   world\n\tfoo") == "hello world foo"

    def test_strips_edges(self):
        assert clean_text("  padded  ") == "padded"


class TestFirstSentences:
    def test_extracts_n_sentences(self):
        text = "First sentence. Second sentence. Third sentence."
        assert first_sentences(text, 2) == "First sentence. Second sentence."

    def test_returns_all_if_fewer(self):
        text = "Only one."
        assert first_sentences(text, 3) == "Only one."


class TestStripHtml:
    def test_removes_tags(self):
        result = strip_html("<p>hello <b>world</b></p>")
        assert "hello" in result and "world" in result
        assert "<" not in result
