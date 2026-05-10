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
	"""Convert a page title to a WikiJS-safe path segment."""
	# Replace spaces with underscores, keep only safe chars
	path = name.replace(" ", "_")
	path = re.sub(r"[^a-zA-Z0-9_/-]", "", path)
	if lowercase:
		path = path.lower()
	return path.strip("/")
