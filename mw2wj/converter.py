from __future__ import annotations

import logging
import re
import subprocess
from typing import TYPE_CHECKING

import mwparserfromhell
import pypandoc

from mw2wj.template_plugins.base import MissingTemplatePluginError
from mw2wj.template_plugins.registry import registry

if TYPE_CHECKING:
	from mw2wj.models import ConversionContext, Revision

logger = logging.getLogger(__name__)

LINK_PLACEHOLDER_RE = re.compile(r"MWLINKPLACEHOLDER(\d+)(?:END)?")

# Category link: [[Category:Name]] or [[Category:Name|sort]]
CATEGORY_RE = re.compile(r"\[\[[Cc]ategory:([^\]|]+)(?:[^\]|]*)?\]\]")


def convert_revision(rev: Revision, context: ConversionContext) -> str:
	"""Convert a single revision's wikitext to Markdown and store the result."""
	text = rev.text
	text, link_map = _preprocess(text, context)
	try:
		text = _pandoc_convert(text)
	except RuntimeError as e:
		import tempfile
		# Dump both original and preprocessed text so the user
		# can compare them to identify the source of corruption.
		raw_path = tempfile.mktemp(
			suffix=".mw", prefix=f"mw2w_raw_{rev.id}_",
		)
		pp_path = tempfile.mktemp(
			suffix=".mw", prefix=f"mw2w_preprocessed_{rev.id}_",
		)
		try:
			with open(raw_path, "w") as f:
				f.write(rev.text)
			with open(pp_path, "w") as f:
				f.write(text)
		except OSError:
			pass
		raise RuntimeError(
			f"{e}\nRaw dump: {raw_path}\nPreprocessed: {pp_path}"
		) from e
	text = _postprocess(text, rev, context, link_map)
	rev.markdown = text
	return text


def _apply_preprocess_rules(text: str, context: ConversionContext) -> str:
	"""Apply user-configured regex substitutions to raw wikitext.

	Each rule in context.preprocess_rules is a dict with 'pattern' and
	'replacement' keys.  Patterns are applied in order, each against the
	result of the previous substitution.
	"""
	for rule in context.preprocess_rules:
		try:
			text = re.sub(rule["pattern"], rule["replacement"], text)
		except re.error as e:
			logger.warning(
				"Invalid preprocess rule pattern '%s': %s",
				rule.get("pattern", ""), e,
			)
	return text


def _wikijs_link_path(title: str, context: ConversionContext) -> str:
	"""Build a Wiki.js link target path from a page title.

	Uses the same sanitization as page path creation (sanitize_path)
	and includes the locale prefix so intra-wiki links resolve
	to the same locale the pages are imported under.  Anchors
	(#section) are preserved after the sanitized path.

	@param title: Page title (e.g. "Audio & Video Editing#Section")
	@param context: Conversion context with locale and path settings
	@returns: Path segment for use in Markdown links (e.g. "it/Audio__Video_Editing#Section")
	"""
	from mw2wj.utils import sanitize_path
	anchor = ""
	if "#" in title:
		title, anchor_part = title.rsplit("#", 1)
		anchor = f"#{anchor_part}"
	sanitized = sanitize_path(title, context.lowercase_paths)
	if context.locale:
		sanitized = f"{context.locale}/{sanitized}"
	return sanitized + anchor


def _protect_code_fences(text: str, fence_map: dict[str, str]) -> str:
	"""Replace markdown fenced code blocks with placeholders.

	Our template plugins generate proper markdown code fences, but
	pandoc's mediawiki reader does not understand them — it collapses
	newlines, entity-encodes > < &, and treats # as a numbered list.
	By replacing the entire fence block with a plain-text placeholder
	we let it pass through pandoc untouched, then restore it in
	_postprocess.

	@param text: Wikitext with embedded markdown code fences
	@param fence_map: Dict to populate with placeholder→fence mappings
	@returns: Text with code fences replaced by MWCODEFENCE{n}END
	"""
	FENCE_RE = re.compile(r'```(\w*)\n(.*?)\n```', re.DOTALL)

	def _replace(match: re.Match) -> str:
		lang = match.group(1) or ""
		content = match.group(2)
		key = f"MWCODEFENCE{len(fence_map)}END"
		fence_map[key] = f"```{lang}\n{content}\n```\n"
		return key

	return FENCE_RE.sub(_replace, text)


