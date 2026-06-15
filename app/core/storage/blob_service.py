"""
Azure Blob Storage service.

Provides upload_bytes() for uploading generated PDFs and documents.
Falls back gracefully when Azure Storage is not configured (e.g., local dev).
"""
from __future__ import annotations

import logging
from datetime import UTC

from app.config import settings

logger = logging.getLogger(__name__)


async def upload_bytes(data: bytes, blob_name: str, content_type: str = "application/octet-stream") -> str:
    """
    Upload bytes to Azure Blob Storage.

    Returns the blob path/name on success.
    Raises if Azure Storage is not configured.
    """
    if not settings.AZURE_STORAGE_CONNECTION_STRING:
        raise RuntimeError("Azure Storage not configured (AZURE_STORAGE_CONNECTION_STRING not set)")

    from azure.storage.blob.aio import BlobServiceClient  # type: ignore[import]

    async with BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING) as client:
        container = client.get_container_client(settings.AZURE_STORAGE_CONTAINER_NAME)
        blob = container.get_blob_client(blob_name)
        await blob.upload_blob(data, overwrite=True, content_settings={"content_type": content_type})
        logger.debug("Uploaded %d bytes to blob: %s", len(data), blob_name)
        return blob_name


async def get_sas_url(blob_name: str) -> str:
    """
    Generate a time-limited SAS URL for a blob.

    Expires after AZURE_STORAGE_BLOB_URL_EXPIRY_HOURS hours.
    """
    from datetime import datetime, timedelta

    from azure.storage.blob import (  # type: ignore[import]
        BlobSasPermissions,
        BlobServiceClient,
        generate_blob_sas,
    )

    client = BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
    account_name = client.account_name
    account_key = client.credential.account_key

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=settings.AZURE_STORAGE_CONTAINER_NAME,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(UTC) + timedelta(hours=settings.AZURE_STORAGE_BLOB_URL_EXPIRY_HOURS),
    )
    return f"https://{account_name}.blob.core.windows.net/{settings.AZURE_STORAGE_CONTAINER_NAME}/{blob_name}?{sas_token}"
