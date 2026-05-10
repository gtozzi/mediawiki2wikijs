from __future__ import annotations

from mwparserfromhell.nodes import Template

from mw2wj.models import ConversionContext
from mw2wj.template_plugins.base import TemplatePlugin


class CodeBlockPlugin(TemplatePlugin):
	"""Generic fallback: marks the template as an inline note, preserving
	its name and first few parameters without raw wikitext syntax."""

	@property
	def name(self) -> str:
		return "__codeblock__"

	def convert(self, template: Template, context: ConversionContext) -> str:
		params = [str(p.value).strip() for p in template.params if p.name.strip()]
		summary = ", ".join(params[:3])
		if len(params) > 3:
			summary += ", ..."
		result = f"[Template: {template.name.strip()}]"
		if summary:
			collapsed = " ".join(summary.split())
			if len(collapsed) > 120:
				collapsed = collapsed[:117] + "..."
			result = f"[Template: {template.name.strip()}: {collapsed}]"
		return result
