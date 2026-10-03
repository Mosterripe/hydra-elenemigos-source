import json
import re
import time
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://elenemigos.com"
PASTE_DOMAIN = "paste.elenemigos.com"

# Servidores objetivo de descarga reconocidos por Hydra
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
    """Limpia el título dejando ÚNICAMENTE el nombre comercial limpio para el matching de Hydra."""
    if not titulo_raw:
        return ""
    # Quitar palabras descriptivas de la web
    titulo = re.sub(r"(?i)\b(descargar|gratis|pc|elenemigos|el\s*enemigos)\b", "", titulo_raw)
    # Quitar versiones, builds, cracks y updates
    titulo = re.sub(r"(?i)\b(v?\d+(\.\d+)+|b\d+|build\s*\d+|repack|full|crack|multi\d+|update\s*\d*)\b.*", "", titulo)
    # Quitar caracteres especiales residuales
    titulo = re.sub(r"[-|:_]", " ", titulo)
    titulo_limpio = re.sub(r"\s+", " ", titulo).strip()
    return titulo_limpio

def extraer_enlaces_de_pastebin(context, url_pastebin: str) -> list[str]:
    enlaces_encontrados = []
    url_pastebin = url_pastebin.rstrip(";:,. \"'")
    
    page = context.new_page()
    try:
        page.goto(url_pastebin, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(3500)

        texto_desencriptado = page.evaluate("""() => {
            let texto = "";
            let elClear = document.querySelector('#cleartext') || document.querySelector('#deletelink') || document.querySelector('#pastebytes');
            if (elClear) texto += " " + (elClear.innerText || elClear.value || "");
            
            let elPre = document.querySelectorAll('pre, code, textarea');
            elPre.forEach(e => texto += " " + (e.innerText || e.value || ""));
            
            return texto + " " + document.body.innerText;
        }""")

        patron_general = r'https?://[^\s<>"]+'
        urls_general = re.findall(patron_general, texto_desencriptado)
        for u in urls_general:
            u_clean = u.rstrip(";:,. \"'")
            if any(s in u_clean.lower() for s in SERVIDORES_DESCARGA):
                if u_clean not in enlaces_encontrados:
                    enlaces_encontrados.append(u_clean)

        magnets = re.findall(r'magnet:\?xt=urn:btih:[a-zA-Z0-9]+[^\s<>"]*', texto_desencriptado)
        for m in magnets:
            m_clean = m.rstrip(";:,. \"'")
            if m_clean not in enlaces_encontrados:
                enlaces_encontrados.append(m_clean)

    except Exception as e:
        print(f"  [ERROR] Fallo al procesar Pastebin {url_pastebin}: {e}")
    finally:
        page.close()

    return list(set(enlaces_encontrados))

def extraer_datos_juego(context, url_juego: str) -> dict | None:
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

            if PASTE_DOMAIN in href or "/paste" in href.lower():
                if not href.startswith("http"):
                    href = "https://" + href if href.startswith(PASTE_DOMAIN) else BASE_URL + href
                
                href_limpio = href.rstrip(";:,. \"'")
                pastes_a_procesar.add(href_limpio)

        for url_paste in pastes_a_procesar:
            enlaces_paste = extraer_enlaces_de_pastebin(context, url_paste)
            for ep in enlaces_paste:
                if ep not in enlaces:
                    enlaces.append(ep)

        if not enlaces:
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

def obtener_urls_juegos(max_paginas: int = 299) -> list[str]:
    urls = set()
    print(f"Iniciando escaneo continuo de las {max_paginas} páginas del catálogo...")

    for i in range(1, max_paginas + 1):
        p = BASE_URL if i == 1 else f"{BASE_URL}/page/{i}/"
        try:
            print(f"Escaneando catálogo ({i}/{max_paginas}): {p}")
            r = scraper.get(p, timeout=12)
            if r.status_code == 200:
                sp = BeautifulSoup(r.text, "html.parser")
                for a in sp.find_all("a", href=True):
                    href = a["href"]
                    if "/app/" in href:
                        if not href.startswith("http"):
                            href = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"
                        urls.add(href)
            time.sleep(0.4)
        except Exception as e:
            print(f"Error en página {p}: {e}")

    return list(urls)

def generar_json():
    # Configurado a 299 páginas del catálogo completo
    PAGINAS = 299 
    descargas_acumuladas = {}

    urls = obtener_urls_juegos(max_paginas=PAGINAS)
    print(f"Total de URLs de juegos encontradas en el catálogo: {len(urls)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )

        for idx, url in enumerate(urls, 1):
            print(f"[{idx}/{len(urls)}] Procesando juego: {url}")
            datos = extraer_datos_juego(context, url)
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

    print(f"¡Proceso completado con éxito! Se guardaron {len(lista_final)} juegos en elenemigos.json.")

if __name__ == "__main__":
    generar_json()
