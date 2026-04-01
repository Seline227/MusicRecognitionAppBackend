from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from dotenv import load_dotenv
from database import get_db_connection  # Folosim funcția ta de conexiune
from models import create_recognition_history_table, create_password_resets_table
from routes.recognize import recognize_bp

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

# Register blueprints
app.register_blueprint(recognize_bp)

# --- DEBUGGING: Interceptăm ORICE cerere care ajunge la server ---
@app.before_request
def log_request_info():
    print(f"📡 [TRAFIC INTERCEPTAT] Metodă: {request.method} | Către: {request.url} | IP Sursă: {request.remote_addr}", flush=True)
# -----------------------------------------------------------------

# Create tables at startup
create_recognition_history_table()
create_password_resets_table()

# 🔹 Signup
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

        # 🔹 Verificăm dacă emailul există deja
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()
        if existing_user:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Acest email este deja folosit'}), 409  # 409 = Conflict

        # 🔹 Creare user nou
        user_id = str(uuid.uuid4())  # ID unic
        hashed_password = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (id, first_name, last_name, email, password) VALUES (%s,%s,%s,%s,%s)",
            (user_id, first_name, last_name, email, hashed_password)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        # 🔹 Generăm JWT pentru autologin
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

# 🔹 Signin
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
            # 🔹 Generăm JWT
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

# 🔹 Google Sign-In
@app.route('/api/auth/google', methods=['POST'])
def google_signin():
    print("🔥 [BACKEND] Se primește cerere POST la /api/auth/google pentru login Google...", flush=True)

    data = request.json
    token = data.get('idToken') or data.get('id_token')

    if not token:
        return jsonify({'error': 'idToken este obligatoriu'}), 400

    try:
        # 1. Validăm Token-ul primit de la Flutter cu serverele Google
        google_client_id = os.getenv('GOOGLE_CLIENT_ID')
        idinfo = id_token.verify_oauth2_token(
            token, 
            google_requests.Request(), 
            google_client_id
        )

        # 2. Extragem datele utilizatorului din payload-ul de la Google
        email = idinfo.get('email')
        google_id = idinfo.get('sub')  # ID-ul unic returnat de Google
        name = idinfo.get('name', '')
        profile_picture = idinfo.get('picture', '')

        # Despărțim numele (Google aduce fullname, iar DB-ul tău are first_name/last_name)
        name_parts = name.split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 3. Verificăm dacă utilizatorul există
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user:
            # Actualizăm google_id dacă inițial făcuse cont cu parolă
            if not user.get('google_id'):
                cursor.execute(
                    "UPDATE users SET google_id = %s, profile_picture = %s WHERE email = %s",
                    (google_id, profile_picture, email)
                )
                conn.commit()
            user_id = user['id']
        else:
            # 4. Creăm cont nou fără parolă
            user_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO users (id, first_name, last_name, email, google_id, profile_picture, password) 
                VALUES (%s, %s, %s, %s, %s, %s, NULL)
                """,
                (user_id, first_name, last_name, email, google_id, profile_picture)
            )
            conn.commit()

        cursor.close()
        conn.close()

        # 5. Generăm JWT
        jwt_secret = os.getenv('JWT_SECRET_KEY')
        payload = {
            'user_id': user_id,
            'email': email,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
        }
        
        session_token = jwt.encode(payload, jwt_secret, algorithm='HS256')

        # 6. Returnăm răspunsul curat către Flutter
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
        print(f"❌ [BACKEND] Eroare validare token Google (ValueError): {e}", flush=True)
        return jsonify({'error': f'Token de la Google invalid: {e}'}), 401
    except Exception as err:
        import traceback
        print(f"❌ [BACKEND] EROARE GRAVĂ INTERNĂ la Google Login: {err}", flush=True)
        traceback.print_exc()  # Asta va printa exact linia de cod unde a crăpat
        return jsonify({'error': f'Eroare internă de server: {str(err)}'}), 500

# ---------------------------------------------------------
# 🔹 HELPER: Trimitere Email OTP
# ---------------------------------------------------------
def send_otp_email(to_email, otp):
    smtp_email = os.getenv('SMTP_EMAIL')
    smtp_password = os.getenv('SMTP_PASSWORD')
    
    if not smtp_email or not smtp_password:
        print("❌ [BACKEND] Eroare: SMTP_EMAIL sau SMTP_PASSWORD lipsesc din .env!", flush=True)
        return False

    msg = MIMEText(f"Salut!\n\nCodul tău de resetare a parolei este: {otp}\nAcest cod expiră în 15 minute.\n\nDacă nu ai cerut o resetare de parolă, te rugăm să ignori acest email.")
    msg['Subject'] = 'Cod de resetare a parolei - Harmoniq'  # type: ignore
    msg['From'] = smtp_email  # type: ignore
    msg['To'] = to_email  # type: ignore

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

# ---------------------------------------------------------
# 🔹 Forgot Password Flow (Resetare Parolă via OTP)
# ---------------------------------------------------------
@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.json
    email = data.get('email')

    if not email:
        return jsonify({"success": False, "error": "Email is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Verificăm dacă email-ul există în baza de date
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()

    if not user:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "error": "Email not found"}), 404

    # Generează cod OTP de 6 cifre
    otp = str(random.randint(100000, 999999))
    expires_at = datetime.datetime.now() + datetime.timedelta(minutes=15)

    # Ștergem orice OTP vechi pentru acest email și inserăm unul nou
    cursor.execute("DELETE FROM password_resets WHERE email = %s", (email,))
    cursor.execute(
        "INSERT INTO password_resets (email, otp, expires_at) VALUES (%s, %s, %s)",
        (email, otp, expires_at)
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Trimitem emailul
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

    # Re-verificăm OTP-ul pentru securitate
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

    # Hash-uim noua parolă și actualizăm în users
    hashed_password = generate_password_hash(new_password)
    cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_password, email))

    # Ștergem TOATE OTP-urile pentru acest email (invalidare completă)
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
        
        # ── Cascading manual: ștergem datele dependente ──
        # 1. Istoric scanări
        cursor.execute("DELETE FROM recognition_history WHERE user_id = %s", (user_id,))
        print(f"ℹ️ [DELETE ACCOUNT] Deleted {cursor.rowcount} records from recognition_history.", flush=True)
        
        # 2. Toate cererile de resetare a parolei
        if email:
            cursor.execute("DELETE FROM password_resets WHERE email = %s", (email,))
            print(f"ℹ️ [DELETE ACCOUNT] Deleted {cursor.rowcount} records from password_resets.", flush=True)
            
        # 3. Stergere user
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        print(f"ℹ️ [DELETE ACCOUNT] Deleted {cursor.rowcount} records from users table.", flush=True)
        
        # Salvăm modificările
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

if __name__ == '__main__':
    # Ascultăm pe '0.0.0.0' pentru a fi accesibili din rețeaua locală
    app.run(host='0.0.0.0', port=5000, debug=True)
