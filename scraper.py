import json
import re
import time
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup

BASE_URL = "https://elenemigos.com"

# Lista exacta de servidores principales que utiliza Elenemigos
SERVIDORES_DESCARGA = [
    "datavaults.co",
    "filekeeper.net",
    "vikingfile.com",
    "akirabox.to",
    "fileq.net",
    "mediafire.com",
    # Servidores de respaldo habituales
    "mega.nz",
    "mega.co.nz",
    "1fichier.com",
    "pixeldrain.com",
    "gofile.io",
    "drive.google.com",
    "qiwi.gg",
    "terabox.com",
    "krakenfiles.com"
]

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

def limpiar_titulo(titulo_raw: str) -> str:
    """Limpia el nombre del juego para optimizar la coincidencia en Hydra Launcher."""
    if not titulo_raw:
        return ""
    titulo = re.sub(r"(?i)\b(descargar|gratis|pc|elenemigos|el\s*enemigos)\b", "", titulo_raw)
    titulo = re.sub(r"[-|:]", " ", titulo)
    titulo = re.sub(r"(?i)\b(v?\d+(\.\d+)+|b\d+|build\s*\d+|repack|full|crack|multi\d+)\b.*", "", titulo)
    return re.sub(r"\s+", " ", titulo).strip()

def extraer_enlaces_de_pastebin(url_pastebin: str) -> list[str]:
    """Accede al Pastebin de Elenemigos y extrae los enlaces a los servidores reales."""
    enlaces_encontrados = []
    try:
        print(f"  -> Extrayendo desde Pastebin: {url_pastebin}")
        resp = scraper.get(url_pastebin, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 1. Etiquetas <a> con los servidores objetivo
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.startswith("magnet:") or any(s in href.lower() for s in SERVIDORES_DESCARGA):
                    if href not in enlaces_encontrados:
                        enlaces_encontrados.append(href)

            # 2. Expresión regular en texto plano para capturar URLs no hipervinculadas
            patron_urls = r'https?://[^\s<>"]+'
            urls_texto = re.findall(patron_urls, resp.text)
            for u in urls_texto:
                u_clean = u.rstrip(".,;)'\"")
                if any(s in u_clean.lower() for s in SERVIDORES_DESCARGA):
                    if u_clean not in enlaces_encontrados:
                        enlaces_encontrados.append(u_clean)

            # 3. Enlaces Magnet en texto plano
            magnets = re.findall(r'magnet:\?xt=urn:btih:[a-zA-Z0-9]+[^\s<>"]*', resp.text)
            for m in magnets:
                if m not in enlaces_encontrados:
                    enlaces_encontrados.append(m)

    except Exception as e:
        print(f"Error procesando Pastebin {url_pastebin}: {e}")
        
    return enlaces_encontrados

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
        pastes_a_procesar = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()

            if href.startswith("magnet:") or href.endswith(".torrent"):
                if href not in enlaces:
                    enlaces.append(href)
                continue

            # Si está directo en la ficha sin pasar por pastebin
            if any(server in href.lower() for server in SERVIDORES_DESCARGA):
                if href not in enlaces:
                    enlaces.append(href)
                continue

            # Detectar enlaces de Pastebin / redirecciones internas
            if any(p in href.lower() for p in ["paste", "pastebin", "/go/", "/redirect/", "/links/", "/p/"]):
                if not href.startswith("http"):
                    href = BASE_URL + href if href.startswith("/") else f"{BASE_URL}/{href}"
                pastes_a_procesar.add(href)

        # Entrar a los pastebins encontrados
        for url_paste in pastes_a_procesar:
            enlaces_paste = extraer_enlaces_de_pastebin(url_paste)
            for ep in enlaces_paste:
                if ep not in enlaces:
                    enlaces.append(ep)

        if not enlaces:
            print(f"Sin enlaces directos/servidores hallados para: {titulo}")
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
    paginas = [BASE_URL] + [f"{BASE_URL}/page/{i}/" for i in range(2, 8)]

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
    print("Iniciando extracción con lista de servidores específicos...")
    
    descargas_acumuladas = {}

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

    print(f"¡Proceso completado! Se guardaron {len(lista_final)} juegos con enlaces a {', '.join(SERVIDORES_DESCARGA[:6])}.")

if __name__ == "__main__":
    generar_json()
