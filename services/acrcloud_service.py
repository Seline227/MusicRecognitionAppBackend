import os
import hmac
import hashlib
import base64
import time
import json
import requests


def recognize_song(file_path: str, mode: str = "ambient") -> dict:
    """
    Sends an audio file to ACRCloud for music recognition.

    ACRCloud uses HMAC-SHA1 signature-based authentication.

    Args:
        file_path: Absolute path to the audio file (.m4a or .wav).
        mode: 'ambient' for normal recognition, 'humming' for hum/singing recognition.

    Returns:
        dict with keys: title, artist, album, cover_url, releaseDate.

    Raises:
        Exception: If ACRCloud returns an error or no result is found.
    """
    host          = os.getenv("ACRCLOUD_HOST", "")
    access_key    = os.getenv("ACRCLOUD_ACCESS_KEY", "")
    access_secret = os.getenv("ACRCLOUD_ACCESS_SECRET", "")

    if not all([host, access_key, access_secret]):
        raise Exception(
            f"ACRCloud credentials missing for mode '{mode}'! "
            "Check your .env file."
        )

    # ACRCloud uses different data_type for humming vs. ambient
    data_type = "humming" if mode == "humming" else "audio"

    # ── Build HMAC-SHA1 signature ──────────────────────────────────────
    http_method       = "POST"
    http_uri          = "/v1/identify"
    signature_version = "1"
    timestamp         = str(time.time())

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
    print(f"[ACRCloud] File: {file_path} ({file_size} bytes) | mode={mode} | data_type={data_type}")

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
    print("\n--- [ACRCloud] FULL JSON RESPONSE ---")
    print(json.dumps(result_json, indent=2))
    print("--------------------------------------\n")

    # ── Parse response ─────────────────────────────────────────────────
    status_code = result_json.get("status", {}).get("code")
    
    if status_code == 1001:
        # "No Result" - nu e eroare de server, ci doar nu a recunoscut piesa
        raise Exception("Nu am putut recunoaște piesa din înregistrare. Încearcă să cânți/fredonezi mai tare și mai clar.")
    
    if status_code != 0:
        msg = result_json.get("status", {}).get("msg", "Unknown ACRCloud error")
        raise Exception(f"ACRCloud a returnat o eroare: {msg} (code {status_code})")

    music_list = result_json.get("metadata", {}).get("music", [])
    if not music_list:
        raise Exception("No song recognized. Try a longer or clearer audio sample.")

    top_match   = music_list[0]
    artist_list = top_match.get("artists", [{}])
    artist      = artist_list[0].get("name") if artist_list else None

    # Try to get cover art from Spotify metadata embedded in the response
    cover_url   = None
    spotify_meta = top_match.get("external_metadata", {}).get("spotify", {})
    album_images = spotify_meta.get("album", {}).get("images", [])
    if album_images:
        cover_url = album_images[0].get("url")

    print(f"[ACRCloud] Recognized: {artist} - {top_match.get('title')}")

    return {
        "title":       top_match.get("title"),
        "artist":      artist,
        "album":       top_match.get("album", {}).get("name"),
        "cover_url":   cover_url,
        "releaseDate": top_match.get("release_date", "Unknown Date"),
    }

