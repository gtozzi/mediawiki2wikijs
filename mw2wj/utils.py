from __future__ import annotations

import logging
import re


def setup_logging(level: int = logging.INFO) -> None:
	logging.basicConfig(
		level=level,
		format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
		datefmt="%Y-%m-%d %H:%M:%S",
	)


def sanitize_path(name: str, lowercase: bool = False) -> str:
	"""Convert a page title to a WikiJS-safe path segment.

	Invalid characters are replaced with underscores and consecutive
	underscores are collapsed, so "File::Something" becomes
	"File_Something" instead of silently losing the separator.

	@param name: Page title or path segment
	@param lowercase: If True, convert to lowercase
	@returns: Safe path segment
	"""
	# Replace any run of characters that are not alphanumeric,
	# underscore, slash, or hyphen with a single underscore.
	path = re.sub(r"[^a-zA-Z0-9_/-]+", "_", name)
	# Collapse consecutive underscores
	path = re.sub(r"_+", "_", path)
	if lowercase:
		path = path.lower()
	return path.strip("/")


def sanitize_filename(name: str, lowercase: bool = False) -> str:
	"""Sanitize a filename for Wiki.js assets, preserving the extension.

	The base name is sanitized like a page path, then the extension
	(lowercased if requested) is reattached with a dot.

	@param name: Original filename (e.g. "Diagram 1.PNG")
	@param lowercase: If True, convert both base and extension to lowercase
	@returns: Safe filename (e.g. "Diagram_1.png")
	"""
	parts = name.rsplit(".", 1)
	base = parts[0] if parts else name
	ext = parts[1] if len(parts) == 2 else ""
	safe_base = sanitize_path(base, lowercase)
	if ext:
		# Keep extension characters but collapse runs of non-alnum
		safe_ext = re.sub(r"[^a-zA-Z0-9]+", "_", ext)
		if lowercase:
			safe_ext = safe_ext.lower()
		return f"{safe_base}.{safe_ext}"
	return safe_base
