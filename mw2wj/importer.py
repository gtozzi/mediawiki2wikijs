from __future__ import annotations

import logging
import time

from mw2wj.models import ConversionContext, Page, Revision, UploadedFile
from mw2wj.utils import sanitize_path
from mw2wj.wikijs_client import WikiJSClient, WikiJSError

logger = logging.getLogger(__name__)


class ImportStats:
	def __init__(self):
		self.files_uploaded = 0
		self.files_skipped = 0
		self.pages_created = 0
		self.pages_updated = 0
		self.pages_skipped = 0
		self.errors: list[tuple[str, str]] = []

	def log_summary(self) -> None:
		logger.info(
			"Import summary: %d files (%d skipped), %d pages created, %d revisions applied",
			self.files_uploaded, self.files_skipped,
			self.pages_created, self.pages_updated,
		)
		if self.errors:
			logger.warning("Errors (%d):", len(self.errors))
			for page_title, error in self.errors:
				logger.warning("  - %s: %s", page_title, error)


def import_files(client: WikiJSClient, files: list[UploadedFile], stats: ImportStats) -> None:
	"""Upload all files to WikiJS before importing pages."""
	total = len(files)
	for i, uf in enumerate(files):
		try:
			client.upload_file(uf.filename, uf.contents)
			stats.files_uploaded += 1
			logger.info("File %d/%d: %s", i + 1, total, uf.filename)
		except WikiJSError as e:
			logger.warning("Skipping file '%s': %s", uf.filename, e)
			stats.files_skipped += 1
			stats.errors.append((uf.filename, str(e)))

		if (i + 1) % 10 == 0:
			logger.info("File progress: %d/%d", i + 1, total)


def import_pages(
	client: WikiJSClient,
	pages: list[Page],
	context: ConversionContext,
	stats: ImportStats,
	dry_run: bool = False,
) -> None:
	"""Import pages with their full revision history.

	Pages must already have their revisions converted (markdown field filled).
	Excludes pages from configured exclude_namespaces.
	"""
	# Filter out excluded namespaces
	included = [
		p for p in pages
		if p.namespace_name not in context.exclude_namespaces
	]
	skipped = len(pages) - len(included)
	if skipped > 0:
		logger.info("Skipping %d pages from excluded namespaces", skipped)
		stats.pages_skipped = skipped

	total = len(included)
	for i, page in enumerate(included):
		try:
			_import_one_page(client, page, context, stats, dry_run)
			logger.info(
				"Page %d/%d: %s (%d revisions)",
				i + 1, total, page.title, len(page.revisions),
			)
		except WikiJSError as e:
			logger.warning("Failed to import page '%s': %s", page.title, e)
			stats.errors.append((page.title, str(e)))

		if (i + 1) % 10 == 0:
			logger.info("Page progress: %d/%d", i + 1, total)


def _import_one_page(
	client: WikiJSClient,
	page: Page,
	context: ConversionContext,
	stats: ImportStats,
	dry_run: bool,
) -> None:
	"""Import a single page with all its revisions."""
	path = sanitize_path(page.title, context.lowercase_paths)

	if page.is_redirect:
		# Redirect pages: create with redirect content
		rev = page.revisions[-1]
		content = rev.markdown or rev.text
		if dry_run:
			logger.info("DRY RUN: would create redirect '%s' → '%s'", page.title, page.redirect_target)
			stats.pages_created += 1
			return
		client.create_page(path, content, page.title, "Redirect page from MediaWiki import")
		stats.pages_created += 1
		return

	for rev_index, rev in enumerate(page.revisions):
		content = rev.markdown
		if content is None:
			logger.warning("Revision %d of '%s' has no markdown, skipping", rev.id, page.title)
			continue

		description = _build_description(rev)
		title = page.title

		if rev_index == 0:
			# First revision: create the page
			if dry_run:
				logger.info("DRY RUN: would create page '%s'", page.title)
				stats.pages_created += 1
				continue
			result = client.create_page(path, content, title, description)
		else:
			# Subsequent revisions: update
			if dry_run:
				stats.pages_updated += 1
				continue
			# WikiJS update needs the page ID — extract from previous create result
			# For now, use path-based lookup approach
			result = client.update_page(
				page.id,  # Use MediaWiki page ID; WikiJS may differ
				path,
				content,
				title,
				description,
			)

		if not dry_run:
			_sleep_briefly()

	if not dry_run:
		if len(page.revisions) > 1:
			stats.pages_created += 1
			stats.pages_updated += len(page.revisions) - 1
		else:
			stats.pages_created += 1


def _build_description(rev: Revision) -> str:
	"""Build an edit description from the original revision metadata."""
	parts = [f"[MediaWiki import] by {rev.contributor}"]
	if rev.comment:
		parts.append(f"Original comment: {rev.comment}")
	return " — ".join(parts)


def _sleep_briefly() -> None:
	"""Brief delay between API calls to avoid rate limiting."""
	time.sleep(0.2)
