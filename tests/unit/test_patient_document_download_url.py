"""Unit tests: patient document download_url is a resolved SAS URL string.

Regression guard: ``get_sas_url`` is async, so the service must ``await`` it.
Without the await, ``download_url`` was set to a coroutine object instead of a str.
No database or Azure connection required: the repository/session are mocked and
``app.core.storage.blob_service`` functions are patched (the service imports them
locally inside each method, so patching the module attribute is effective).
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.storage import blob_service
from app.modules.patients.service import PatientService

FAKE_SAS_URL = "https://example.test/sas"


async def _fake_get_sas_url(blob_name: str) -> str:
    return FAKE_SAS_URL


@pytest.fixture
def patched_blob(monkeypatch):
    monkeypatch.setattr(blob_service, "get_sas_url", _fake_get_sas_url)
    monkeypatch.setattr(blob_service, "upload_bytes", AsyncMock(return_value="ignored"))


def _make_service(execute_result=None) -> PatientService:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)
    repo = MagicMock()
    repo.session = session
    repo.get_by_id = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
    return PatientService(repo)


async def test_upload_document_sets_download_url_to_sas_string(patched_blob):
    service = _make_service()

    doc = await service.upload_document(
        patient_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        document_type="aadhaar",
        file_name="card.pdf",
        content_type="application/pdf",
        file_bytes=b"%PDF-1.4 test",
        notes=None,
        uploaded_by=uuid.uuid4(),
    )

    assert isinstance(doc.download_url, str)
    assert doc.download_url == FAKE_SAS_URL


async def test_list_documents_sets_download_url_to_sas_string(patched_blob):
    docs_in = [
        SimpleNamespace(blob_path="patient-docs/a/1_card.pdf", download_url=None),
        SimpleNamespace(blob_path="patient-docs/a/2_scan.png", download_url=None),
    ]
    result = MagicMock()
    result.scalars.return_value.all.return_value = docs_in
    service = _make_service(execute_result=result)

    docs = await service.list_documents(patient_id=uuid.uuid4(), org_id=uuid.uuid4())

    assert len(docs) == 2
    for doc in docs:
        assert isinstance(doc.download_url, str)
        assert doc.download_url == FAKE_SAS_URL
