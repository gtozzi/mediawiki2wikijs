from __future__ import annotations

import pytest

from mw2wj.converter import _preprocess, _postprocess, LINK_PLACEHOLDER_RE, CATEGORY_RE
from mw2wj.models import ConversionContext, Revision
import mw2wj.template_plugins  # noqa: F401 — loads builtin plugins

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
		# Link path includes locale prefix ("en" by default)
		assert link_map[placeholder] == "[links](/en/Internal_Link)"

	def test_link_path_uses_same_sanitization_as_page_creation(self):
		"""Link targets must match the paths created by sanitize_path(),
		including locale prefix and special-character stripping."""
		from mw2wj.utils import sanitize_path
		ctx = ConversionContext(locale="it")
		result, link_map = _preprocess("[[Audio & Video Editing]]", ctx)
		placeholder = list(link_map.keys())[0]
		# Link target should be /it/Audio__Video_Editing (& stripped, double
		# underscore from _&_ collapsing — same as sanitize_path produces)
		expected_path = f"{ctx.locale}/{sanitize_path('Audio & Video Editing', ctx.lowercase_paths)}"
		assert link_map[placeholder] == f"[Audio & Video Editing](/{expected_path})"

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

	def test_commandline_plugin_simple(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{Commandline|cmd=echo hello}}", ctx)
		assert "MWCODEFENCE0END" in result
		assert "```shell" not in result
		assert ctx.code_fence_map["MWCODEFENCE0END"] == "```shell\necho hello\n```\n"

	def test_commandline_plugin_multiline(self):
		ctx = ConversionContext()
		result, link_map = _preprocess(
			"{{Commandline|cmd=line1\nline2}}", ctx
		)
		assert "MWCODEFENCE0END" in result
		assert "line1" not in result
		fence = ctx.code_fence_map["MWCODEFENCE0END"]
		assert "```shell" in fence
		assert "line1\nline2" in fence
		assert fence.endswith("```\n")

	def test_commandline_plugin_root_prompt(self):
		ctx = ConversionContext()
		result, link_map = _preprocess(
			"{{Commandline|root=yes|cmd=mplayer -v -dvd-device /dev/dvd dvd://1 > info.txt}}",
			ctx,
		)
		assert "MWCODEFENCE0END" in result
		assert "mplayer" not in result
		assert "root=yes" not in result
		fence = ctx.code_fence_map["MWCODEFENCE0END"]
		assert "mplayer" in fence
		assert "> info.txt" in fence

	def test_commandline_plugin_root_no(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{Commandline|root=no|cmd=ls}}", ctx)
		assert "MWCODEFENCE0END" in result
		fence = ctx.code_fence_map["MWCODEFENCE0END"]
		assert "ls" in fence

	def test_commandline_plugin_empty_cmd(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{Commandline|cmd=}}", ctx)
		assert "MWCODEFENCE" not in result

	def test_commandline_plugin_nowiki(self):
		"""nowiki-tagged cmd content must stay verbatim, protected from pandoc."""
		ctx = ConversionContext()
		result, link_map = _preprocess(
			"{{Commandline|cmd=<nowiki>D:\\i386> adprep</nowiki>}}", ctx
		)
		assert "MWCODEFENCE0END" in result
		fence = ctx.code_fence_map["MWCODEFENCE0END"]
		assert "&gt;" not in fence
		assert "D:\\i386> adprep" in fence
		assert fence == "```shell\nD:\\i386> adprep\n```\n"

	def test_commandline_plugin_nowiki_multiline(self):
		"""Multiline nowiki content must preserve all newlines."""
		ctx = ConversionContext()
		result, link_map = _preprocess(
			"{{Commandline|cmd=<nowiki>D:\\i386> adprep /forestprep\nD:\\i386> adprep /domainprep</nowiki>}}",
			ctx,
		)
		fence = ctx.code_fence_map["MWCODEFENCE0END"]
		assert "adprep /forestprep" in fence
		assert "adprep /domainprep" in fence
		lines = fence.split("\n")
		assert lines[1] == "D:\\i386> adprep /forestprep"
		assert lines[2] == "D:\\i386> adprep /domainprep"

	def test_commandline_plugin_nowiki_preserves_weird_text(self):
		"""All nowiki content must stay verbatim, including special chars."""
		ctx = ConversionContext()
		weird = "<nowiki>[[Link]] {{Template}} &amp; &gt; &lt; # list * bullet</nowiki>"
		result, link_map = _preprocess(
			f"{{{{Commandline|cmd={weird}}}}}", ctx
		)
		fence = ctx.code_fence_map["MWCODEFENCE0END"]
		assert "[[Link]]" in fence
		assert "{{Template}}" in fence
		assert "&amp;" in fence
		assert "# list" in fence
		assert "* bullet" in fence

	def test_link_anchor_preserved(self):
		"""[[Page#section]] must preserve the anchor in the link target."""
		ctx = ConversionContext(locale="it", lowercase_paths=True)
		result, link_map = _preprocess("[[Android#Sviluppo|Android]]", ctx)
		placeholder = list(link_map.keys())[0]
		link = link_map[placeholder]
		assert "#Sviluppo" in link, (
			f"Anchor missing in link: {repr(link)}"
		)
		assert "[Android](/it/android#Sviluppo)" == link

	def test_filename_plugin(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{Filename|test.txt}}", ctx)
		assert "`test.txt`" in result

	def test_filename_plugin_empty(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{Filename}}", ctx)
		assert "``" in result

	def test_boxcode_plugin(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{Box Code|swap setup|<nowiki>#/bin/sh\nmkswap /dev/sda</nowiki>}}", ctx)
		assert "MWCODEFENCE0END" in result
		fence = ctx.code_fence_map["MWCODEFENCE0END"]
		assert fence == "```text\n# Code: swap setup\n#/bin/sh\nmkswap /dev/sda\n```\n"
		assert "<nowiki>" not in fence

	def test_boxcode_plugin_no_desc(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{Box Code||echo hello}}", ctx)
		assert "MWCODEFENCE0END" in result
		fence = ctx.code_fence_map["MWCODEFENCE0END"]
		assert fence == "```text\necho hello\n```\n"
		assert "# Code:" not in fence

	def test_boxcode_plugin_empty(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{Box Code}}", ctx)
		assert result == ""

	def test_cmd_plugin(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{cmd|mdadm --grow}}", ctx)
		assert "`mdadm --grow`" in result

	def test_cmd_plugin_empty(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{cmd}}", ctx)
		assert "``" in result

	def test_boxfile_plugin(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{Box File|name=fstab|content=<nowiki>/dev/sda1 / ext4 defaults 0 1</nowiki>}}", ctx)
		assert "MWCODEFENCE0END" in result
		fence = ctx.code_fence_map["MWCODEFENCE0END"]
		assert fence == "```text\n# File: fstab\n/dev/sda1 / ext4 defaults 0 1\n```\n"
		assert "<nowiki>" not in fence

	def test_boxfile_scroll_alias(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{Box File Scroll|name=mdadm.conf|content=DEVICE /dev/sda}}", ctx)
		assert "MWCODEFENCE0END" in result
		fence = ctx.code_fence_map["MWCODEFENCE0END"]
		assert fence == "```text\n# File: mdadm.conf\nDEVICE /dev/sda\n```\n"

	def test_boxfile_plugin_empty(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{Box File|name=x|content=}}", ctx)
		assert result == ""

	def test_parser_function_stripped(self):
		ctx = ConversionContext()
		result, link_map = _preprocess("{{#if: {{NAMESPACE}}|<table>then</table>|{{{content}}}}}", ctx)
		assert "#if" not in result
		assert "<table>" not in result
		assert result.strip() == ""


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

	def test_include_metadata_false_suppresses_comment(self):
		rev = make_rev("Hello", author="Alice", comment="Fixed typo")
		result = _postprocess("Hello", rev, ConversionContext(include_metadata=False), {})
		assert "<!-- mediawiki-revision:" not in result
		assert "author:" not in result

	def test_category_regex_removal(self):
		result = CATEGORY_RE.sub("", "Text [[Category:Foo]] more")
		assert "[[Category:Foo]]" not in result
		assert "Text  more" in result

	def test_backtick_unescaping(self):
		"""Pandoc-escaped backticks must be restored to literal backticks."""
		rev = make_rev("test")
		bs = chr(92)  # backslash
		bt = chr(96)  # backtick
		escaped = f"{bs}{bt}{bs}{bt}{bs}{bt}shell\ncode\n{bs}{bt}{bs}{bt}{bs}{bt}"
		result = _postprocess(escaped, rev, ConversionContext(), {})
		assert (bs + bt) not in result, f"Escaped backtick still in output: {repr(result)}"
		assert "```" in result, f"No code fence found: {repr(result)}"

	def test_backtick_unescaping_inline(self):
		"""Inline escaped backticks must also be restored."""
		rev = make_rev("test")
		bs = chr(92)  # backslash
		bt = chr(96)  # backtick
		escaped = f"Use {bs}{bt}ls -la{bs}{bt} to list files"
		result = _postprocess(escaped, rev, ConversionContext(), {})
		assert (bs + bt) not in result, f"Escaped backtick still in output: {repr(result)}"
		assert "`ls -la`" in result, f"Inline code not found: {repr(result)}"

	def test_entity_decode_in_fence(self):
		"""HTML entities inside fenced code blocks must be decoded."""
		rev = make_rev("test")
		result = _postprocess(
			"```shell\necho a &gt; b &amp;&amp; c &lt; d\n```",
			rev, ConversionContext(), {},
		)
		assert "&gt;" not in result
		assert "&lt;" not in result
		assert "&amp;" not in result
		assert ">" in result
		assert "<" in result
		assert "&&" in result
		assert "echo a > b && c < d" in result

	def test_entity_decode_inline(self):
		"""HTML entities inside inline backticks must be decoded."""
		rev = make_rev("test")
		result = _postprocess(
			"Run `adb backup -f &lt;file&gt;` to backup",
			rev, ConversionContext(), {},
		)
		assert "&lt;" not in result
		assert "&gt;" not in result
		assert "`adb backup -f <file>`" in result

	def test_fence_starts_on_newline(self):
		"""Fenced code blocks must start on a new line."""
		rev = make_rev("test")
		result = _postprocess(
			"Some text```shell\nls\n```",
			rev, ConversionContext(), {},
		)
		assert "text\n```shell" in result

	def test_code_fence_restore(self):
		"""Protected code fences must be restored from context.code_fence_map."""
		rev = make_rev("test")
		ctx = ConversionContext()
		ctx.code_fence_map = {
			"MWCODEFENCE0END": "```shell\necho hello\n```\n",
		}
		result = _postprocess("Run MWCODEFENCE0END now", rev, ctx, {})
		assert "MWCODEFENCE" not in result
		assert "```shell\necho hello\n```\n" in result

	def test_code_fence_restore_multiline(self):
		"""Multiline code fences must be restored with all newlines intact."""
		rev = make_rev("test")
		ctx = ConversionContext()
		ctx.code_fence_map = {
			"MWCODEFENCE0END": "```shell\nline1\nline2\nline3\n```\n",
		}
		ctx_no_meta = ConversionContext(include_metadata=False)
		ctx_no_meta.code_fence_map = {
			"MWCODEFENCE0END": "```shell\nline1\nline2\nline3\n```\n",
		}
		result = _postprocess("MWCODEFENCE0END", rev, ctx_no_meta, {})
		lines = result.split("\n")
		assert lines[0] == "```shell"
		assert lines[1] == "line1"
		assert lines[2] == "line2"
		assert lines[3] == "line3"
		assert lines[4] == "```"



@pytest.mark.skipif(not HAS_PANDOC, reason="pandoc not installed")
class TestImageHandling:
	"""Verify image/file wikilinks convert without breaking and connect to uploads."""

	def test_uploaded_file_is_parsed(self):
		from mw2wj.parser import parse_dump
		dump = parse_dump("tests/fixtures/with_upload.xml")
		assert len(dump.files) == 1
		assert dump.files[0].filename == "TestImage.png"
		assert len(dump.files[0].contents) == 70
		assert dump.files[0].sha1 == "up1up1up1up1up1up1up1up1up1up1"

	def test_file_wikilink_does_not_crash(self):
		"""[[File:...]] links must not cause pandoc errors."""
		from mw2wj.converter import convert_revision
		from mw2wj.parser import parse_dump
		dump = parse_dump("tests/fixtures/with_upload.xml")
		ctx = ConversionContext(template_fallback="codeblock")
		for page in dump.pages:
			for rev in page.revisions:
				md = convert_revision(rev, ctx)
				assert md is not None
				assert len(md) > 50

	def test_file_wikilink_produces_img_tag(self):
		"""[[File:name.png]] must produce a markdown image link."""
		from mw2wj.converter import convert_revision
		from mw2wj.parser import parse_dump
		dump = parse_dump("tests/fixtures/with_upload.xml")
		ctx = ConversionContext(template_fallback="codeblock")
		for page in dump.pages:
			for rev in page.revisions:
				md = convert_revision(rev, ctx)
				assert "![" in md, f"No image syntax in output: {repr(md[:300])}"
				assert "](/import_mw/TestImage.png)" in md, (
					f"Image path not found in output: {repr(md[:300])}"
				)

	def test_file_wikilink_with_caption(self):
		"""[[File:name.png|thumb|caption]] produces markdown image with caption."""
		from mw2wj.converter import convert_revision
		from mw2wj.parser import parse_dump
		dump = parse_dump("tests/fixtures/with_upload.xml")
		ctx = ConversionContext(template_fallback="codeblock")
		for page in dump.pages:
			for rev in page.revisions:
				md = convert_revision(rev, ctx)
				assert "![" in md, f"No image syntax in output"
				assert "A test caption" in md, f"Caption not in output"

	def test_file_link_uses_upload_dir(self):
		"""Image link path must include the configured file_upload_dir."""
		from mw2wj.converter import convert_revision
		from mw2wj.parser import parse_dump
		dump = parse_dump("tests/fixtures/with_upload.xml")
		ctx = ConversionContext(
			template_fallback="codeblock",
			file_upload_dir="custom_uploads",
		)
		for page in dump.pages:
			for rev in page.revisions:
				md = convert_revision(rev, ctx)
				assert "](/custom_uploads/TestImage.png)" in md, (
					f"Expected /custom_uploads/ path: {repr(md[:300])}"
				)

	def test_file_link_lowercased(self):
		"""Image link filename must be lowercased when lowercase_paths is True."""
		from mw2wj.converter import convert_revision
		from mw2wj.parser import parse_dump
		dump = parse_dump("tests/fixtures/with_upload.xml")
		ctx = ConversionContext(
			template_fallback="codeblock",
			lowercase_paths=True,
		)
		for page in dump.pages:
			for rev in page.revisions:
				md = convert_revision(rev, ctx)
				assert "](/import_mw/testimage.png)" in md, (
					f"Expected lowercased filename: {repr(md[:300])}"
				)

	def test_upload_filename_matches_img_src(self):
		"""The <img src> filename must match UploadedFile.filename from the dump."""
		from mw2wj.converter import convert_revision
		from mw2wj.parser import parse_dump
		dump = parse_dump("tests/fixtures/with_upload.xml")
		ctx = ConversionContext(template_fallback="codeblock")
		for uploaded_file in dump.files:
			filename = uploaded_file.filename
			for page in dump.pages:
				for rev in page.revisions:
					md = convert_revision(rev, ctx)
					assert filename in md, (
						f"Uploaded file '{filename}' not referenced in output"
					)


@pytest.mark.skipif(not HAS_PANDOC, reason="pandoc not installed")
class TestFullPipeline:
	"""End-to-end tests verifying code fences survive the full conversion."""

	def test_multiline_nowiki_preserves_newlines(self):
		"""Two commands on separate lines must stay on separate lines."""
		from mw2wj.converter import convert_revision
		rev = make_rev(
			"{{Commandline|cmd=<nowiki>D:\\i386> adprep /forestprep\n"
			"D:\\i386> adprep /domainprep</nowiki>}}"
		)
		ctx = ConversionContext()
		md = convert_revision(rev, ctx)
		lines = md.split("\n")
		fence_start = None
		fence_end = None
		for i, line in enumerate(lines):
			if line == "```shell":
				fence_start = i
			elif line == "```" and fence_start is not None:
				fence_end = i
				break
		assert fence_start is not None, f"No opening fence found in:\n{md}"
		assert fence_end is not None, f"No closing fence found in:\n{md}"
		code_lines = lines[fence_start + 1:fence_end]
		assert len(code_lines) >= 2, (
			f"Expected at least 2 code lines, got {len(code_lines)}: {code_lines}"
		)
		assert "adprep /forestprep" in code_lines[0]
		assert "adprep /domainprep" in code_lines[1]

	def test_hash_preserved_in_code_block(self):
		"""# at the start of a code line must not become a numbered list."""
		from mw2wj.converter import convert_revision
		rev = make_rev(
			"{{Commandline|cmd=<nowiki># mplayer -v -dvd-device "
			"/dev/dvd dvd://1 > info.txt</nowiki>}}"
		)
		ctx = ConversionContext()
		md = convert_revision(rev, ctx)
		assert "1. mplayer" not in md, (
			f"# was converted to numbered list:\n{md}"
		)
		assert "mplayer" in md
		assert "# mplayer" in md, (
			f"# comment not preserved:\n{md}"
		)

	def test_weird_text_in_nowiki_preserved(self):
		"""Special characters inside <nowiki> must stay verbatim."""
		from mw2wj.converter import convert_revision
		rev = make_rev(
			"{{Commandline|cmd=<nowiki>[[Link]] {{Template}} "
			"&amp; # list * bullet</nowiki>}}"
		)
		ctx = ConversionContext()
		md = convert_revision(rev, ctx)
		assert "[[Link]]" in md
		assert "{{Template}}" in md
		assert "&amp;" in md
		assert "# list" in md
		assert "* bullet" in md

