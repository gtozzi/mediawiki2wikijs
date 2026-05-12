# mediawiki2wikijs — MediaWiki to Wiki.js migration tool
# Copyright (C) 2026  Gabriele Tozzi <gabriele@tozzi.eu>
# SPDX-License-Identifier: AGPL-3.0-only


from __future__ import annotations

from mwparserfromhell.nodes import Template

from mw2wj.models import ConversionContext
from mw2wj.template_plugins.base import TemplatePlugin


class CommandlinePlugin(TemplatePlugin):
	"""Renders {{Commandline|cmd=...}} as a fenced shell code block.

	The MediaWiki template renders a black-background box with the command
	text.  In Markdown, a fenced code block with a ``shell`` language tag
	is the closest semantic equivalent, and renders with a dark background
	in most Markdown renderers (Wiki.js, GitHub, etc.).
	"""

	@property
	def name(self) -> str:
		return "Commandline"

	def convert(self, template: Template, context: ConversionContext) -> str:
		import re

		cmd = ""
		if template.has("cmd"):
			cmd = str(template.get("cmd").value).strip()

		# Strip <nowiki> tags so pandoc does not escape > to &gt; inside them
		cmd = re.sub(r"</?nowiki>", "", cmd, flags=re.IGNORECASE)

		if not cmd:
			return ""

		return f"```shell\n{cmd}\n```"
