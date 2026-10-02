import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
import requests
from bs4 import BeautifulSoup

SITEMAP_URL = "https://elenemigos.com/sitemap.xml"
BASE_URL = "https://elenemigos.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def limpiar_titulo(titulo_raw: str) -> str:
    """Limpia el título para optimizar la coincidencia en Hydra Launcher."""
    if not titulo_raw:
        return ""
    # Eliminar marcas de agua y textos adicionales del sitio
    titulo = re.sub(r"(?i)\b(descargar|gratis|pc|elenemigos|el\s*enemigos)\b", "", titulo_raw)
    titulo = re.sub(r"[-|:]", " ", titulo)
    # Eliminar versiones y repacks para dejar el nombre limpio del juego
    titulo = re.sub(r"(?i)\b(v?\d+(\.\d+)+|build\s*\d+|repack|full|crack|multi\d+)\b.*", "", titulo)
    return re.sub(r"\s+", " ", titulo).strip()

def extraer_datos_juego(url_juego: str) -> dict | None:
    try:
        respuesta = requests.get(url_juego, headers=HEADERS, timeout=8)
        if respuesta.status_code != 200:
            return None

        soup = BeautifulSoup(respuesta.text, "html.parser")

        # 1. Extraer y limpiar título
        h1 = soup.find("h1") or soup.find("title")
        if not h1:
            return None
        
        titulo = limpiar_titulo(h1.text)
        if not titulo or len(titulo) < 2:
            return None

        # 2. Extraer enlaces de descarga o enlaces de referencia
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

        # Si el sitio no muestra el enlace directo abiertamente, se usa la URL de la ficha
        if not enlaces:
            enlaces = [url_juego]

        # 3. Tamaño del juego
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

def obtener_urls_desde_sitemap() -> list[str]:
    """Obtiene las URLs de todos los juegos registrados en el sitemap.xml."""
    urls = []
    try:
        resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            # Analizar el XML del sitemap
            root = ET.fromstring(resp.content)
            # Manejo de namespaces de XML en sitemaps
            for elem in root.iter():
                if elem.tag.endswith("loc") and elem.text:
                    url = elem.text.strip()
                    if "/app/" in url or (BASE_URL in url and not any(x in url for x in ["/category/", "/tag/", "/page/", "sitemap"])):
                        urls.append(url)
    except Exception as e:
        print(f"Error al leer sitemap: {e}")
    return urls

def generar_json():
    print("Iniciando obtención de juegos mediante Sitemap...")
    urls = obtener_urls_desde_sitemap()
    print(f"Se encontraron {len(urls)} URLs en el sitemap.")

    # Si el sitemap no responde, usar páginas secundarias como respaldo
    if not urls:
        urls = [f"{BASE_URL}/page/{i}/" for i in range(1, 10)]

    lista_descargas = []
    # Procesar hasta 50 juegos por ejecución para evitar límites de tiempo en Actions
    for url in urls[:50]:
        print(f"Procesando: {url}")
        datos = extraer_datos_juego(url)
        if datos:
            lista_descargas.append(datos)

    # Eliminar duplicados basándose en el título
    juegos_unicos = {}
    for item in lista_descargas:
        juegos_unicos[item["title"]] = item

    descargas_finales = list(juegos_unicos.values())
    descargas_finales.sort(key=lambda x: x["title"])

    fuente_hydra = {
        "name": "Elenemigos Public Source",
        "downloads": descargas_finales
    }

    with open("elenemigos.json", "w", encoding="utf-8") as f:
        json.dump(fuente_hydra, f, ensure_ascii=False, indent=2)

    print(f"¡Éxito! Se guardaron {len(descargas_finales)} juegos en 'elenemigos.json'.")

if __name__ == "__main__":
    generar_json()
