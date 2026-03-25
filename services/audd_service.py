import os
import requests


def recognize_song(file_path):
    """
    Sends an audio file to the AudD API for music recognition.

    Args:
        file_path: Absolute path to the audio file (.m4a or .wav).

    Returns:
        dict with keys: artist, title, album (values may be None if not found).

    Raises:
        Exception: If the API returns an error or no result is found.
    """
    api_key = os.getenv("AUDD_API_KEY", "")

    # ── Debug logging ──
    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
    print(f"[AudD] File: {file_path} ({file_size} bytes)")
    print(f"[AudD] API Key present: {'YES' if api_key else 'NO (EMPTY!)'}")

    if not api_key:
        raise Exception("AUDD_API_KEY is not set! Create a .env file with your key.")

    with open(file_path, "rb") as audio_file:
        response = requests.post(
            "https://api.audd.io/",
            data={"api_token": api_key, "return": "apple_music,spotify"},
            files={"file": audio_file},
            timeout=30,
        )

    data = response.json()
    print(f"[AudD] Response: {data}")

    status_field = data.get("status")

    # Handle ACRCloud Enterprise format (where status is a dict)
    if isinstance(status_field, dict):
        if status_field.get("code") != 0:
            raise Exception(f"ACR API error: {status_field.get('msg')}")
        
        metadata = data.get("metadata", {})
        music_list = metadata.get("music", [])
        if not music_list:
            raise Exception("No song recognized. Try with a clearer audio sample.")
        
        music = music_list[0]
        artist_name = music.get("artists", [{}])[0].get("name", "Unknown Artist") if music.get("artists") else "Unknown Artist"
        title = music.get("title", "Unknown Title")
        album_name = music.get("album", {}).get("name", "Unknown Album") if music.get("album") else "Unknown Album"
        release_date = music.get("release_date", "Unknown Date")
        
        print(f"[AudD] Recognized (ACR format): {artist_name} - {title}")
        return {
            "artist": artist_name,
            "title": title,
            "album": album_name,
            "releaseDate": release_date,
        }

    # Handle Standard AudD format (where status is a string "success")
    if status_field != "success":
        error_msg = data.get("error", {}).get("error_message", "Unknown AudD error")
        raise Exception(f"AudD API error: {error_msg}")

    result = data.get("result")
    if not result:
        raise Exception("No song recognized. Try with a clearer audio sample or hold the phone closer to the speaker.")

    print(f"[AudD] Recognized: {result.get('artist')} - {result.get('title')}")
    return {
        "artist": result.get("artist"),
        "title": result.get("title"),
        "album": result.get("album"),
        "releaseDate": result.get("release_date", "Unknown Date"),
    }