def _restore_code_fences(text: str, fence_map: dict[str, str]) -> str:
	"""Restore code fences from placeholders saved by _protect_code_fences."""
	FENCE_PLACEHOLDER_RE = re.compile(r'MWCODEFENCE\d+END')

	def _restore(match: re.Match) -> str:
		key = match.group(0)
		return fence_map.get(key, key)

	return FENCE_PLACEHOLDER_RE.sub(_restore, text)


def _preprocess(text: str, context: ConversionContext) -> tuple[str, dict[str, str]]:
	"""Apply pre-processing before pandoc conversion.

	Returns (processed_text, link_map) where link_map maps placeholder keys
	to their final Markdown link strings.
	"""
	link_map: dict[str, str] = {}


	# Apply configurable pre-processing regex rules before
	# any wikitext parsing.  Useful for fixing wiki-specific
	# broken syntax (e.g. mistyped link brackets).
	text = _apply_preprocess_rules(text, context)

	# Handle #REDIRECT
	if text.strip().lower().startswith("#redirect"):
		target = text.strip()[len("#redirect"):].strip()
		target = target.removeprefix("[[")
		target = target.removesuffix("]]")
		target = target.split("|")[0].strip()
		path = _wikijs_link_path(target, context)
		return f"> Redirect to: [{target}](/{path})", link_map

	try:
		wikicode = mwparserfromhell.parse(text)
	except Exception:
		logger.warning("mwparserfromhell failed to parse wikitext, using raw text")
		return text, link_map

	link_counter = 0

	# Process wikilinks: replace with placeholders, build link_map
	for link in wikicode.filter_wikilinks():
		title = str(link.title).strip()
		if not title:
			continue

		# Handle category links based on category_mode
		if ":" in title and title.split(":")[0].lower() == "category":
			cat_name = title.split(":", 1)[1].strip()
			logger.info("Found category: %s", cat_name)
			context.collected_categories.append(cat_name)
			if context.category_mode in ("text", "both"):
				# Convert to a regular wikilink so pandoc renders it
				display = f"Category: {cat_name}"
				cat_path = _wikijs_link_path(f"Category:{cat_name}", context)
				markdown_link = f"[{display}](/{cat_path})"
				placeholder = f"MWLINKPLACEHOLDER{link_counter}END"
				link_map[placeholder] = markdown_link
				link_counter += 1
				try:
					wikicode.replace(link, placeholder)
				except ValueError:
					pass
			else:
				# tag or discard: strip from text
				try:
					wikicode.replace(link, "")
				except ValueError:
					pass
			continue

		# Transform file/image links to markdown images pointing
		# at the Wiki.js assets directory where files are uploaded.
		if ":" in title:
			prefix = title.split(":")[0].lower()
			if prefix in ("file", "image"):
				from mw2wj.utils import sanitize_filename
				fname = title.split(":", 1)[1].strip()
				fname = sanitize_filename(fname, context.lowercase_paths)
				display = str(link.text) if link.text is not None else fname
				if display.strip() == fname.strip():
					display = fname.rsplit(".", 1)[0]
				img_path = f"{context.file_upload_dir}/{fname}"
				markdown_link = f"![{display}](/{img_path})"
				placeholder = f"MWLINKPLACEHOLDER{link_counter}END"
				link_map[placeholder] = markdown_link
				link_counter += 1
				try:
					wikicode.replace(link, placeholder)
				except ValueError:
					pass
				continue

		# Build display text
		display = str(link.text) if link.text is not None else title
		if display.strip() == title.strip() and ":" in title:
			display = title.split(":", 1)[1].strip()

		# Build target path using same sanitization as page
		# creation, including locale prefix
		path = _wikijs_link_path(title, context)
		markdown_link = f"[{display}](/{path})"
		placeholder = f"MWLINKPLACEHOLDER{link_counter}END"
		link_map[placeholder] = markdown_link
		link_counter += 1

		try:
			wikicode.replace(link, placeholder)
		except ValueError:
			logger.warning("Could not replace wikilink '%s' in-place", title)

	# Process templates through plugin registry.
	# Parser functions (#if, #ifeq, #switch, etc.) are stripped from
	# regular pages but preserved in template namespace (ns=10) where
	# they define the template's structure and logic.
	# Magic words (NAMESPACE, PAGENAME, !, etc.) are MediaWiki
	# built-in variables — strip them everywhere since we cannot
	# expand them meaningfully and pandoc does not understand them.
	MAGIC_WORD_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
	for template in wikicode.filter_templates():
		name = template.name.strip()
		if name.startswith("#") or MAGIC_WORD_RE.match(name):
			if context.current_namespace == 10 and name.startswith("#"):
				# Parser functions in template namespace
				# contain structural HTML — leave them
				# for pandoc to handle natively.
				continue
			replacement = ""
			try:
				wikicode.replace(template, replacement)
			except ValueError:
				pass
			continue
		try:
			replacement = registry.convert(template, context)
		except MissingTemplatePluginError:
			# Template has no plugin and fallback is 'error'.
			# Try to strip it.  If it is nested inside another
			# template, replace() will fail — skip, the parent
			# or final regex pass will clean it up.
			try:
				wikicode.replace(template, '')
			except ValueError:
				continue
			raise
		try:
			wikicode.replace(template, replacement)
		except ValueError:
			logger.warning("Could not replace template '%s' in-place", name)

	text = str(wikicode)

	# Protect generated markdown code fences from pandoc's mediawiki
	# reader.  Pandoc does not understand fenced code blocks in
	# mediawiki input: it collapses newlines, treats # as numbered
	# lists, entity-encodes >, and backslash-escapes special chars.
	context.code_fence_map = {}
	text = _protect_code_fences(text, context.code_fence_map)

	# Strip <ref> tags — references don't translate well to Markdown and
	# broken ref tags (from template stripping) crash pandoc.
	text = re.sub(r"<ref[^>]*/?>", "", text, flags=re.IGNORECASE)
	text = re.sub(r"</ref>", "", text, flags=re.IGNORECASE)

	# Fix orphaned quoted attributes in table cells (e.g.
	# |style="val" "width: 20px;" |1). Wikipedia's parser tolerates
	# these but pandoc's mediawiki reader does not.
	text = re.sub(r'(="[^"]*")\s+"[^"]+"', r'\1', text)

	# Regex pass: strip any remaining {{templates}} that mwparserfromhell
	# could not replace (e.g. templates nested inside <ref> tags).
	# Apply iteratively to handle single-level nesting.
	TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
	prev = None
	while prev != text:
		prev = text
		text = TEMPLATE_RE.sub("", text)

	return text, link_map


