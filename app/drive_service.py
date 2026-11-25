import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_drive_service():
    oauth_json_str = os.environ.get("GOOGLE_OAUTH_JSON")
    if not oauth_json_str:
        raise ValueError("Falta la variable de entorno GOOGLE_OAUTH_JSON en Render.")
    
    info = json.loads(oauth_json_str)
    creds = Credentials(
        token=None,
        refresh_token=info["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=info["client_id"],
        client_secret=info["client_secret"],
        scopes=SCOPES
    )
    creds.refresh(Request())
    return build('drive', 'v3', credentials=creds)

def upload_file_to_drive(file_stream, filename: str, mime_type: str) -> str:
    service = get_drive_service()
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()

    file_metadata = {'name': filename}
    if folder_id:
        file_metadata['parents'] = [folder_id]

    media = MediaIoBaseUpload(file_stream, mimetype=mime_type, resumable=True)
    
    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()

    file_id = uploaded_file.get('id')

    service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()

    return uploaded_file.get('webViewLink')
