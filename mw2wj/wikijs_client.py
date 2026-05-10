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
			raise WikiJSError(
				f"GraphQL request failed (HTTP {response.status_code})",
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

	def create_page(self, path: str, content: str, title: str, description: str = "") -> dict[str, Any]:
		"""Create a new page via the pages.create mutation.

		@param path: WikiJS page path (e.g. "some/page")
		@param content: Page content in Markdown
		@param title: Page title
		@param description: Edit description/summary
		@returns: GraphQL response data
		"""
		query = """
		mutation CreatePage($path: String!, $content: String!, $title: String!, $description: String!) {
			pages {
				create(path: $path, content: $content, title: $title, description: $description, editor: "markdown") {
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
		}
		return self.graphql(query, variables)

	def update_page(self, page_id: int, path: str, content: str, title: str, description: str = "") -> dict[str, Any]:
		"""Update an existing page via the pages.update mutation.

		@param page_id: WikiJS internal page ID
		@param path: Page path
		@param content: New Markdown content
		@param title: Page title
		@param description: Edit description/summary
		@returns: GraphQL response data
		"""
		query = """
		mutation UpdatePage($id: Int!, $path: String!, $content: String!, $title: String!, $description: String!) {
			pages {
				update(id: $id, path: $path, content: $content, title: $title, description: $description, editor: "markdown") {
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
		}
		return self.graphql(query, variables)

	def upload_file(self, filename: str, contents: bytes) -> bool:
		"""Upload a file via the REST /u endpoint.

		@param filename: Destination filename on the wiki
		@param contents: Binary file contents
		@returns: True on success
		"""
		url = f"{self.base_url}/u"
		files = {"media": (filename, contents, "application/octet-stream")}

		response = self._session.post(url, files=files, timeout=self.timeout * 2)
		if response.status_code == 401:
			raise WikiJSAuthError("Authentication failed uploading file — check your API token")
		if not response.ok:
			raise WikiJSError(
				f"File upload failed for '{filename}' (HTTP {response.status_code})",
				status_code=response.status_code,
				response_body=response.text,
			)
		logger.info("Uploaded file: %s (%d bytes)", filename, len(contents))
		return True
