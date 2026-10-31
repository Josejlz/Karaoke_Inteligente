"""
importer.py - Lectura de archivos de texto: canciones (opcion t) y PROGRAMA.

FORMATO DEL ARCHIVO DE CANCIONES
    NOMBRE DE LA CANCION        <- primera linea del bloque
    primera linea de la letra   <- siguientes lineas
    segunda linea de la letra
    ...
Las canciones se separan por UNA LINEA EN BLANCO.
Si la letra tiene lineas en blanco internas (entre estrofas), separe las
canciones con una linea de tres o mas guiones o signos igual (--- o ===);
cuando el archivo contiene alguna de esas marcas, las lineas en blanco
dejan de ser separadores y se ignoran.

FORMATO DE PROGRAMA
    Un nombre de cancion por linea, en el orden planeado.  Se ignoran lineas
    vacias y las que empiezan con #.  Se permite numeracion ("1. ", "2) ").
"""
import re

import config
from db import limpiar_lineas

_SEP = re.compile(r"^\s*(-{3,}|={3,}|_{3,})\s*$")
_NUM = re.compile(r"^\s*\d+\s*[.)\-]\s+")


def leer_texto(ruta):
    """Lee un archivo probando UTF-8 y, si falla, la codificacion de Windows."""
    with open(ruta, "rb") as f:
        datos = f.read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return datos.decode(enc)
        except UnicodeDecodeError:
            continue
    return datos.decode("utf-8", errors="replace")


def _bloques(texto):
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    lineas = texto.split("\n")
    if any(_SEP.match(l) for l in lineas):
        bloques, actual = [], []
        for l in lineas:
            if _SEP.match(l):
                bloques.append(actual)
                actual = []
            else:
                actual.append(l)
        bloques.append(actual)
        return bloques
    return [b.split("\n") for b in re.split(r"\n\s*\n", texto)]


def parse_songs_text(texto):
    """-> (lista de (nombre, [lineas]), lista de advertencias)"""
    canciones, avisos = [], []
    for bloque in _bloques(texto):
        bloque = [l.strip() for l in bloque if l.strip()]
        if not bloque:
            continue
        nombre = bloque[0].strip("\"'«»# ").strip()
        letra = limpiar_lineas(bloque[1:])
        if not letra:
            avisos.append("'%s': sin letra, se omite" % nombre)
            continue
        largas = [l for l in letra if len(l) > config.LIMITE_AVISO_LINEA]
        if largas:
            avisos.append("'%s': %d linea(s) de mas de %d caracteres"
                          % (nombre, len(largas), config.LIMITE_AVISO_LINEA))
        canciones.append((nombre, letra))
    return canciones, avisos


def import_songs(db, texto, reemplazar=False):
    """Agrega las canciones del texto.  Si ya existe una con el mismo nombre
    se omite (o se reemplaza su letra si reemplazar=True)."""
    canciones, avisos = parse_songs_text(texto)
    rep = {"agregadas": [], "reemplazadas": [], "existentes": [], "avisos": avisos}
    for nombre, letra in canciones:
        existente = db.song_exists_by_name(nombre)
        if existente:
            if reemplazar:
                db.update_song(existente, nombre, letra)
                rep["reemplazadas"].append((existente, nombre))
            else:
                rep["existentes"].append(nombre)
            continue
        rep["agregadas"].append((db.add_song(nombre, letra), nombre))
    return rep


def import_songs_file(db, ruta, reemplazar=False):
    return import_songs(db, leer_texto(ruta), reemplazar)


def parse_program_text(texto):
    items = []
    for l in texto.replace("\r\n", "\n").split("\n"):
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        items.append(_NUM.sub("", l).strip())
    return items


def load_program(db, texto):
    """Guarda el programa y resuelve cada nombre contra la BD.
    Devuelve la lista de entradas (dict) ya guardadas."""
    items = []
    for t in parse_program_text(texto):
        items.append((t, db.find_song_by_name(t)))
    db.set_program(items)
    return db.get_program()


def load_program_file(db, ruta):
    return load_program(db, leer_texto(ruta))
