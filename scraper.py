import json
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://elenemigos.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
}

def extraer_datos_juego(url_juego):
    try:
        respuesta = requests.get(url_juego, headers=HEADERS, timeout=10)
        if respuesta.status_code != 200:
            return None

        soup = BeautifulSoup(respuesta.text, "html.parser")

        titulo_tag = soup.find("h1")
        if not titulo_tag:
            return None
        titulo = titulo_tag.text.strip().replace(" - Elenemigos", "").replace(" Descargar PC", "")

        enlaces = []
        for a in soup.find_all("a", href=True):
            link = a["href"]
            if (
                link.startswith("magnet:")
                or link.endswith(".torrent")
                or any(server in link for server in ["mediafire.com", "mega.nz", "1fichier.com", "pixeldrain.com"])
            ):
                if link not in enlaces:
                    enlaces.append(link)

        if not enlaces:
            return None

        tamano = "N/A"
        coincidencia_tamano = re.search(r"(\d+(?:\.\d+)?\s*(?:GB|MB))", soup.text, re.IGNORECASE)
        if coincidencia_tamano:
            tamano = coincidencia_tamano.group(1).upper()

        fecha = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

        return {
            "title": titulo,
            "uris": enlaces,
            "uploadDate": fecha,
            "fileSize": tamano
        }
    except Exception:
        return None

def generar_json():
    respuesta = requests.get(BASE_URL, headers=HEADERS, timeout=10)
    if respuesta.status_code != 200:
        return

    soup = BeautifulSoup(respuesta.text, "html.parser")
    links_juegos = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if BASE_URL in href and href != BASE_URL and not any(x in href for x in ["/page/", "/category/", "/tag/"]):
            links_juegos.add(href)

    lista_descargas = []
    for url in links_juegos:
        datos = extraer_datos_juego(url)
        if datos:
            lista_descargas.append(datos)

    fuente_hydra = {
        "name": "Elenemigos Public Source",
        "downloads": lista_descargas
    }

    with open("elenemigos.json", "w", encoding="utf-8") as f:
        json.dump(fuente_hydra, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    generar_json()
