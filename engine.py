"""
engine.py - Motor del karaoke: modo MANUAL y modo AUTOMATICO.

Una sola clase (Controller) que la interfaz consulta.  No depende de Kivy ni
del microfono: recibe texto (teclas del usuario o frases del reconocedor) y
mantiene "que linea mostrar".  Por eso se puede probar sin pantalla ni audio.

MODO AUTOMATICO - maquina de estados
------------------------------------
  escuchando  --(una cancion coincide)-->      siguiendo
  escuchando  --(muchas palabras sin match)--> capturando   (cancion nueva)
  siguiendo   --(el cantante se pierde / silencio largo)--> escuchando
  capturando  --(silencio largo)-->            escuchando   (queda en TMP_*)

  ESCUCHANDO : junta las palabras oidas ("episodio") y las busca en LETRAS con
               coincidencia aproximada.  Se fija una cancion cuando su
               puntaje >= SEARCH_THRESHOLD y no hay otra casi empatada.
  SIGUIENDO  : compara las palabras de la frase en curso con la linea actual.
               Cuando ya reconocio ADVANCE_PROGRESS de ella, muestra la
               siguiente.  Detecta saltos hacia adelante, repeticiones hacia
               atras y perdida (-> vuelve a escuchar).
  CAPTURANDO : cada frase transcrita se guarda en TMP_LETRAS para corregirla
               y ponerle nombre despues (opcion "n" del menu).
"""
import time

import config
from matcher import LyricsIndex, progress
from textutil import tokens


class Player:
    """Cancion que se muestra: lineas e indice de la linea actual."""

    def __init__(self, db):
        self.db = db
        self.reset()

    def reset(self):
        self.codigo = None
        self.nombre = ""
        self.lines = []
        self.ltoks = []
        self.idx = 0
        self.ended = False

    @property
    def loaded(self):
        return self.codigo is not None

    def load(self, codigo, idx=0):
        song = self.db.get_song(codigo)
        if not song:
            raise KeyError("No existe la cancion %s" % codigo)
        self.codigo = codigo
        self.nombre = song["nombre_cancion"]
        self.lines = self.db.get_lines(codigo)
        self.ltoks = [tokens(l) for l in self.lines]
        self.idx = max(0, min(idx, len(self.lines) - 1))
        self.ended = False

    def advance(self):
        """Pasa a la siguiente linea.  False si ya era la ultima (fin)."""
        if self.idx >= len(self.lines) - 1:
            self.ended = True
            return False
        self.idx += 1
        return True


class _Auto:
    """Estado interno del modo automatico."""

    def __init__(self, now=0.0):
        self.reset(now)

    def reset(self, now=0.0):
        self.state = "escuchando"
        self.E = []              # palabras de frases ya finalizadas del episodio
        self.E_lines = []        # textos de esas frases
        self.finals = 0
        self.utt = []            # palabras de la frase en curso
        self.consumed = 0        # palabras de utt ya asignadas a lineas anteriores
        self.last_voice = now
        self.tmp_id = None
        self.cap_lines = []
        self.live = ""


