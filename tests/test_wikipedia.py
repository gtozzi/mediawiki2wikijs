"""Integration tests using real Wikipedia XML exports.

Fixtures are downloaded automatically on first run via Wikipedia's
Special:Export API and cached in tests/fixtures/. They are git-ignored
so Wikipedia's CC BY-SA content is never redistributed with this repo.

Run tests/fetch_wikipedia_fixture.py manually for an initial bulk
download, or just run the tests — missing fixtures are fetched on demand.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

import mw2wj.template_plugins  # noqa: F401 — loads builtin plugins
from mw2wj.converter import convert_revision
from mw2wj.models import ConversionContext
from mw2wj.parser import parse_dump
from tests.fetch_wikipedia_fixture import PAGES_TO_FETCH, ensure_fixtures, fixture_path_for

logger = logging.getLogger(__name__)

FIXTURES = Path(__file__).parent / "fixtures"


def _get_fixture_paths() -> list[Path]:
	"""Return paths to available Wikipedia fixtures, downloading missing ones."""
	ensure_fixtures()
	paths = []
	for page_spec in PAGES_TO_FETCH:
		title = str(page_spec["title"])
		p = fixture_path_for(title)
		if p.exists():
			paths.append(p)
	return paths


WIKIPEDIA_FIXTURES = _get_fixture_paths()


class TestWikipediaParsing:
	"""Verify the parser handles real Wikipedia XML dumps across all namespaces."""

	def test_fixtures_exist(self):
		assert WIKIPEDIA_FIXTURES, (
			"No Wikipedia fixtures available. "
			"Run: python3 tests/fetch_wikipedia_fixture.py"
		)

	@pytest.mark.parametrize("fixture_path", WIKIPEDIA_FIXTURES)
	def test_parse_real_dump(self, fixture_path):
		dump = parse_dump(str(fixture_path))
		assert dump.sitename
		assert dump.generator
		assert len(dump.pages) > 0, f"No pages found in {fixture_path.name}"
		for page in dump.pages:
			assert page.title
			assert len(page.revisions) > 0, f"Page '{page.title}' has no revisions"
			for rev in page.revisions:
				assert rev.text, f"Revision {rev.id} of '{page.title}' has no text"
				assert rev.timestamp
				assert rev.contributor

	@pytest.mark.parametrize("fixture_path", WIKIPEDIA_FIXTURES)
	def test_convert_real_dump(self, fixture_path):
		dump = parse_dump(str(fixture_path))
		ctx = ConversionContext(
			category_mode="text",
			template_fallback="codeblock",
			exclude_namespaces=[],
		)
		for page in dump.pages:
			ctx.current_namespace = page.namespace
			for rev in page.revisions:
				md = convert_revision(rev, ctx)
				assert md is not None
				assert len(md) > 0
				assert "<!-- mediawiki-revision:" in md
				assert len(md) > 20, f"Output too short for {page.title} rev {rev.id}"

	@pytest.mark.parametrize("fixture_path", WIKIPEDIA_FIXTURES)
	def test_converted_output_is_clean_markdown(self, fixture_path):
		"""Verify the output contains no raw wikitext artifacts."""
		dump = parse_dump(str(fixture_path))
		ctx = ConversionContext(
			category_mode="text",
			template_fallback="codeblock",
		)
		for page in dump.pages:
			ctx.current_namespace = page.namespace
			for rev in page.revisions:
				md = convert_revision(rev, ctx)
				assert "[[Category:" not in md
				assert "MWLINKPLACEHOLDER" not in md
				# Template namespace pages legitimately contain {{{param}}}
				# parameter reference syntax.
				if page.namespace != 10:
					assert "{{{" not in md

	@pytest.mark.parametrize("fixture_path", WIKIPEDIA_FIXTURES)
	def test_has_content_after_conversion(self, fixture_path):
		"""Verify conversion doesn't produce empty or near-empty pages."""
		dump = parse_dump(str(fixture_path))
		ctx = ConversionContext(
			category_mode="text",
			template_fallback="codeblock",
		)
		for page in dump.pages:
			ctx.current_namespace = page.namespace
			for rev in page.revisions:
				md = convert_revision(rev, ctx)
				# Real articles should produce substantial output
				min_len = 30 if page.namespace == 14 else 100
				assert len(md) > min_len, (
					f"Output too short ({len(md)} chars) for {page.title}"
				)
