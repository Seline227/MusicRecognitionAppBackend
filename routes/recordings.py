import os
import shutil
from flask import Blueprint, request, jsonify, send_file
from database import get_db_connection
from services.google_drive_service import upload_to_drive, get_download_url
from pydub import AudioSegment

recordings_bp = Blueprint("recordings", __name__)

TEMP_RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp_recordings")
os.makedirs(TEMP_RECORDINGS_DIR, exist_ok=True)


def normalize_audio(file_path, target_dBFS=-14.0):
    """
    Normalizează volumul unui fișier audio la un nivel țintă.
    -14 dBFS este un nivel optim: puternic și clar, fără distorsiuni.
    """
    try:
        ext = os.path.splitext(file_path)[1].lower().lstrip('.')
        if ext == 'wav':
            audio = AudioSegment.from_wav(file_path)
        elif ext == 'm4a':
            audio = AudioSegment.from_file(file_path, format='m4a')
        elif ext == 'mp3':
            audio = AudioSegment.from_mp3(file_path)
        else:
            audio = AudioSegment.from_file(file_path)
        
        # Calculăm diferența dintre volumul actual și cel dorit
        change_in_dBFS = target_dBFS - audio.dBFS
        
        # Aplicăm câștigul (boost) doar dacă audio-ul e prea încet
        if change_in_dBFS > 0:
            normalized = audio.apply_gain(change_in_dBFS)
            normalized.export(file_path, format=ext if ext != 'm4a' else 'ipod')
            print(f"[AUDIO] ✅ Audio normalizat: {audio.dBFS:.1f} dBFS → {target_dBFS} dBFS (+{change_in_dBFS:.1f} dB boost)", flush=True)
        else:
            print(f"[AUDIO] ℹ️ Audio deja la volum bun ({audio.dBFS:.1f} dBFS), nu e nevoie de normalizare.", flush=True)
    except Exception as e:
        print(f"[AUDIO] ⚠️ Nu am putut normaliza audio-ul: {e}", flush=True)

