import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/drive.file']
FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
CLIENT_SECRET_FILE = os.getenv("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json")

# Rutas posibles del token (local y Render)
POSIBLES_RUTAS_TOKEN = [
    "/etc/secrets/token.json",
    "token.json",
    os.path.join(os.path.dirname(__file__), "token.json"),
    "app/token.json"
]

def obtener_credenciales():
    creds = None

    # 1. Intentar cargar desde variable de entorno (prioridad máxima para Render)
    token_env = os.getenv("GOOGLE_TOKEN_JSON")
    if token_env:
        try:
            info = json.loads(token_env)
            creds = Credentials.from_authorized_user_info(info, SCOPES)
        except Exception as e:
            print(f"Error cargando token desde variable de entorno: {e}")

    # 2. Si no hay variable de entorno, buscar en las rutas de archivo
    if not creds:
        for ruta in POSIBLES_RUTAS_TOKEN:
            if os.path.exists(ruta):
                try:
                    creds = Credentials.from_authorized_user_file(ruta, SCOPES)
                    break
                except Exception as e:
                    print(f"Error leyendo {ruta}: {e}")

    # 3. Validar y refrescar el token si está expirado
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            print(f"Error al refrescar token: {e}")
            creds = None

    # 4. Flujo interactivo (solo para ejecución local)
    if not creds or not creds.valid:
        if os.path.exists(CLIENT_SECRET_FILE):
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            with open("token.json", "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())
        else:
            raise RuntimeError("No se encontraron credenciales válidas ni archivo de cliente para generar un token.")

    return creds

def get_drive_service():
    creds = obtener_credenciales()
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