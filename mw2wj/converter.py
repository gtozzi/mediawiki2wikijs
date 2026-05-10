from __future__ import annotations

import logging
import re
import subprocess
from typing import TYPE_CHECKING

import mwparserfromhell
import pypandoc

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
	text = _pandoc_convert(text)
	text = _postprocess(text, rev, context, link_map)
	rev.markdown = text
	return text


def _preprocess(text: str, context: ConversionContext) -> tuple[str, dict[str, str]]:
	"""Apply pre-processing before pandoc conversion.

	Returns (processed_text, link_map) where link_map maps placeholder keys
	to their final Markdown link strings.
	"""
	link_map: dict[str, str] = {}

	# Handle #REDIRECT
	if text.strip().lower().startswith("#redirect"):
		target = text.strip()[len("#redirect"):].strip()
		target = target.removeprefix("[[")
		target = target.removesuffix("]]")
		target = target.split("|")[0].strip()
		path = target.replace(" ", "_")
		if context.lowercase_paths:
			path = path.lower()
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

		# Remove category links from text
		if ":" in title and title.split(":")[0].lower() == "category":
			cat_name = title.split(":", 1)[1].strip()
			logger.info("Found category: %s", cat_name)
			try:
				wikicode.replace(link, "")
			except ValueError:
				pass
			continue

		# Skip file/image links — they remain as-is for pandoc
		if ":" in title:
			prefix = title.split(":")[0].lower()
			if prefix in ("file", "image"):
				continue

		# Build display text
		display = str(link.text) if link.text is not None else title
		if display.strip() == title.strip() and ":" in title:
			display = title.split(":", 1)[1].strip()

		# Build target path
		path = title.replace(" ", "_")
		if context.lowercase_paths:
			path = path.lower()

		markdown_link = f"[{display}](/{path})"
		placeholder = f"MWLINKPLACEHOLDER{link_counter}END"
		link_map[placeholder] = markdown_link
		link_counter += 1

		try:
			wikicode.replace(link, placeholder)
		except ValueError:
			logger.warning("Could not replace wikilink '%s' in-place", title)

	# Process templates through plugin registry
	for template in wikicode.filter_templates():
		replacement = registry.convert(template, context)
		try:
			wikicode.replace(template, replacement)
		except ValueError:
			logger.warning("Could not replace template '%s' in-place", template.name.strip())

	text = str(wikicode)

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
		logger.info("Using pandoc %s at %s", pandoc_version, pandoc_path)
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
		raise RuntimeError(
			f"Pandoc exited with code {result.returncode}: {result.stderr[:500]}"
		)

	return result.stdout


def _postprocess(text: str, rev: Revision, context: ConversionContext, link_map: dict[str, str]) -> str:
	"""Apply post-processing to the pandoc output."""
	# Remove trailing whitespace on each line
	text = "\n".join(line.rstrip() for line in text.split("\n"))

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

	# Remove any remaining category links that pandoc may have preserved
	text = CATEGORY_RE.sub("", text)

	# Insert revision metadata as HTML comment
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
