import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf8')

from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

from dotenv import load_dotenv
from database import get_db_connection
from models import create_users_table, create_recognition_history_table, create_password_resets_table, create_audio_recordings_table, create_chords_cache_table
from routes.recognize import recognize_bp
from routes.chords import chords_bp
from routes.history import history_bp
from routes.recordings import recordings_bp

load_dotenv()

import os
import datetime

import jwt
import random

import smtplib
from email.mime.text import MIMEText
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

app = Flask(__name__)

CORS(app)

app.register_blueprint(recognize_bp)

app.register_blueprint(chords_bp)

app.register_blueprint(history_bp)

app.register_blueprint(recordings_bp)

@app.before_request

def log_request_info():

    print(f"[TRAFIC INTERCEPTAT] Metoda: {request.method} | Catre: {request.url} | IP Sursa: {request.remote_addr}", flush=True)

create_users_table()

create_recognition_history_table()

create_password_resets_table()

create_audio_recordings_table()

create_chords_cache_table()

@app.route('/signup', methods=['POST'])

def signup():

    data = request.json

    first_name = data.get('first_name')

    last_name = data.get('last_name')

    email = data.get('email')

    password = data.get('password')

    if not all([first_name, last_name, email, password]):

        return jsonify({'error': 'Toate câmpurile sunt obligatorii'}), 400

    try:

        conn = get_db_connection()

        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))

        existing_user = cursor.fetchone()

        if existing_user:

            cursor.close()

            conn.close()

            return jsonify({'error': 'Acest email este deja folosit'}), 409

        user_id = str(uuid.uuid4())

        hashed_password = generate_password_hash(password)

        cursor.execute(

            "INSERT INTO users (id, first_name, last_name, email, password) VALUES (%s,%s,%s,%s,%s)",

            (user_id, first_name, last_name, email, hashed_password)

        )

        conn.commit()

        cursor.close()

        conn.close()

        jwt_secret = os.getenv('JWT_SECRET_KEY')

        payload = {

            'user_id': user_id,

            'email': email,

            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)

        }

        session_token = jwt.encode(payload, jwt_secret, algorithm='HS256')

        return jsonify({

            'message': 'User creat cu succes',

            'user_id': user_id,

            'token': session_token,

            'user': {

                'id': user_id,

                'email': email,

                'first_name': first_name,

                'last_name': last_name,

                'profile_picture': ''

            }

        })

    except Exception as err:

        return jsonify({'error': str(err)}), 500

@app.route('/signin', methods=['POST'])

def signin():

    data = request.json

    email = data.get('email')

    password = data.get('password')

    if not all([email, password]):

        return jsonify({'error': 'Email și parola sunt obligatorii'}), 400

    try:

        conn = get_db_connection()

        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))

        user = cursor.fetchone()

        cursor.close()

        conn.close()

        if user and check_password_hash(user['password'], password):

            jwt_secret = os.getenv('JWT_SECRET_KEY')

            payload = {

                'user_id': user['id'],

                'email': user['email'],

                'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)

            }

            session_token = jwt.encode(payload, jwt_secret, algorithm='HS256')

            return jsonify({

                'message': 'Autentificare reușită',

                'user_id': user['id'],

                'token': session_token,

                'user': {

                    'id': user['id'],

                    'email': user['email'],

                    'first_name': user['first_name'],

                    'last_name': user['last_name'],

                    'profile_picture': user.get('profile_picture', '')

                }

            })

        else:

            return jsonify({'error': 'Email sau parola incorecte'}), 401

    except Exception as err:

        return jsonify({'error': str(err)}), 500

@app.route('/api/auth/google', methods=['POST'])

def google_signin():

    print("[BACKEND] Se primeste cerere POST la /api/auth/google pentru login Google...", flush=True)

    data = request.json

    token = data.get('idToken') or data.get('id_token')

    if not token:

        return jsonify({'error': 'idToken este obligatoriu'}), 400

    try:

        google_client_id = os.getenv('GOOGLE_CLIENT_ID')

        idinfo = id_token.verify_oauth2_token(

            token,

            google_requests.Request(),

            google_client_id

        )

        email = idinfo.get('email')

        google_id = idinfo.get('sub')

        name = idinfo.get('name', '')

        profile_picture = idinfo.get('picture', '')

        name_parts = name.split(' ', 1)

        first_name = name_parts[0]

        last_name = name_parts[1] if len(name_parts) > 1 else ''

        conn = get_db_connection()

        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))

        user = cursor.fetchone()

        if user:

            if not user.get('google_id'):

                cursor.execute(

                    "UPDATE users SET google_id = %s, profile_picture = %s WHERE email = %s",

                    (google_id, profile_picture, email)

                )

                conn.commit()

            user_id = user['id']

        else:

            user_id = str(uuid.uuid4())

            cursor.execute(

                "INSERT INTO users (id, first_name, last_name, email, google_id, profile_picture) VALUES (%s, %s, %s, %s, %s, %s)",

                (user_id, first_name, last_name, email, google_id, profile_picture)

            )

            conn.commit()

        cursor.close()

        conn.close()

        jwt_secret = os.getenv('JWT_SECRET_KEY')

        payload = {

            'user_id': user_id,

            'email': email,

            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)

        }

        session_token = jwt.encode(payload, jwt_secret, algorithm='HS256')

        return jsonify({

            'message': 'Autentificare cu Google reușită',

            'token': session_token,

            'user': {

                'id': user_id,

                'email': email,

                'first_name': first_name,

                'last_name': last_name,

                'profile_picture': profile_picture

            }

        }), 200

    except ValueError as e:

        print(f"[BACKEND] Eroare validare token Google (ValueError): {e}", flush=True)

        return jsonify({'error': f'Token de la Google invalid: {e}'}), 401

    except Exception as err:

        import traceback

        print(f"[BACKEND] EROARE GRAVA INTERNA la Google Login: {err}", flush=True)

        traceback.print_exc()

        return jsonify({'error': f'Eroare internă de server: {str(err)}'}), 500

