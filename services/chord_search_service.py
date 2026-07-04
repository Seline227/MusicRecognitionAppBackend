import re
import json

import time
import requests

from bs4 import BeautifulSoup
from urllib.parse import quote_plus

_HEADERS = {

    "User-Agent": (

        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "

        "AppleWebKit/537.36 (KHTML, like Gecko) "

        "Chrome/125.0.0.0 Safari/537.36"

    ),

    "Accept-Language": "en-US,en;q=0.9",

    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",

}

_REQUEST_TIMEOUT = 15

def search_chords(query: str) -> dict:

    query = query.strip()

    if not query or len(query) < 2:

        raise ValueError("Query-ul trebuie sa aiba cel putin 2 caractere.")

    print(f"[CHORDS] Cautare acorduri pentru: '{query}'", flush=True)

    errors = []

    try:

        result = _search_guitaretab(query)

        if result:

            print(f"[CHORDS] OK - Gasit pe Guitaretab: {result['title']} - {result['artist']}", flush=True)

            return result

    except Exception as e:

        print(f"[CHORDS] WARN - Guitaretab a esuat: {e}", flush=True)

        errors.append(f"Guitaretab: {e}")

    try:

        result = _search_songsterr(query)

        if result:

            print(f"[CHORDS] OK - Gasit pe Songsterr: {result['title']} - {result['artist']}", flush=True)

            return result

    except Exception as e:

        print(f"[CHORDS] WARN - Songsterr a esuat: {e}", flush=True)

        errors.append(f"Songsterr: {e}")

    if errors:

        print(f"[CHORDS] FAIL - Toate sursele au esuat: {errors}", flush=True)

        raise ConnectionError(

            f"Serviciile externe sunt indisponibile. Detalii: {'; '.join(errors)}"

        )

    print("[CHORDS] FAIL - Piesa nu a fost gasita in nicio sursa.", flush=True)

    raise LookupError("Piesa nu a fost gasita. Incearca un alt titlu sau adauga numele artistului.")

def _search_guitaretab(query: str) -> dict | None:

    search_url = f"https://www.guitaretab.com/fetch/?type=tab&query={quote_plus(query)}"

    print(f"[GUITARETAB] Cautare: {search_url}", flush=True)

    try:

        resp = requests.get(search_url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)

        resp.raise_for_status()

    except requests.RequestException as e:

        raise ConnectionError(f"Nu se poate accesa Guitaretab: {e}")

    soup = BeautifulSoup(resp.text, "html.parser")

    all_links = soup.find_all("a", href=True)

    song_links = []

    for link in all_links:

        href = link.get("href", "")

        text = link.get_text(strip=True)

        if re.match(r'^/\w/[\w-]+/\d+\.html$', href) and text:

            is_chords = "chords" in text.lower()

            song_links.append({

                "href": href,

                "text": text,

                "is_chords": is_chords,

            })

    if not song_links:

        print("[GUITARETAB] Niciun rezultat gasit.", flush=True)

        return None

    chord_links = [s for s in song_links if s["is_chords"]]

    best_link = chord_links[0] if chord_links else song_links[0]

    tab_url = f"https://www.guitaretab.com{best_link['href']}"

    print(f"[GUITARETAB] Accesam: {tab_url}", flush=True)

    link_text = best_link["text"]

    time.sleep(0.5)

    try:

        resp2 = requests.get(tab_url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)

        resp2.raise_for_status()

    except requests.RequestException as e:

        print(f"[GUITARETAB] Eroare la accesarea tab-ului: {e}", flush=True)

        return None

    soup2 = BeautifulSoup(resp2.text, "html.parser")

    pre_tag = soup2.find("pre")

    if not pre_tag:

        print("[GUITARETAB] Nu s-a gasit tag-ul <pre> cu continutul.", flush=True)

        return None

    content = pre_tag.get_text()

    if not content or len(content.strip()) < 20:

        print("[GUITARETAB] Continut prea scurt sau gol.", flush=True)

        return None

    title, artist = _extract_title_artist_from_content(content, link_text)

    content = _clean_guitaretab_content(content)

    return {

        "title": title,

        "artist": artist,

        "content": content,

        "source": "guitaretab",

    }

def _extract_title_artist_from_content(content: str, fallback_text: str) -> tuple:

    title = "Unknown"

    artist = "Unknown"

    lines = content.split("\n")

    for line in lines[:20]:

        line_clean = line.strip()

        title_match = re.match(r'^Title\s*[-:]\s*(.+)', line_clean, re.IGNORECASE)

        if title_match:

            title = title_match.group(1).strip()

        artist_match = re.match(r'^Artist\s*[-:]\s*(.+)', line_clean, re.IGNORECASE)

        if artist_match:

            artist = artist_match.group(1).strip()

    if title == "Unknown" and fallback_text:

        cleaned = re.sub(r'\b(chords?|tabs?|ver\s*\d+|acoustic|live)\b', '', fallback_text, flags=re.IGNORECASE)

        title = cleaned.strip().strip("-").strip()

    return title, artist

def _clean_guitaretab_content(content: str) -> str:

    lines = content.split("\n")

    clean_lines = []

    skip_header = True

    for line in lines:

        if skip_header:

            stripped = line.strip()

            if stripped.startswith("#") or stripped.startswith("-"):

                continue

            if not stripped:

                continue

            skip_header = False

        clean_lines.append(line)

    result = "\n".join(clean_lines)

    result = re.sub(r'\n{4,}', '\n\n\n', result)

    return result.strip()

def _search_songsterr(query: str) -> dict | None:

    search_url = f"https://www.songsterr.com/api/songs?pattern={quote_plus(query)}"

    print(f"[SONGSTERR] Cautare: {search_url}", flush=True)

    try:

        resp = requests.get(search_url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)

    except requests.RequestException as e:

        raise ConnectionError(f"Nu se poate accesa Songsterr: {e}")

    if resp.status_code == 404:

        return None

    resp.raise_for_status()

    try:

        songs = resp.json()

    except (json.JSONDecodeError, ValueError):

        return None

    if not songs or not isinstance(songs, list):

        return None

    song = songs[0]

    song_id = song.get("songId")

    title = song.get("title", "Unknown")

    artist = song.get("artist", "Unknown")

    has_chords = song.get("hasChords", False)

    if not song_id:

        return None

    artist_slug = re.sub(r'[^a-zA-Z0-9]+', '-', artist.lower()).strip('-')

    title_slug = re.sub(r'[^a-zA-Z0-9]+', '-', title.lower()).strip('-')

    if has_chords:

        chords_url = f"https://www.songsterr.com/a/wsa/{artist_slug}-{title_slug}-chords-s{song_id}"

    else:

        chords_url = f"https://www.songsterr.com/a/wsa/{artist_slug}-{title_slug}-tab-s{song_id}"

    content_lines = [

        f"Song: {title}",

        f"Artist: {artist}",

        f"",

    ]

    tracks = song.get("tracks", [])

    guitar_tracks = [t for t in tracks if "guitar" in t.get("instrument", "").lower()]

    if guitar_tracks:

        content_lines.append("Available guitar tracks:")

        for track in guitar_tracks:

            name = track.get("name", track.get("instrument", "Guitar"))

            difficulty = track.get("difficulty", "N/A")

            views = track.get("views", 0)

            content_lines.append(f"  - {name} (difficulty: {difficulty}, views: {views:,})")

        content_lines.append("")

    content_lines.append(f"View full chords/tab at: {chords_url}")

    return {

        "title": title,

        "artist": artist,

        "content": "\n".join(content_lines),

        "source": "songsterr",

        "url": chords_url,

    }
