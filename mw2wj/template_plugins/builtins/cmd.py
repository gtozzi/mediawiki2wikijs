# mediawiki2wikijs — MediaWiki to Wiki.js migration tool
# Copyright (C) 2026  Gabriele Tozzi <gabriele@tozzi.eu>
# SPDX-License-Identifier: AGPL-3.0-only


from __future__ import annotations

from mwparserfromhell.nodes import Template

from mw2wj.models import ConversionContext
from mw2wj.template_plugins.base import TemplatePlugin


class CmdPlugin(TemplatePlugin):
	"""Renders {{cmd|command}} as inline monospace text.

	The MediaWiki template renders an inline command with a dark
	background.  In Markdown, backtick-quoted inline code is the
	semantic equivalent for a shell command reference.
	"""

	@property
	def name(self) -> str:
		return "cmd"

	def convert(self, template: Template, context: ConversionContext) -> str:
		if template.has(1):
			cmd = str(template.get(1).value).strip()
		else:
			cmd = ""
		if not cmd:
			return "``"
		return f"`{cmd}`"
