from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


class WikiJSError(Exception):
	def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None):
		self.status_code = status_code
		self.response_body = response_body
		super().__init__(message)


class WikiJSAuthError(WikiJSError):
	pass


class WikiJSAPIError(WikiJSError):
	def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None,
	             errors: list[dict[str, Any]] | None = None):
		self.errors = errors or []
		super().__init__(message, status_code, response_body)


class WikiJSClient:
	def __init__(self, base_url: str, api_token: str, timeout: int = 30):
		self.base_url = base_url.rstrip("/")
		self.api_token = api_token
		self.timeout = timeout
		self._session = requests.Session()
		self._session.headers.update({
			"Authorization": f"Bearer {api_token}",
			"User-Agent": "mediawiki2wikijs/0.1",
		})

	def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
		"""Execute a GraphQL query against the WikiJS API."""
		url = f"{self.base_url}/graphql"
		payload: dict[str, Any] = {"query": query}
		if variables:
			payload["variables"] = variables

		response = self._session.post(url, json=payload, timeout=self.timeout)
		if response.status_code == 401:
			raise WikiJSAuthError("Authentication failed — check your API token")
		if not response.ok:
			body = response.text[:1000]
			raise WikiJSError(
				f"GraphQL request failed (HTTP {response.status_code}): {body}",
				status_code=response.status_code,
				response_body=response.text,
			)

		data = response.json()
		if "errors" in data:
			raise WikiJSAPIError(
				f"GraphQL error: {data['errors'][0].get('message', 'unknown')}",
				status_code=response.status_code,
				response_body=response.text,
				errors=data["errors"],
			)
		return data.get("data", {})

	def _check_result(self, data: dict[str, Any]) -> None:
		"""Verify that a pages.create/update mutation actually succeeded.

		The GraphQL layer may return HTTP 200 even when the operation
		fails at the application level (e.g. path conflict, permission
		denied).  This inspects the nested responseResult.
		"""
		result = data.get("pages", {}).get("create", {}) or data.get("pages", {}).get("update", {})
		if not result:
			return  # unexpected shape — let caller handle
		rr = result.get("responseResult")
		if rr and not rr.get("succeeded"):
			raise WikiJSAPIError(
				f"Page operation failed: {rr.get('message', 'unknown')} (code: {rr.get('errorCode', 'unknown')})",
				errors=[rr],
			)

	def create_page(self, path: str, content: str, title: str, description: str = "", is_private: bool = True, locale: str = "en", tags: list[str] | None = None) -> dict[str, Any]:
		"""Create a new page via the pages.create mutation.

		@param path: WikiJS page path (e.g. "some/page")
		@param content: Page content in Markdown
		@param title: Page title
		@param description: Edit description/summary
		@returns: GraphQL response data
		"""
		query = """
		mutation CreatePage($path: String!, $content: String!, $title: String!, $description: String!, $isPublished: Boolean!, $isPrivate: Boolean!, $locale: String!, $tags: [String]!) {
			pages {
				create(path: $path, content: $content, title: $title, description: $description, editor: "markdown", isPublished: $isPublished, isPrivate: $isPrivate, locale: $locale, tags: $tags) {
					responseResult {
						succeeded
						errorCode
						message
						slug
					}
					page {
						id
						path
						title
					}
				}
			}
		}
		"""
		variables = {
			"path": path,
			"content": content,
			"title": title,
			"description": description,
			"isPublished": True,
			"isPrivate": is_private,
			"locale": locale,
			"tags": tags or [],
		}
		data = self.graphql(query, variables)
		self._check_result(data)
		return data

	def update_page(self, page_id: int, path: str, content: str, title: str, description: str = "", is_private: bool = True, locale: str = "en", tags: list[str] | None = None) -> dict[str, Any]:
		"""Update an existing page via the pages.update mutation.

		@param page_id: WikiJS internal page ID
		@param path: Page path
		@param content: New Markdown content
		@param title: Page title
		@param description: Edit description/summary
		@returns: GraphQL response data
		"""
		query = """
		mutation UpdatePage($id: Int!, $path: String!, $content: String!, $title: String!, $description: String!, $isPublished: Boolean!, $isPrivate: Boolean!, $locale: String!, $tags: [String]!) {
			pages {
				update(id: $id, path: $path, content: $content, title: $title, description: $description, editor: "markdown", isPublished: $isPublished, isPrivate: $isPrivate, locale: $locale, tags: $tags) {
					responseResult {
						succeeded
						errorCode
						message
						slug
					}
					page {
						id
						path
						title
					}
				}
			}
		}
		"""
		variables = {
			"id": page_id,
			"path": path,
			"content": content,
			"title": title,
			"description": description,
			"isPublished": True,
			"isPrivate": is_private,
			"locale": locale,
			"tags": tags or [],
		}
		data = self.graphql(query, variables)
		self._check_result(data)
		return data

	def list_pages(self) -> list[dict[str, Any]]:
		"""List all pages in the wiki.

		@returns: List of page dicts with id, path, title
		"""
		query = """
		{
			pages {
				list {
					id
					path
					title
				}
			}
		}
		"""
		data = self.graphql(query)
		return data.get("pages", {}).get("list", [])

	def delete_page(self, page_id: int) -> dict[str, Any]:
		"""Delete a page by its Wiki.js internal ID.

		@param page_id: Wiki.js internal page ID
		@returns: GraphQL response data
		"""
		query = """
		mutation DeletePage($id: Int!) {
			pages {
				delete(id: $id) {
					responseResult {
						succeeded
						errorCode
						message
					}
				}
			}
		}
		"""
		data = self.graphql(query, {"id": page_id})
		self._check_result(data)
		return data

	def move_page(self, page_id: int, new_path: str) -> dict[str, Any]:
		"""Rename/move a page by changing its path.

		@param page_id: Wiki.js internal page ID
		@param new_path: New path for the page
		@returns: GraphQL response data
		"""
		query = """
		mutation MovePage($id: Int!, $path: String!) {
			pages {
				update(id: $id, path: $path) {
					responseResult {
						succeeded
						errorCode
						message
					}
				}
			}
		}
		"""
		data = self.graphql(query, {"id": page_id, "path": new_path})
		self._check_result(data)
		return data

	def get_page(self, page_id: int) -> dict[str, Any]:
		"""Fetch a single page's full data by its Wiki.js internal ID.

		@param page_id: Wiki.js internal page ID
		@returns: Page dict with id, path, title, content, etc.
		"""
		query = """
		query GetPage($id: Int!) {
			pages {
				single(id: $id) {
					id
					path
					title
					content
					description
					isPrivate
					isPublished
					locale
					tags {
						id
						tag
					}
				}
			}
		}
		"""
		data = self.graphql(query, {"id": page_id})
		page_data = data.get("pages", {}).get("single")
		if page_data is None:
			raise WikiJSError(f"Page with id {page_id} not found")
		return page_data

	def create_asset_folder(self, slug: str, parent_folder_id: int = 0) -> dict[str, Any]:
		"""Create an asset folder via GraphQL.

		If the folder already exists, the error is logged and ignored.

		@param slug: URL-safe folder slug (e.g. "import_mw")
		@param parent_folder_id: Parent folder ID, 0 for root
		@returns: GraphQL response data
		"""
		query = """
		mutation CreateFolder($parentFolderId: Int!, $slug: String!, $name: String) {
			assets {
				createFolder(parentFolderId: $parentFolderId, slug: $slug, name: $name) {
					responseResult {
						succeeded
						errorCode
						slug
						message
					}
				}
			}
		}
		"""
		data = self.graphql(query, {
			"parentFolderId": parent_folder_id,
			"slug": slug,
			"name": slug,
		})
		rr = (
			data.get("assets", {})
			.get("createFolder", {})
			.get("responseResult", {})
		)
		if rr and not rr.get("succeeded"):
			# Folder already exists is harmless — log and continue
			if rr.get("slug") == "AssetFolderExists":
				logger.info("Asset folder '%s' already exists, reusing", slug)
			else:
				raise WikiJSAPIError(
					f"Failed to create asset folder '{slug}': {rr.get('message')}",
					errors=[rr],
				)
		return data

	def get_asset_folder_id(self, slug: str) -> int | None:
		"""Look up an asset folder ID by its slug.

		@param slug: Folder slug (e.g. "import_mw")
		@returns: Folder ID, or None if not found
		"""
		query = """
		query GetFolders($parentFolderId: Int!) {
			assets {
				folders(parentFolderId: $parentFolderId) {
					id
					slug
				}
			}
		}
		"""
		data = self.graphql(query, {"parentFolderId": 0})
		for folder in data.get("assets", {}).get("folders", []):
			if folder.get("slug") == slug:
				return folder["id"]
		return None

	def upload_file(self, filename: str, contents: bytes, folder_id: int = 0) -> bool:
		"""Upload a file via the REST /u endpoint.

		Wiki.js expects a multipart form with two 'mediaUpload' parts:
		one JSON string with the folderId, and one with the file binary.

		@param filename: Destination filename on the wiki
		@param contents: Binary file contents
		@param folder_id: Target asset folder ID (0 for root)
		@returns: True on success
		"""
		import json as _json
		url = f"{self.base_url}/u"
		upload_data = (
			("mediaUpload", (None, _json.dumps({"folderId": folder_id}), "application/json")),
			("mediaUpload", (filename, contents, "application/octet-stream")),
		)

		response = self._session.post(url, files=upload_data, timeout=self.timeout * 2)
		if response.status_code == 401:
			raise WikiJSAuthError("Authentication failed uploading file — check your API token")
		if not response.ok:
			body = response.text[:1000]
			raise WikiJSError(
				f"File upload failed for '{filename}' (HTTP {response.status_code}): {body}",
				status_code=response.status_code,
				response_body=response.text,
			)
		logger.info("Uploaded file: %s (%d bytes)", filename, len(contents))
		return True