def _format_pandoc_error(text: str, result: subprocess.CompletedProcess, trace_stderr: str = "") -> str:
	"""Build a pandoc error message with surrounding context lines."""
	stderr = result.stderr
	error_msg = stderr.strip().split("\n")[-1] if stderr.strip() else "unknown error"
	msg = f"Pandoc exited with code {result.returncode}: {error_msg}"

	# Pandoc reports errors as "Error at (line N, column M):"
	m = re.search(r"line\s+(\d+)", stderr)
	if m:
		err_line = int(m.group(1))
		lines = text.split("\n")
		if err_line > len(lines):
			start = max(0, len(lines) - 10)
			end = len(lines)
			msg += f"\n\nEnd of file (line {err_line} is past EOF, "
			msg += f"showing last {end - start} of {len(lines)} lines):\n"
		else:
			start = max(0, err_line - 4)
			end = min(len(lines), err_line + 3)
			msg += "\n\nContext (line numbers are 1-based):\n"
		for i in range(start, end):
			marker = ">>>" if i == err_line - 1 else "   "
			msg += f"  {marker} {i+1:5d} | {lines[i][:200]}\n"

	# Show the last few trace lines from a second --trace run.
	# These reveal what pandoc last parsed successfully before
	# the error (useful for identifying unclosed blocks).
	trace_lines = [l for l in trace_stderr.split("\n") if l.startswith("[trace]")]
	if trace_lines:
		msg += "\nLast parsed elements (--trace):\n"
		for tl in trace_lines[-5:]:
			msg += f"  {tl[:250]}\n"

	# Scan for unmatched block openers — the most common cause
	# of "unexpected end of input" in pandoc's mediawiki reader.
	unclosed = _find_unclosed_blocks(text)
	if unclosed:
		msg += "\nUnclosed blocks (missing closer):\n"
		for line_no, block_type, opener in unclosed[:8]:
			msg += f"  line {line_no}: {block_type} — {opener[:120]}\n"

	return msg


