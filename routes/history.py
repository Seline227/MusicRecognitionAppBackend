import os
from flask import Blueprint, request, jsonify
from database import get_db_connection
from services.google_drive_service import upload_to_drive, delete_file_from_drive, delete_from_drive_by_link
import uuid
import datetime
import jwt

history_bp = Blueprint('history', __name__)

def get_user_id_from_token():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    token = auth_header.split(' ')[1]
    jwt_secret = os.getenv('JWT_SECRET_KEY')
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=['HS256'])
        return payload.get('user_id')
    except Exception:
        return None

@history_bp.route('/api/history', methods=['POST'])
def save_history():
    user_id = get_user_id_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400

    audio_file = request.files['audio']
    custom_name = request.form.get('custom_name', 'Înregistrare')
    status = request.form.get('status', 'unknown')
    artist = request.form.get('artist', '')
    title = request.form.get('title', '')
    album = request.form.get('album', '')

    # Save audio to a temporary file
    temp_filename = f"temp_{uuid.uuid4()}.m4a"
    temp_filepath = os.path.join('/tmp' if os.name != 'nt' else os.environ.get('TEMP', '.'), temp_filename)
    audio_file.save(temp_filepath)

    # Upload to Google Drive
    file_id, web_content_link = upload_to_drive(temp_filepath, f"{custom_name}.m4a")

    # Clean up temp file
    try:
        os.remove(temp_filepath)
    except Exception as e:
        print(f"[HISTORY] Error removing temp file: {e}")

    # Save to database
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO recognition_history 
            (user_id, custom_name, status, artist, title, album, google_drive_link) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, custom_name, status, artist, title, album, web_content_link))
        conn.commit()
        
        history_id = cursor.lastrowid
        
        # Inserăm și în tabelul audio_recordings pentru a păstra tabelele sincronizate
        cursor.execute("""
            INSERT INTO audio_recordings (history_id, user_id, drive_file_id, status, audio_extension)
            VALUES (%s, %s, %s, 'confirmed', '.m4a')
        """, (history_id, user_id, file_id))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'History saved successfully', 'google_drive_link': web_content_link}), 201
    except Exception as err:
        print(f"[HISTORY] DB Error: {err}", flush=True)
        return jsonify({'error': str(err)}), 500

@history_bp.route('/api/history', methods=['GET'])
def get_history():
    user_id = get_user_id_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM recognition_history 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        """, (user_id,))
        records = cursor.fetchall()
        cursor.close()
        conn.close()

        # Formatăm timestamp-ul pentru ca Flutter (DateTime.parse) să îl poată citi
        for r in records:
            if isinstance(r.get('created_at'), datetime.datetime):
                r['created_at'] = r['created_at'].isoformat()

        return jsonify(records), 200
    except Exception as err:
        return jsonify({'error': str(err)}), 500

@history_bp.route('/api/history/<int:history_id>', methods=['DELETE'])
def delete_history(history_id):
    user_id = get_user_id_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Obținem linkul de drive pentru a-l șterge și din Google Drive
        cursor.execute("SELECT google_drive_link FROM recognition_history WHERE id = %s AND user_id = %s", (history_id, user_id))
        record = cursor.fetchone()
        
        if not record:
            cursor.close()
            conn.close()
            return jsonify({'error': 'History record not found or unauthorized'}), 404
            
        drive_link = record.get('google_drive_link')
        
        # Stergem din drive daca exista link
        if drive_link:
            delete_from_drive_by_link(drive_link)
            
        # Stergem inregistrarea din baza de date
        cursor.execute("DELETE FROM recognition_history WHERE id = %s AND user_id = %s", (history_id, user_id))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'History record deleted successfully'}), 200
    except Exception as err:
        print(f"[HISTORY DELETE] DB Error: {err}", flush=True)
        return jsonify({'error': str(err)}), 500

@history_bp.route('/delete-recording/<int:record_id>', methods=['DELETE'])
@history_bp.route('/api/delete-recording/<int:record_id>', methods=['DELETE'])
def delete_recording(record_id):
    """
    Șterge o înregistrare din baza de date și din Google Drive.
    """
    user_id = get_user_id_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized', 'message': 'Token lipsă sau invalid.'}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verificăm dacă înregistrarea există și aparține utilizatorului
        cursor.execute("SELECT id FROM recognition_history WHERE id = %s AND user_id = %s", (record_id, user_id))
        history_record = cursor.fetchone()
        
        if not history_record:
            return jsonify({'error': 'Not Found', 'message': 'Înregistrarea nu a fost găsită sau nu îți aparține.'}), 404

        # Preluăm ID-ul din Google Drive din tabelul audio_recordings
        cursor.execute("SELECT drive_file_id FROM audio_recordings WHERE history_id = %s", (record_id,))
        audio_record = cursor.fetchone()
        
        drive_file_id = audio_record.get('drive_file_id') if audio_record else None

        # Dacă există în Drive, încercăm să ștergem
        if drive_file_id:
            success, err_msg = delete_file_from_drive(drive_file_id)
            if not success:
                # Dacă primim 403 sau altă eroare critică, oprim procesul
                return jsonify({'error': 'Drive Error', 'message': err_msg}), 500
        
        # Dacă ștergerea din Drive a reușit (sau a returnat 404/lipsă fișier) -> ștergem din DB
        cursor.execute("DELETE FROM audio_recordings WHERE history_id = %s", (record_id,))
        cursor.execute("DELETE FROM recognition_history WHERE id = %s", (record_id,))
        conn.commit()
        
        return jsonify({'message': 'Înregistrarea a fost ștearsă cu succes din sistem și din Drive.'}), 200

    except Exception as err:
        print(f"[HISTORY] EROARE la stergere record {record_id}: {err}", flush=True)
        return jsonify({'error': 'Server Error', 'message': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

