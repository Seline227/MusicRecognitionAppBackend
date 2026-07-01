import os
import shutil
import tempfile
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from database import get_db_connection
from services.acrcloud_service import recognize_song
from services.whisper_service import transcribe_audio, search_by_lyrics
from routes.recordings import normalize_audio


recognize_bp = Blueprint("recognize", __name__)

ALLOWED_EXTENSIONS = {".m4a", ".wav", ".mp3", ".aac", ".ogg"}
VALID_MODES        = {"ambient", "humming", "lyrics"}


def _is_allowed_file(filename):
    """Check if the file has an allowed audio extension."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


# ─────────────────────────────────────────────────────────────────────────────
# Helper: unified response format
# ─────────────────────────────────────────────────────────────────────────────
def _build_response(song_data: dict, history_id: int) -> dict:
    """
    Builds a clean, unified JSON response regardless of recognition source.
    Expected keys in song_data: title, artist, album, cover_url, releaseDate
    """
    return {
        "message":     "Song recognized successfully",
        "history_id":  history_id,
        "title":       song_data.get("title"),
        "artist":      song_data.get("artist"),
        "album":       song_data.get("album"),
        "cover_url":   song_data.get("cover_url"),
        "releaseDate": song_data.get("releaseDate"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/recognize
# ─────────────────────────────────────────────────────────────────────────────
@recognize_bp.route("/api/recognize", methods=["POST"])
def recognize():
    """
    POST /api/recognize
    Accepts multipart/form-data with:
        - audio:            audio file (.m4a, .wav, .mp3, ...) [required]
        - user_id:          UUID string                        [optional]

    Logic (Smart Fallback):
        - Step 1: Ambient Fingerprinting (ACRCloud)
        - Step 2: Speech-to-Text (Whisper) -> Lyrics API Search
    """

    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided. Send a file with key 'audio'."}), 400

    audio_file = request.files["audio"]
    if audio_file.filename == "":
        return jsonify({"error": "Empty filename."}), 400

    if not _is_allowed_file(audio_file.filename):
        return jsonify({
            "error": f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        }), 400

    user_id = request.form.get("user_id")

    original_filename = secure_filename(audio_file.filename)
    ext               = os.path.splitext(original_filename)[1]
    temp_fd, temp_path = tempfile.mkstemp(suffix=ext)
    os.close(temp_fd)

    try:
        audio_file.save(temp_path)
        print(f"[API] /api/recognize | Smart Flow | user={user_id}")

        song_data = None

        # ── PASUL 1: Recunoastere Ambientala (ACRCloud) ────────────────
        try:
            print("[API] Incercam recunoastere ambientala (ACRCloud)...")
            song_data = recognize_song(temp_path, mode="ambient")
            print("[API] 🟢 Piesa gasita via ACRCloud!")
        except Exception as e_acr:
            print(f"[API] 🟡 ACRCloud nu a gasit piesa: {str(e_acr)}")
            print("[API] trecem la PASUL 2: Fallback la Versuri (STT)...")
            
            # ── PASUL 2: Fallback la Versuri (STT -> Lyrics Search) ────
            try:
                lyrics_text = transcribe_audio(temp_path)
                if not lyrics_text or len(lyrics_text.strip()) < 3:
                    raise Exception("Transcrierea nu contine suficient text pentru o cautare.")
                
                print(f"[API] Versuri extrase: '{lyrics_text}'. Cautam piesa...")
                song_data = search_by_lyrics(lyrics_text)
                song_data.setdefault("releaseDate", None)
                print("[API] 🟢 Piesa gasita via Lyrics Tracker!")
            except Exception as e_lyrics:
                print(f"[API] 🔴 Piesa nu a fost gasita nici dupa versuri: {str(e_lyrics)}")
                
                # CASE B: Save unidentified recording locally + attempt Drive upload
                try:
                    conn_unid = get_db_connection()
                    cursor_unid = conn_unid.cursor()

                    # Creăm intrarea în istoric pentru a o afișa în UI
                    cursor_unid.execute(
                        """
                        INSERT INTO recognition_history
                            (user_id, custom_name, status, artist, title, album, google_drive_link)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (user_id, "Înregistrare Nereușită", "not_found", "Necunoscut", "Piesă neidentificată", None, None)
                    )
                    conn_unid.commit()
                    history_id_unid = cursor_unid.lastrowid

                    # Salvăm fișierul LOCAL (ca să poată fi redat chiar dacă Drive-ul nu merge)
                    target_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp_recordings")
                    os.makedirs(target_dir, exist_ok=True)
                    target_path_unid = os.path.join(target_dir, f"{history_id_unid}{ext}")
                    shutil.copy2(temp_path, target_path_unid)
                    normalize_audio(target_path_unid)
                    print(f"[API] ✅ Fișier audio salvat local: {target_path_unid}")

                    # Creăm intrarea în audio_recordings (inițial fără drive_file_id)
                    cursor_unid.execute(
                        "INSERT INTO audio_recordings (history_id, user_id, drive_file_id, status, audio_extension) VALUES (%s, %s, %s, 'unidentified', %s)",
                        (history_id_unid, user_id, None, ext)
                    )
                    conn_unid.commit()

                    # Încercăm upload pe Drive (opțional — dacă reușește, actualizăm drive_file_id)
                    try:
                        from services.google_drive_service import upload_to_drive
                        file_name_for_drive = f"Unidentified_Entry_{history_id_unid}{ext}"
                        file_id, _ = upload_to_drive(temp_path, file_name_for_drive)
                        if file_id:
                            cursor_unid.execute(
                                "UPDATE audio_recordings SET drive_file_id = %s WHERE history_id = %s",
                                (file_id, history_id_unid)
                            )
                            conn_unid.commit()
                    except Exception as e_drive:
                        print(f"[API] ⚠️ Drive upload failed (audio is safe locally): {e_drive}")

                    cursor_unid.close()
                    conn_unid.close()
                except Exception as e_upload:
                    print(f"[API] Failed to auto-save unidentified audio: {e_upload}")

                # Returnam JSON cu status: "not_found" (404) pentru Flutter
                return jsonify({"status": "not_found", "error": "Piesa nu a fost gasita"}), 404

        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO recognition_history
                (user_id, artist, title, album, google_drive_link)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                user_id,
                song_data.get("artist"),
                song_data.get("title"),
                song_data.get("album"),
                None,   # google_drive_link deprecated
            ),
        )
        conn.commit()
        history_id = cursor.lastrowid

        # CASE A: Save pending recording and copy file
        cursor.execute(
            "INSERT INTO audio_recordings (history_id, user_id, status, audio_extension) VALUES (%s, %s, 'pending', %s)",
            (history_id, user_id, ext)
        )
        conn.commit()
        cursor.close()
        conn.close()

        target_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp_recordings")
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, f"{history_id}{ext}")
        shutil.copy2(temp_path, target_path)
        normalize_audio(target_path)

        # ── Returnare raspuns ─────────────────────────────────────────
        response = _build_response(song_data, history_id)
        print(f"[API] Sending to phone: {response['title']} - {response['artist']}")
        return jsonify(response), 200

    except Exception as err:
        error_msg = str(err)
        print(f"[ERROR in /api/recognize] Critical: {error_msg}")
        return jsonify({"error": error_msg}), 500

    finally:
        # ── Cleanup temp file ─────────────────────────────────────────
        if os.path.exists(temp_path):
            os.remove(temp_path)
