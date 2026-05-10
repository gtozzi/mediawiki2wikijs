from __future__ import annotations

from mwparserfromhell.nodes import Template

from mw2wj.models import ConversionContext
from mw2wj.template_plugins.base import MissingTemplatePluginError, TemplatePlugin


class TemplatePluginRegistry:
	def __init__(self):
		self._plugins: dict[str, TemplatePlugin] = {}

	def register(self, plugin: TemplatePlugin) -> None:
		key = plugin.name.lower()
		if key in self._plugins:
			raise ValueError(f"Template plugin '{plugin.name}' is already registered")
		self._plugins[key] = plugin

	def get(self, template_name: str) -> TemplatePlugin | None:
		return self._plugins.get(template_name.lower())

	def convert(self, template: Template, context: ConversionContext) -> str:
		name = template.name.strip()
		plugin = self.get(name)
		if plugin is not None:
			return plugin.convert(template, context)

		if context.template_fallback == "codeblock":
			params = [str(p.value).strip() for p in template.params if p.name.strip()]
			summary = ", ".join(params[:3])
			if len(params) > 3:
				summary += ", ..."
			result = f"[Template: {name}]"
			if summary:
				collapsed = " ".join(summary.split())
				if len(collapsed) > 120:
					collapsed = collapsed[:117] + "..."
				result = f"[Template: {name}: {collapsed}]"
			return result

		params = [f"{p.name}={p.value}" for p in template.params if p.name.strip()]
		raise MissingTemplatePluginError(name, params)
# Global registry instance
registry = TemplatePluginRegistry()
