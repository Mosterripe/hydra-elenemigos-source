import json
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://elenemigos.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def limpiar_titulo(titulo_raw: str) -> str:
    """Limpia el título para mejorar la coincidencia con Hydra Launcher."""
    if not titulo_raw:
        return "Juego Desconocido"
    
    # Quitar sufijos comunes del sitio
    titulo = titulo_raw.replace(" - Descargar Gratis", "").replace(" - ElEnemigos", "").replace(" | ElEnemigos", "").replace("Descargar", "")
    
    # Eliminar versiones, repacks y marcas de agua habituales (ej. v1.0, Build 1234, etc.)
    titulo = re.sub(r"(?i)\b(v?\d+(\.\d+)+|build\s*\d+|repack|full|multi\d+|crack)\b.*", "", titulo)
    titulo = re.sub(r"\s+", " ", titulo).strip()
    return titulo

def extraer_datos_juego(url_juego: str) -> dict | None:
    try:
        respuesta = requests.get(url_juego, headers=HEADERS, timeout=10)
        if respuesta.status_code != 200:
            return None

        soup = BeautifulSoup(respuesta.text, "html.parser")

        # 1. Título
        h1 = soup.find("h1") or soup.find("title")
        if not h1:
            return None
        
        titulo = limpiar_titulo(h1.text)
        if not titulo or len(titulo) < 2:
            return None

        # 2. Enlaces (uris)
        enlaces = []
        for a in soup.find_all("a", href=True):
            link = a["href"]
            if (
                link.startswith("magnet:")
                or link.endswith(".torrent")
                or any(server in link for server in ["mediafire.com", "mega.nz", "1fichier.com", "pixeldrain.com", "gofile.io", "drive.google.com"])
            ):
                if link not in enlaces:
                    enlaces.append(link)

        # Si no detecta servidor directo, incluye la ficha como enlace de referencia
        if not enlaces:
            enlaces = [url_juego]

        # 3. Tamaño aproximado
        tamano = "N/A"
        coincidencia = re.search(r"(\d+(?:\.\d+)?\s*(?:GB|MB))", soup.text, re.IGNORECASE)
        if coincidencia:
            tamano = coincidencia.group(1).upper()

        fecha = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

        return {
            "title": titulo,
            "uris": enlaces,
            "uploadDate": fecha,
            "fileSize": tamano
        }
    except Exception as e:
        print(f"Error procesando {url_juego}: {e}")
        return None

def obtener_urls_juegos() -> set:
    """Escanea la portada y las primeras paginas del catalogo para obtener mas juegos."""
    urls_juegos = set()
    
    # Escanear las primeras 5 paginas del sitio
    paginas_a_escanear = [BASE_URL] + [f"{BASE_URL}/page/{i}/" for i in range(2, 6)]
    
    for url_pagina in paginas_a_escanear:
        try:
            print(f"Buscando juegos en: {url_pagina}")
            resp = requests.get(url_pagina, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Detectar enlaces a fichas individuales
                if "/app/" in href or ("elenemigos.com/" in href and not any(x in href for x in ["/category/", "/tag/", "/page/", "/contacto"])):
                    if not href.startswith("http"):
                        href = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"
                    if href != BASE_URL and href != f"{BASE_URL}/":
                        urls_juegos.add(href)
        except Exception as e:
            print(f"Error escaneando pagina {url_pagina}: {e}")

    return urls_juegos

def generar_json():
    print("Iniciando scraping amplio de Elenemigos...")
    urls_juegos = obtener_urls_juegos()
    print(f"Total de juegos recopilados para procesar: {len(urls_juegos)}")

    lista_descargas = []
    for url in list(urls_juegos):
        datos = extraer_datos_juego(url)
        if datos:
            lista_descargas.append(datos)

    # Ordenar por titulo alfabetico
    lista_descargas.sort(key=lambda x: x["title"])

    fuente_hydra = {
        "name": "Elenemigos Public Source",
        "downloads": lista_descargas
    }

    with open("elenemigos.json", "w", encoding="utf-8") as f:
        json.dump(fuente_hydra, f, ensure_ascii=False, indent=2)

    print(f"¡Exito! Se genero 'elenemigos.json' con {len(lista_descargas)} juegos.")

if __name__ == "__main__":
    generar_json()
