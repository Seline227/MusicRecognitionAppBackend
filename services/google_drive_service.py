import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account


SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _get_drive_service():
    """Builds and returns an authenticated Google Drive service instance."""
    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    credentials = service_account.Credentials.from_service_account_file(
        service_account_file, scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials)


def upload_to_drive(file_path, file_name):
    """
    Uploads a file to Google Drive and returns a shareable link.

    Args:
        file_path: Absolute path to the file to upload.
        file_name: Name to give the file on Google Drive.

    Returns:
        str: Shareable Google Drive link.
    """
    service = _get_drive_service()
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

    # Determine MIME type based on extension
    extension = os.path.splitext(file_name)[1].lower()
    mime_types = {
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
    }
    mime_type = mime_types.get(extension, "application/octet-stream")

    # Upload file
    file_metadata = {"name": file_name}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
    uploaded_file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )

    file_id = uploaded_file.get("id")

    # Set permission: anyone with link can view
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
