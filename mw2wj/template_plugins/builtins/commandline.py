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
		cmd = ""
		if template.has("cmd"):
			cmd = str(template.get("cmd").value).strip()

		# Determine prompt: # for root, $ for user
		is_root = False
		if template.has("root"):
			root_val = str(template.get("root").value).strip().lower()
			is_root = root_val not in ("", "no", "0", "false")
		prompt = "# " if is_root else "$ "

		# Normalise trailing newlines
		cmd = cmd.rstrip("\n")

		if not cmd:
			return "```shell\n```"

		# Prefix each non-empty line with the prompt
		lines = cmd.split("\n")
		prompted = "\n".join(prompt + line if line.strip() else line for line in lines)

		return f"```shell\n{prompted}\n```"
