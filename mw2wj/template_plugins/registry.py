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
		plugin = self.get(template.name.strip())
		if plugin is not None:
			return plugin.convert(template, context)

		if context.template_fallback == "codeblock":
			# Generic fallback: wrap the raw template invocation in a code fence
			return f"```mediawiki\n{str(template)}\n```"

		params = [f"{p.name}={p.value}" for p in template.params if p.name.strip()]
		raise MissingTemplatePluginError(template.name.strip(), params)


# Global registry instance
registry = TemplatePluginRegistry()
