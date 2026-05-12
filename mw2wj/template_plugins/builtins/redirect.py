# mediawiki2wikijs — MediaWiki to Wiki.js migration tool
# Copyright (C) 2026  Gabriele Tozzi <gabriele@tozzi.eu>
# SPDX-License-Identifier: AGPL-3.0-only


from __future__ import annotations

from mwparserfromhell.nodes import Template

from mw2wj.models import ConversionContext
from mw2wj.template_plugins.base import TemplatePlugin


class RedirectPlugin(TemplatePlugin):
	"""Handles #REDIRECT [[Target]] directives.

	Replaces the redirect with a link to the target page.
	"""

	@property
	def name(self) -> str:
		return "__redirect__"

	def convert(self, template: Template, context: ConversionContext) -> str:
		target = str(template.get(1).value) if template.has(1) else ""
		target = target.strip()
		if not target:
			return "> Redirect to: *(unknown target)*"
		# Convert MediaWiki page title to path
		path = target.replace(" ", "_")
		if context.lowercase_paths:
			path = path.lower()
		return f"> Redirect to: [{target}](/{path})"
