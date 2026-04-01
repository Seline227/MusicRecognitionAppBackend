import os
import tempfile
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from database import get_db_connection
from services.acrcloud_service import recognize_song
from services.whisper_service import transcribe_audio, search_by_lyrics


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
                # Returnam JSON cu status: "not_found" (404) pentru Flutter
                return jsonify({"status": "not_found", "error": "Piesa nu a fost gasita"}), 404

        # ── Salvare in istoric (doar daca s-a gasit piesa) ────────────
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
        cursor.close()
        conn.close()

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
