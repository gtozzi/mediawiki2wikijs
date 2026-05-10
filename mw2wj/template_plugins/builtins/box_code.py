from __future__ import annotations

import re

from mwparserfromhell.nodes import Template

from mw2wj.models import ConversionContext
from mw2wj.template_plugins.base import TemplatePlugin


class BoxCodePlugin(TemplatePlugin):
	"""Renders {{Box Code|Description|Code}} as a fenced code block.

	The MediaWiki template renders a green-bordered box with a header
	showing the description and the code below.  In Markdown, a fenced
	code block preceded by a bold description line is the closest
	semantic equivalent.
	"""

	@property
	def name(self) -> str:
		return "Box Code"

	def convert(self, template: Template, context: ConversionContext) -> str:
		desc = ""
		if template.has(1):
			desc = str(template.get(1).value).strip()

		code = ""
		if template.has(2):
			code = str(template.get(2).value).strip()
			# Strip <nowiki> wrappers used to escape wikitext inside code
			code = re.sub(r"</?nowiki>", "", code, flags=re.IGNORECASE)

		if not code:
			return ""

		result = "```text\n"
		if desc:
			result += f"# Code: {desc}\n"
		result += f"{code}\n"
		result += "```"
		return result
