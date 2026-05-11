from __future__ import annotations

import argparse
import logging
import sys

import yaml

import mw2wj.template_plugins  # noqa: F401 — loads builtin plugins
from mw2wj.converter import convert_revision
from mw2wj.importer import ImportStats, import_files, import_pages
from mw2wj.models import ConversionContext
from mw2wj.parser import parse_dump
from mw2wj.utils import setup_logging
from mw2wj.wikijs_client import WikiJSClient

logger = logging.getLogger(__name__)


def load_config(path: str) -> dict:
	with open(path, "r") as f:
		config = yaml.safe_load(f)
	if config is None:
		raise ValueError(f"Config file '{path}' is empty")
	for key in ("wiki_url", "input_xml"):
		if key not in config:
			raise ValueError(f"Missing required config key: '{key}'")
	return config


def run(config_path: str, dry_run: bool = False, log_level: int = logging.INFO, skip_failed: bool = False, prune: bool = False, force: bool = False) -> None:
	config = load_config(config_path)

	if dry_run:
		config["dry_run"] = True

	# Verbose/quiet flags override the default, but dry-run mode
	# still bumps to DEBUG unless the user explicitly set quiet.
	if log_level != logging.INFO or not config.get("dry_run"):
		setup_logging(log_level)
	else:
		setup_logging(logging.DEBUG)

	dry_run_mode = config.get("dry_run", False)
	logger.info("Starting %s", "dry run" if dry_run_mode else "import")

	# Phase 1: Parse
	logger.info("Phase 1: Parsing XML dump '%s'", config["input_xml"])
	dump = parse_dump(config["input_xml"])
	logger.info(
		"Parsed: sitename=%s, pages=%d, files=%d",
		dump.sitename, len(dump.pages), len(dump.files),
	)

	# Phase 2: Convert
	ctx = ConversionContext(
		category_mode=config.get("category_mode", "tag"),
		namespace_separator=config.get("namespace_separator", "/"),
		exclude_namespaces=config.get("exclude_namespaces", []),
		lowercase_paths=config.get("lowercase_paths", False),
		template_fallback=config.get("template_fallback", "error"),
		preprocess_rules=config.get("preprocess_rules", []),
		locale=config.get("locale", "en"),
		include_metadata=config.get("include_metadata", True),
		file_upload_dir=config.get("file_upload_dir", "import_mw"),
		include_edit_description=config.get("include_edit_description", True),
	)

	total_revisions = sum(len(p.revisions) for p in dump.pages)
	logger.info("Phase 2: Converting %d pages (%d revisions total)", len(dump.pages), total_revisions)

	for page in dump.pages:
		# Skip pages in excluded namespaces — they are listed
		# in the config and will also be filtered at import time.
		# Skipping them here avoids needless pandoc conversion.
		if page.namespace_name in ctx.exclude_namespaces:
			logger.debug("Skipping %s page '%s'", page.namespace_name, page.title)
			continue
		ctx.current_namespace = page.namespace
		ctx.collected_categories.clear()
		for rev in page.revisions:
			try:
				convert_revision(rev, ctx)
			except RuntimeError as e:
				logger.error(
					"Conversion failed for page '%s' (rev %d): %s",
					page.title, rev.id, e,
				)
				if skip_failed:
					continue
				raise
		page.categories = list(ctx.collected_categories)
	logger.info("Conversion complete")

	if dry_run_mode:
		logger.info("Dry run complete — stopping before import")
		_print_dry_run_summary(dump)
		return

	# Phase 3: Import
	client = WikiJSClient(
		base_url=config["wiki_url"],
		api_token=config.get("api_token", ""),
	)

	if not config.get("api_token"):
		raise ValueError("API token is required for import — set 'api_token' in config")

	if prune:
		_prune_existing_pages(client, force)

	stats = ImportStats()

	if dump.files:
		logger.info("Phase 3a: Uploading %d files", len(dump.files))
		import_files(client, dump.files, stats, upload_dir=config.get("file_upload_dir", "import_mw"), skip_failed=skip_failed, lowercase_paths=config.get("lowercase_paths", False))

	logger.info("Phase 3b: Importing %d pages", len(dump.pages))
	is_private = config.get("is_private", True)
	locale = config.get("locale", "en")
	import_pages(client, dump.pages, ctx, stats, skip_failed=skip_failed, is_private=is_private, locale=locale)

	stats.log_summary()

	# If home_page is configured, rename that page to "home"
	# so it becomes the wiki landing page.
	home_page = config.get("home_page")
	if home_page:
		_set_home_page(client, home_page, config.get("locale", "en"), config["wiki_url"])


