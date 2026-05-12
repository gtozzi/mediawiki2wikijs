# mediawiki2wikijs — MediaWiki to Wiki.js migration tool
# Copyright (C) 2026  Gabriele Tozzi <gabriele@tozzi.eu>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


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
	categories: list[str] = field(default_factory=list)

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
		current_namespace: int = 0,
		preprocess_rules: list[dict[str, str]] | None = None,
		locale: str = "en",
		include_metadata: bool = True,
		file_upload_dir: str = "import_mw",
		include_edit_description: bool = True,
	):
		self.category_mode = category_mode
		self.namespace_separator = namespace_separator
		self.exclude_namespaces = exclude_namespaces or []
		self.lowercase_paths = lowercase_paths
		self.template_fallback = template_fallback
		self.current_namespace = current_namespace
		self.preprocess_rules = preprocess_rules or []
		self.collected_categories: list[str] = []
		self.locale = locale
		self.include_metadata = include_metadata
		self.file_upload_dir = file_upload_dir
		self.include_edit_description = include_edit_description