def send_otp_email(to_email, otp):

    smtp_email = os.getenv('SMTP_EMAIL')

    smtp_password = os.getenv('SMTP_PASSWORD')

    if not smtp_email or not smtp_password:

        print("❌ [BACKEND] Eroare: SMTP_EMAIL sau SMTP_PASSWORD lipsesc din .env!", flush=True)

        return False

    msg = MIMEText(f"Salut!\n\nCodul tău de resetare a parolei este: {otp}\nAcest cod expiră în 15 minute.\n\nDacă nu ai cerut o resetare de parolă, te rugăm să ignori acest email.")

    msg['Subject'] = 'Cod de resetare a parolei - Harmoniq'

    msg['From'] = smtp_email

    msg['To'] = to_email

    try:

        server = smtplib.SMTP('smtp.gmail.com', 587)

        server.starttls()

        server.login(str(smtp_email), str(smtp_password))

        server.send_message(msg)

        server.quit()

        return True

    except Exception as e:

        print(f"❌ [BACKEND] Eroare la trimiterea email-ului SMTP: {e}", flush=True)

        return False

@app.route('/forgot-password', methods=['POST'])

def forgot_password():

    data = request.json

    email = data.get('email')

    if not email:

        return jsonify({"success": False, "error": "Email is required"}), 400

    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))

    user = cursor.fetchone()

    if not user:

        cursor.close()

        conn.close()

        return jsonify({"success": False, "error": "Email not found"}), 404

    otp = str(random.randint(100000, 999999))

    expires_at = datetime.datetime.now() + datetime.timedelta(minutes=15)

    cursor.execute("DELETE FROM password_resets WHERE email = %s", (email,))

    cursor.execute(

        "INSERT INTO password_resets (email, otp, expires_at) VALUES (%s, %s, %s)",

        (email, otp, expires_at)

    )

    conn.commit()

    cursor.close()

    conn.close()

    if send_otp_email(email, otp):

        return jsonify({"success": True, "message": "OTP trimis"}), 200

    else:

        return jsonify({"success": False, "error": "Failed to send email. Check SMTP settings."}), 500

@app.route('/verify-otp', methods=['POST'])

def verify_otp():

    data = request.json

    email = data.get('email')

    otp = data.get('otp')

    if not email or not otp:

        return jsonify({"success": False, "error": "Email and OTP are required"}), 400

    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)

    cursor.execute(

        "SELECT otp, expires_at FROM password_resets WHERE email = %s ORDER BY created_at DESC LIMIT 1",

        (email,)

    )

    record = cursor.fetchone()

    cursor.close()

    conn.close()

    if not record or record['otp'] != otp:

        return jsonify({"success": False, "error": "Invalid or expired code"}), 400

    if record['expires_at'] < datetime.datetime.now():

        return jsonify({"success": False, "error": "Invalid or expired code"}), 400

    return jsonify({"success": True, "message": "OTP valid"}), 200

@app.route('/reset-password', methods=['POST'])

def reset_password():

    data = request.json

    email = data.get('email')

    otp = data.get('otp')

    new_password = data.get('new_password')

    if not all([email, otp, new_password]):

        return jsonify({"success": False, "error": "All fields are required"}), 400

    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)

    cursor.execute(

        "SELECT otp, expires_at FROM password_resets WHERE email = %s ORDER BY created_at DESC LIMIT 1",

        (email,)

    )

    record = cursor.fetchone()

    if not record or record['otp'] != otp:

        cursor.close()

        conn.close()

        return jsonify({"success": False, "error": "Invalid or expired code"}), 400

    if record['expires_at'] < datetime.datetime.now():

        cursor.close()

        conn.close()

        return jsonify({"success": False, "error": "Invalid or expired code"}), 400

    hashed_password = generate_password_hash(new_password)

    cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_password, email))

    cursor.execute("DELETE FROM password_resets WHERE email = %s", (email,))

    conn.commit()

    cursor.close()

    conn.close()

    return jsonify({"success": True, "message": "Password reset successfully"}), 200

@app.route('/api/users/me', methods=['DELETE'])

