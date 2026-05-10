from __future__ import annotations

import base64
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Minimal dump with 2 pages (TestPage, Template:Infobox), 3 revisions total.
# No uploaded files.
MINIMAL_XML = FIXTURES_DIR / "minimal_dump.xml"

# A dump with a binary file upload (base64-encoded 1x1 PNG).
UPLOAD_XML = FIXTURES_DIR / "with_upload.xml"

# A dump with #REDIRECT page.
REDIRECT_XML = FIXTURES_DIR / "redirect_dump.xml"


def _write_dump(path: Path, root: ET.Element) -> None:
	ET.indent(root, space="  ")
	tree = ET.ElementTree(root)
	tree.write(path, encoding="utf-8", xml_declaration=True)


def _ns_tag(name: str) -> str:
	ns = "http://www.mediawiki.org/xml/export-0.11/"
	return f"{{{ns}}}{name}"


def _make_siteinfo() -> ET.Element:
	si = ET.Element(_ns_tag("siteinfo"))
	ET.SubElement(si, _ns_tag("sitename")).text = "TestWiki"
	ET.SubElement(si, _ns_tag("base")).text = "http://testwiki.example.com/wiki/Main_Page"
	ET.SubElement(si, _ns_tag("generator")).text = "MediaWiki 1.43"
	ET.SubElement(si, _ns_tag("case")).text = "first-letter"
	nss = ET.SubElement(si, _ns_tag("namespaces"))
	for key, name in [(0, ""), (1, "Talk"), (2, "User"), (6, "File"), (10, "Template"), (14, "Category")]:
		ns_elem = ET.SubElement(nss, _ns_tag("namespace"), key=str(key))
		ns_elem.set("case", "first-letter")
		ns_elem.text = name
	return si


def _make_page(title: str, page_id: int, ns: int, revisions: list[dict[str, Any]]) -> ET.Element:
	page = ET.Element(_ns_tag("page"))
	ET.SubElement(page, _ns_tag("title")).text = title
	ET.SubElement(page, _ns_tag("ns")).text = str(ns)
	ET.SubElement(page, _ns_tag("id")).text = str(page_id)
	for rev_data in revisions:
		rev = ET.SubElement(page, _ns_tag("revision"))
		ET.SubElement(rev, _ns_tag("id")).text = str(rev_data["id"])
		if "parent_id" in rev_data:
			ET.SubElement(rev, _ns_tag("parentid")).text = str(rev_data["parent_id"])
		ET.SubElement(rev, _ns_tag("timestamp")).text = rev_data["timestamp"]
		contrib = ET.SubElement(rev, _ns_tag("contributor"))
		if "username" in rev_data:
			ET.SubElement(contrib, _ns_tag("username")).text = rev_data["username"]
			ET.SubElement(contrib, _ns_tag("id")).text = str(rev_data.get("user_id", 1))
		else:
			ET.SubElement(contrib, _ns_tag("ip")).text = rev_data.get("ip", "127.0.0.1")
		if rev_data.get("minor"):
			ET.SubElement(rev, _ns_tag("minor"))
		if "comment" in rev_data:
			ET.SubElement(rev, _ns_tag("comment")).text = rev_data["comment"]
		ET.SubElement(rev, _ns_tag("model")).text = "wikitext"
		ET.SubElement(rev, _ns_tag("format")).text = "text/x-wiki"
		text_elem = ET.SubElement(rev, _ns_tag("text"))
		text_elem.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
		text_elem.set("bytes", str(len(rev_data["text"])))
		text_elem.text = rev_data["text"]
		ET.SubElement(rev, _ns_tag("sha1")).text = "abc123" * 7
	return page


def _make_upload(filename: str, contents: bytes, timestamp: str, contributor: str) -> ET.Element:
	upload = ET.Element(_ns_tag("upload"))
	ET.SubElement(upload, _ns_tag("filename")).text = filename
	ET.SubElement(upload, _ns_tag("timestamp")).text = timestamp
	contrib = ET.SubElement(upload, _ns_tag("contributor"))
	ET.SubElement(contrib, _ns_tag("username")).text = contributor
	ET.SubElement(contrib, _ns_tag("id")).text = "1"
	ET.SubElement(upload, _ns_tag("size")).text = str(len(contents))
	ET.SubElement(upload, _ns_tag("sha1")).text = "up1" * 10
	contents_elem = ET.SubElement(upload, _ns_tag("contents"))
	contents_elem.text = base64.b64encode(contents).decode("ascii")
	return upload


# Minimal 1x1 transparent PNG
MINI_PNG = base64.b64decode(
	"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
	"+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

# --- Build and write fixture files ---

# with_upload.xml
root_upload = ET.Element(_ns_tag("mediawiki"))
root_upload.set("xmlns", "http://www.mediawiki.org/xml/export-0.11/")
root_upload.set("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation",
	"http://www.mediawiki.org/xml/export-0.11/ http://www.mediawiki.org/xml/export-0.11.xsd")
root_upload.set("version", "0.11")
root_upload.set("xml:lang", "en")
root_upload.append(_make_siteinfo())
root_upload.append(_make_page("TestPage", 1, 0, [
	{"id": 1, "timestamp": "2024-01-01T12:00:00Z", "username": "Alice",
	 "comment": "Initial", "text": "Hello!"},
]))
root_upload.append(_make_upload("TestImage.png", MINI_PNG, "2024-01-01T12:00:00Z", "Alice"))
_write_dump(UPLOAD_XML, root_upload)

# redirect_dump.xml
root_redirect = ET.Element(_ns_tag("mediawiki"))
root_redirect.set("xmlns", "http://www.mediawiki.org/xml/export-0.11/")
root_redirect.set("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation",
	"http://www.mediawiki.org/xml/export-0.11/ http://www.mediawiki.org/xml/export-0.11.xsd")
root_redirect.set("version", "0.11")
root_redirect.set("xml:lang", "en")
root_redirect.append(_make_siteinfo())
root_redirect.append(_make_page("OldPage", 1, 0, [
	{"id": 1, "timestamp": "2024-01-01T12:00:00Z", "username": "Alice",
	 "comment": "Created", "text": "#REDIRECT [[NewPage]]"},
]))
_write_dump(REDIRECT_XML, root_redirect)
