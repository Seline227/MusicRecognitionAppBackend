import os
import wave

import tempfile
import requests

import speech_recognition as sr
from pydub import AudioSegment

def _convert_to_wav(input_path: str) -> str:

    ext = os.path.splitext(input_path)[1].lower().lstrip(".")

    try:

        if ext == "wav":

            audio = AudioSegment.from_wav(input_path)

        else:

            fmt = {"m4a": "m4a", "aac": "aac", "mp3": "mp3", "ogg": "ogg", "flac": "flac"}.get(ext, ext)

            audio = AudioSegment.from_file(input_path, format=fmt)

    except Exception as e:

        raise Exception(f"Nu am putut citi fisierul audio ({ext}). Asigura-te ca ffmpeg este instalat. Eroare: {e}")

    audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)

    temp_fd, wav_path = tempfile.mkstemp(suffix=".wav")

    os.close(temp_fd)

    audio.export(wav_path, format="wav")

    print(f"[SpeechService] Converted to WAV: {wav_path} ({os.path.getsize(wav_path)} bytes)")

    return wav_path

def transcribe_audio(file_path: str) -> str:

    wav_path = None

    try:

        wav_path = _convert_to_wav(file_path)

        recognizer = sr.Recognizer()

        with sr.AudioFile(wav_path) as source:

            recognizer.adjust_for_ambient_noise(source, duration=0.3)

            audio_data = recognizer.record(source)

        try:

            text = recognizer.recognize_google(audio_data, language="ro-RO")

            print(f"[SpeechService] Transcribed (ro-RO): '{text}'")

            return text

        except sr.UnknownValueError:

            pass

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

        if wav_path and wav_path != file_path and os.path.exists(wav_path):

            os.remove(wav_path)

from ytmusicapi import YTMusic

ytmusic = YTMusic()

def search_by_lyrics(lyrics_text: str) -> dict:

    if not lyrics_text or len(lyrics_text.strip()) < 3:

        raise Exception(

            "Textul transcris este prea scurt pentru cautare. "

            "Incearca sa canti un fragment mai lung (minim 3-4 cuvinte)."

        )

    print(f"[YTMusic] Searching for lyrics: '{lyrics_text[:100]}'")

    try:

        results = ytmusic.search(query=lyrics_text, filter="songs", limit=3)

    except Exception as e:

        raise Exception(f"Eroare la contactarea motorului YT Music: {e}")

    if not results:

        raise Exception(

            "Nu am gasit nicio melodie dupa versurile transcrise. "

            "Incearca sa pronunti mai clar un fragment diferit."

        )

    top = results[0]

    title = top.get("title")

    artists_data = top.get("artists", [])

    artist = artists_data[0].get("name") if artists_data else "Unknown Artist"

    album_data = top.get("album")

    album = album_data.get("name") if album_data else None

    cover_url = None

    thumbnails = top.get("thumbnails", [])

    if thumbnails:

        cover_url = thumbnails[-1].get("url")

    release_date = None

    print(f"[YTMusic] Found: {artist} - {title}")

    return {

        "title":       title,

        "artist":      artist,

        "album":       album,

        "cover_url":   cover_url,

        "releaseDate": release_date,

    }
