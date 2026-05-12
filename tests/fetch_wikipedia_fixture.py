#!/usr/bin/env python3
"""Download real Wikipedia XML exports for integration testing.

Usage:
  python3 tests/fetch_wikipedia_fixture.py

Downloads Wikipedia pages via Special:Export and saves them as XML
fixtures. The fixture files are git-ignored (licensing: Wikipedia text
is CC BY-SA). Tests auto-download missing fixtures on first run.

To share fixtures in a team, distribute them through a private channel
or run this script once per checkout.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Pages chosen to cover diverse wikitext features.
# Each page exercises different conversion paths: infoboxes, tables,
# math notation, coordinates, nested lists, quotes, citations, etc.
PAGES_TO_FETCH: list[dict[str, str | int]] = [
	{
		"title": "Ada_Lovelace",
		"description": "Biography: infobox, citations, categories, images",
		"revisions": 2,
	},
	{
		"title": "Quicksort",
		"description": "Technical: code blocks, algorithms, lists",
		"revisions": 2,
	},
	{
		"title": "Python_(programming_language)",
		"description": "Software: infobox, tables, code samples, dense citations",
		"revisions": 1,
	},
	{
		"title": "Molecule",
		"description": "Science: infobox, tables, chemistry, manageable size",
		"revisions": 1,
	},
	{
		"title": "Charles_Babbage",
		"description": "Biography: infobox, images, redirects point here",
		"revisions": 1,
	},
	{
		"title": "Hello,_World!",
		"description": "Disambiguation: lists, cross-references",
		"revisions": 1,
	},
	{
		"title": "Template:Blockquote",
		"description": "Template namespace: {{{param}}} syntax, parser functions",
		"revisions": 1,
	},
	{
		"title": "Category:Computer_programming",
		"description": "Category namespace: subcategories, category links",
		"revisions": 1,
	},
	{
		"title": "Trigonometry",
		"description": "Math: LaTeX-style formulas, history, diagrams",
		"revisions": 1,
	},
	{
		"title": "Himalayas",
		"description": "Geography: coordinates, mountain ranges, climbing, manageable size",
		"revisions": 1,
	},
	{
		"title": "DNA",
		"description": "Science: complex infobox, heavy citations, gene tables",
		"revisions": 1,
	},
	{
		"title": "William_Shakespeare",
		"description": "Literature: quotes, extensive bibliography, plays lists",
		"revisions": 1,
	},
	{
		"title": "Venus",
		"description": "Astronomy: planet infobox, science, atmosphere, exploration",
		"revisions": 1,
	},
	{
		"title": "Wikipedia:About",
		"description": "Project namespace: meta page with different formatting style",
		"revisions": 1,
	},
	{
		"title": "Kyoto",
		"description": "Geography: infobox settlement, history, transport, manageable size",
		"revisions": 1,
	},
	{
		"title": "Marie_Curie",
		"description": "Biography: Nobel prize infobox, citations, science history",
		"revisions": 1,
	},
	{
		"title": "Logic",
		"description": "Philosophy: formal notation, history, lists, manageable size",
		"revisions": 1,
	},
	{
		"title": "Industrial_Revolution",
		"description": "History: infobox, timelines, economic tables, citations",
		"revisions": 1,
	},
	{
		"title": "Help:Contents",
		"description": "Help namespace: boxes, icons, multi-column layout",
		"revisions": 1,
	},
	{
		"title": "Wikipedia:List_of_policies",
		"description": "Project namespace: dense link lists, shortcut boxes",
		"revisions": 1,
	},
	{
		"title": "Red_bean_paste",
		"description": "Short article: stub-length, few links, simple structure",
		"revisions": 1,
	},
	{
		"title": "Chocolate",
		"description": "Food: etymology, varieties, nutrition infobox, production",
		"revisions": 1,
	},
	{
		"title": "Coffee",
		"description": "Food/drink: infobox, cultivation, processing, history",
		"revisions": 1,
	},
	{
		"title": "Penguin",
		"description": "Animal: species taxobox, biology, conservation, gallery",
		"revisions": 1,
	},
	{
		"title": "Helium",
		"description": "Element: element infobox, physics properties, isotopes table",
		"revisions": 1,
	},
	{
		"title": "Sonata",
		"description": "Music: lists of movements, composers, audio templates",
		"revisions": 1,
	},
	{
		"title": "Common_cold",
		"description": "Medicine: disease infobox, symptoms, prevention, citations",
		"revisions": 1,
	},
]

EXPORT_URL = "https://en.wikipedia.org/w/index.php"


def fetch_export(title: str, limit: int = 1) -> str | None:
	"""Fetch a page in MediaWiki XML export format.

	@param title: Wikipedia page title (underscored)
	@param limit: Max number of revisions to include
	@returns: Raw XML string, or None on failure
	"""
	params: dict[str, str | int] = {
		"title": "Special:Export",
		"pages": title,
		"limit": limit,
	}
	if limit == 1:
		params["curonly"] = "1"
	url = f"{EXPORT_URL}?{urlencode(params)}"

	response = requests.get(url, timeout=60, headers={"User-Agent": "mediawiki2wikijs-test/0.1"})
	if not response.ok:
		logger.error("HTTP %d fetching '%s'", response.status_code, title)
		return None

	text = response.text
	if "<mediawiki" not in text[:500]:
		logger.warning("Response does not look like a MediaWiki XML dump for '%s'", title)
		return None

	return text


def fixture_path_for(title: str) -> Path:
	"""Return the expected fixture path for a page title."""
	return FIXTURES_DIR / f"wikipedia_{title}.xml"


def ensure_fixtures() -> bool:
	"""Download any missing Wikipedia fixtures.

	@returns: True if all fixtures are present (or were downloaded), False on failure
	"""
	FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
	missing = 0

	for page_spec in PAGES_TO_FETCH:
		title = str(page_spec["title"])
		desc = str(page_spec["description"])
		limit = int(page_spec["revisions"])
		output_path = fixture_path_for(title)

		if output_path.exists():
			continue

		logger.info("Downloading '%s' (%s)...", title, desc)
		xml = fetch_export(title, limit)
		if xml is None:
			logger.error("Failed to fetch '%s' – tests using it will be skipped", title)
			missing += 1
			continue

		output_path.write_text(xml, encoding="utf-8")
		file_size = output_path.stat().st_size
		logger.info("Saved %s (%d bytes)", output_path.name, file_size)

	if missing:
		logger.warning("%d fixture(s) could not be downloaded", missing)
		return False
	return True


def main() -> int:
	success = ensure_fixtures()
	return 0 if success else 1


if __name__ == "__main__":
	sys.exit(main())
