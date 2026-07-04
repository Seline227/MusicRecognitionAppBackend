import os
import json

from dotenv import load_dotenv

load_dotenv(override=True)

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/drive"]

def _load_config():

    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()

    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()

    refresh_token = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN", "").strip()

    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip().strip('"').strip("'")

    print(f"[DRIVE CONFIG] GOOGLE_OAUTH_CLIENT_ID = {'Setat' if client_id else 'Lipseste'}", flush=True)

    print(f"[DRIVE CONFIG] GOOGLE_OAUTH_CLIENT_SECRET = {'Setat' if client_secret else 'Lipseste'}", flush=True)

    print(f"[DRIVE CONFIG] GOOGLE_OAUTH_REFRESH_TOKEN = {'Setat' if refresh_token else 'Lipseste'}", flush=True)

    print(f"[DRIVE CONFIG] GOOGLE_DRIVE_FOLDER_ID = '{folder_id}'", flush=True)

    errors = []

    if not client_id: errors.append("❌ GOOGLE_OAUTH_CLIENT_ID lipseste!")

    if not client_secret: errors.append("❌ GOOGLE_OAUTH_CLIENT_SECRET lipseste!")

    if not refresh_token: errors.append("❌ GOOGLE_OAUTH_REFRESH_TOKEN lipseste!")

    if not folder_id: errors.append("❌ GOOGLE_DRIVE_FOLDER_ID lipseste!")

    return client_id, client_secret, refresh_token, folder_id, errors

def _get_drive_service():

    client_id, client_secret, refresh_token, folder_id, config_errors = _load_config()

    if config_errors:

        for err in config_errors:

            print(f"[DRIVE AUTH] {err}", flush=True)

        raise ValueError("Configurația Google Drive OAuth2 este incompletă.")

    try:

        credentials = Credentials(

            token=None,

            refresh_token=refresh_token,

            token_uri="https://oauth2.googleapis.com/token",

            client_id=client_id,

            client_secret=client_secret

        )

        print("[DRIVE AUTH] ✅ Credentiale OAuth2 inițializate cu succes.", flush=True)

    except Exception as e:

        print(f"[DRIVE AUTH] ❌ Eroare la inițializarea credentialelor OAuth2: {e}", flush=True)

        raise

    try:

        service = build("drive", "v3", credentials=credentials)

        print("[DRIVE AUTH] ✅ Serviciul Google Drive v3 construit cu succes.", flush=True)

        return service

    except Exception as e:

        print(f"[DRIVE AUTH] ❌ Eroare la construirea serviciului Drive: {e}", flush=True)

        raise

def verify_folder_access(service, folder_id):

    print(f"[DRIVE FOLDER] Verificăm accesul la folderul: {folder_id} ...", flush=True)

    try:

        result = service.files().list(

            q=f"'{folder_id}' in parents",

            pageSize=1,

            fields="files(id, name)"

        ).execute()

        files = result.get('files', [])

        print(f"[DRIVE FOLDER] ✅ Acces CONFIRMAT la folder! ({len(files)} fișiere găsite în el)", flush=True)

        return True

    except HttpError as e:

        status = e.resp.status if hasattr(e, 'resp') else 'N/A'

        print(f"[DRIVE FOLDER] ❌ Eroare HTTP {status} la accesarea folderului!", flush=True)

        if status == 404:

            print(f"[DRIVE FOLDER]    → CAUZA: Folderul cu ID '{folder_id}' NU EXISTA sau nu este vizibil pentru Service Account.", flush=True)

            print(f"[DRIVE FOLDER]    → SOLUTIE: Mergi în Google Drive, dă click dreapta pe folder → Share → adaugă email-ul Service Account-ului ca Editor.", flush=True)

        elif status == 403:

            print(f"[DRIVE FOLDER]    → CAUZA: Service Account-ul NU are permisiuni pe acest folder.", flush=True)

            print(f"[DRIVE FOLDER]    → SOLUTIE: Mergi în Google Drive, dă click dreapta pe folder → Share → adaugă email-ul Service Account-ului ca Editor.", flush=True)

        else:

            print(f"[DRIVE FOLDER]    → Detalii eroare: {e}", flush=True)

        return False

    except Exception as e:

        print(f"[DRIVE FOLDER] ❌ Eroare neașteptată la verificarea folderului: {e}", flush=True)

        return False

