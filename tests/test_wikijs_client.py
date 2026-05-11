from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from mw2wj.wikijs_client import WikiJSClient, WikiJSAuthError, WikiJSAPIError, WikiJSError


@pytest.fixture
def client():
	return WikiJSClient("https://wiki.example.com", "test-token")


class TestCreatePage:
	def test_sends_required_fields(self, client):
		"""CreatePage mutation must include isPublished, isPrivate, locale, tags."""
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"data": {"pages": {"create": {"responseResult": {"succeeded": True}}}}}

		with patch.object(client._session, "post", return_value=mock_response) as mock_post:
			client.create_page("test-page", "# Hello", "Test Page", "Initial import")

		# Verify the request was sent
		mock_post.assert_called_once()
		call_args = mock_post.call_args
		payload = call_args.kwargs["json"]
		variables = payload["variables"]

		# Required Wiki.js fields
		assert variables["isPublished"] is True
		assert variables["isPrivate"] is True
		assert variables["locale"] == "en"
		assert variables["tags"] == []

	def test_passes_custom_is_private_locale_tags(self, client):
		"""is_private, locale, and tags should flow through to variables."""
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"data": {"pages": {"create": {"responseResult": {"succeeded": True}}}}}

		with patch.object(client._session, "post", return_value=mock_response) as mock_post:
			client.create_page(
				"test-page", "# Hello", "Test Page", "description",
				is_private=False, locale="it", tags=["linux", "networking"],
			)

		variables = mock_post.call_args.kwargs["json"]["variables"]
		assert variables["isPrivate"] is False
		assert variables["locale"] == "it"
		assert variables["tags"] == ["linux", "networking"]

	def test_returns_data_on_success(self, client):
		"""Successful create should return the GraphQL data."""
		expected = {"pages": {"create": {"responseResult": {"succeeded": True}, "page": {"id": 42}}}}
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"data": expected}

		with patch.object(client._session, "post", return_value=mock_response):
			result = client.create_page("p", "c", "t")

		assert result == expected


class TestUpdatePage:
	def test_sends_required_fields(self, client):
		"""UpdatePage mutation must include isPublished, isPrivate, locale, tags."""
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"data": {"pages": {"update": {"responseResult": {"succeeded": True}}}}}

		with patch.object(client._session, "post", return_value=mock_response) as mock_post:
			client.update_page(42, "test-page", "# Updated", "Test Page")

		variables = mock_post.call_args.kwargs["json"]["variables"]
		assert variables["id"] == 42
		assert variables["isPublished"] is True
		assert variables["isPrivate"] is True
		assert variables["locale"] == "en"
		assert variables["tags"] == []


class TestErrorHandling:
	def test_401_raises_auth_error(self, client):
		"""HTTP 401 must raise WikiJSAuthError."""
		mock_response = MagicMock()
		mock_response.status_code = 401
		mock_response.ok = False

		with patch.object(client._session, "post", return_value=mock_response):
			with pytest.raises(WikiJSAuthError, match="Authentication failed"):
				client.create_page("p", "c", "t")

	def test_400_with_graphql_errors_raises_api_error(self, client):
		"""HTTP 400 with GraphQL errors in body must include response in message."""
		mock_response = MagicMock()
		mock_response.status_code = 400
		mock_response.ok = False
		mock_response.text = json.dumps({
			"errors": [{"message": "Field 'create' argument 'isPublished' is required"}],
		})

		with patch.object(client._session, "post", return_value=mock_response):
			with pytest.raises(WikiJSError, match="isPublished"):
				client.create_page("p", "c", "t")

	def test_200_with_graphql_errors_raises_api_error(self, client):
		"""HTTP 200 with GraphQL errors array must raise WikiJSAPIError."""
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.ok = True
		mock_response.json.return_value = {
			"errors": [{"message": "Page already exists"}],
		}

		with patch.object(client._session, "post", return_value=mock_response):
			with pytest.raises(WikiJSAPIError, match="Page already exists"):
				client.create_page("p", "c", "t")

	def test_response_result_false_raises(self, client):
		"""Application-level failure (succeeded=false) must raise WikiJSAPIError."""
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.ok = True
		mock_response.json.return_value = {
			"data": {
				"pages": {
					"create": {
						"responseResult": {
							"succeeded": False,
							"errorCode": "PageCreateFailed",
							"message": "Path already in use",
						},
					},
				},
			},
		}

		with patch.object(client._session, "post", return_value=mock_response):
			with pytest.raises(WikiJSAPIError, match="Path already in use"):
				client.create_page("p", "c", "t")

	def test_500_raises_generic_error(self, client):
		"""Non-401/200 HTTP errors must raise WikiJSError with body in message."""
		mock_response = MagicMock()
		mock_response.status_code = 500
		mock_response.ok = False
		mock_response.text = "Internal Server Error"

		with patch.object(client._session, "post", return_value=mock_response):
			with pytest.raises(WikiJSError, match="Internal Server Error"):
				client.create_page("p", "c", "t")


