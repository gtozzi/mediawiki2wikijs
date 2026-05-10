from __future__ import annotations

import base64
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from mw2wj.models import DumpInfo, Page, Revision, UploadedFile

logger = logging.getLogger(__name__)

MW_XML_NS = "http://www.mediawiki.org/xml/export-0.11/"


def _tag(name: str) -> str:
	return f"{{{MW_XML_NS}}}{name}"


def _find_text(element: ET.Element, name: str) -> str | None:
	child = element.find(_tag(name))
	if child is not None:
		return child.text
	return None


def _require_text(element: ET.Element, name: str, context: str) -> str:
	value = _find_text(element, name)
	if value is None:
		raise ValueError(f"Missing required element <{name}> in {context}")
	return value


def parse_dump(filepath: str) -> DumpInfo:
	tree = ET.parse(filepath)
	root = tree.getroot()

	# The root tag may use different schema versions; find the actual ns from the tag.
	# ElementTree stores the ns in the tag like {http://...}mediawiki
	# We'll search for siteinfo and page elements regardless of schema version.
	siteinfo = root.find(_tag("siteinfo"))
	if siteinfo is None:
		# Try older common schema versions
		global MW_XML_NS
		for ns_ver in ("0.10", "0.8", "0.7"):
			test_ns = f"http://www.mediawiki.org/xml/export-{ns_ver}/"
			siteinfo = root.find(f"{{{test_ns}}}siteinfo")
			if siteinfo is not None:
				MW_XML_NS = test_ns
				break
		if siteinfo is None:
			raise ValueError("Could not find <siteinfo> element — unknown XML schema version")

	sitename = _require_text(siteinfo, "sitename", "siteinfo")
	base = _require_text(siteinfo, "base", "siteinfo")
	generator = _require_text(siteinfo, "generator", "siteinfo")

	namespaces: dict[int, str] = {}
	for ns_elem in siteinfo.findall(_tag("namespaces") + "/" + _tag("namespace")):
		key_str = ns_elem.get("key")
		if key_str is not None:
			namespaces[int(key_str)] = ns_elem.text or ""

	pages: list[Page] = []
	files: list[UploadedFile] = []

	for page_elem in root.findall(_tag("page")):
		page = _parse_page(page_elem, namespaces)
		if page is not None:
			pages.append(page)

	for file_elem in root.findall(_tag("upload")):
		uf = _parse_upload(file_elem)
		if uf is not None:
			files.append(uf)

	logger.info("Parsed dump: %d pages, %d files, %d namespaces", len(pages), len(files), len(namespaces))
	if not pages:
		logger.warning("No pages found in dump")
	if not files:
		logger.warning("No uploaded files found in dump (use --uploads --include-files when generating)")

	return DumpInfo(
		sitename=sitename,
		base=base,
		generator=generator,
		namespaces=namespaces,
		pages=pages,
		files=files,
	)


def _parse_page(page_elem: ET.Element, namespaces: dict[int, str]) -> Page | None:
	title = _require_text(page_elem, "title", "page")
	ns_str = _require_text(page_elem, "ns", f"page '{title}'")
	id_str = _require_text(page_elem, "id", f"page '{title}'")

	ns = int(ns_str)
	page_id = int(id_str)
	namespace_name = namespaces.get(ns, "")

	revisions: list[Revision] = []
	for rev_elem in page_elem.findall(_tag("revision")):
		rev = _parse_revision(rev_elem, title)
		if rev is not None:
			revisions.append(rev)

	# Validate revision ordering (oldest first)
	for i in range(len(revisions) - 1):
		if revisions[i].timestamp > revisions[i + 1].timestamp:
			logger.warning(
				"Revisions out of order for page '%s': rev %d (%s) after rev %d (%s)",
				title, revisions[i].id, revisions[i].timestamp,
				revisions[i + 1].id, revisions[i + 1].timestamp,
			)

	if not revisions:
		logger.warning("Page '%s' has no revisions, skipping", title)
		return None

	return Page(
		id=page_id,
		title=title,
		namespace=ns,
		namespace_name=namespace_name,
		revisions=revisions,
	)


def _parse_revision(rev_elem: ET.Element, page_title: str) -> Revision | None:
	rev_id = int(_require_text(rev_elem, "id", f"revision in page '{page_title}'"))

	parent_id_str = _find_text(rev_elem, "parentid")
	parent_id = int(parent_id_str) if parent_id_str else None

	timestamp_str = _require_text(rev_elem, "timestamp", f"revision {rev_id}")
	timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

	contributor_elem = rev_elem.find(_tag("contributor"))
	if contributor_elem is not None:
		username = _find_text(contributor_elem, "username")
		if username:
			contributor = username
		else:
			contributor = _find_text(contributor_elem, "ip") or "Unknown"
	else:
		contributor = "Unknown"

	comment = _find_text(rev_elem, "comment")

	text_elem = rev_elem.find(_tag("text"))
	if text_elem is None:
		logger.warning("Revision %d of page '%s' has no <text> element, skipping", rev_id, page_title)
		return None

	text = text_elem.text or ""

	return Revision(
		id=rev_id,
		parent_id=parent_id,
		timestamp=timestamp,
		contributor=contributor,
		comment=comment,
		text=text,
	)


def _parse_upload(file_elem: ET.Element) -> UploadedFile | None:
	filename = _require_text(file_elem, "filename", "upload")
	timestamp_str = _require_text(file_elem, "timestamp", f"upload '{filename}'")
	timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

	contributor_elem = file_elem.find(_tag("contributor"))
	if contributor_elem is not None:
		username = _find_text(contributor_elem, "username")
		contributor = username if username else (_find_text(contributor_elem, "ip") or "Unknown")
	else:
		contributor = "Unknown"

	size_str = _require_text(file_elem, "size", f"upload '{filename}'")
	sha1_text = _require_text(file_elem, "sha1", f"upload '{filename}'")

	contents_elem = file_elem.find(_tag("contents"))
	if contents_elem is None or contents_elem.text is None:
		logger.warning("Upload '%s' has no <contents>, skipping", filename)
		return None

	contents = base64.b64decode(contents_elem.text.strip())

	return UploadedFile(
		filename=filename,
		timestamp=timestamp,
		contributor=contributor,
		size=int(size_str),
		sha1=sha1_text,
		contents=contents,
	)