def upload_to_drive(file_path, file_name):

    print("", flush=True)

    print("=" * 70, flush=True)

    print("[DRIVE UPLOAD] ═══ ÎNCEPUT UPLOAD GOOGLE DRIVE ═══", flush=True)

    print(f"[DRIVE UPLOAD] Fișier local: {file_path}", flush=True)

    print(f"[DRIVE UPLOAD] Nume pe Drive: {file_name}", flush=True)

    print("=" * 70, flush=True)

    if not file_path or not os.path.exists(file_path):

        print(f"[DRIVE UPLOAD] ❌ EROARE: Fișierul local NU EXISTĂ la calea: '{file_path}'", flush=True)

        print(f"[DRIVE UPLOAD]    Posibil fișierul temporar a fost deja șters înainte de upload.", flush=True)

        return None, None

    file_size = os.path.getsize(file_path)

    print(f"[DRIVE UPLOAD] ✅ Fișier local găsit. Dimensiune: {file_size} bytes ({file_size/1024:.1f} KB)", flush=True)

    if file_size == 0:

        print(f"[DRIVE UPLOAD] ❌ EROARE: Fișierul are 0 bytes! Înregistrarea este goală.", flush=True)

        return None, None

    try:

        service = _get_drive_service()

    except Exception as e:

        print(f"[DRIVE UPLOAD] ❌ Nu se poate construi serviciul Drive. Upload ANULAT.", flush=True)

        return None, None

    _, _, _, folder_id, _ = _load_config()

    folder_id = folder_id.strip().strip('"').strip("'")

    if not verify_folder_access(service, folder_id):

        print(f"[DRIVE UPLOAD] ❌ Nu am acces la folder. Upload ANULAT.", flush=True)

        print(f"[DRIVE UPLOAD]    👉 Du-te în Google Drive, click dreapta pe folder → Share", flush=True)

        print(f"[DRIVE UPLOAD]    👉 Adaugă email-ul Service Account-ului cu rol de EDITOR", flush=True)

        return None, None

    extension = os.path.splitext(file_name)[1].lower()

    mime_types = {

        ".m4a": "audio/mp4",

        ".wav": "audio/wav",

        ".mp3": "audio/mpeg",

        ".ogg": "audio/ogg",

        ".aac": "audio/aac",

    }

    mime_type = mime_types.get(extension, "application/octet-stream")

    print(f"[DRIVE UPLOAD] Extensie: '{extension}' → MIME type: '{mime_type}'", flush=True)

    try:

        file_metadata = {"name": file_name}

        if folder_id:

            file_metadata["parents"] = [folder_id]

        print(f"[DRIVE UPLOAD] Se uploadează fișierul în folderul '{folder_id}'...", flush=True)

        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)

        uploaded_file = (

            service.files()

            .create(body=file_metadata, media_body=media, fields="id, webContentLink, name")

            .execute()

        )

        file_id = uploaded_file.get("id")

        web_content_link = uploaded_file.get("webContentLink")

        uploaded_name = uploaded_file.get("name")

        print(f"[DRIVE UPLOAD] ✅ UPLOAD REUȘIT!", flush=True)

        print(f"[DRIVE UPLOAD]    → File ID: {file_id}", flush=True)

        print(f"[DRIVE UPLOAD]    → Nume: {uploaded_name}", flush=True)

        print(f"[DRIVE UPLOAD]    → Link: {web_content_link}", flush=True)

    except HttpError as e:

        status = e.resp.status if hasattr(e, 'resp') else 'N/A'

        print(f"[DRIVE UPLOAD] ❌ EROARE HTTP {status} la upload!", flush=True)

        if status == 403:

            print(f"[DRIVE UPLOAD]    → CAUZA: Permisiuni insuficiente. Service Account-ul nu are drept de scriere.", flush=True)

        elif status == 404:

            print(f"[DRIVE UPLOAD]    → CAUZA: Folderul specificat nu există.", flush=True)

        elif status == 400:

            print(f"[DRIVE UPLOAD]    → CAUZA: Cererea este invalidă. Verifică MIME type-ul și metadata.", flush=True)

        else:

            print(f"[DRIVE UPLOAD]    → Detalii: {e}", flush=True)

        return None, None

    except Exception as e:

        print(f"[DRIVE UPLOAD] ❌ EROARE NEAȘTEPTATĂ la upload: {type(e).__name__}: {e}", flush=True)

        return None, None

    try:

        service.permissions().create(

            fileId=file_id,

            body={"type": "anyone", "role": "reader"},

        ).execute()

        print(f"[DRIVE UPLOAD] ✅ Permisiuni publice setate (anyone can read).", flush=True)

    except HttpError as e:

        status = e.resp.status if hasattr(e, 'resp') else 'N/A'

        print(f"[DRIVE UPLOAD] ⚠️  AVERTISMENT: Nu s-au putut seta permisiunile publice (HTTP {status}).", flush=True)

        print(f"[DRIVE UPLOAD]    Fișierul a fost uploadat, dar nu va fi accesibil public pentru redare.", flush=True)

        print(f"[DRIVE UPLOAD]    Detalii: {e}", flush=True)

    except Exception as e:

        print(f"[DRIVE UPLOAD] ⚠️  AVERTISMENT: Eroare la setarea permisiunilor: {e}", flush=True)

    print("=" * 70, flush=True)

    print(f"[DRIVE UPLOAD] ═══ UPLOAD COMPLET ═══", flush=True)

    print("=" * 70, flush=True)

    print("", flush=True)

    return file_id, web_content_link