def _find_unclosed_blocks(text: str) -> list[tuple[int, str, str]]:
	"""Find unclosed MediaWiki blocks that would cause pandoc parse errors."""
	results: list[tuple[int, str, str]] = []
	lines = text.split("\n")

	# Table: {| opens, |} closes — simple stack-based scan.
	# Also collect all positions so errors show the full picture.
	table_stack: list[tuple[int, str]] = []
	all_opens: list[int] = []
	all_closes: list[int] = []
	for i, line in enumerate(lines, 1):
		stripped = line.strip()
		if stripped.startswith("{|"):
			all_opens.append(i)
			# MediaWiki tables cannot nest — a {| inside an
			# already-open table is just cell content.
			if not table_stack:
				table_stack.append((i, stripped))
		elif stripped.startswith("|}"):
			all_closes.append(i)
			if table_stack:
				table_stack.pop()
	for line_no, opener in table_stack:
		results.append((
			line_no, "table",
			f"{opener}  (all {{|}}: {all_opens}, all |{{}}: {all_closes})",
		))

	# HTML tags that wrap blocks
	for tag in ("div", "pre", "blockquote", "source", "code"):
		opens = len(re.findall(rf"<{tag}\b", text, re.IGNORECASE))
		closes = len(re.findall(rf"</{tag}>", text, re.IGNORECASE))
		if opens > closes:
			# Find the first unmatched open line
			for i, line in enumerate(lines, 1):
				if re.search(rf"<{tag}\b", line, re.IGNORECASE):
					results.append((i, f"<{tag}>", line.strip()))
					break

	return results

# Maximum wall-clock seconds allowed for a single pandoc invocation.
# Large/complex wikitext pages can trigger exponential-time behaviour in
# pandoc's mediawiki reader. This cap prevents tests from hanging forever.
PANDOC_TIMEOUT = 120


def _pandoc_convert(text: str) -> str:
	"""Convert MediaWiki wikitext to Markdown using pandoc.

	@param text: Raw MediaWiki wikitext
	@returns: Markdown output from pandoc
	@raises RuntimeError: If pandoc is not installed or times out
	"""
	try:
		pandoc_path = pypandoc.get_pandoc_path()
		pandoc_version = pypandoc.get_pandoc_version()
		logger.debug("Using pandoc %s at %s", pandoc_version, pandoc_path)
	except OSError:
		raise RuntimeError(
			"Pandoc is not installed. Install it with: apt install pandoc"
		)

	result = subprocess.run(
		[
			pandoc_path,
			"--from=mediawiki",
			"--to=markdown_strict",
			"--wrap=none",
			"--markdown-headings=atx",
		],
		input=text,
		capture_output=True,
		text=True,
		timeout=PANDOC_TIMEOUT,
	)

	if result.returncode != 0:
		trace_stderr = ""
		try:
			trace_args = [
				pandoc_path,
				"--from=mediawiki",
				"--to=markdown_strict",
				"--wrap=none",
				"--markdown-headings=atx",
				"--trace",
			]
			trace_result = subprocess.run(
				trace_args,
				input=text,
				capture_output=True,
				text=True,
				timeout=PANDOC_TIMEOUT,
			)
			trace_stderr = trace_result.stderr
		except Exception:
			pass
		raise RuntimeError(_format_pandoc_error(text, result, trace_stderr))

	return result.stdout