def _set_home_page(client: WikiJSClient, page_path: str, locale: str, wiki_url: str) -> None:
	"""Rename a page to 'home' so it becomes the wiki landing page.

	Wiki.js determines the home page by convention: the page at path
	"home" is served at the root URL.  This operation finds the
	specified page, fetches its full content, and re-creates it at
	path "home" via the pages.update mutation.

	@param client: Authenticated WikiJSClient
	@param page_path: The sanitized page path (without locale prefix)
	@param locale: Locale code (e.g. "it", "en")
	@param wiki_url: Wiki.js base URL (for the final log message)
	"""
	# The source path in Wiki.js includes the locale prefix
	source_path = f"{locale}/{page_path}"

	logger.info("Looking for page with path '%s'", source_path)
	pages = client.list_pages()
	match = None
	for p in pages:
		if p.get("path") == source_path:
			match = p
			break

	if not match:
		# Try without locale prefix
		for p in pages:
			if p.get("path") == page_path:
				match = p
				break

	if not match:
		logger.error(
			"Page with path '%s' not found. Available paths: %s",
			source_path,
			", ".join(p.get("path", "?") for p in pages[:20]),
		)
		sys.exit(1)

	# Fetch full page data so we can re-submit content via update_page
	page_data = client.get_page(match["id"])
	target_path = "home"
	logger.info(
		"Moving page '%s' (id=%d) from '%s' to '%s'",
		page_data.get("title"), page_data["id"], page_data.get("path"), target_path,
	)
	# Extract tag strings from PageTag objects ({id, tag})
	raw_tags = page_data.get("tags", [])
	tag_names = [t["tag"] for t in raw_tags] if raw_tags else []
	client.update_page(
		page_data["id"],
		target_path,
		page_data.get("content", ""),
		page_data.get("title", ""),
		description="Set as home page",
		is_private=page_data.get("isPrivate", True),
		locale=page_data.get("locale", locale),
		tags=tag_names,
	)
	logger.info("Home page set — visit %s to verify", wiki_url)


def _prune_existing_pages(client: WikiJSClient, force: bool) -> None:
	"""Delete all existing pages from the wiki.

	Fetches the current page list, asks for confirmation (unless --force),
	and deletes every page one by one.  Intended for re-running an
	interrupted import on a clean slate.
	"""
	pages = client.list_pages()
	if not pages:
		logger.info("No existing pages to prune")
		return

	logger.info("Found %d existing page(s) to delete", len(pages))
	for p in pages:
		logger.info("  - %s (id=%d)", p.get("title", p.get("path")), p["id"])

	if not force:
		print(f"\nThis will permanently delete ALL {len(pages)} page(s) from the wiki.")
		print("This action cannot be undone.")
		try:
			answer = input("Continue? [y/N] ")
		except (EOFError, KeyboardInterrupt):
			print("Aborted")
			sys.exit(130)
		if answer.strip().lower() not in ("y", "yes"):
			print("Aborted")
			sys.exit(0)

	for i, p in enumerate(pages):
		logger.info("Deleting page %d/%d: %s", i + 1, len(pages), p.get("title", p.get("path")))
		client.delete_page(p["id"])

	logger.info("Prune complete — %d page(s) deleted", len(pages))


def _print_dry_run_summary(dump) -> None:
	logger.info("")
	logger.info("=== Dry Run Summary ===")
	logger.info("Site: %s (%s)", dump.sitename, dump.generator)
	logger.info("Namespaces: %d", len(dump.namespaces))
	logger.info("Pages: %d", len(dump.pages))
	logger.info("Files: %d", len(dump.files))
	total_revs = sum(len(p.revisions) for p in dump.pages)
	redirects = sum(1 for p in dump.pages if p.is_redirect)
	logger.info("Total revisions: %d", total_revs)
	logger.info("Redirects: %d", redirects)
	logger.info("=== Ready for import ===")


def main() -> None:
	parser = argparse.ArgumentParser(
		prog="mediawiki2wikijs",
		description="Migrate a MediaWiki XML dump into Wiki.js",
		epilog="For XML dump generation help, see https://www.mediawiki.org/wiki/Manual:DumpBackup.php",
	)
	parser.add_argument(
		"-c", "--config",
		required=True,
		help="Path to YAML config file (see config.example.yaml)",
	)
	parser.add_argument(
		"--dry-run",
		action="store_true",
		help="Parse and convert only, do not import (overrides config setting)",
	)
	verbosity = parser.add_mutually_exclusive_group()
	verbosity.add_argument(
		"-v", "--verbose",
		action="store_true",
		help="Enable debug-level logging",
	)
	verbosity.add_argument(
		"-q", "--quiet",
		action="store_true",
		help="Suppress info messages, show warnings and errors only",
	)
	parser.add_argument(
		"--skip-failed",
		action="store_true",
		help="Continue importing even if some pages fail to convert",
	)
	parser.add_argument(
		"--prune",
		action="store_true",
		help="Delete ALL existing pages from the wiki before importing. "
		     "Useful for re-running an interrupted or incomplete import. "
		     "Will prompt for confirmation unless --force is also passed.",
	)
	parser.add_argument(
		"-f", "--force",
		action="store_true",
		help="Skip confirmation prompts (currently only affects --prune)",
	)

	args = parser.parse_args()

	if args.verbose:
		log_level = logging.DEBUG
	elif args.quiet:
		log_level = logging.WARNING
	else:
		log_level = logging.INFO

	try:
		run(args.config, args.dry_run, log_level, args.skip_failed,
		    prune=args.prune, force=args.force)
	except FileNotFoundError as e:
		logger.error("File not found: %s", e)
		sys.exit(1)
	except ValueError as e:
		logger.error("Configuration error: %s", e)
		sys.exit(1)
	except KeyboardInterrupt:
		logger.info("Interrupted by user")
		sys.exit(130)
	except Exception as e:
		logger.error("Unexpected error: %s", e, exc_info=True)
		sys.exit(2)