def get_download_url(file_id):

    try:

        service = _get_drive_service()

        file_info = service.files().get(fileId=file_id, fields="webContentLink").execute()

        return file_info.get("webContentLink")

    except Exception as e:

        print(f"[DRIVE SERVICE] Fetch URL error: {e}", flush=True)

        return None

def delete_from_drive_by_link(web_content_link):

    if not web_content_link:

        return True

    import urllib.parse as urlparse

    from urllib.parse import parse_qs

    try:

        parsed = urlparse.urlparse(web_content_link)

        file_id = parse_qs(parsed.query).get('id', [None])[0]

        if not file_id:

            print(f"[DRIVE DELETE] Eroare: Nu am putut extrage file_id din '{web_content_link}'", flush=True)

            return False

        service = _get_drive_service()

        service.files().delete(fileId=file_id).execute()

        print(f"[DRIVE DELETE] ✅ Fișierul cu ID {file_id} a fost șters cu succes din Drive.", flush=True)

        return True

    except HttpError as e:

        status = e.resp.status if hasattr(e, 'resp') else 'N/A'

        if status == 404:

            print(f"[DRIVE DELETE] ✅ Fișierul nu mai există pe Drive (deja șters).", flush=True)

            return True

        print(f"[DRIVE DELETE] ❌ EROARE HTTP {status}: {e}", flush=True)

        return False

    except Exception as e:

        print(f"[DRIVE DELETE] ❌ Eroare la ștergerea fișierului: {e}", flush=True)

        return False

def delete_file_from_drive(file_id):

    if not file_id:

        return False, "File ID missing"

    try:

        service = _get_drive_service()

        service.files().delete(fileId=file_id).execute()

        print(f"[DRIVE SERVICE] ✅ Fișierul {file_id} a fost șters cu succes din Drive.", flush=True)

        return True, None

    except HttpError as e:

        status = e.resp.status if hasattr(e, 'resp') else 'N/A'

        if status == 404:

            print(f"[DRIVE SERVICE] ⚠️  Fișierul {file_id} nu există în Drive (poate a fost șters deja).", flush=True)

            return True, None

        elif status == 403:

            print(f"[DRIVE SERVICE] ❌ EROARE HTTP 403 la ștergere! Lipsă permisiuni pe fișierul {file_id}.", flush=True)

            return False, "Eroare de permisiuni (403) la ștergerea de pe Google Drive."

        else:

            print(f"[DRIVE SERVICE] ❌ EROARE HTTP {status} la ștergere: {e}", flush=True)

            return False, f"Eroare HTTP {status} de la Google Drive."

    except Exception as e:

        print(f"[DRIVE SERVICE] ❌ EROARE la ștergerea din Drive: {e}", flush=True)

        return False, str(e)
