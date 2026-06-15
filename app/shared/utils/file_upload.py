import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas

from app.config import settings

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx"}
MAX_FILE_SIZE_MB = 10


def get_blob_client() -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)


def build_blob_path(org_id: str, category: str, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    unique_name = f"{uuid.uuid4()}{ext}"
    return f"{org_id}/{category}/{unique_name}"


async def upload_file(
    file_content: bytes,
    blob_path: str,
    content_type: str = "application/octet-stream",
) -> str:
    client = get_blob_client()
    container_client = client.get_container_client(settings.AZURE_STORAGE_CONTAINER_NAME)
    blob_client = container_client.get_blob_client(blob_path)
    blob_client.upload_blob(file_content, content_type=content_type, overwrite=True)
    return blob_path


def generate_sas_url(blob_path: str, expiry_hours: int | None = None) -> str:
    expiry_hours = expiry_hours or settings.AZURE_STORAGE_BLOB_URL_EXPIRY_HOURS
    client = get_blob_client()
    account_name = client.account_name
    account_key = client.credential.account_key

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=settings.AZURE_STORAGE_CONTAINER_NAME,
        blob_name=blob_path,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(UTC) + timedelta(hours=expiry_hours),
    )
    return f"https://{account_name}.blob.core.windows.net/{settings.AZURE_STORAGE_CONTAINER_NAME}/{blob_path}?{sas_token}"
