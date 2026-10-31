"""Descarga y descomprime el modelo de voz en espanol de Vosk (~40 MB, una sola vez).

    python descargar_modelo.py

Crea la carpeta  models/vosk-model-small-es-0.42  junto al programa.
Si prefiere hacerlo a mano: descargue https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip
y descomprimalo dentro de la carpeta  models/.
"""
import os
import sys
import urllib.request
import zipfile

import config

URL = "https://alphacephei.com/vosk/models/%s.zip" % config.NOMBRE_MODELO_VOSK


def main():
    destino = os.path.join(config.DATA_DIR, "models")
    os.makedirs(destino, exist_ok=True)
    zip_path = os.path.join(destino, config.NOMBRE_MODELO_VOSK + ".zip")
    if os.path.isdir(os.path.join(destino, config.NOMBRE_MODELO_VOSK)):
        print("El modelo ya esta instalado.")
        return
    print("Descargando", URL)

    def prog(n, bs, total):
        if total > 0:
            sys.stdout.write("\r  %3d%%" % min(100, n * bs * 100 // total))
            sys.stdout.flush()
    urllib.request.urlretrieve(URL, zip_path, prog)
    print("\nDescomprimiendo...")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(destino)
    os.remove(zip_path)
    print("Listo:", os.path.join(destino, config.NOMBRE_MODELO_VOSK))


if __name__ == "__main__":
    main()
