import json
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://elenemigos.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def extraer_datos_juego(url_juego):
    try:
        respuesta = requests.get(url_juego, headers=HEADERS, timeout=10)
        if respuesta.status_code != 200:
            return None

        soup = BeautifulSoup(respuesta.text, "html.parser")

        # Extraer el título del juego
        titulo_tag = soup.find("h1") or soup.find("title")
        if not titulo_tag:
            return None
        
        # Limpieza básica del título para coincidencia con Hydra
        titulo = titulo_tag.text.strip()
        titulo = titulo.replace(" - Descargar Gratis", "").replace(" - ElEnemigos", "").replace(" | ElEnemigos", "")
        titulo = re.sub(r"\s+v?\d+(\.\d+)*.*", "", titulo, flags=re.IGNORECASE).strip()

        # Extraer enlaces
        enlaces = []
        for a in soup.find_all("a", href=True):
            link = a["href"]
            if (
                link.startswith("magnet:")
                or link.endswith(".torrent")
                or any(server in link for server in ["mediafire.com", "mega.nz", "1fichier.com", "pixeldrain.com", "gofile.io"])
            ):
                if link not in enlaces:
                    enlaces.append(link)

        # Si no tiene enlaces directos/magnet, guardamos la misma ficha como fuente temporal
        if not enlaces:
            enlaces = [url_juego]

        # Extraer tamaño
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
    except Exception as e:
        print(f"Error procesando {url_juego}: {e}")
        return None

def generar_json():
    print("Iniciando scraping en Elenemigos...")
    lista_descargas = []
    
    try:
        respuesta = requests.get(BASE_URL, headers=HEADERS, timeout=10)
        if respuesta.status_code == 200:
            soup = BeautifulSoup(respuesta.text, "html.parser")
            links_juegos = set()

            # Buscar especificamente enlaces con la estructura /app/ de Elenemigos
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/app/" in href:
                    if not href.startswith("http"):
                        href = BASE_URL + href if href.startswith("/") else BASE_URL + "/" + href
                    links_juegos.add(href)

            print(f"Se encontraron {len(links_juegos)} juegos en portada.")
            for url in links_juegos:
                datos = extraer_datos_juego(url)
                if datos:
                    lista_descargas.append(datos)
        else:
            print(f"Error en respuesta HTTP: {respuesta.status_code}")
    except Exception as e:
        print(f"Error general en la conexion: {e}")

    # Si por alguna razon la portada no arroja resultados, incluye una lista base
    if not lista_descargas:
        print("Agregando juego de prueba base...")
        lista_descargas.append({
            "title": "Alan Wake",
            "uris": ["https://elenemigos.com/app/alan-wake-descargar-gratis/1782"],
            "uploadDate": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "fileSize": "2.5 GB"
        })

    fuente_hydra = {
        "name": "Elenemigos Public Source",
        "downloads": lista_descargas
    }

    with open("elenemigos.json", "w", encoding="utf-8") as f:
        json.dump(fuente_hydra, f, ensure_ascii=False, indent=2)

    print(f"¡Archivo elenemigos.json generado con exito con {len(lista_descargas)} juegos!")

if __name__ == "__main__":
    generar_json()
