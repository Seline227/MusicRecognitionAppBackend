from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from database import get_db_connection  # Folosim funcția ta de conexiune

app = Flask(__name__)
CORS(app)

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
        return jsonify({'message': 'User creat cu succes', 'user_id': user_id})

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
            return jsonify({'message': 'Autentificare reușită', 'user_id': user['id']})
        else:
            return jsonify({'error': 'Email sau parola incorecte'}), 401
    except Exception as err:
        return jsonify({'error': str(err)}), 500

if __name__ == '__main__':
    app.run(debug=True)
