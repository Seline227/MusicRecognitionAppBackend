import os
import jwt

from flask import Blueprint, request, jsonify
from services.chord_search_service import search_chords
from database import get_db_connection

chords_bp = Blueprint("chords", __name__)

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

@chords_bp.route("/search-chords", methods=["POST"])

def search_chords_route():

    data = request.get_json(silent=True)

    if not data:

        return jsonify({"status": "error", "error": "Request body trebuie să fie JSON valid."}), 400

    query = data.get("query", "").strip()

    if not query or len(query) < 2:

        return jsonify({"status": "error", "error": "Query-ul trebuie să aibă cel puțin 2 caractere."}), 400

    try:

        conn = get_db_connection()

        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT song_title, artist, chords_text, url FROM chords_cache WHERE query_text = %s", (query,))

        cached_result = cursor.fetchone()

        if cached_result:

            print(f"[CACHE] Hit pentru query: '{query}'", flush=True)

            cursor.close()

            conn.close()

            return jsonify({

                "status": "success",

                "title": cached_result["song_title"],

                "artist": cached_result["artist"],

                "content": cached_result["chords_text"],

                "source": cached_result["url"] if cached_result["url"] else "cache",

            }), 200

    except Exception as e:

        print(f"[CACHE] Eroare la citire: {e}", flush=True)

    try:

        result = search_chords(query)

        try:

            cursor.execute("""
                INSERT INTO chords_cache (query_text, song_title, artist, chords_text, url)
                VALUES (%s, %s, %s, %s, %s)
            """, (query, result["title"], result["artist"], result["content"], result["source"]))

            conn.commit()

            print(f"[CACHE] Salvat pentru query: '{query}'", flush=True)

        except Exception as e:

            print(f"[CACHE] Eroare la salvare: {e}", flush=True)

        finally:

            if 'cursor' in locals():

                cursor.close()

            if 'conn' in locals():

                conn.close()

        return jsonify({

            "status": "success",

            "title": result["title"],

            "artist": result["artist"],

            "content": result["content"],

            "source": result["source"],

        }), 200

    except ValueError as e:

        return jsonify({"status": "error", "error": str(e)}), 400

    except LookupError as e:

        return jsonify({"status": "not_found", "error": str(e)}), 404

    except ConnectionError as e:

        return jsonify({"status": "service_unavailable", "error": str(e)}), 503

    except Exception as e:

        print(f"[CHORDS] ERROR: {e}", flush=True)

        return jsonify({"status": "error", "error": f"Eroare internă: {str(e)}"}), 500
