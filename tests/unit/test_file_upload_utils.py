"""Unit tests for file upload utilities — no Azure connection required."""

import uuid

import pytest

from app.shared.utils.file_upload import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_MB,
    build_blob_path,
)


class TestAllowedExtensions:
    def test_pdf_is_allowed(self):
        assert ".pdf" in ALLOWED_EXTENSIONS

    def test_jpg_is_allowed(self):
        assert ".jpg" in ALLOWED_EXTENSIONS

    def test_jpeg_is_allowed(self):
        assert ".jpeg" in ALLOWED_EXTENSIONS

    def test_png_is_allowed(self):
        assert ".png" in ALLOWED_EXTENSIONS

    def test_docx_is_allowed(self):
        assert ".docx" in ALLOWED_EXTENSIONS

    def test_xlsx_is_allowed(self):
        assert ".xlsx" in ALLOWED_EXTENSIONS

    def test_executable_is_not_allowed(self):
        assert ".exe" not in ALLOWED_EXTENSIONS

    def test_python_script_is_not_allowed(self):
        assert ".py" not in ALLOWED_EXTENSIONS

    def test_shell_script_is_not_allowed(self):
        assert ".sh" not in ALLOWED_EXTENSIONS

    def test_all_extensions_start_with_dot(self):
        for ext in ALLOWED_EXTENSIONS:
            assert ext.startswith("."), f"Extension missing leading dot: {ext}"

    def test_all_extensions_are_lowercase(self):
        for ext in ALLOWED_EXTENSIONS:
            assert ext == ext.lower(), f"Extension not lowercase: {ext}"


class TestMaxFileSizeMb:
    def test_max_size_is_positive(self):
        assert MAX_FILE_SIZE_MB > 0

    def test_max_size_is_reasonable(self):
        """Healthcare documents should not require files larger than 100 MB."""
        assert MAX_FILE_SIZE_MB <= 100


class TestBuildBlobPath:
    def test_returns_string(self):
        org_id = str(uuid.uuid4())
        path = build_blob_path(org_id, "prescriptions", "report.pdf")
        assert isinstance(path, str)

    def test_path_starts_with_org_id(self):
        org_id = str(uuid.uuid4())
        path = build_blob_path(org_id, "prescriptions", "report.pdf")
        assert path.startswith(org_id)

    def test_path_contains_category(self):
        org_id = str(uuid.uuid4())
        path = build_blob_path(org_id, "lab-results", "result.pdf")
        assert "lab-results" in path

    def test_preserves_file_extension(self):
        org_id = str(uuid.uuid4())
        path = build_blob_path(org_id, "documents", "scan.jpg")
        assert path.endswith(".jpg")

    def test_extension_is_lowercased(self):
        org_id = str(uuid.uuid4())
        path = build_blob_path(org_id, "documents", "SCAN.JPG")
        assert path.endswith(".jpg")

    def test_two_uploads_produce_different_paths(self):
        """Each upload must get a unique UUID filename to avoid collisions."""
        org_id = str(uuid.uuid4())
        path1 = build_blob_path(org_id, "documents", "file.pdf")
        path2 = build_blob_path(org_id, "documents", "file.pdf")
        assert path1 != path2

    def test_path_format_is_org_slash_category_slash_filename(self):
        org_id = str(uuid.uuid4())
        path = build_blob_path(org_id, "prescriptions", "rx.pdf")
        parts = path.split("/")
        assert len(parts) == 3
        assert parts[0] == org_id
        assert parts[1] == "prescriptions"
        assert parts[2].endswith(".pdf")
