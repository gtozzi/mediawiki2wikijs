# mediawiki2wikijs — MediaWiki to Wiki.js migration tool
# Copyright (C) 2026  Gabriele Tozzi <gabriele@tozzi.eu>
# SPDX-License-Identifier: AGPL-3.0-only


from __future__ import annotations

from mwparserfromhell.nodes import Template

from mw2wj.models import ConversionContext
from mw2wj.template_plugins.base import TemplatePlugin


class FilenamePlugin(TemplatePlugin):
	"""Renders {{Filename|File Name}} as inline monospace text.

	The MediaWiki template renders a filename in green monospace.  In
	Markdown, backtick-quoted inline code is the semantic equivalent for
	a filename or path reference.
	"""

	@property
	def name(self) -> str:
		return "Filename"

	def convert(self, template: Template, context: ConversionContext) -> str:
		if template.has(1):
			name = str(template.get(1).value).strip()
		else:
			name = ""
		if not name:
			return "``"
		return f"`{name}`"
