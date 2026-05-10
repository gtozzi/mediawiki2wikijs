from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from mwparserfromhell.nodes import Template
	from mw2wj.models import ConversionContext


class TemplatePlugin(ABC):
	@property
	@abstractmethod
	def name(self) -> str:
		"""Case-insensitive template name this plugin handles."""

	@abstractmethod
	def convert(self, template: Template, context: ConversionContext) -> str:
		"""Return Markdown string for this template invocation."""


class MissingTemplatePluginError(Exception):
	def __init__(self, template_name: str, params: list[str]):
		self.template_name = template_name
		self.params = params
		param_detail = ", ".join(params) if params else "no params"
		super().__init__(
			f"No plugin registered for template '{{{template_name}}}' (params: {param_detail}). "
			"Register a custom plugin or set template_fallback to 'codeblock' in config."
		)
