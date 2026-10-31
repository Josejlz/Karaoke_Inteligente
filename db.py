"""
db.py - Acceso a la base de datos SQLite "CANCIONES".

Tablas de la especificacion:
    NOMBRES(codigo, nombre_cancion, ...)      una fila por cancion
    LETRAS(codigo, linea, ...)                una fila por linea de letra

Tablas / campos agregados (ver manual tecnico):
    NOMBRES.nombre_norm, artista, fecha_alta, veces_cantada
    LETRAS.num_linea (orden), linea_norm (texto normalizado para buscar)
    PROGRAMA        lista planeada por el cantante (archivo PROGRAMA)
    HISTORIAL       canciones cantadas en las sesiones
    TMP_CANCIONES / TMP_LETRAS   canciones nuevas capturadas por el modo
                                 automatico, pendientes de revisar

Nota: los nombres de campo van sin tildes (codigo, linea, nombre_cancion) para
evitar problemas de codificacion entre sistemas.
"""
import datetime
import os
import sqlite3
from difflib import SequenceMatcher

from textutil import normalize

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS NOMBRES(
    codigo         INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_cancion TEXT    NOT NULL,
    nombre_norm    TEXT    NOT NULL,
    artista        TEXT    NOT NULL DEFAULT '',
    fecha_alta     TEXT,
    veces_cantada  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS LETRAS(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo     INTEGER NOT NULL REFERENCES NOMBRES(codigo) ON DELETE CASCADE,
    num_linea  INTEGER NOT NULL,
    linea      TEXT    NOT NULL,
    linea_norm TEXT    NOT NULL,
    UNIQUE(codigo, num_linea)
);
CREATE INDEX IF NOT EXISTS idx_letras_codigo ON LETRAS(codigo, num_linea);
CREATE INDEX IF NOT EXISTS idx_nombres_norm  ON NOMBRES(nombre_norm);

CREATE TABLE IF NOT EXISTS PROGRAMA(
    orden  INTEGER PRIMARY KEY,
    texto  TEXT    NOT NULL,
    codigo INTEGER,
    estado TEXT    NOT NULL DEFAULT 'pendiente'   -- pendiente | cantada | no_encontrada
);
CREATE TABLE IF NOT EXISTS HISTORIAL(
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo INTEGER,
    fecha  TEXT,
    modo   TEXT
);
CREATE TABLE IF NOT EXISTS TMP_CANCIONES(
    tmp_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_provisional TEXT,
    fecha              TEXT
);
CREATE TABLE IF NOT EXISTS TMP_LETRAS(
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    tmp_id    INTEGER NOT NULL REFERENCES TMP_CANCIONES(tmp_id) ON DELETE CASCADE,
    num_linea INTEGER NOT NULL,
    linea     TEXT    NOT NULL
);
"""


def _ahora():
    return datetime.datetime.now().isoformat(timespec="seconds")


def limpiar_lineas(lineas):
    """Quita espacios y lineas vacias."""
    return [l.strip() for l in lineas if l and l.strip()]


class Database:
    def __init__(self, path):
        self.path = path
        self.existia = os.path.exists(path)
        carpeta = os.path.dirname(path)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.revision = 0          # sube con cada cambio de letras (el indice se recarga)
        self._preparar()

    # ------------------------------------------------------------ preparacion
    def _preparar(self):
        """Si la BD no existe: crea todas las tablas.  Si existe: verifica
        que tenga todas (crea las que falten) y la deja lista para usar."""
        self.con.executescript(SCHEMA)
        self.con.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
        self.con.commit()

    def close(self):
        self.con.close()

    def _touch(self):
        self.revision += 1

    # --------------------------------------------------------------- canciones
    def add_song(self, nombre, lineas, artista=""):
        lineas = limpiar_lineas(lineas)
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("El nombre de la cancion esta vacio")
        if not lineas:
            raise ValueError("La cancion no tiene letra")
        with self.con:
            cur = self.con.execute(
                "INSERT INTO NOMBRES(nombre_cancion,nombre_norm,artista,fecha_alta) VALUES(?,?,?,?)",
                (nombre, normalize(nombre), artista, _ahora()))
            codigo = cur.lastrowid
            self._put_lines(codigo, lineas)
        self._touch()
        return codigo

    def _put_lines(self, codigo, lineas):
        self.con.executemany(
            "INSERT INTO LETRAS(codigo,num_linea,linea,linea_norm) VALUES(?,?,?,?)",
            [(codigo, i, l, normalize(l)) for i, l in enumerate(lineas)])

    def get_song(self, codigo):
        r = self.con.execute("SELECT * FROM NOMBRES WHERE codigo=?", (codigo,)).fetchone()
        return dict(r) if r else None

    def get_lines(self, codigo):
        rows = self.con.execute(
            "SELECT linea FROM LETRAS WHERE codigo=? ORDER BY num_linea", (codigo,)).fetchall()
        return [r["linea"] for r in rows]

    def count_songs(self):
        return self.con.execute("SELECT COUNT(*) FROM NOMBRES").fetchone()[0]

    def list_songs(self, offset=0, limit=10):
        rows = self.con.execute(
            "SELECT codigo, nombre_cancion FROM NOMBRES ORDER BY codigo LIMIT ? OFFSET ?",
            (limit, offset)).fetchall()
        return [(r["codigo"], r["nombre_cancion"]) for r in rows]

    def all_song_names(self):
        return [(r["codigo"], r["nombre_cancion"])
                for r in self.con.execute("SELECT codigo, nombre_cancion FROM NOMBRES")]

    def all_lines(self):
        return [(r["codigo"], r["num_linea"], r["linea_norm"], r["linea"])
                for r in self.con.execute(
                    "SELECT codigo,num_linea,linea_norm,linea FROM LETRAS ORDER BY codigo,num_linea")]

    def update_song(self, codigo, nombre, lineas):
        lineas = limpiar_lineas(lineas)
        if not nombre.strip() or not lineas:
            raise ValueError("Nombre o letra vacios")
        with self.con:
            self.con.execute("UPDATE NOMBRES SET nombre_cancion=?, nombre_norm=? WHERE codigo=?",
                             (nombre.strip(), normalize(nombre), codigo))
            self.con.execute("DELETE FROM LETRAS WHERE codigo=?", (codigo,))
            self._put_lines(codigo, lineas)
        self._touch()

    def delete_song(self, codigo):
        with self.con:
            self.con.execute("DELETE FROM LETRAS WHERE codigo=?", (codigo,))
            self.con.execute("DELETE FROM NOMBRES WHERE codigo=?", (codigo,))
            self.con.execute("UPDATE PROGRAMA SET codigo=NULL, estado='no_encontrada' WHERE codigo=?",
                             (codigo,))
        self._touch()

    def song_exists_by_name(self, nombre):
        r = self.con.execute("SELECT codigo FROM NOMBRES WHERE nombre_norm=?",
                             (normalize(nombre),)).fetchone()
        return r["codigo"] if r else None

    def register_play(self, codigo, modo):
        with self.con:
            self.con.execute("INSERT INTO HISTORIAL(codigo,fecha,modo) VALUES(?,?,?)",
                             (codigo, _ahora(), modo))
            self.con.execute("UPDATE NOMBRES SET veces_cantada=veces_cantada+1 WHERE codigo=?",
                             (codigo,))

    # ------------------------------------------------------ busqueda por nombre
    def search_names(self, texto, limit=8):
        """Devuelve [(codigo, nombre, puntaje)] ordenado de mejor a peor."""
        q = normalize(texto)
        if not q:
            return []
        qt = q.split()
        res = []
        for codigo, nombre in self.all_song_names():
            n = normalize(nombre)
            if n == q:
                s = 1.0
            elif all(t in n for t in qt):
                s = 0.9
            else:
                s = SequenceMatcher(None, q, n).ratio() * 0.85
            if s >= 0.6:
                res.append((codigo, nombre, s))
        res.sort(key=lambda x: (-x[2], x[0]))
        return res[:limit]

    def find_song_by_name(self, texto):
        """Codigo de la cancion que mejor coincide con el nombre, o None si no
        hay una coincidencia confiable (>= 0.8)."""
        res = self.search_names(texto, limit=2)
        if not res or res[0][2] < 0.8:
            return None
        if len(res) > 1 and res[1][2] >= res[0][2] and res[0][2] < 1.0:
            return None          # empate ambiguo
        return res[0][0]

    # ---------------------------------------------------------------- programa
    def set_program(self, items):
        """items: lista de (texto, codigo_o_None)."""
        with self.con:
            self.con.execute("DELETE FROM PROGRAMA")
            for i, (texto, codigo) in enumerate(items, start=1):
                estado = "pendiente" if codigo else "no_encontrada"
                self.con.execute("INSERT INTO PROGRAMA(orden,texto,codigo,estado) VALUES(?,?,?,?)",
                                 (i, texto, codigo, estado))

    def get_program(self):
        return [dict(r) for r in self.con.execute("SELECT * FROM PROGRAMA ORDER BY orden")]

    def mark_program_sung(self, codigo):
        """Marca como cantada la primera entrada pendiente de esa cancion."""
        with self.con:
            r = self.con.execute(
                "SELECT orden FROM PROGRAMA WHERE codigo=? AND estado='pendiente' ORDER BY orden LIMIT 1",
                (codigo,)).fetchone()
            if r:
                self.con.execute("UPDATE PROGRAMA SET estado='cantada' WHERE orden=?", (r["orden"],))

    def pending_program_codes(self):
        return [r["codigo"] for r in self.con.execute(
            "SELECT codigo FROM PROGRAMA WHERE estado='pendiente' AND codigo IS NOT NULL ORDER BY orden")]

    def next_pending(self):
        r = self.con.execute(
            "SELECT * FROM PROGRAMA WHERE estado='pendiente' AND codigo IS NOT NULL "
            "ORDER BY orden LIMIT 1").fetchone()
        return dict(r) if r else None

    # ------------------------------------------------------ tablas temporales
    def tmp_create(self, nombre_provisional="Cancion nueva"):
        with self.con:
            cur = self.con.execute("INSERT INTO TMP_CANCIONES(nombre_provisional,fecha) VALUES(?,?)",
                                   (nombre_provisional, _ahora()))
        return cur.lastrowid

    def tmp_add_line(self, tmp_id, linea):
        linea = linea.strip()
        if not linea:
            return
        with self.con:
            n = self.con.execute("SELECT COUNT(*) FROM TMP_LETRAS WHERE tmp_id=?", (tmp_id,)).fetchone()[0]
            self.con.execute("INSERT INTO TMP_LETRAS(tmp_id,num_linea,linea) VALUES(?,?,?)",
                             (tmp_id, n, linea))

    def tmp_set_name(self, tmp_id, nombre):
        with self.con:
            self.con.execute("UPDATE TMP_CANCIONES SET nombre_provisional=? WHERE tmp_id=?",
                             (nombre, tmp_id))

    def tmp_list(self):
        return [dict(r) for r in self.con.execute(
            "SELECT t.tmp_id, t.nombre_provisional, t.fecha, "
            "(SELECT COUNT(*) FROM TMP_LETRAS l WHERE l.tmp_id=t.tmp_id) AS lineas "
            "FROM TMP_CANCIONES t ORDER BY t.tmp_id")]

    def tmp_get(self, tmp_id):
        r = self.con.execute("SELECT * FROM TMP_CANCIONES WHERE tmp_id=?", (tmp_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["lineas"] = [x["linea"] for x in self.con.execute(
            "SELECT linea FROM TMP_LETRAS WHERE tmp_id=? ORDER BY num_linea", (tmp_id,))]
        return d

    def tmp_discard(self, tmp_id):
        with self.con:
            self.con.execute("DELETE FROM TMP_LETRAS WHERE tmp_id=?", (tmp_id,))
            self.con.execute("DELETE FROM TMP_CANCIONES WHERE tmp_id=?", (tmp_id,))

    def tmp_commit(self, tmp_id, nombre, lineas):
        """Pasa una cancion temporal (ya corregida por el usuario) a las
        tablas permanentes y borra la temporal.  Devuelve el codigo nuevo."""
        codigo = self.add_song(nombre, lineas)
        self.tmp_discard(tmp_id)
        return codigo
