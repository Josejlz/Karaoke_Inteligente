"""
matcher.py - Coincidencia aproximada entre lo escuchado y las letras.

Es el corazon tanto de la busqueda manual (2-3 palabras tecleadas) como del
modo automatico (palabras transcritas).  Un reconocedor de voz se equivoca
("corazon" -> "corazones", "amor" -> "a mor"), por eso se compara por palabras
con tolerancia (config.FUZZY_TOKEN) y no por texto exacto.

Funciones clave:
    align(q, linea)        cuantas palabras de q aparecen, en orden, en la linea
    LyricsIndex.search()   canciones candidatas para una lista de palabras
"""
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
from functools import lru_cache

import config
from textutil import tokens


@lru_cache(maxsize=100000)
def tok_eq(a, b):
    if a == b:
        return True
    if min(len(a), len(b)) < 4:
        return False
    return SequenceMatcher(None, a, b).ratio() >= config.FUZZY_TOKEN


def align(q, linea):
    """Alinea las palabras q (lo escuchado) con las de una linea.
    Devuelve (coincidentes, bloque_mas_largo, q_fin) donde q_fin es la
    posicion en q donde termina la ultima coincidencia."""
    if not q or not linea:
        return 0, 0, 0
    usadas = set()
    canon = []
    for t in q:
        rep = t
        for k, lt in enumerate(linea):
            if k not in usadas and tok_eq(t, lt):
                rep = lt
                usadas.add(k)
                break
        canon.append(rep)
    bloques = SequenceMatcher(None, canon, linea, autojunk=False).get_matching_blocks()
    matched = sum(b.size for b in bloques)
    longest = max(b.size for b in bloques)
    q_fin = max((b.a + b.size for b in bloques if b.size), default=0)
    return matched, longest, q_fin


def progress(q, linea):
    """Fraccion de la linea que ya se reconocio en q, y donde termina en q."""
    m, _, q_fin = align(q, linea)
    return (m / len(linea) if linea else 0.0), m, q_fin


@dataclass
class Hit:
    codigo: int
    nombre: str
    num_linea: int
    linea: str
    score: float


class LyricsIndex:
    """Indice en memoria de todas las lineas (miles de lineas caben de sobra)."""

    def __init__(self, db):
        self.db = db
        self._rev = -1
        self.reload()

    def reload(self):
        self.songs = dict(self.db.all_song_names())
        self.lines = []
        self.inv = {}
        for codigo, num, norm, texto in self.db.all_lines():
            toks = norm.split()
            lid = len(self.lines)
            self.lines.append((codigo, num, toks, texto))
            for t in set(toks):
                self.inv.setdefault(t, []).append(lid)
        self.vocab = sorted(self.inv)
        self._fz = {}
        self._rev = self.db.revision

    def _fuzzy(self, t):
        r = self._fz.get(t)
        if r is None:
            r = []
            for w in get_close_matches(t, self.vocab, n=3, cutoff=config.FUZZY_TOKEN):
                r.extend(self.inv[w])
            if len(self._fz) > 5000:
                self._fz.clear()
            self._fz[t] = r
        return r

    def fresh(self):
        if self._rev != self.db.revision:
            self.reload()

    def search(self, q, top=None, prior=()):
        """q: lista de palabras normalizadas.  Devuelve un Hit por cancion
        (su mejor linea), de mayor a menor puntaje.  prior: codigos de
        canciones con ligera preferencia (las pendientes del PROGRAMA)."""
        self.fresh()
        q = list(q)
        if not q:
            return []
        cap = max(50, int(len(self.lines) * config.PALABRA_COMUN_FRACCION))
        cnt = Counter()
        comunes = Counter()
        for t in set(q):
            ids = self.inv.get(t)
            if ids is None and len(t) >= 4:
                ids = self._fuzzy(t)
            if not ids:
                continue
            (cnt if len(ids) <= cap else comunes).update(ids)
        if not cnt:                      # solo palabras comunes: no hay otra opcion
            cnt = comunes
        need = 2 if len(set(q)) >= 4 and any(c >= 2 for c in cnt.values()) else 1
        cand = [lid for lid, c in cnt.items() if c >= need]
        mejor = {}
        prior = set(prior)
        for lid in cand:
            codigo, num, toks, texto = self.lines[lid]
            m, longest, _ = align(q, toks)
            if m == 0:
                continue
            sc = (0.8 * m + 0.2 * longest) / len(q)
            if m >= 3 or len(toks) <= 3:
                sc = max(sc, 0.95 * m / len(toks))      # q puede abarcar mas que la linea
            if codigo in prior:
                sc += 0.05
            h = mejor.get(codigo)
            if h is None or sc > h.score:
                mejor[codigo] = Hit(codigo, self.songs.get(codigo, "?"), num, texto, sc)
        hits = sorted(mejor.values(), key=lambda h: (-h.score, h.codigo))
        return hits[:top] if top else hits

    def search_text(self, texto, top=None, prior=()):
        return self.search(tokens(texto), top=top, prior=prior)

    def line_tokens(self, codigo):
        self.fresh()
        return [toks for (c, _n, toks, _t) in self.lines if c == codigo]


def find_song(db, texto):
    """Resuelve 'codigo o nombre' tecleado por el usuario.
    Devuelve (cancion_dict_o_None, [(codigo, nombre, puntaje)] alternativas)."""
    texto = (texto or "").strip()
    if not texto:
        return None, []
    if texto.isdigit():
        s = db.get_song(int(texto))
        return s, []
    res = db.search_names(texto)
    if not res:
        return None, []
    return db.get_song(res[0][0]), res
