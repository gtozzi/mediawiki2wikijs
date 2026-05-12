# mediawiki2wikijs — MediaWiki to Wiki.js migration tool
# Copyright (C) 2026  Gabriele Tozzi <gabriele@tozzi.eu>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


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


def import_files(client: WikiJSClient, files: list[UploadedFile], stats: ImportStats, upload_dir: str = "", skip_failed: bool = False, lowercase_paths: bool = False) -> None:
	"""Upload all files to WikiJS before importing pages.

	@param client: WikiJSClient instance
	@param files: List of files to upload
	@param stats: ImportStats to update
	@param upload_dir: Subdirectory in Wiki.js assets (e.g. "import_mw")
	@param skip_failed: If True, log and skip files that fail to upload
	@param lowercase_paths: If True, sanitize and lowercase filenames
	"""
	from mw2wj.utils import sanitize_filename

	# Sanitize filenames and detect collisions
	sanitized: dict[str, str] = {}
	upload_names: dict[str, str] = {}
	for uf in files:
		clean = sanitize_filename(uf.filename, lowercase_paths)
		if clean in sanitized:
			raise ValueError(
				f"File name collision: '{uf.filename}' and "
				f"'{sanitized[clean]}' both map to '{clean}'. "
				f"Rename one of the files to resolve the conflict."
			)
		sanitized[clean] = uf.filename
		upload_names[uf.filename] = clean

	folder_id = 0
	if upload_dir:
		try:
			client.create_asset_folder(upload_dir)
		except WikiJSError as e:
			logger.warning("Could not create asset folder '%s': %s", upload_dir, e)
		folder_id = client.get_asset_folder_id(upload_dir) or 0
		if folder_id:
			logger.info("Uploading files to folder '%s' (id=%d)", upload_dir, folder_id)
		else:
			logger.warning("Asset folder '%s' not found, uploading to root", upload_dir)

	total = len(files)
	for i, uf in enumerate(files):
		upload_name = upload_names[uf.filename]
		try:
			client.upload_file(upload_name, uf.contents, folder_id)
			stats.files_uploaded += 1
			logger.info("File %d/%d: %s", i + 1, total, upload_name)
		except WikiJSError as e:
			if skip_failed:
				logger.warning("Skipping file '%s': %s", upload_name, e)
				stats.files_skipped += 1
				stats.errors.append((upload_name, str(e)))
			else:
				raise

		if (i + 1) % 10 == 0:
			logger.info("File progress: %d/%d", i + 1, total)


def import_pages(
	client: WikiJSClient,
	pages: list[Page],
	context: ConversionContext,
	stats: ImportStats,
	dry_run: bool = False,
	skip_failed: bool = False,
	is_private: bool = True,
	locale: str = "en",
) -> None:
	"""Import pages with their full revision history.

	Pages must already have their revisions converted (markdown field filled).
	Excludes pages from configured exclude_namespaces.
	"""
	# Filter out pages from excluded namespaces as configured.
	# This list should typically include Template (ns=10, whose
	# parser functions pandoc cannot handle) and File (ns=6,
	# which are metadata stubs for binary uploads).
	included = [
		p for p in pages
		if p.namespace_name not in context.exclude_namespaces
	]
	skipped = len(pages) - len(included)
	if skipped > 0:
		logger.info("Skipping %d pages from excluded namespaces", skipped)
		stats.pages_skipped = skipped

	seen_paths: dict[str, str] = {}
	total = len(included)
	for i, page in enumerate(included):
		path = sanitize_path(page.title, context.lowercase_paths)
		if path in seen_paths:
			raise ValueError(
				f"Path collision: '{page.title}' and '{seen_paths[path]}' "
				f"both map to '{path}'. "
				f"Rename one of the pages to resolve the conflict."
			)
		seen_paths[path] = page.title
		try:
			_import_one_page(client, page, context, stats, dry_run, is_private, locale)
			logger.info(
				"Page %d/%d: %s (%d revisions)",
				i + 1, total, page.title, len(page.revisions),
			)
		except WikiJSError as e:
			if skip_failed:
				logger.warning("Failed to import page '%s': %s", page.title, e)
				stats.errors.append((page.title, str(e)))
			else:
				raise

		if (i + 1) % 10 == 0:
			logger.info("Page progress: %d/%d", i + 1, total)


def _import_one_page(
	client: WikiJSClient,
	page: Page,
	context: ConversionContext,
	stats: ImportStats,
	dry_run: bool,
	is_private: bool = True,
	locale: str = "en",
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
		client.create_page(path, content, page.title, "Redirect page from MediaWiki import", is_private=is_private, locale=locale)
		stats.pages_created += 1
		return

	for rev_index, rev in enumerate(page.revisions):
		content = rev.markdown
		if not content or not content.strip():
			logger.warning("Revision %d of '%s' has no markdown, skipping", rev.id, page.title)
			continue

		description = _build_description(rev, context.include_edit_description)
		title = page.title

		if rev_index == 0:
			# First revision: create the page
			if dry_run:
				logger.info("DRY RUN: would create page '%s'", page.title)
				stats.pages_created += 1
				continue
			tags = _get_tags(page, context)
			result = client.create_page(path, content, title, description, is_private=is_private, locale=locale, tags=tags)
			# Extract the Wiki.js page ID from the create response.
			# MediaWiki page IDs are unrelated to Wiki.js internal IDs,
			# and subsequent updates require the real Wiki.js ID.
			wikijs_page_id = (
				result.get("pages", {})
				.get("create", {})
				.get("page", {})
				.get("id")
			)
		else:
			# Subsequent revisions: update
			if dry_run:
				stats.pages_updated += 1
				continue
			result = client.update_page(
				wikijs_page_id,
				path,
				content,
				title,
				description,
				is_private=is_private,
				locale=locale,
				tags=tags,
			)

		if not dry_run:
			_sleep_briefly()

	if not dry_run:
		if len(page.revisions) > 1:
			stats.pages_created += 1
			stats.pages_updated += len(page.revisions) - 1
		else:
			stats.pages_created += 1


def _get_tags(page: Page, context: ConversionContext) -> list[str]:
	"""Return tags for a page based on category_mode.

	@param page: Page with collected categories
	@param context: Conversion context with category_mode setting
	@returns: List of tag strings, or empty list
	"""
	if context.category_mode in ("tag", "both") and page.categories:
		return page.categories
	return []


def _build_description(rev: Revision, include_edit_description: bool = True) -> str:
	"""Build an edit description from the original revision metadata.

	Wiki.js limits edit descriptions to 255 characters in the database.
	Long revision comments are truncated to avoid insert failures.

	@param rev: Revision with contributor and comment metadata
	@param include_edit_description: If False, return a minimal description
	"""
	if not include_edit_description:
		return ""
	MAX_LEN = 250
	parts = [f"[MediaWiki import] by {rev.contributor}"]
	if rev.comment:
		parts.append(f"Original comment: {rev.comment}")
	result = " — ".join(parts)
	if len(result) > MAX_LEN:
		result = result[:MAX_LEN - 3] + "..."
	return result


def _sleep_briefly() -> None:
	"""Brief delay between API calls to avoid rate limiting."""
	time.sleep(0.2)
