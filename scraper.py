import json
import re
import time
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://elenemigos.com"
PASTE_DOMAIN = "paste.elenemigos.com"

# Servidores objetivo de descarga
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
    """Limpia el nombre del juego y le añade la clave de descompresión para Hydra Launcher."""
    if not titulo_raw:
        return ""
    titulo = re.sub(r"(?i)\b(descargar|gratis|pc|elenemigos|el\s*enemigos)\b", "", titulo_raw)
    titulo = re.sub(r"[-|:]", " ", titulo)
    titulo = re.sub(r"(?i)\b(v?\d+(\.\d+)+|b\d+|build\s*\d+|repack|full|crack|multi\d+)\b.*", "", titulo)
    titulo_limpio = re.sub(r"\s+", " ", titulo).strip()
    
    return f"{titulo_limpio} [Clave: www.elenemigos.com]"

def extraer_enlaces_de_pastebin(page, url_pastebin: str) -> list[str]:
    """Carga el pastebin y extrae el texto desde textareas, pres y contenedores JS."""
    enlaces_encontrados = []
    url_pastebin = url_pastebin.rstrip(";:,. \"'")
    print(f"  -> Abriendo Pastebin: {url_pastebin}")
    
    try:
        page.goto(url_pastebin, timeout=20000, wait_until="domcontentloaded")
        
        # Intentar hacer clic si hay un botón de confirmación o descifrado en la pantalla
        try:
            page.click("button:has-text('Decrypt')", timeout=1500)
        except Exception:
            pass
        try:
            page.click("button:has-text('Ver')", timeout=1500)
        except Exception:
            pass

        # Esperar 4.5 segundos a que la desencriptación en JS finalice
        page.wait_for_timeout(4500)

        # 1. Extraer desde el DOM del navegador (texto interno del body y inputs/textareas)
        body_text = page.inner_text("body")
        
        # Búsqueda en el texto visible del navegador
        for server in SERVIDORES_DESCARGA:
            patron = r'https?://[^\s<>"]*' + re.escape(server) + r'[^\s<>"]*'
            encontrados = re.findall(patron, body_text, re.IGNORECASE)
            for e in encontrados:
                e_clean = e.rstrip(";:,. \"'")
                if e_clean not in enlaces_encontrados:
                    enlaces_encontrados.append(e_clean)

        # 2. Extraer de elementos específicos: textarea, pre, code
        elementos_texto = page.eval_on_selector_all(
            "textarea, pre, code, div.clear, div.post-text", 
            "nodes => nodes.map(n => n.innerText || n.value)"
        )
        bloque_completo = " ".join(elementos_texto) + " " + page.content()

        # Búsqueda mediante expresiones regulares en todo el HTML y elementos
        patron_general = r'https?://[^\s<>"]+'
        urls_general = re.findall(patron_general, bloque_completo)
        for u in urls_general:
            u_clean = u.rstrip(";:,. \"'")
            if any(s in u_clean.lower() for s in SERVIDORES_DESCARGA):
                if u_clean not in enlaces_encontrados:
                    enlaces_encontrados.append(u_clean)

        # 3. Magnet links
        magnets = re.findall(r'magnet:\?xt=urn:btih:[a-zA-Z0-9]+[^\s<>"]*', bloque_completo)
        for m in magnets:
            m_clean = m.rstrip(";:,. \"'")
            if m_clean not in enlaces_encontrados:
                enlaces_encontrados.append(m_clean)

    except Exception as e:
        print(f"  [ERROR] Fallo al procesar Pastebin {url_pastebin}: {e}")

    resultado = list(set(enlaces_encontrados))
    print(f"     [EXITO] {len(resultado)} enlaces extraídos de este Pastebin.")
    return resultado

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
                href_clean = href.rstrip(";:,. \"'")
                if href_clean not in enlaces:
                    enlaces.append(href_clean)
                continue

            if any(server in href.lower() for server in SERVIDORES_DESCARGA):
                href_clean = href.rstrip(";:,. \"'")
                if href_clean not in enlaces:
                    enlaces.append(href_clean)
                continue

            # Detectar enlaces al subdominio paste.elenemigos.com o rutas de paste
            if PASTE_DOMAIN in href or "/paste" in href.lower():
                if not href.startswith("http"):
                    href = "https://" + href if href.startswith(PASTE_DOMAIN) else BASE_URL + href
                
                href_limpio = href.rstrip(";:,. \"'")
                pastes_a_procesar.add(href_limpio)

        # Procesar los Pastebins encontrados con Playwright
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
    print("Iniciando extracción con análisis profundo del DOM de Pastebin...")
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

    print(f"¡Proceso completado! Se guardaron {len(lista_final)} juegos en elenemigos.json.")

if __name__ == "__main__":
    generar_json()
