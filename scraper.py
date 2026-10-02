import json
import re
import time
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

BASE_URL = "https://elenemigos.com"

# Inicializar cloudscraper para evadir bloqueos de Cloudflare
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

def limpiar_titulo(titulo_raw: str) -> str:
    if not titulo_raw:
        return ""
    # Quitar etiquetas y marcas comunes
    titulo = re.sub(r"(?i)\b(descargar|gratis|pc|elenemigos|el\s*enemigos)\b", "", titulo_raw)
    titulo = re.sub(r"[-|:]", " ", titulo)
    # Limpiar versiones (v1.0, b12345, etc.) para que coincida con Hydra
    titulo = re.sub(r"(?i)\b(v?\d+(\.\d+)+|b\d+|build\s*\d+|repack|full|crack|multi\d+)\b.*", "", titulo)
    return re.sub(r"\s+", " ", titulo).strip()

def extraer_datos_juego(url_juego: str) -> dict | None:
    try:
        resp = scraper.get(url_juego, timeout=10)
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

        # Si no hay enlace directo expuesto, usar la URL del juego en la fuente
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
        print(f"Error procesando {url_juego}: {e}")
        return None

def obtener_urls_juegos() -> list[str]:
    urls = set()
    # Recorrer las primeras paginas del sitio
    paginas = [BASE_URL] + [f"{BASE_URL}/page/{i}/" for i in range(2, 8)]

    for p in paginas:
        try:
            print(f"Escaneando: {p}")
            r = scraper.get(p, timeout=12)
            if r.status_code == 200:
                sp = BeautifulSoup(r.text, "html.parser")
                for a in sp.find_all("a", href=True):
                    href = a["href"]
                    if "/app/" in href:
                        if not href.startswith("http"):
                            href = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"
                        urls.add(href)
            time.sleep(1) # Pausa amigable entre peticiones
        except Exception as e:
            print(f"Error escaneando {p}: {e}")

    return list(urls)

def generar_json():
    print("Iniciando actualización con Cloudscraper...")
    
    # Cargar juegos existentes para no perder historial
    descargas_acumuladas = {}
    try:
        with open("elenemigos.json", "r", encoding="utf-8") as f:
            datos_previos = json.load(f)
            for item in datos_previos.get("downloads", []):
                descargas_acumuladas[item["title"]] = item
    except Exception:
        pass

    urls = obtener_urls_juegos()
    print(f"URLs de juegos encontradas: {len(urls)}")

    for url in urls:
        print(f"Procesando juego: {url}")
        datos = extraer_datos_juego(url)
        if datos:
            descargas_acumuladas[datos["title"]] = datos

    lista_final = list(descargas_acumuladas.values())
    lista_final.sort(key=lambda x: x["title"])

    fuente_hydra = {
        "name": "Elenemigos Public Source",
        "downloads": lista_final
    }

    with open("elenemigos.json", "w", encoding="utf-8") as f:
        json.dump(fuente_hydra, f, ensure_ascii=False, indent=2)

    print(f"¡Proceso completado! Archivo actualizado con {len(lista_final)} juegos.")

if __name__ == "__main__":
    generar_json()
