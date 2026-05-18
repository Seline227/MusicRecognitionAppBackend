"""
Blueprint Flask pentru căutarea de acorduri și versuri.
Rută: POST /search-chords
"""

from flask import Blueprint, request, jsonify
from services.chord_search_service import search_chords


chords_bp = Blueprint("chords", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# POST /search-chords
# ─────────────────────────────────────────────────────────────────────────────
@chords_bp.route("/search-chords", methods=["POST"])
def search_chords_route():
    """
    POST /search-chords
    Accepts JSON body:
        { "query": "Hotel California Eagles" }

    Returns:
        200 — { title, artist, content, source }
        400 — Input invalid (query lipsă sau prea scurt)
        404 — Piesa nu a fost găsită
        503 — Servicii externe indisponibile
    """
    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "status": "error",
            "error": "Request body trebuie să fie JSON valid cu cheia 'query'."
        }), 400

    query = data.get("query", "").strip()

    if not query:
        return jsonify({
            "status": "error",
            "error": "Câmpul 'query' este obligatoriu."
        }), 400

    if len(query) < 2:
        return jsonify({
            "status": "error",
            "error": "Query-ul trebuie să aibă cel puțin 2 caractere."
        }), 400

    try:
        result = search_chords(query)
        return jsonify({
            "status": "success",
            "title": result["title"],
            "artist": result["artist"],
            "content": result["content"],
            "source": result["source"],
        }), 200

    except ValueError as e:
        # Input invalid
        return jsonify({
            "status": "error",
            "error": str(e),
        }), 400

    except LookupError as e:
        # Piesa nu a fost găsită
        return jsonify({
            "status": "not_found",
            "error": str(e),
        }), 404

    except ConnectionError as e:
        # Servicii externe indisponibile
        return jsonify({
            "status": "service_unavailable",
            "error": str(e),
        }), 503

    except Exception as e:
        # Eroare neașteptată
        print(f"[CHORDS] ERROR - Eroare neasteptata: {e}", flush=True)
        return jsonify({
            "status": "error",
            "error": f"Eroare internă de server: {str(e)}",
        }), 500
