"""
Serviciu de cautare acorduri si versuri.

Strategia de cautare (cu fallback):
  1. Guitaretab.com - Web scraping (simplu, text curat, functioneaza fara JS)
  2. Songsterr - API intern pentru metadata + link catre tab
  3. Eroare gracioasa daca niciuna nu returneaza rezultate
"""

import re
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus


# ─────────────────────────────────────────────────────────────────────────────
# Headers comuni pentru a simula un browser real
# ─────────────────────────────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_REQUEST_TIMEOUT = 15  # secunde


# ═════════════════════════════════════════════════════════════════════════════
#  FUNCTIA PRINCIPALA
# ═════════════════════════════════════════════════════════════════════════════
def search_chords(query: str) -> dict:
    """
    Cauta acorduri + versuri pentru un query dat (titlu, artist, sau versuri).

    Returns:
        dict cu cheile: title, artist, content, source
    Raises:
        LookupError  - daca piesa nu a fost gasita (404)
        ConnectionError - daca toate serviciile externe sunt indisponibile (503)
    """
    query = query.strip()
    if not query or len(query) < 2:
        raise ValueError("Query-ul trebuie sa aiba cel putin 2 caractere.")

    print(f"[CHORDS] Cautare acorduri pentru: '{query}'", flush=True)

    errors = []

    # -- Strategia 1: Guitaretab.com (scraping simplu, text curat) ----------
    try:
        result = _search_guitaretab(query)
        if result:
            print(f"[CHORDS] OK - Gasit pe Guitaretab: {result['title']} - {result['artist']}", flush=True)
            return result
    except Exception as e:
        print(f"[CHORDS] WARN - Guitaretab a esuat: {e}", flush=True)
        errors.append(f"Guitaretab: {e}")

    # -- Strategia 2: Songsterr API (metadata + link) ----------------------
    try:
        result = _search_songsterr(query)
        if result:
            print(f"[CHORDS] OK - Gasit pe Songsterr: {result['title']} - {result['artist']}", flush=True)
            return result
    except Exception as e:
        print(f"[CHORDS] WARN - Songsterr a esuat: {e}", flush=True)
        errors.append(f"Songsterr: {e}")

    # -- Niciun rezultat ----------------------------------------------------
    if errors:
        print(f"[CHORDS] FAIL - Toate sursele au esuat: {errors}", flush=True)
        raise ConnectionError(
            f"Serviciile externe sunt indisponibile. Detalii: {'; '.join(errors)}"
        )

    print("[CHORDS] FAIL - Piesa nu a fost gasita in nicio sursa.", flush=True)
    raise LookupError("Piesa nu a fost gasita. Incearca un alt titlu sau adauga numele artistului.")


