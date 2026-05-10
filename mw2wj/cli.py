from __future__ import annotations

import argparse
import logging
import sys

import yaml

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


def run(config_path: str, dry_run: bool = False) -> None:
	config = load_config(config_path)

	if dry_run:
		config["dry_run"] = True

	setup_logging(logging.DEBUG if config.get("dry_run") else logging.INFO)

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
	)

	total_revisions = sum(len(p.revisions) for p in dump.pages)
	logger.info("Phase 2: Converting %d pages (%d revisions total)", len(dump.pages), total_revisions)

	for page in dump.pages:
		for rev in page.revisions:
			convert_revision(rev, ctx)
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

	stats = ImportStats()

	if dump.files:
		logger.info("Phase 3a: Uploading %d files", len(dump.files))
		import_files(client, dump.files, stats)

	logger.info("Phase 3b: Importing %d pages", len(dump.pages))
	import_pages(client, dump.pages, ctx, stats)

	stats.log_summary()


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

	args = parser.parse_args()

	try:
		run(args.config, args.dry_run)
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
