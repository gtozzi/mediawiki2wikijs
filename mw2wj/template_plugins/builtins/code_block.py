from __future__ import annotations

from mwparserfromhell.nodes import Template

from mw2wj.models import ConversionContext
from mw2wj.template_plugins.base import TemplatePlugin


class CodeBlockPlugin(TemplatePlugin):
	"""Generic fallback: wraps any template in a fenced code block."""

	@property
	def name(self) -> str:
		return "__codeblock__"

	def convert(self, template: Template, context: ConversionContext) -> str:
		return f"```mediawiki\n{str(template)}\n```"
