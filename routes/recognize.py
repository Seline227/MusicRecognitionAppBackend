import os
import tempfile
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from database import get_db_connection
from services.acrcloud_service import recognize_song


recognize_bp = Blueprint("recognize", __name__)

ALLOWED_EXTENSIONS = {".m4a", ".wav"}


def _is_allowed_file(filename):
    """Check if the file has an allowed audio extension."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


@recognize_bp.route("/api/recognize", methods=["POST"])
def recognize():
    """
    POST /api/recognize
    Accepts multipart/form-data with:
        - audio: audio file (.m4a or .wav) [required]
        - user_id: UUID string [optional]

    Returns JSON with artist, title, album, google_drive_link, and history_id.
    """

    # ── 1. Validate input ──────────────────────────────────────────────
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided. Send a file with key 'audio'."}), 400

    audio_file = request.files["audio"]
    if audio_file.filename == "":
        return jsonify({"error": "Empty filename."}), 400

    if not _is_allowed_file(audio_file.filename):
        return jsonify({"error": "Invalid file type. Only .m4a and .wav are accepted."}), 400

    user_id = request.form.get("user_id")

    # ── 2. Save the file temporarily ───────────────────────────────────
    original_filename = secure_filename(audio_file.filename)
    ext = os.path.splitext(original_filename)[1]
    temp_fd, temp_path = tempfile.mkstemp(suffix=ext)
    os.close(temp_fd)

    try:
        audio_file.save(temp_path)

        # ── 3. Recognize with AudD ─────────────────────────────────────
        song_data = recognize_song(temp_path)
        artist = song_data.get("artist")
        title = song_data.get("title")
        album = song_data.get("album")

        # ── 4. [REMOVED] Google Drive logic ────────────────────────────
        drive_link = None

        # ── 5. Save to database ────────────────────────────────────────
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO recognition_history
                (user_id, artist, title, album, google_drive_link)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, artist, title, album, drive_link),
        )
        conn.commit()
        history_id = cursor.lastrowid
        cursor.close()
        conn.close()

        # ── 6. Return response ─────────────────────────────────────────
        print(f"[API] Sending to phone: {title} / {artist} / Release: {song_data.get('releaseDate')}")
        return jsonify({
            "message": "Song recognized successfully",
            "history_id": history_id,
            "artist": artist,
            "title": title,
            "album": album,
            "releaseDate": song_data.get("releaseDate")
        }), 200

    except Exception as err:
        error_msg = str(err)
        print(f"[ERROR in /api/recognize]: {error_msg}")
        return jsonify({"error": error_msg}), 500

    finally:
        # ── 7. Cleanup temp file ───────────────────────────────────────
        if os.path.exists(temp_path):
            os.remove(temp_path)
