from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mw2wj.importer import ImportStats, import_pages
from mw2wj.models import ConversionContext, Page


def test_collision_detection():
	"""Two pages whose sanitized paths collide must raise ValueError."""
	ctx = ConversionContext()
	stats = ImportStats()
	client = MagicMock()

	# "Hello World" → hello_world (with lowercase)
	# "Hello!World" → also hello_world (collision)
	ctx.lowercase_paths = True
	page1 = Page(id=1, title="Hello World", namespace=0, namespace_name="")
	page2 = Page(id=2, title="Hello!World", namespace=0, namespace_name="")

	pages = [page1, page2]

	with pytest.raises(ValueError, match="Path collision"):
		import_pages(client, pages, ctx, stats)

	# Verify no API calls were made before the collision check
	client.create_page.assert_not_called()
	client.update_page.assert_not_called()


def test_no_collision_when_paths_differ():
	"""Pages with different sanitized paths must not collide."""
	ctx = ConversionContext()
	stats = ImportStats()
	client = MagicMock()

	page1 = Page(id=1, title="Page One", namespace=0, namespace_name="")
	page2 = Page(id=2, title="Page Two", namespace=0, namespace_name="")

	pages = [page1, page2]

	# This should not raise (the collision check passes, and the
	# mock client will fail on GraphQL calls, but that's after
	# the collision check)
	try:
		import_pages(client, pages, ctx, stats)
	except Exception as e:
		# We expect it to fail at the GraphQL call, not at collision
		assert "Path collision" not in str(e)


def test_file_lowercasing():
	"""Filenames must be lowercased during upload when lowercase_paths is True."""
	from datetime import datetime, timezone
	from mw2wj.importer import ImportStats, import_files
	from mw2wj.models import UploadedFile

	client = MagicMock()
	client.upload_file.return_value = True
	stats = ImportStats()
	files = [
		UploadedFile(
			filename="Diagram 1.PNG",
			timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
			contributor="Alice",
			size=100,
			sha1="abc",
			contents=b"data",
		),
	]

	import_files(client, files, stats, lowercase_paths=True)

	# Verify the uploaded filename was lowercased
	client.upload_file.assert_called_once()
	uploaded_name = client.upload_file.call_args[0][0]
	assert uploaded_name == "diagram_1.png", (
		f"Expected 'diagram_1.png', got '{uploaded_name}'"
	)


def test_file_collision_detection():
	"""Files mapping to the same sanitized name must raise ValueError."""
	from datetime import datetime, timezone
	from mw2wj.importer import ImportStats, import_files
	from mw2wj.models import UploadedFile

	client = MagicMock()
	stats = ImportStats()
	files = [
		UploadedFile(
			filename="Diagram 1.PNG",
			timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
			contributor="Alice",
			size=100,
			sha1="abc",
			contents=b"data1",
		),
		UploadedFile(
			filename="Diagram_1.png",
			timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
			contributor="Bob",
			size=200,
			sha1="def",
			contents=b"data2",
		),
	]

	with pytest.raises(ValueError, match="File name collision"):
		import_files(client, files, stats, lowercase_paths=True)

	# Verify no uploads were performed before collision detection
	client.upload_file.assert_not_called()


def test_file_no_collision_when_names_differ():
	"""Files with different sanitized names must upload successfully."""
	from datetime import datetime, timezone
	from mw2wj.importer import ImportStats, import_files
	from mw2wj.models import UploadedFile

	client = MagicMock()
	client.upload_file.return_value = True
	stats = ImportStats()
	files = [
		UploadedFile(
			filename="Image1.png",
			timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
			contributor="Alice",
			size=100,
			sha1="abc",
			contents=b"data1",
		),
		UploadedFile(
			filename="Image2.png",
			timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
			contributor="Bob",
			size=200,
			sha1="def",
			contents=b"data2",
		),
	]

	import_files(client, files, stats, lowercase_paths=True)
	assert stats.files_uploaded == 2


def test_build_description_short():
	"""include_edit_description=False must return minimal description."""
	from datetime import datetime, timezone
	from mw2wj.importer import _build_description
	from mw2wj.models import Revision

	rev = Revision(
		id=1,
		parent_id=None,
		timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
		contributor="Alice",
		comment="Fixed typo in section 3",
		text="test",
	)

	result = _build_description(rev, include_edit_description=False)
	assert result == "", (
		f"Expected empty string, got '{result}'"
	)

def test_build_description_full():
	"""Default (include_edit_description=True) must include contributor and comment."""
	from datetime import datetime, timezone
	from mw2wj.importer import _build_description
	from mw2wj.models import Revision

	rev = Revision(
		id=1,
		parent_id=None,
		timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
		contributor="Alice",
		comment="Fixed typo",
		text="test",
	)

	result = _build_description(rev)
	assert "[MediaWiki import] by Alice" in result
	assert "Fixed typo" in result
