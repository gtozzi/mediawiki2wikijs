from __future__ import annotations

import re

from mwparserfromhell.nodes import Template

from mw2wj.models import ConversionContext
from mw2wj.template_plugins.base import TemplatePlugin


class BoxFilePlugin(TemplatePlugin):
	"""Renders {{Box File|name=...|content=...}} as a fenced code block.

	The MediaWiki template renders a red-bordered scrollable box with a
	filename header.  In Markdown, a fenced code block with a header
	comment is the closest semantic equivalent.  Handles both the
	``Box File`` and ``Box File Scroll`` template names.
	"""

	@property
	def name(self) -> str:
		return "Box File"

	def convert(self, template: Template, context: ConversionContext) -> str:
		filename = ""
		if template.has("name"):
			filename = str(template.get("name").value).strip()

		code = ""
		if template.has("content"):
			code = str(template.get("content").value).strip()
			code = re.sub(r"</?nowiki>", "", code, flags=re.IGNORECASE)

		if not code:
			return ""

		result = "```text\n"
		if filename:
			result += f"# File: {filename}\n"
		result += f"{code}\n"
		result += "```"
		return result