def delete_account():

    print(f"🔥 [DELETE ACCOUNT] Request received from {request.remote_addr}", flush=True)

    auth_header = request.headers.get('Authorization')

    if not auth_header or not auth_header.startswith('Bearer '):

        print("❌ [DELETE ACCOUNT] Token missing or invalid format.", flush=True)

        return jsonify({'error': 'Unauthorized', 'message': 'Token lipsă sau invalid'}), 401

    token = auth_header.split(' ')[1]

    jwt_secret = os.getenv('JWT_SECRET_KEY')

    try:

        payload = jwt.decode(token, jwt_secret, algorithms=['HS256'])

        user_id = payload.get('user_id')

        email = payload.get('email')

        print(f"✅ [DELETE ACCOUNT] Decoded token for user_id: {user_id}, email: {email}", flush=True)

        if not user_id:

            return jsonify({'error': 'Unauthorized', 'message': 'Token invalid'}), 401

    except jwt.ExpiredSignatureError:

        print("❌ [DELETE ACCOUNT] Token expired.", flush=True)

        return jsonify({'error': 'Unauthorized', 'message': 'Token expirat'}), 401

    except jwt.InvalidTokenError as e:

        print(f"❌ [DELETE ACCOUNT] Invalid token error: {e}", flush=True)

        return jsonify({'error': 'Unauthorized', 'message': 'Token invalid'}), 401

    try:

        conn = get_db_connection()

        cursor = conn.cursor()

        cursor.execute("DELETE FROM recognition_history WHERE user_id = %s", (user_id,))

        print(f"ℹ️ [DELETE ACCOUNT] Deleted {cursor.rowcount} records from recognition_history.", flush=True)

        if email:

            cursor.execute("DELETE FROM password_resets WHERE email = %s", (email,))

            print(f"ℹ️ [DELETE ACCOUNT] Deleted {cursor.rowcount} records from password_resets.", flush=True)

        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))

        print(f"ℹ️ [DELETE ACCOUNT] Deleted {cursor.rowcount} records from users table.", flush=True)

        conn.commit()

        cursor.close()

        conn.close()

        if cursor.rowcount == 0:

            print("⚠️ [DELETE ACCOUNT] No user found with that ID in the database!", flush=True)

            return jsonify({'success': False, 'message': 'User not found in the database (already deleted?)'}), 404

        print("✅ [DELETE ACCOUNT] User successfully deleted from database.", flush=True)

        return jsonify({'success': True, 'message': 'User deleted successfully'}), 200

    except Exception as err:

        print(f"❌ [ERROR in delete_account]: {err}", flush=True)

        return jsonify({'error': 'Server Error', 'message': str(err)}), 500

from services.chord_service import search_chords, get_chord_content, search_and_get_first

@app.route('/api/chords/search', methods=['POST'])

def chord_search():

    data = request.json

    query = data.get('query', '').strip() if data else ''

    if not query:

        return jsonify({'error': 'Query is required'}), 400

    print(f"🎸 [CHORDS ENDPOINT] Căutare acorduri pentru: '{query}'", flush=True)

    try:

        conn = get_db_connection()

        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT song_title as title, artist, chords_text, url FROM chords_cache WHERE query_text = %s", (query,))

        cached_result = cursor.fetchone()

        if cached_result:

            print(f"✅ [CACHE] Hit pentru query: '{query}'", flush=True)

            cursor.close()

            conn.close()

            return jsonify(cached_result), 200

    except Exception as e:

        print(f"❌ [CACHE] Eroare la citire: {e}", flush=True)

    result = search_and_get_first(query)

    if not result:

        return jsonify({

            'error': 'not_found',

            'message': 'Nu s-au găsit acorduri pentru această căutare.'

        }), 404

    try:

        url_to_save = result.get("url", "https://www.ultimate-guitar.com")

        cursor.execute("""
            INSERT INTO chords_cache (query_text, song_title, artist, chords_text, url)
            VALUES (%s, %s, %s, %s, %s)
        """, (query, result["title"], result["artist"], result["chords_text"], url_to_save))

        conn.commit()

        print(f"✅ [CACHE] Salvat pentru query: '{query}'", flush=True)

    except Exception as e:

        print(f"❌ [CACHE] Eroare la salvare: {e}", flush=True)

    finally:

        if 'cursor' in locals() and cursor:

            cursor.close()

        if 'conn' in locals() and conn:

            conn.close()

    return jsonify(result), 200

@app.route('/api/chords/results', methods=['POST'])

def chord_results():

    data = request.json

    query = data.get('query', '').strip() if data else ''

    if not query:

        return jsonify({'error': 'Query is required'}), 400

    results = search_chords(query)

    return jsonify({'results': results}), 200

@app.route('/api/chords/tab', methods=['POST'])

def chord_tab():

    data = request.json

    url = data.get('url', '').strip() if data else ''

    if not url:

        return jsonify({'error': 'URL is required'}), 400

    result = get_chord_content(url)

    if not result:

        return jsonify({

            'error': 'extraction_failed',

            'message': 'Nu s-au putut extrage acordurile de la acest URL.'

        }), 404

    return jsonify(result), 200

if __name__ == '__main__':

    app.run(host='0.0.0.0', port=5000, debug=True)
