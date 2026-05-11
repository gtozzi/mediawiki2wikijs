from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from mw2wj.parser import parse_dump

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_minimal_dump():
	dump = parse_dump(str(FIXTURES / "minimal_dump.xml"))

	assert dump.sitename == "TestWiki"
	assert dump.base == "http://testwiki.example.com/wiki/Main_Page"
	assert "MediaWiki" in dump.generator
	assert len(dump.namespaces) == 6
	assert dump.namespaces[0] == ""
	assert dump.namespaces[10] == "Template"
	assert dump.files == []

	assert len(dump.pages) == 2

	# Page 1: TestPage in namespace 0
	page1 = dump.pages[0]
	assert page1.title == "TestPage"
	assert page1.namespace == 0
	assert page1.namespace_name == ""
	assert len(page1.revisions) == 2
	assert not page1.is_redirect

	rev1 = page1.revisions[0]
	assert rev1.id == 1
	assert rev1.contributor == "Alice"
	assert rev1.comment == "Initial revision"
	assert rev1.timestamp == datetime.datetime(2024, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
	assert "'''TestPage'''" in rev1.text

	rev2 = page1.revisions[1]
	assert rev2.id == 2
	assert rev2.parent_id == 1
	assert rev2.contributor == "Bob"
	assert rev2.comment == "Added see also section"
	assert "[[Category:Test Category]]" in rev2.text
	assert rev2.markdown is None

	# Page 2: Template:Infobox in namespace 10
	page2 = dump.pages[1]
	assert page2.title == "Template:Infobox"
	assert page2.namespace == 10
	assert page2.namespace_name == "Template"
	assert len(page2.revisions) == 1

	rev3 = page2.revisions[0]
	assert rev3.contributor == "192.168.1.1"


def test_parse_redirect_dump():
	dump = parse_dump(str(FIXTURES / "redirect_dump.xml"))
	assert len(dump.pages) == 1

	page = dump.pages[0]
	assert page.title == "OldPage"
	assert page.is_redirect
	assert page.redirect_target == "NewPage"


def test_parse_upload_dump():
	dump = parse_dump(str(FIXTURES / "with_upload.xml"))
	assert len(dump.pages) == 1
	assert len(dump.files) == 1

	uf = dump.files[0]
	assert uf.filename == "TestImage.png"
	assert uf.contributor == "Alice"
	assert uf.size == len(uf.contents)
	assert uf.size > 0  # 1x1 transparent PNG


def test_parse_nested_upload_in_page():
	"""<upload> elements nested inside <page> must be parsed as files."""
	dump = parse_dump(str(FIXTURES / "with_nested_upload.xml"))
	assert len(dump.pages) == 1
	assert len(dump.files) == 1

	uf = dump.files[0]
	assert uf.filename == "Nested.png"
	assert uf.contributor == "Alice"
	assert uf.sha1 == "nestnestnestnestnestnestnestnestnestnest"

	page = dump.pages[0]
	assert page.namespace == 6  # File namespace


def test_missing_file_raises():
	with pytest.raises(FileNotFoundError):
		parse_dump(str(FIXTURES / "nonexistent.xml"))
