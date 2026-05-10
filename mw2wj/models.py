from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Revision:
	id: int
	parent_id: int | None
	timestamp: datetime
	contributor: str
	comment: str | None
	text: str
	markdown: str | None = None


@dataclass
class Page:
	id: int
	title: str
	namespace: int
	namespace_name: str
	revisions: list[Revision] = field(default_factory=list)

	@property
	def is_redirect(self) -> bool:
		if not self.revisions:
			return False
		text = self.revisions[-1].text.strip().lower()
		return text.startswith("#redirect") or text.startswith("#redirect")

	@property
	def redirect_target(self) -> str | None:
		if not self.is_redirect:
			return None
		text = self.revisions[-1].text.strip()
		prefix = "#REDIRECT" if text.startswith("#REDIRECT") else "#redirect"
		target = text[len(prefix):].strip()
		target = target.removeprefix("[[")
		target = target.removesuffix("]]")
		return target.split("|")[0].strip()


@dataclass
class UploadedFile:
	filename: str
	timestamp: datetime
	contributor: str
	size: int
	sha1: str
	contents: bytes


@dataclass
class DumpInfo:
	sitename: str
	base: str
	generator: str
	namespaces: dict[int, str] = field(default_factory=dict)
	pages: list[Page] = field(default_factory=list)
	files: list[UploadedFile] = field(default_factory=list)


class ConversionContext:
	def __init__(
		self,
		category_mode: str = "tag",
		namespace_separator: str = "/",
		exclude_namespaces: list[str] | None = None,
		lowercase_paths: bool = False,
		template_fallback: str = "error",
	):
		self.category_mode = category_mode
		self.namespace_separator = namespace_separator
		self.exclude_namespaces = exclude_namespaces or []
		self.lowercase_paths = lowercase_paths
		self.template_fallback = template_fallback