# ═════════════════════════════════════════════════════════════════════════════
#  STRATEGIA 1: GUITARETAB.COM (SCRAPING)
# ═════════════════════════════════════════════════════════════════════════════
def _search_guitaretab(query: str) -> dict | None:
    """
    Scraping pe Guitaretab.com:
    1. Cautam piesa pe pagina de search
    2. Filtram rezultatele de tip 'chords' (nu tab)
    3. Accesam pagina si extragem continutul din <pre>
    """
    search_url = f"https://www.guitaretab.com/fetch/?type=tab&query={quote_plus(query)}"
    print(f"[GUITARETAB] Cautare: {search_url}", flush=True)

    try:
        resp = requests.get(search_url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"Nu se poate accesa Guitaretab: {e}")

    soup = BeautifulSoup(resp.text, "html.parser")

    # Gasim toate link-urile catre piese
    all_links = soup.find_all("a", href=True)

    # Filtram doar link-urile care duc la pagini de acorduri/tab-uri
    # Format URL tipic: /e/eagles/286856.html
    song_links = []
    for link in all_links:
        href = link.get("href", "")
        text = link.get_text(strip=True)
        # Link-urile valide contin un path de tip /letter/artist/id.html
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

    # Prioritizam rezultatele de tip "chords" peste "tab"
    chord_links = [s for s in song_links if s["is_chords"]]
    best_link = chord_links[0] if chord_links else song_links[0]

    tab_url = f"https://www.guitaretab.com{best_link['href']}"
    print(f"[GUITARETAB] Accesam: {tab_url}", flush=True)

    # Extragem titlul si artistul din textul link-ului
    link_text = best_link["text"]

    # Accesam pagina tab-ului
    time.sleep(0.5)  # Rate limiting respectuos

    try:
        resp2 = requests.get(tab_url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        resp2.raise_for_status()
    except requests.RequestException as e:
        print(f"[GUITARETAB] Eroare la accesarea tab-ului: {e}", flush=True)
        return None

    soup2 = BeautifulSoup(resp2.text, "html.parser")

    # Continutul tab-ului este in tag-ul <pre>
    pre_tag = soup2.find("pre")
    if not pre_tag:
        print("[GUITARETAB] Nu s-a gasit tag-ul <pre> cu continutul.", flush=True)
        return None

    content = pre_tag.get_text()

    if not content or len(content.strip()) < 20:
        print("[GUITARETAB] Continut prea scurt sau gol.", flush=True)
        return None

    # Extragem titlul si artistul din continut (de obicei sunt in primele linii)
    title, artist = _extract_title_artist_from_content(content, link_text)

    # Curatam headerul standard (comentarii cu ---- si ##)
    content = _clean_guitaretab_content(content)

    return {
        "title": title,
        "artist": artist,
        "content": content,
        "source": "guitaretab",
    }


def _extract_title_artist_from_content(content: str, fallback_text: str) -> tuple:
    """
    Extrage titlul si artistul din continutul tab-ului.
    De obicei apar in format:
        Title - Hotel California
        Artist - Eagles
    """
    title = "Unknown"
    artist = "Unknown"

    lines = content.split("\n")
    for line in lines[:20]:  # Cautam doar in primele 20 de linii
        line_clean = line.strip()

        # Pattern: "Title - Xyz" sau "Title: Xyz"
        title_match = re.match(r'^Title\s*[-:]\s*(.+)', line_clean, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()

        # Pattern: "Artist - Xyz" sau "Artist: Xyz"
        artist_match = re.match(r'^Artist\s*[-:]\s*(.+)', line_clean, re.IGNORECASE)
        if artist_match:
            artist = artist_match.group(1).strip()

    # Fallback: extragem din textul link-ului
    if title == "Unknown" and fallback_text:
        # Remove "chords", "tab", "ver X" etc.
        cleaned = re.sub(r'\b(chords?|tabs?|ver\s*\d+|acoustic|live)\b', '', fallback_text, flags=re.IGNORECASE)
        title = cleaned.strip().strip("-").strip()

    return title, artist


def _clean_guitaretab_content(content: str) -> str:
    """
    Curata continutul extras de pe Guitaretab:
    - Elimina headerul standard cu disclaimerul
    - Pastreaza acordurile si versurile
    """
    lines = content.split("\n")
    clean_lines = []
    skip_header = True

    for line in lines:
        # Sarim peste liniile de header (comentarii cu # si -)
        if skip_header:
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("-"):
                continue
            if not stripped:
                continue
            # Am gasit prima linie non-header
            skip_header = False

        clean_lines.append(line)

    result = "\n".join(clean_lines)

    # Eliminam linii goale excesive (max 2 consecutive)
    result = re.sub(r'\n{4,}', '\n\n\n', result)

    return result.strip()


# ═════════════════════════════════════════════════════════════════════════════
#  STRATEGIA 2: SONGSTERR API
# ═════════════════════════════════════════════════════════════════════════════
def _search_songsterr(query: str) -> dict | None:
    """
    Cauta pe Songsterr folosind API-ul /api/songs (functional, public, fara cheie).
    Returneza metadata + link la pagina de acorduri Songsterr.
    
    Nota: Songsterr nu expune continutul tab-urilor via API in format text,
    dar putem returna metadata + URL-ul paginii cu acorduri.
    """
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

    # Luam primul rezultat (cel mai relevant)
    song = songs[0]
    song_id = song.get("songId")
    title = song.get("title", "Unknown")
    artist = song.get("artist", "Unknown")
    has_chords = song.get("hasChords", False)

    if not song_id:
        return None

    # Construim URL-ul catre pagina de acorduri Songsterr
    artist_slug = re.sub(r'[^a-zA-Z0-9]+', '-', artist.lower()).strip('-')
    title_slug = re.sub(r'[^a-zA-Z0-9]+', '-', title.lower()).strip('-')

    if has_chords:
        chords_url = f"https://www.songsterr.com/a/wsa/{artist_slug}-{title_slug}-chords-s{song_id}"
    else:
        chords_url = f"https://www.songsterr.com/a/wsa/{artist_slug}-{title_slug}-tab-s{song_id}"

    # Construim un continut informativ cu datele disponibile
    content_lines = [
        f"Song: {title}",
        f"Artist: {artist}",
        f"",
    ]

    # Adaugam informatii despre track-uri disponibile
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
