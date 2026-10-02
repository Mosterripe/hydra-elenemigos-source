import json
import re
import time
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://elenemigos.com"
PASTE_DOMAIN = "paste.elenemigos.com"

# Servidores objetivos de Elenemigos
SERVIDORES_DESCARGA = [
    "datavaults.co",
    "filekeeper.net",
    "vikingfile.com",
    "akirabox.to",
    "fileq.net",
    "mediafire.com",
    "mega.nz",
    "1fichier.com",
    "pixeldrain.com",
    "gofile.io",
    "drive.google.com"
]

scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
)

def limpiar_titulo(titulo_raw: str) -> str:
    if not titulo_raw:
        return ""
    titulo = re.sub(r"(?i)\b(descargar|gratis|pc|elenemigos|el\s*enemigos)\b", "", titulo_raw)
    titulo = re.sub(r"[-|:]", " ", titulo)
    titulo = re.sub(r"(?i)\b(v?\d+(\.\d+)+|b\d+|build\s*\d+|repack|full|crack|multi\d+)\b.*", "", titulo)
    return re.sub(r"\s+", " ", titulo).strip()

def extraer_enlaces_de_pastebin(page, url_pastebin: str) -> list[str]:
    """Carga la página de paste.elenemigos.com y extrae los enlaces a los servidores."""
    enlaces_encontrados = []
    
    # Intento 1: Probar si tiene endpoint /raw/ o /raw
    raw_url = url_pastebin.rstrip('/') + '/raw' if not url_pastebin.endswith('/raw') else url_pastebin
    try:
        r_raw = scraper.get(raw_url, timeout=5)
        if r_raw.status_code == 200 and len(r_raw.text) > 20:
            texto_raw = r_raw.text
            # Buscar URLs directas en el RAW
            urls_texto = re.findall(r'https?://[^\s<>"]+', texto_raw)
            for u in urls_texto:
                u_clean = u.rstrip(".,;)'\"")
                if any(s in u_clean.lower() for s in SERVIDORES_DESCARGA):
                    enlaces_encontrados.append(u_clean)
            magnets = re.findall(r'magnet:\?xt=urn:btih:[a-zA-Z0-9]+[^\s<>"]*', texto_raw)
            enlaces_encontrados.extend(magnets)
            if enlaces_encontrados:
                return list(set(enlaces_encontrados))
    except Exception:
        pass

    # Intento 2: Usar Playwright para renderizar el JavaScript en paste.elenemigos.com
    try:
        print(f"  -> Abriendo con navegador: {url_pastebin}")
        page.goto(url_pastebin, timeout=15000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500) # Esperar renderizado de JS

        html_content = page.content()
        soup = BeautifulSoup(html_content, "html.parser")

        # Buscar enlaces <a> renderizados
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("magnet:") or any(s in href.lower() for s in SERVIDORES_DESCARGA):
                if href not in enlaces_encontrados:
                    enlaces_encontrados.append(href)

        # Buscar en todo el texto HTML por si están en bloques <pre> / <code> / textarea
        patron_urls = r'https?://[^\s<>"]+'
        urls_texto = re.findall(patron_urls, html_content)
        for u in urls_texto:
            u_clean = u.rstrip(".,;)'\"")
            if any(s in u_clean.lower() for s in SERVIDORES_DESCARGA):
                if u_clean not in enlaces_encontrados:
                    enlaces_encontrados.append(u_clean)

        magnets = re.findall(r'magnet:\?xt=urn:btih:[a-zA-Z0-9]+[^\s<>"]*', html_content)
        for m in magnets:
            if m not in enlaces_encontrados:
                enlaces_encontrados.append(m)

    except Exception as e:
        print(f"  Error leyendo Pastebin {url_pastebin}: {e}")

    return list(set(enlaces_encontrados))

def extraer_datos_juego(page, url_juego: str) -> dict | None:
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
        pastes_a_procesar = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()

            if href.startswith("magnet:") or href.endswith(".torrent"):
                if href not in enlaces:
                    enlaces.append(href)
                continue

            # Enlaces directos a servidores
            if any(server in href.lower() for server in SERVIDORES_DESCARGA):
                if href not in enlaces:
                    enlaces.append(href)
                continue

            # Detectar específicamente paste.elenemigos.com o rutas internas de paste
            if PASTE_DOMAIN in href or any(p in href.lower() for p in ["/paste", "/p/"]):
                if not href.startswith("http"):
                    href = "https://" + href if href.startswith(PASTE_DOMAIN) else BASE_URL + href
                pastes_a_procesar.add(href)

        # Extraer enlaces desde cada pastebin
        for url_paste in pastes_a_procesar:
            enlaces_paste = extraer_enlaces_de_pastebin(page, url_paste)
            for ep in enlaces_paste:
                if ep not in enlaces:
                    enlaces.append(ep)

        if not enlaces:
            print(f"Sin enlaces capturados para: {titulo}")
            return None

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
    paginas = [BASE_URL] + [f"{BASE_URL}/page/{i}/" for i in range(2, 6)]

    for p in paginas:
        try:
            print(f"Escaneando catálogo: {p}")
            r = scraper.get(p, timeout=12)
            if r.status_code == 200:
                sp = BeautifulSoup(r.text, "html.parser")
                for a in sp.find_all("a", href=True):
                    href = a["href"]
                    if "/app/" in href:
                        if not href.startswith("http"):
                            href = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"
                        urls.add(href)
            time.sleep(1)
        except Exception as e:
            print(f"Error escaneando {p}: {e}")

    return list(urls)

def generar_json():
    print("Iniciando extracción enfocada en paste.elenemigos.com...")
    descargas_acumuladas = {}

    urls = obtener_urls_juegos()
    print(f"URLs de juegos encontradas: {len(urls)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for url in urls:
            print(f"Procesando juego: {url}")
            datos = extraer_datos_juego(page, url)
            if datos:
                descargas_acumuladas[datos["title"]] = datos

        browser.close()

    lista_final = list(descargas_acumuladas.values())
    lista_final.sort(key=lambda x: x["title"])

    fuente_hydra = {
        "name": "Elenemigos Public Source",
        "downloads": lista_final
    }

    with open("elenemigos.json", "w", encoding="utf-8") as f:
        json.dump(fuente_hydra, f, ensure_ascii=False, indent=2)

    print(f"¡Proceso completado! Se guardaron {len(lista_final)} juegos con enlaces extraídos de paste.elenemigos.com.")

if __name__ == "__main__":
    generar_json()