class Controller:
    def __init__(self, db, index=None, clock=time.time):
        self.db = db
        self.index = index or LyricsIndex(db)
        self.clock = clock
        self.player = Player(db)
        self.mode = "manual"
        self.ignoring = False
        self.songs_sung = 0
        self.session = []            # codigos cantados en la sesion
        self.new_captures = []       # tmp_id de canciones nuevas capturadas
        self.message = ""
        self.flash = 0               # sube cuando el usuario pulsa "igual" (la UI parpadea)
        self.auto = _Auto(clock())

    # --------------------------------------------------------------- general
    def set_mode(self, mode):
        self.mode = mode
        self.ignoring = False
        self.auto.reset(self.clock())
        self.player.reset()
        self.songs_sung = 0
        self.session = []
        self.new_captures = []
        self.message = ("Modo automatico: escuchando..." if mode == "auto"
                        else "Modo manual: busque la cancion o pulse 'p' para el PROGRAMA")

    def _start_song(self, codigo, idx=0, modo=None):
        self.player.load(codigo, idx)
        self.songs_sung += 1
        self.session.append(codigo)
        self.db.register_play(codigo, modo or self.mode)
        self.db.mark_program_sung(codigo)

    def _prior(self):
        return self.db.pending_program_codes()

    def finish(self):
        """Termina la sesion (tecla f).  Devuelve un resumen."""
        if self.auto.state == "capturando":
            self._close_capture()
        resumen = {
            "canciones": self.songs_sung,
            "nombres": [(c, (self.db.get_song(c) or {}).get("nombre_cancion", "?"))
                        for c in self.session],
            "nuevas": list(self.new_captures),
        }
        self.player.reset()
        self.auto.reset(self.clock())
        return resumen

    # ---------------------------------------------------------- modo manual
    def manual_search(self, texto):
        """Busca por palabras de la letra y por nombre.  Devuelve una lista de
        dict(codigo, nombre, num_linea, linea, score) de mejor a peor."""
        res = {}
        for h in self.index.search_text(texto, top=config.BUSQUEDA_MAX_RESULTADOS,
                                        prior=self._prior()):
            res[h.codigo] = {"codigo": h.codigo, "nombre": h.nombre, "num_linea": h.num_linea,
                             "linea": h.linea, "score": h.score}
        for codigo, nombre, sc in self.db.search_names(texto, config.BUSQUEDA_MAX_RESULTADOS):
            if codigo not in res or sc > res[codigo]["score"]:
                lineas = self.db.get_lines(codigo)
                res[codigo] = {"codigo": codigo, "nombre": nombre, "num_linea": 0,
                               "linea": lineas[0] if lineas else "", "score": sc}
        out = sorted(res.values(), key=lambda r: (-r["score"], r["codigo"]))
        return out[:config.BUSQUEDA_MAX_RESULTADOS]

    def manual_select(self, codigo, num_linea=0):
        """Sincroniza: muestra la cancion desde la linea num_linea."""
        self._start_song(codigo, num_linea, "manual")
        self.ignoring = False
        self.message = "Sincronizado: %s" % self.player.nombre

    def manual_program_next(self):
        """Carga la siguiente cancion pendiente del PROGRAMA (tecla p)."""
        item = self.db.next_pending()
        if not item:
            self.message = "El PROGRAMA no tiene canciones pendientes"
            return False
        self._start_song(item["codigo"], 0, "programa")
        self.message = "PROGRAMA #%d: %s" % (item["orden"], self.player.nombre)
        return True

    def key_c(self):
        """Continuar con la linea siguiente."""
        p = self.player
        if not p.loaded or p.ended:
            self.message = "No hay cancion activa: busque una (o 'p' para el PROGRAMA)"
            return
        if self.ignoring:
            self.message = "En pausa (g). Pulse 's' para seguir"
            return
        if not p.advance():
            self.message = "FIN de la cancion. Busque la siguiente o 'f' para terminar"
        else:
            self.message = ""

    def key_r(self):
        """Repetir la misma cancion desde el principio."""
        if not self.player.loaded:
            self.message = "No hay cancion para repetir"
            return
        self._start_song(self.player.codigo, 0)
        self.message = "Cancion repetida desde el inicio"

    def key_igual(self):
        """El cantante repite la linea actual: no avanza."""
        if not self.player.loaded or self.player.ended:
            return
        self.flash += 1
        self.message = "Se mantiene la misma linea"
        if self.mode == "auto":
            self.auto.consumed = len(self.auto.utt)

    def key_ignorar(self):
        """Suspende el proceso (el cantante solo afina / hace ejercicios)."""
        self.ignoring = True
        self.message = "EN PAUSA: se ignora lo que suene. 's' para seguir"

    def key_seguir(self):
        self.ignoring = False
        if self.mode == "auto":
            a = self.auto
            a.utt, a.consumed, a.E, a.E_lines, a.finals = [], 0, [], [], 0
            a.last_voice = self.clock()
        self.message = "Seguimos"

    # -------------------------------------------------------- modo automatico
    def feed(self, text, final=False, now=None):
        """Recibe una frase (parcial o final) del reconocedor de voz."""
        if self.mode != "auto" or self.ignoring:
            return
        now = self.clock() if now is None else now
        a = self.auto
        toks = tokens(text)
        if not toks:
            if final:
                a.utt, a.consumed, a.live = [], 0, ""
            return
        if a.state == "escuchando" and now - a.last_voice > config.EPISODE_TIMEOUT:
            a.E, a.E_lines, a.finals = [], [], 0
        a.last_voice = now
        a.live = text
        if a.state == "escuchando":
            self._listen(toks, text, final, now)
        elif a.state == "siguiendo":
            self._track(toks, final, now)
        else:
            self._capture(toks, text, final, now)
        if final:
            a.utt, a.consumed, a.live = [], 0, ""

    def tick(self, now=None):
        """Llamar periodicamente (cada ~0.5 s) para detectar silencios."""
        if self.mode != "auto" or self.ignoring:
            return
        now = self.clock() if now is None else now
        a = self.auto
        idle = now - a.last_voice
        if a.state == "capturando" and idle > config.CAPTURE_END_SILENCE:
            self._close_capture()
        elif a.state == "siguiendo" and idle > config.TRACK_IDLE_TIMEOUT:
            a.state = "escuchando"
            a.E, a.E_lines, a.finals, a.utt, a.consumed = [], [], 0, [], 0
            self.message = "Silencio. Escuchando de nuevo..."

    # ---- escuchando
    def _listen(self, toks, text, final, now):
        a = self.auto
        total = a.E + toks
        best, second = None, None
        if len(total) >= config.SEARCH_MIN_TOKENS:
            hits = self.index.search(total[-config.SEARCH_TAIL:], prior=self._prior())
            if hits:
                best = hits[0]
                second = hits[1] if len(hits) > 1 else None
        if best is not None:
            clear = second is None or best.score - second.score >= config.SEARCH_AMBIGUITY
            enough = len(total) >= config.UNKNOWN_TOKENS
            if (best.score >= config.SEARCH_THRESHOLD and clear) or \
               (enough and best.score >= config.UNKNOWN_BEST_GUESS):
                self._lock(best, toks, final, now)
                return
        if final:
            a.E = (a.E + toks)[-config.UNKNOWN_TOKENS * 4:]
            a.E_lines.append(text)
            a.finals += 1
            if (len(a.E) >= config.UNKNOWN_TOKENS and a.finals >= config.UNKNOWN_MIN_FINALS
                    and (best is None or best.score < config.UNKNOWN_BEST_GUESS)):
                self._open_capture()

    def _lock(self, hit, utt, final, now):
        """Fija la cancion identificada y empieza a seguirla."""
        a = self.auto
        self._start_song(hit.codigo, hit.num_linea)
        a.state = "siguiendo"
        a.E, a.E_lines, a.finals = [], [], 0
        a.utt = utt
        a.consumed = max(0, len(utt) - config.SEARCH_TAIL)
        self.message = "Identificada: %s" % self.player.nombre
        self._skip_empty()
        self._track(utt, final, now)

    # ---- siguiendo
    def _skip_empty(self):
        p = self.player
        while p.loaded and not p.ended and not p.ltoks[p.idx] and p.idx < len(p.lines) - 1:
            p.idx += 1

    def _track(self, utt, final, now):
        a, p = self.auto, self.player
        a.utt = utt
        a.consumed = min(a.consumed, len(utt))
        while not p.ended:
            q = utt[a.consumed:]
            cur = p.ltoks[p.idx]
            prog, m, qfin = progress(q, cur)
            need = config.FINAL_ADVANCE if final else config.ADVANCE_PROGRESS
            if cur and prog >= need and m >= min(2, len(cur)):
                a.consumed += qfin
                if not p.advance():
                    self._song_finished()
                    return
                self._skip_empty()
                continue
            moved = False
            for j in range(1, config.MAX_JUMP + 1):
                if p.idx + j >= len(p.lines):
                    break
                pj, mj, _ = progress(q, p.ltoks[p.idx + j])
                if (pj >= config.JUMP_THRESHOLD and mj >= min(3, len(p.ltoks[p.idx + j]))
                        and pj > prog + config.DELTA_MOVE):
                    p.idx += j
                    self.message = "Salto de %d linea(s)" % j
                    moved = True
                    break
            if not moved:
                for b in range(1, config.MAX_BACK + 1):
                    if p.idx - b < 0:
                        break
                    pb, mb, _ = progress(q, p.ltoks[p.idx - b])
                    if (pb >= config.BACK_THRESHOLD and mb >= min(2, len(p.ltoks[p.idx - b]))
                            and pb > prog + config.DELTA_MOVE):
                        p.idx -= b
                        self.message = "Repite %d linea(s) atras" % b
                        moved = True
                        break
            if moved:
                continue
            if len(q) >= config.LOST_TOKENS and prog < config.MIN_PROGRESS:
                a.state = "escuchando"
                a.E, a.E_lines, a.finals = [], [], 0
                self.message = "Perdido el hilo: buscando de nuevo..."
                self._listen(utt, " ".join(utt), final, now)
            return

    def _song_finished(self):
        a = self.auto
        a.state = "escuchando"
        a.E, a.E_lines, a.finals, a.utt, a.consumed = [], [], 0, [], 0
        self.message = "FIN de la cancion. Escuchando la siguiente..."

    # ---- capturando (cancion nueva)
    def _open_capture(self):
        a = self.auto
        a.tmp_id = self.db.tmp_create("Cancion nueva")
        for t in a.E_lines:
            if len(tokens(t)) >= 2:
                self.db.tmp_add_line(a.tmp_id, t[:1].upper() + t[1:])
        a.cap_lines = [t[:1].upper() + t[1:] for t in a.E_lines if len(tokens(t)) >= 2]
        a.state = "capturando"
        a.E, a.E_lines, a.finals = [], [], 0
        self.player.reset()
        self.message = "Cancion NUEVA: transcribiendo para guardarla en pendientes..."

    def _capture(self, toks, text, final, now):
        a = self.auto
        if not final:
            return
        # puede que la cancion SI exista y las primeras palabras salieron mal
        hits = self.index.search(toks[-config.SEARCH_TAIL:], prior=self._prior())
        if hits and hits[0].score >= config.SEARCH_THRESHOLD and len(toks) >= config.SEARCH_MIN_TOKENS:
            self.db.tmp_discard(a.tmp_id)
            a.tmp_id = None
            a.cap_lines = []
            self._lock(hits[0], toks, final, now)
            return
        if len(toks) >= 2:
            linea = text[:1].upper() + text[1:]
            self.db.tmp_add_line(a.tmp_id, linea)
            a.cap_lines.append(linea)

    def _close_capture(self):
        a = self.auto
        if a.tmp_id is None:
            a.state = "escuchando"
            return
        if len(a.cap_lines) < config.MIN_CAPTURE_LINES:
            self.db.tmp_discard(a.tmp_id)
            self.message = "Captura descartada (muy corta, parecia ruido)"
        else:
            nombre = " ".join(a.cap_lines[0].split()[:6])
            self.db.tmp_set_name(a.tmp_id, "Nueva: " + nombre)
            self.new_captures.append(a.tmp_id)
            self.message = "Cancion nueva guardada en pendientes (revisela con la opcion n)"
        a.state = "escuchando"
        a.tmp_id, a.cap_lines = None, []
        a.E, a.E_lines, a.finals = [], [], 0

    # ----------------------------------------------------------------- vista
    def view(self):
        """Todo lo que la pantalla necesita dibujar."""
        p, a = self.player, self.auto
        v = {
            "modo": self.mode,
            "estado": a.state if self.mode == "auto" else ("espera" if not p.loaded else "manual"),
            "pausa": self.ignoring,
            "mensaje": self.message,
            "cantadas": self.songs_sung,
            "flash": self.flash,
            "titulo": p.nombre,
            "fin": p.ended,
            "prev": "", "cur": "", "sig": [], "idx": 0, "total": 0,
            "live": a.live if self.mode == "auto" else "",
            "captura": list(a.cap_lines[-3:]) if a.state == "capturando" else [],
        }
        if p.loaded:
            v["total"] = len(p.lines)
            v["idx"] = p.idx
            v["prev"] = p.lines[p.idx - 1] if p.idx > 0 else ""
            v["cur"] = p.lines[p.idx]
            v["sig"] = p.lines[p.idx + 1:p.idx + 3]
        return v
