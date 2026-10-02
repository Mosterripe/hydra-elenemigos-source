import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
import requests
from bs4 import BeautifulSoup

SITEMAP_URL = "https://elenemigos.com/sitemap.xml"
BASE_URL = "https://elenemigos.com"

# Cabeceras completas simulando un navegador real para evitar bloqueos Cloudflare/403
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive"
}

def limpiar_titulo(titulo_raw: str) -> str:
    """Limpia el título para mejorar la coincidencia en Hydra Launcher."""
    if not titulo_raw:
        return ""
    titulo = re.sub(r"(?i)\b(descargar|gratis|pc|elenemigos|el\s*enemigos)\b", "", titulo_raw)
    titulo = re.sub(r"[-|:]", " ", titulo)
    titulo = re.sub(r"(?i)\b(v?\d+(\.\d+)+|build\s*\d+|repack|full|crack|multi\d+)\b.*", "", titulo)
    return re.sub(r"\s+", " ", titulo).strip()

def extraer_datos_juego(url_juego: str) -> dict | None:
    try:
        resp = requests.get(url_juego, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        h1 = soup.find("h1") or soup.find("title")
        if not h1:
            return None
        
        titulo = limpiar_titulo(h1.text)
        if not titulo or len(titulo) < 2:
            return None

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

        if not enlaces:
            enlaces = [url_juego]

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
        print(f"Error extrayendo {url_juego}: {e}")
        return None

def obtener_urls() -> list[str]:
    urls = []
    # Intento 1: Obtener mediante Sitemap
    try:
        resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for elem in root.iter():
                if elem.tag.endswith("loc") and elem.text:
                    u = elem.text.strip()
                    if "/app/" in u or (BASE_URL in u and not any(x in u for x in ["/category/", "/tag/", "/page/", "sitemap"])):
                        urls.append(u)
    except Exception as e:
        print(f"Aviso sitemap: {e}")

    # Intento 2: Paginación si el sitemap falla o devuelve pocos resultados
    if len(urls) < 5:
        print("Buscando mediante paginación del sitio...")
        paginas = [BASE_URL] + [f"{BASE_URL}/page/{i}/" for i in range(2, 6)]
        for p in paginas:
            try:
                r = requests.get(p, headers=HEADERS, timeout=10)
                if r.status_code == 200:
                    sp = BeautifulSoup(r.text, "html.parser")
                    for a in sp.find_all("a", href=True):
                        href = a["href"]
                        if "/app/" in href:
                            if not href.startswith("http"):
                                href = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"
                            urls.append(href)
            except Exception as e:
                print(f"Error paginación {p}: {e}")

    return list(set(urls))

def generar_json():
    print("Iniciando actualización de la fuente de Elenemigos...")
    
    # Cargar JSON existente si está disponible como respaldo (fallback)
    descargas_previas = {}
    try:
        with open("elenemigos.json", "r", encoding="utf-8") as f:
            datos_viejos = json.load(f)
            for item in datos_viejos.get("downloads", []):
                descargas_previas[item["title"]] = item
    except Exception:
        pass

    urls = obtener_urls()
    print(f"URLs detectadas para procesar: {len(urls)}")

    NUEVAS_DESCARGAS = {}
    for url in urls[:40]:  # Procesa las primeras 40 entradas por ciclo
        datos = extraer_datos_juego(url)
        if datos:
            NUEVAS_DESCARGAS[datos["title"]] = datos

    # Combinar juegos nuevos con los almacenados anteriormente
    descargas_previas.update(NUEVAS_DESCARGAS)
    lista_final = list(descargas_previas.values())
    lista_final.sort(key=lambda x: x["title"])

    fuente_hydra = {
        "name": "Elenemigos Public Source",
        "downloads": lista_final
    }

    with open("elenemigos.json", "w", encoding="utf-8") as f:
        json.dump(fuente_hydra, f, ensure_ascii=False, indent=2)

    print(f"¡Éxito! El archivo 'elenemigos.json' contiene {len(lista_final)} juegos acumulados.")

if __name__ == "__main__":
    generar_json()