@recordings_bp.route("/api/recordings/confirm", methods=["POST"])
def confirm_recording():
    """
    Called by the client when the user confirms the recognized song is correct.
    Uploads the pending audio file to Google Drive and updates the database.
    Body JSON: {"history_id": 123, "user_given_name": "My Cool Song"}
    """
    data = request.json or {}
    history_id = data.get("history_id")
    user_given_name = data.get("user_given_name")

    if not history_id:
        return jsonify({"error": "history_id is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Check if we have a pending recording for this history_id
        cursor.execute("SELECT * FROM audio_recordings WHERE history_id = %s", (history_id,))
        recording = cursor.fetchone()

        if not recording:
            return jsonify({"error": "Recording not found"}), 404
        
        if recording["status"] == "confirmed":
            return jsonify({"message": "Already confirmed"}), 200

        ext = recording.get("audio_extension", ".wav")
        user_id = recording.get("user_id")
        
        temp_file_path = os.path.join(TEMP_RECORDINGS_DIR, f"{history_id}{ext}")
        
        drive_file_id = None
        if os.path.exists(temp_file_path):
            file_name_for_drive = f"Confirmed_{user_given_name or history_id}{ext}"
            file_id, web_content_link = upload_to_drive(temp_file_path, file_name_for_drive)
            
            if file_id:
                drive_file_id = file_id
                # Cleanup
                os.remove(temp_file_path)
            else:
                return jsonify({"error": "Failed to upload to Google Drive"}), 500
        else:
            # File might have been deleted or expired
            return jsonify({"error": "Temporary audio file no longer exists"}), 404

        # Update DB
        cursor.execute(
            """
            UPDATE audio_recordings 
            SET status = 'confirmed', drive_file_id = %s, user_given_name = %s 
            WHERE id = %s
            """,
            (drive_file_id, user_given_name, recording["id"])
        )
        conn.commit()

        return jsonify({
            "message": "Recording confirmed and saved to Drive",
            "drive_file_id": drive_file_id
        }), 200

    except Exception as e:
        print(f"[API] Error confirming recording: {e}", flush=True)
        return jsonify({"error": "Internal server error"}), 500
    finally:
        cursor.close()
        conn.close()


@recordings_bp.route("/api/recordings/save-unidentified", methods=["POST"])
def save_unidentified():
    """
    Called internally or by the client to save an unidentified recording.
    Expects multipart/form-data with 'audio' and optionally 'user_id'.
    """
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided."}), 400

    audio_file = request.files["audio"]
    user_id = request.form.get("user_id")

    if audio_file.filename == "":
        return jsonify({"error": "Empty filename."}), 400

    ext = os.path.splitext(audio_file.filename)[1].lower()
    
    # Save temp file
    temp_path = os.path.join(TEMP_RECORDINGS_DIR, f"temp_unidentified_{os.urandom(4).hex()}{ext}")
    audio_file.save(temp_path)

    try:
        file_name_for_drive = f"Unidentified_Entry_{os.urandom(4).hex()}{ext}"
        file_id, web_content_link = upload_to_drive(temp_path, file_name_for_drive)
        
        if not file_id:
            return jsonify({"error": "Failed to upload to Google Drive"}), 500

        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT INTO audio_recordings (user_id, drive_file_id, status, audio_extension)
            VALUES (%s, %s, 'unidentified', %s)
            """,
            (user_id, file_id, ext)
        )
        conn.commit()
        record_id = cursor.lastrowid
        cursor.close()
        conn.close()

        return jsonify({
            "message": "Unidentified recording saved successfully",
            "recording_id": record_id,
            "drive_file_id": file_id
        }), 200

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@recordings_bp.route("/api/recordings/<int:history_id>/stream-url", methods=["GET"])
def get_stream_url(history_id):
    """
    Returns the direct download/stream link for a saved recording.
    Fallback: if Drive file doesn't exist, returns a local streaming URL.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT drive_file_id, audio_extension FROM audio_recordings WHERE history_id = %s", (history_id,))
        recording = cursor.fetchone()
        
        # Prioritate 1: Google Drive (dacă există în audio_recordings)
        if recording and recording.get("drive_file_id"):
            url = get_download_url(recording["drive_file_id"])
            if url:
                return jsonify({"stream_url": url}), 200
        
        # Prioritate 1.5: Fallback la google_drive_link direct din recognition_history (salvat prin /api/history POST)
        cursor.execute("SELECT google_drive_link FROM recognition_history WHERE id = %s", (history_id,))
        history_record = cursor.fetchone()
        if history_record and history_record.get("google_drive_link"):
            return jsonify({"stream_url": history_record["google_drive_link"]}), 200
            
        if not recording:
            return jsonify({"error": "Recording not found"}), 404
        
        # Prioritate 2: Fișier local din temp_recordings/
        ext = recording.get("audio_extension", ".wav")
        local_path = os.path.join(TEMP_RECORDINGS_DIR, f"{history_id}{ext}")
        if os.path.exists(local_path):
            # Returnăm URL-ul local pentru streaming direct de pe server
            from flask import request as flask_request
            base_url = flask_request.host_url.rstrip('/')
            local_url = f"{base_url}/api/recordings/{history_id}/audio"
            return jsonify({"stream_url": local_url}), 200
        
        return jsonify({"error": "Audio file not available (neither on Drive nor locally)"}), 404
            
    finally:
        cursor.close()
        conn.close()


@recordings_bp.route("/api/recordings/<int:history_id>/audio", methods=["GET"])
def serve_audio(history_id):
    """
    Servește fișierul audio direct de pe server (fallback local când Drive nu merge).
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT audio_extension FROM audio_recordings WHERE history_id = %s", (history_id,))
        recording = cursor.fetchone()
        
        if not recording:
            return jsonify({"error": "Recording not found"}), 404
        
        ext = recording.get("audio_extension", ".wav")
        local_path = os.path.join(TEMP_RECORDINGS_DIR, f"{history_id}{ext}")
        
        if not os.path.exists(local_path):
            return jsonify({"error": "Audio file not found on server"}), 404
        
        mime_types = {
            ".m4a": "audio/mp4",
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".ogg": "audio/ogg",
            ".aac": "audio/aac",
        }
        mime_type = mime_types.get(ext, "application/octet-stream")
        
        return send_file(local_path, mimetype=mime_type)
    finally:
        cursor.close()
        conn.close()