class TestUploadFile:
	def test_upload_success(self, client):
		"""Successful file upload returns True."""
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.ok = True

		with patch.object(client._session, "post", return_value=mock_response):
			assert client.upload_file("image.png", b"\x89PNG") is True

	def test_upload_401_raises_auth_error(self, client):
		"""File upload 401 must raise WikiJSAuthError."""
		mock_response = MagicMock()
		mock_response.status_code = 401
		mock_response.ok = False

		with patch.object(client._session, "post", return_value=mock_response):
			with pytest.raises(WikiJSAuthError):
				client.upload_file("image.png", b"data")

	def test_upload_500_raises_error(self, client):
		"""File upload failure must include response body in message."""
		mock_response = MagicMock()
		mock_response.status_code = 500
		mock_response.ok = False
		mock_response.text = "Storage full"

		with patch.object(client._session, "post", return_value=mock_response):
			with pytest.raises(WikiJSError, match="Storage full"):
				client.upload_file("image.png", b"data")

	def test_upload_to_folder_includes_folder_id(self, client):
		"""folder_id must be sent as JSON in the first mediaUpload part."""
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.ok = True

		with patch.object(client._session, "post", return_value=mock_response) as mock_post:
			client.upload_file("image.png", b"\x89PNG", folder_id=5)

		# Verify the multipart upload includes the folderId in the JSON part
		files_arg = mock_post.call_args.kwargs["files"]
		assert len(files_arg) == 2
		# First part: JSON metadata with folderId
		json_part = files_arg[0]
		assert json_part[0] == "mediaUpload"
		# Second part: the file
		file_part = files_arg[1]
		assert file_part[0] == "mediaUpload"
		assert file_part[1][0] == "image.png"


class TestGetPage:
	def test_returns_page_data(self, client):
		"""get_page must return page fields including tags as objects."""
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {
			"data": {
				"pages": {
					"single": {
						"id": 42,
						"path": "my-page",
						"title": "My Page",
						"content": "# Hello",
						"description": "desc",
						"isPrivate": True,
						"isPublished": True,
						"locale": "it",
						"tags": [{"id": 1, "tag": "linux"}, {"id": 2, "tag": "net"}],
					}
				}
			}
		}

		with patch.object(client._session, "post", return_value=mock_response):
			data = client.get_page(42)

		assert data["id"] == 42
		assert data["path"] == "my-page"
		assert data["content"] == "# Hello"
		assert data["locale"] == "it"
		assert data["tags"] == [{"id": 1, "tag": "linux"}, {"id": 2, "tag": "net"}]

	def test_missing_page_raises(self, client):
		"""get_page with nonexistent id must raise WikiJSError."""
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"data": {"pages": {"single": None}}}

		with patch.object(client._session, "post", return_value=mock_response):
			with pytest.raises(WikiJSError, match="not found"):
				client.get_page(9999)

	def test_sends_correct_query(self, client):
		"""get_page must include tags subfield selection in the GraphQL query."""
		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {
			"data": {"pages": {"single": {
				"id": 1, "path": "x", "title": "x", "content": "x",
				"description": "", "isPrivate": True, "isPublished": True,
				"locale": "en", "tags": [],
			}}}
		}

		with patch.object(client._session, "post", return_value=mock_response) as mock_post:
			client.get_page(1)

		payload = mock_post.call_args.kwargs["json"]
		query = payload["query"]
		assert "tags {" in query, f"tags subfield selection missing: {query}"
		assert "id" in query
		assert "tag" in query