def _decode_entities_in_fences(text: str) -> str:
	"""Decode HTML entities inside fenced code blocks.

	Pandoc's markdown_strict writer entity-encodes > < & inside
	code blocks.  Wiki.js and most renderers display these as
	literal characters inside code, so we must restore them.
	"""
	def _decode(match: re.Match) -> str:
		block = match.group(0)
		block = block.replace("&amp;", "&")
		block = block.replace("&gt;", ">")
		block = block.replace("&lt;", "<")
		return block

	return re.sub(r'```.*?```', _decode, text, flags=re.DOTALL)


def _decode_entities_inline(text: str) -> str:
	"""Decode HTML entities inside inline backtick code spans."""
	def _decode(match: re.Match) -> str:
		span = match.group(0)
		span = span.replace("&amp;", "&")
		span = span.replace("&gt;", ">")
		span = span.replace("&lt;", "<")
		return span

	return re.sub(r'`[^`]+`', _decode, text)


def _postprocess(text: str, rev: Revision, context: ConversionContext, link_map: dict[str, str]) -> str:
	"""Apply post-processing to the pandoc output."""
	# Remove trailing whitespace on each line
	text = "\n".join(line.rstrip() for line in text.split("\n"))

	# Pandoc escapes backticks in markdown_strict output and
	# collapses multi-line code fences to a single line.
	# Restore proper formatting: first unescape, then split
	# single-line fences into opening + content + closing.
	text = text.replace(r"\`", "`")
	text = re.sub(r'(`{3,})(\S*)\s+(.+?)\s*(`{3,})\s*$',
		r'\1\2\n\3\n\4', text, flags=re.MULTILINE)

	# Pandoc may entity-encode > < & inside code blocks.
	# Decode them so they render as literal characters.
	# Must run BEFORE restoring protected fences — those were
	# never seen by pandoc and must stay verbatim.
	text = _decode_entities_in_fences(text)
	text = _decode_entities_inline(text)

	# Restore code fences that were protected from pandoc
	fence_map = getattr(context, 'code_fence_map', None)
	if fence_map:
		text = _restore_code_fences(text, fence_map)

	# Ensure fenced code blocks start on a new line.
	# Pandoc may concatenate them with preceding text.
	text = re.sub(r'([^\n])```', r'\1\n```', text)

	# Replace link placeholders with actual Markdown links.
	# Normally placeholders end with END, but tolerates the rare case
	# where END gets stripped by downstream processing.
	def _restore_link(match: re.Match) -> str:
		digits = match.group(1)
		key = f"MWLINKPLACEHOLDER{digits}END"
		if key in link_map:
			return link_map[key]
		key = f"MWLINKPLACEHOLDER{digits}"
		if key in link_map:
			return link_map[key]
		return match.group(0)

	text = LINK_PLACEHOLDER_RE.sub(_restore_link, text)

	# Safety net: strip any remaining placeholder artifacts that survived
	# pandoc mangling (rare — happens with adjacent formatting markers).
	text = re.sub(r"MWLINKPLACEHOLDER\S+", "", text)

	# Remove any remaining category links that pandoc may have preserved.
	# Only needed for tag/discard modes — text/both modes keep them as links.
	if context.category_mode in ("tag", "discard"):
		text = CATEGORY_RE.sub("", text)

	# Insert revision metadata as HTML comment (unless disabled)
	if context.include_metadata:
		meta_lines = [
			"<!-- mediawiki-revision:",
			f"  author: {rev.contributor}",
			f"  timestamp: {rev.timestamp.isoformat()}",
		]
		if rev.comment:
			meta_lines.append(f"  comment: {rev.comment}")
		meta_lines.append("-->")

		match = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
		if match:
			insert_pos = match.end()
			text = text[:insert_pos] + "\n".join(meta_lines) + "\n\n" + text[insert_pos:]
		else:
			text = "\n".join(meta_lines) + "\n\n" + text

	return text
