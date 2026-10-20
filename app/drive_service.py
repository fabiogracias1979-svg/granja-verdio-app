import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/drive.file']
FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.json"

def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def upload_file_to_drive(file_obj, filename: str, mime_type: str):
    service = get_drive_service()
    file_metadata = {
        'name': filename,
        'parents': [FOLDER_ID] if FOLDER_ID else []
    }
    media = MediaIoBaseUpload(file_obj, mimetype=mime_type, resumable=True)
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    return file.get('id'), file.get('webViewLink')
