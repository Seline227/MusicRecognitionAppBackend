import os
import hmac
import hashlib
import base64
import time
import requests


def recognize_song(file_path):
    """
    Sends an audio file to ACRCloud for music recognition.

    ACRCloud uses HMAC-SHA1 signature-based authentication.

    Args:
        file_path: Absolute path to the audio file (.m4a or .wav).

    Returns:
        dict with keys: artist, title, album (values may be None if not found).

    Raises:
        Exception: If ACRCloud returns an error or no result is found.
    """
    host        = os.getenv("ACRCLOUD_HOST", "")
    access_key  = os.getenv("ACRCLOUD_ACCESS_KEY", "")
    access_secret = os.getenv("ACRCLOUD_ACCESS_SECRET", "")

    if not all([host, access_key, access_secret]):
        raise Exception(
            "ACRCloud credentials missing! Make sure ACRCLOUD_HOST, "
            "ACRCLOUD_ACCESS_KEY and ACRCLOUD_ACCESS_SECRET are set in .env"
        )

    # ── Build HMAC-SHA1 signature ──────────────────────────────────────
    http_method   = "POST"
    http_uri      = "/v1/identify"
    data_type     = "audio"
    signature_version = "1"
    timestamp     = str(time.time())

    string_to_sign = "\n".join([
        http_method,
        http_uri,
        access_key,
        data_type,
        signature_version,
        timestamp,
    ])

    signature = base64.b64encode(
        hmac.new(
            access_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha1,
        ).digest()
    ).decode("utf-8")

    # ── Read audio file and send request ──────────────────────────────
    file_size = os.path.getsize(file_path)
    print(f"[ACRCloud] File: {file_path} ({file_size} bytes)")
    print(f"[ACRCloud] Sending request to {host}...")

    with open(file_path, "rb") as audio_file:
        files = {"sample": audio_file}
        data = {
            "access_key":        access_key,
            "sample_bytes":      str(file_size),
            "timestamp":         timestamp,
            "signature":         signature,
            "data_type":         data_type,
            "signature_version": signature_version,
        }
        response = requests.post(
            f"https://{host}/v1/identify",
            files=files,
            data=data,
            timeout=30,
        )

    result_json = response.json()
    print(f"[ACRCloud] Response status: {result_json.get('status')}")

    import json
    print("\n--- [ACRCloud] FULL JSON RESPONSE ---")
    print(json.dumps(result_json, indent=2))
    print("--------------------------------------\n")

    # ── Parse response ─────────────────────────────────────────────────
    status_code = result_json.get("status", {}).get("code")
    if status_code != 0:
        msg = result_json.get("status", {}).get("msg", "Unknown ACRCloud error")
        raise Exception(f"ACRCloud: {msg} (code {status_code})")

    music_list = result_json.get("metadata", {}).get("music", [])
    if not music_list:
        raise Exception("No song recognized. Try a longer or clearer audio sample.")

    top_match = music_list[0]
    artist_list = top_match.get("artists", [{}])
    artist = artist_list[0].get("name") if artist_list else None

    print(f"[ACRCloud] Recognized: {artist} - {top_match.get('title')}")

    return {
        "artist": artist,
        "title":  top_match.get("title"),
        "album":  top_match.get("album", {}).get("name"),
        "releaseDate": top_match.get("release_date", "Unknown Date"),
    }
