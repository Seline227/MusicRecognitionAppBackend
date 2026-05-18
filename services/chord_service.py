"""
Serviciu pentru căutarea și extragerea acordurilor de pe Ultimate Guitar.
Folosește scraping cu requests + BeautifulSoup pe structura js-store.
"""

import cloudscraper
import json
import re
import html
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────
# Constante
# ─────────────────────────────────────────────────────────
_SEARCH_URL = "https://www.ultimate-guitar.com/search.php"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.ultimate-guitar.com/",
}

_REQUEST_TIMEOUT = 15  # secunde


# ─────────────────────────────────────────────────────────
# Funcții auxiliare
# ─────────────────────────────────────────────────────────
def _strip_html_tags(text: str) -> str:
    """Elimină tag-urile HTML și decodifică entitățile."""
    # Elimină tag-urile HTML dar păstrează conținutul
    clean = re.sub(r'<[^>]+>', '', text)
    # Decodifică entitățile HTML (&amp; -> &, etc.)
    clean = html.unescape(clean)
    return clean


def _extract_js_store_data(html_content: str) -> dict | None:
    """
    Extrage JSON-ul din atributul data-content al elementului cu clasa 'js-store'.
    Aceasta este metoda principală prin care UG stochează datele paginii.
    """
    soup = BeautifulSoup(html_content, "lxml")
    store_tag = soup.find(class_="js-store")

    if not store_tag or "data-content" not in store_tag.attrs:
        return None

    try:
        return json.loads(store_tag["data-content"])
    except (json.JSONDecodeError, TypeError):
        return None


# ─────────────────────────────────────────────────────────
# API Publică
# ─────────────────────────────────────────────────────────
def search_chords(query: str) -> list[dict]:
    """
    Caută pe Ultimate Guitar și returnează o listă de rezultate 
    (doar tab-uri de tip 'Chords').
    
    Fiecare element: {
        "title": str,
        "artist": str,
        "url": str,
        "rating": float,
        "votes": int,
    }
    """
    params = {
        "search_type": "title",
        "value": query,
    }

    print(f"[CHORDS] Cautam pe UG: '{query}'", flush=True)

    try:
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(
            _SEARCH_URL,
            params=params,
            headers=_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[CHORDS] Eroare la cautare: {e}", flush=True)
        return []

    data = _extract_js_store_data(resp.text)
    if not data:
        print("[CHORDS] Nu s-a gasit js-store in pagina de cautare.", flush=True)
        return []

    # Navigăm prin structura JSON a UG
    try:
        results_raw = data["store"]["page"]["data"]["results"]
    except (KeyError, TypeError):
        print("[CHORDS] Structura JSON a UG s-a schimbat - cheia 'results' nu exista.", flush=True)
        return []

    results = []
    for item in results_raw:
        # Filtrăm doar tipul 'Chords'
        if not isinstance(item, dict):
            continue
        if item.get("type") != "Chords":
            continue

        results.append({
            "title": item.get("song_name", "Unknown"),
            "artist": item.get("artist_name", "Unknown"),
            "url": item.get("tab_url", ""),
            "rating": item.get("rating", 0),
            "votes": item.get("votes", 0),
        })

    # Sortăm după rating descrescător
    results.sort(key=lambda x: x.get("rating", 0), reverse=True)

    print(f"[CHORDS] Gasite {len(results)} rezultate de tip Chords.", flush=True)
    return results


def get_chord_content(tab_url: str) -> dict | None:
    """
    Deschide pagina unui tab individual și extrage textul acordurilor.
    
    Returnează: {
        "title": str,
        "artist": str,
        "chords_text": str,   # text cu acorduri aliniate deasupra versurilor
    }
    sau None dacă extragerea eșuează.
    """
    print(f"[CHORDS] Extragem acorduri de la: {tab_url}", flush=True)

    try:
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(tab_url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        print(f"[CHORDS] Eroare la descarcarea tab-ului: {e}", flush=True)
        return None

    data = _extract_js_store_data(resp.text)
    if not data:
        print("[CHORDS] Nu s-a gasit js-store pe pagina tab-ului.", flush=True)
        return None

    try:
        tab_view = data["store"]["page"]["data"]["tab_view"]
        wiki_tab = tab_view.get("wiki_tab", {})
        content_raw = wiki_tab.get("content", "")

        meta = data["store"]["page"]["data"].get("tab", {})
        title = meta.get("song_name", "Unknown")
        artist = meta.get("artist_name", "Unknown")
    except (KeyError, TypeError) as e:
        print(f"[CHORDS] Structura JSON a tab-ului neasteptata: {e}", flush=True)
        return None

    if not content_raw:
        print("[CHORDS] Continut tab gol.", flush=True)
        return None

    # Curățăm conținutul: eliminăm tag-urile HTML (UG folosește <span> pentru acorduri)
    # dar păstrăm structura liniilor
    # Înlocuim [tab] și [/tab] cu nimic (delimitatori UG)
    content = content_raw
    content = content.replace("[tab]", "").replace("[/tab]", "")
    content = content.replace("[ch]", "").replace("[/ch]", "")
    
    # Eliminăm tag-urile HTML dar păstrăm newline-urile
    content = _strip_html_tags(content)
    
    # Normalizăm spațiile multiple dar păstrăm leading spaces (importante pentru aliniere)
    lines = content.split("\n")
    cleaned_lines = []
    for line in lines:
        # Păstrăm liniile goale (spacing între secțiuni)
        # Nu facem strip pe leading spaces (aliniere acorduri)
        cleaned_lines.append(line.rstrip())
    
    chords_text = "\n".join(cleaned_lines)

    # Eliminăm mai mult de 3 linii goale consecutive
    chords_text = re.sub(r'\n{4,}', '\n\n\n', chords_text)
    chords_text = chords_text.strip()

    print(f"[CHORDS] Extras {len(chords_text)} caractere pentru '{title}' de '{artist}'", flush=True)

    return {
        "title": title,
        "artist": artist,
        "chords_text": chords_text,
    }


def search_and_get_first(query: str) -> dict | None:
    """
    Funcție convenience: caută, ia primul rezultat și extrage acordurile.
    Returnează dict cu title, artist, chords_text sau None.
    """
    results = search_chords(query)
    if not results:
        return None

    # Luăm primul rezultat (cel mai bine votat)
    best = results[0]
    if not best.get("url"):
        return None

    return get_chord_content(best["url"])
