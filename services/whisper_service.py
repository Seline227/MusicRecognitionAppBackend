"""
Speech-to-Text cu Google Web Speech API (gratuit, fara cheie API)
urmat de cautare piesa via ACRCloud Search API (aceleasi credentiale pe care le ai deja).
"""

import os
import wave
import tempfile
import requests
import speech_recognition as sr
from pydub import AudioSegment


# ─────────────────────────────────────────────────────────────────────────────
# Pas 1: Conversie audio → WAV (Google ASR lucreaza DOAR cu WAV PCM)
# ─────────────────────────────────────────────────────────────────────────────
def _convert_to_wav(input_path: str) -> str:
    """
    Converts any audio file supported by pydub/ffmpeg to a 16-bit mono 16kHz WAV.
    Returns the path to the temporary WAV file (caller must delete it).
    """
    ext = os.path.splitext(input_path)[1].lower().lstrip(".")

    try:
        if ext == "wav":
            audio = AudioSegment.from_wav(input_path)
        else:
            fmt = {"m4a": "m4a", "aac": "aac", "mp3": "mp3", "ogg": "ogg", "flac": "flac"}.get(ext, ext)
            audio = AudioSegment.from_file(input_path, format=fmt)
    except Exception as e:
        raise Exception(f"Nu am putut citi fisierul audio ({ext}). Asigura-te ca ffmpeg este instalat. Eroare: {e}")

    # Normalize: mono, 16 kHz, 16-bit — optimal pentru recunoastere vocala
    audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)

    temp_fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(temp_fd)
    audio.export(wav_path, format="wav")
    print(f"[SpeechService] Converted to WAV: {wav_path} ({os.path.getsize(wav_path)} bytes)")
    return wav_path


# ─────────────────────────────────────────────────────────────────────────────
# Pas 2: Transcriere cu Google Web Speech API (gratis, fara cheie)
# ─────────────────────────────────────────────────────────────────────────────
def transcribe_audio(file_path: str) -> str:
    """
    Transcribes audio to text using the free Google Web Speech API.
    Tries Romanian first, then English as fallback (for international songs).

    Args:
        file_path: Path to audio file (.m4a, .wav, .mp3, etc.)

    Returns:
        Transcribed text string.

    Raises:
        Exception: If Google cannot understand the audio or network fails.
    """
    wav_path = None
    try:
        wav_path = _convert_to_wav(file_path)

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio_data = recognizer.record(source)

        # Incercam mai intai romana (pentru muzica romaneasca)
        try:
            text = recognizer.recognize_google(audio_data, language="ro-RO")
            print(f"[SpeechService] Transcribed (ro-RO): '{text}'")
            return text
        except sr.UnknownValueError:
            pass  # Google nu a inteles in romana, incercam engleza

        # Fallback engleza (pentru muzica internationala)
        try:
            text = recognizer.recognize_google(audio_data, language="en-US")
            print(f"[SpeechService] Transcribed (en-US): '{text}'")
            return text
        except sr.UnknownValueError:
            raise Exception(
                "Google Speech nu a putut intelege audio-ul. "
                "Incearca sa canti mai clar sau foloseste modul 'ambient'/'humming'."
            )

    except sr.RequestError as e:
        raise Exception(f"Eroare conexiune Google Speech API: {e}")

    finally:
        # Stergem fisierul WAV temporar
        if wav_path and wav_path != file_path and os.path.exists(wav_path):
            os.remove(wav_path)


# ─────────────────────────────────────────────────────────────────────────────
# Pas 3: Cautare piesa dupa text via YouTube Music Search (ytmusicapi)
# ─────────────────────────────────────────────────────────────────────────────
from ytmusicapi import YTMusic

# Cream o instanta in afara functiei pentru a o refolosi (performanta mai buna)
ytmusic = YTMusic()

def search_by_lyrics(lyrics_text: str) -> dict:
    """
    Searches YouTube Music for a song based on a transcribed lyrics fragment.
    YT Music is incredibly smart at guessing songs even if the lyrics transcription
    has typos or misheard words (e.g. "heart breaker this girl my" -> "Baby" Justin Bieber).

    Returns a unified dict: { title, artist, album, cover_url, releaseDate }.

    Args:
        lyrics_text: Fragment de versuri transcris de Google Speech.

    Raises:
        Exception: If no song is found or the search fails.
    """
    if not lyrics_text or len(lyrics_text.strip()) < 3:
        raise Exception(
            "Textul transcris este prea scurt pentru cautare. "
            "Incearca sa canti un fragment mai lung (minim 3-4 cuvinte)."
        )

    print(f"[YTMusic] Searching for lyrics: '{lyrics_text[:100]}'")

    try:
        # Folosim filtrul 'songs' pentru a ne asigura ca primim piese oficiale (nu coveruri video)
        results = ytmusic.search(query=lyrics_text, filter="songs", limit=3)
    except Exception as e:
        raise Exception(f"Eroare la contactarea motorului YT Music: {e}")

    if not results:
        raise Exception(
            "Nu am gasit nicio melodie dupa versurile transcrise. "
            "Incearca sa pronunti mai clar un fragment diferit."
        )

    # Luam prima piesa oficiala (top match)
    top = results[0]

    title = top.get("title")
    
    # Extragem artistul principal (ytmusic returneaza o lista de dict-uri pt artisti)
    artists_data = top.get("artists", [])
    artist = artists_data[0].get("name") if artists_data else "Unknown Artist"

    # Extragem albumul
    album_data = top.get("album")
    album = album_data.get("name") if album_data else None

    # Extragem cover_url (thumbnails)
    cover_url = None
    thumbnails = top.get("thumbnails", [])
    if thumbnails:
        # Ultimul thumbnail e de obicei cel mai mare si la rezolutia cea mai buna
        cover_url = thumbnails[-1].get("url")

    # YouTube Music API nu ofera direct release_date in sectiunea de cautare rapida
    release_date = None

    print(f"[YTMusic] Found: {artist} - {title}")

    return {
        "title":       title,
        "artist":      artist,
        "album":       album,
        "cover_url":   cover_url,
        "releaseDate": release_date,
    }
