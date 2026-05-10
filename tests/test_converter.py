from __future__ import annotations

import pytest

from mw2wj.converter import _preprocess, _postprocess, LINK_PLACEHOLDER_RE, CATEGORY_RE
from mw2wj.models import ConversionContext, Revision

# Skip pandoc-dependent tests if pandoc is not installed
try:
	import pypandoc
	pypandoc.get_pandoc_version()
	HAS_PANDOC = True
except OSError:
	HAS_PANDOC = False


def make_rev(text: str, author: str = "TestUser", comment: str | None = None) -> Revision:
	from datetime import datetime, timezone
	return Revision(
		id=1,
		parent_id=None,
		timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
		contributor=author,
		comment=comment,
		text=text,
	)


class TestPreprocess:
	def test_redirect_handling(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("#REDIRECT [[NewPage]]", ctx)
		assert result.startswith("> Redirect to:")
		assert "NewPage" in result
		assert link_map == {}

	def test_wikilink_placeholder(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("[[Internal Link|links]]", ctx)
		assert "MWLINKPLACEHOLDER0END" in result
		assert len(link_map) == 1
		placeholder = list(link_map.keys())[0]
		assert "MWLINKPLACEHOLDER" in placeholder
		assert link_map[placeholder] == "[links](/Internal_Link)"

	def test_category_removal(self):
		ctx = ConversionContext(category_mode="tag")
		result, link_map = _preprocess("Some text [[Category:TestCat]] more text", ctx)
		assert "Some text" in result
		assert "more text" in result

	def test_template_codeblock_fallback(self):
		ctx = ConversionContext(template_fallback="codeblock")
		result, link_map = _preprocess("{{UnknownTemplate|param=value}}", ctx)
		assert "UnknownTemplate" in result
		assert "[Template:" in result

	def test_template_error_fallback(self):
		from mw2wj.template_plugins.base import MissingTemplatePluginError
		ctx = ConversionContext(template_fallback="error")
		with pytest.raises(MissingTemplatePluginError):
			_preprocess("{{NonExistentTemplate}}", ctx)


class TestPostProcessing:
	def test_placeholder_restore(self):
		rev = make_rev("Hello")
		link_map = {"MWLINKPLACEHOLDER0END": "[links](/Test)"}
		result = _postprocess("Text MWLINKPLACEHOLDER0END more", rev, ConversionContext(), link_map)
		assert "[links](/Test)" in result
		assert "MWLINKPLACEHOLDER0END" not in result

	def test_placeholder_end_suffix_consumed(self):
		"""The END suffix of MWLINKPLACEHOLDER{n}END must be consumed."""
		rev = make_rev("Hello")
		link_map = {"MWLINKPLACEHOLDER0END": "[Link](/Page)"}
		result = _postprocess("See MWLINKPLACEHOLDER0END.", rev, ConversionContext(), link_map)
		assert "END" not in result, f"END suffix leaked: {repr(result)}"
		assert "[Link](/Page)" in result

	def test_placeholder_end_suffix_multiple(self):
		"""Multiple placeholders each have END consumed."""
		rev = make_rev("Hello")
		link_map = {
			"MWLINKPLACEHOLDER0END": "[A](/A)",
			"MWLINKPLACEHOLDER1END": "[B](/B)",
		}
		result = _postprocess(
			"X MWLINKPLACEHOLDER0END Y MWLINKPLACEHOLDER1END Z",
			rev, ConversionContext(), link_map,
		)
		assert "END" not in result
		assert "[A](/A)" in result
		assert "[B](/B)" in result

	def test_metadata_html_comment(self):
		rev = make_rev("Hello", author="Alice", comment="Fixed typo")
		result = _postprocess("Hello", rev, ConversionContext(), {})
		assert "<!-- mediawiki-revision:" in result
		assert "author: Alice" in result
		assert "comment: Fixed typo" in result

	def test_no_comment(self):
		rev = make_rev("Hello", author="Bob")
		result = _postprocess("Hello", rev, ConversionContext(), {})
		assert "author: Bob" in result
		assert "comment:" not in result

	def test_category_regex_removal(self):
		result = CATEGORY_RE.sub("", "Text [[Category:Foo]] more")
		assert "[[Category:Foo]]" not in result
		assert "Text  more" in result
