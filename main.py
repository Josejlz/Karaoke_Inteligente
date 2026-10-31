"""
main.py - Interfaz Kivy del KARAOKE INTELIGENTE (Windows y Android).

Ejecutar:   python main.py

Pantallas (menu de primer nivel; cada opcion tiene tecla rapida y boton):
  m manual    a automatico    f alimentacion    p PROGRAMA
  w listar    x ver letra     u corregir        b borrar
  n canciones nuevas capturadas (pendientes)    q salir
Esc (o el boton "atras" de Android) regresa al menu.
"""
import os
import random

os.environ.setdefault("KIVY_NO_ARGS", "1")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

import asr as asrmod
import config
import importer
from db import Database
from engine import Controller
from matcher import LyricsIndex

BG = (0.04, 0.05, 0.08, 1)
FG = (0.92, 0.92, 0.95, 1)
DIM = (0.55, 0.58, 0.66, 1)
ACCENT = (1.0, 0.85, 0.25, 1)
OK = (0.4, 0.9, 0.5, 1)
BAD = (1.0, 0.45, 0.4, 1)


# ------------------------------------------------------------------ helpers
def lbl(text="", wrap=False, **kw):
    kw.setdefault("color", FG)
    l = Label(text=text, **kw)
    if wrap:
        l.bind(width=lambda i, w: setattr(i, "text_size", (w, None)))
        l.size_hint_y = None
        l.bind(texture_size=lambda i, s: setattr(i, "height", s[1] + 8))
        l.halign = kw.get("halign", "left")
    return l


def btn(text, cb, **kw):
    b = Button(text=text, **kw)
    b.bind(on_release=lambda *_: cb())
    return b


def popup(title, text, buttons=None, size=(0.85, 0.55)):
    """buttons: lista de (texto, callback). Siempre se cierra al pulsar."""
    box = BoxLayout(orientation="vertical", padding=10, spacing=10)
    sv = ScrollView()
    sv.add_widget(lbl(text, wrap=True))
    box.add_widget(sv)
    row = BoxLayout(size_hint_y=None, height=48, spacing=8)
    p = Popup(title=title, content=box, size_hint=size)
    for t, cb in (buttons or [("Aceptar", None)]):
        def go(*_, cb=cb):
            p.dismiss()
            if cb:
                cb()
        b = Button(text=t)
        b.bind(on_release=go)
        row.add_widget(b)
    box.add_widget(row)
    p.open()
    return p


def fit_font(text, w, h, nlines=2):
    """Tamano de letra para que la linea quepa en (w x h).  Lineas largas ->
    letra mas pequena.  CARACTERES_POR_LINEA (config.py) fija el largo de
    referencia: lineas mas cortas que la mitad de ese valor no crecen mas."""
    n = max(len(text), config.CARACTERES_POR_LINEA * 0.5)
    f = min(1.9 * max(w, 100) * nlines / (n + 1), max(h, 40) / (nlines * 1.25))
    return max(16, min(f, 96))


class Base(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self.box = BoxLayout(orientation="vertical", padding=12, spacing=8)
        self.add_widget(self.box)
        self.build_ui()

    def build_ui(self):
        pass

    def header(self, titulo):
        row = BoxLayout(size_hint_y=None, height=48, spacing=8)
        row.add_widget(lbl(titulo, font_size="22sp", bold=True, color=ACCENT, halign="left"))
        row.add_widget(btn("Menu (Esc)", lambda: self.app.go("menu"), size_hint_x=None, width=140))
        self.box.add_widget(row)

    def typing(self):
        return any(isinstance(w, TextInput) and w.focus for w in self.walk(restrict=True))

    def unfocus(self):
        for w in self.walk(restrict=True):
            if isinstance(w, TextInput):
                w.focus = False

    def key(self, ch, keycode, mods):
        return False

    def on_escape(self):
        self.app.go("menu")

    def scroll_list(self):
        sv = ScrollView()
        g = GridLayout(cols=1, size_hint_y=None, spacing=4)
        g.bind(minimum_height=g.setter("height"))
        sv.add_widget(g)
        self.box.add_widget(sv)
        return g


class FinderMixin:
    """Campo 'codigo o nombre' + lista de coincidencias (usado por x, u, b)."""

    def make_finder(self, on_pick, prompt="Codigo o nombre de la cancion:"):
        self._on_pick = on_pick
        self.box.add_widget(lbl(prompt, size_hint_y=None, height=28, halign="left"))
        row = BoxLayout(size_hint_y=None, height=48, spacing=8)
        self.find_in = TextInput(multiline=False, hint_text="ej. 3  o  noche estrellada", write_tab=False)
        self.find_in.bind(on_text_validate=lambda *_: self.do_find())
        row.add_widget(self.find_in)
        row.add_widget(btn("Buscar", self.do_find, size_hint_x=None, width=110))
        self.box.add_widget(row)
        self.find_msg = lbl("", wrap=True, color=BAD)
        self.box.add_widget(self.find_msg)
        self.find_list = BoxLayout(orientation="vertical", size_hint_y=None, spacing=4)
        self.find_list.bind(minimum_height=self.find_list.setter("height"))
        self.box.add_widget(self.find_list)

    def reset_finder(self):
        self.find_in.text = ""
        self.find_msg.text = ""
        self.find_list.clear_widgets()
        self.find_list.height = 0

    def do_find(self):
        db = self.app.db
        q = self.find_in.text.strip()
        self.find_list.clear_widgets()
        self.find_msg.text = ""
        if not q:
            return
        self.unfocus()
        if q.isdigit():
            s = db.get_song(int(q))
            if not s:
                self.find_msg.text = "No existe ninguna cancion con el codigo %s." % q
                return
            self._on_pick(s["codigo"])
            return
        res = db.search_names(q)
        if not res:
            self.find_msg.text = "No hay canciones que coincidan con '%s'." % q
            return
        if len(res) == 1 or res[0][2] >= 1.0:
            self._on_pick(res[0][0])
            return
        for codigo, nombre, _ in res[:8]:
            self.find_list.add_widget(btn("%d  -  %s" % (codigo, nombre),
                                          lambda c=codigo: self._on_pick(c),
                                          size_hint_y=None, height=44))
        self.find_list.height = 48 * min(len(res), 8)


# --------------------------------------------------------------------- menu
class MenuScreen(Base):
    def build_ui(self):
        self.box.add_widget(lbl("KARAOKE INTELIGENTE", font_size="30sp", bold=True, color=ACCENT,
                                size_hint_y=None, height=60))
        self.info = lbl("", size_hint_y=None, height=30, color=DIM)
        self.box.add_widget(self.info)
        self.items = [
            ("m", "(m)  Modo MANUAL", lambda: self.app.start_karaoke("manual")),
            ("a", "(a)  Modo AUTOMATICO (microfono)", lambda: self.app.start_karaoke("auto")),
            ("f", "(f)  Alimentar la base de datos", lambda: self.app.go("feed")),
            ("p", "(p)  Cargar PROGRAMA del cantante", lambda: self.app.go("programa")),
            ("w", "(w)  Listar canciones", lambda: self.app.go("listar")),
            ("x", "(x)  Ver letra de una cancion", lambda: self.app.go("ver")),
            ("u", "(u)  Corregir letra", lambda: self.app.go("editar")),
            ("b", "(b)  Borrar cancion", lambda: self.app.go("borrar")),
            ("n", "(n)  Canciones nuevas capturadas", lambda: self.app.go("nuevas")),
            ("q", "(q)  Salir", lambda: self.app.stop()),
        ]
        g = GridLayout(cols=2, spacing=8)
        for _, texto, cb in self.items:
            g.add_widget(btn(texto, cb, font_size="18sp"))
        self.box.add_widget(g)

    def on_pre_enter(self, *a):
        n = self.app.db.count_songs()
        nuevas = len(self.app.db.tmp_list())
        self.info.text = "Canciones en la base: %d     Pendientes por revisar: %d" % (n, nuevas)

    def key(self, ch, keycode, mods):
        for k, _, cb in self.items:
            if ch == k:
                cb()
                return True
        return False

    def on_escape(self):
        pass


# ------------------------------------------------------------ manual / auto
class KaraokeScreen(Base):
    def build_ui(self):
        self.ctl = None
        self.asr = None
        self._flash_seen = 0
        self.top_l = lbl("", size_hint_y=None, height=34, color=DIM, halign="left")
        self.top_l.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        self.box.add_widget(self.top_l)

        self.search_row = BoxLayout(size_hint_y=None, height=48, spacing=8)
        self.search_in = TextInput(multiline=False, hint_text="Escriba 2 o 3 palabras que oye (/ para buscar)",
                                   write_tab=False)
        self.search_in.bind(on_text_validate=lambda *_: self.do_search())
        self.search_row.add_widget(self.search_in)
        self.search_row.add_widget(btn("Buscar", self.do_search, size_hint_x=None, width=110))
        self.box.add_widget(self.search_row)

        self.results = BoxLayout(orientation="vertical", size_hint_y=None, height=0, spacing=3)
        self.box.add_widget(self.results)

        self.title_l = lbl("", font_size="20sp", bold=True, color=ACCENT, size_hint_y=None, height=34)
        self.box.add_widget(self.title_l)
        self.prev_l = lbl("", color=DIM, size_hint_y=0.14, halign="center", valign="middle")
        self.cur_l = lbl("", color=FG, bold=True, size_hint_y=0.40, halign="center", valign="middle")
        self.sig1_l = lbl("", color=DIM, size_hint_y=0.17, halign="center", valign="middle")
        self.sig2_l = lbl("", color=DIM, size_hint_y=0.12, halign="center", valign="middle")
        for l in (self.prev_l, self.cur_l, self.sig1_l, self.sig2_l):
            l.bind(size=lambda i, s: setattr(i, "text_size", (s[0] - 20, s[1])))
            self.box.add_widget(l)
        self.live_l = lbl("", size_hint_y=None, height=30, color=OK, halign="center")
        self.live_l.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        self.box.add_widget(self.live_l)
        self.msg_l = lbl("", size_hint_y=None, height=30, color=ACCENT)
        self.box.add_widget(self.msg_l)

        self.bar = BoxLayout(size_hint_y=None, height=56, spacing=6)
        self.box.add_widget(self.bar)
        self.bar_buttons = [
            ("c", "Continuar (c)", lambda: self.act("c")),
            ("r", "Repetir cancion (r)", lambda: self.act("r")),
            ("i", "Igual (i)", lambda: self.act("i")),
            ("g", "Ignorar (g)", lambda: self.act("g")),
            ("s", "Seguir (s)", lambda: self.act("s")),
            ("p", "PROGRAMA (p)", lambda: self.act("p")),
            ("f", "FIN (f)", lambda: self.act("f")),
        ]
        for _, t, cb in self.bar_buttons:
            self.bar.add_widget(btn(t, cb, font_size="14sp"))
        self.demo_btn = btn("Demo", self.demo, font_size="14sp")
        self.bar.add_widget(self.demo_btn)

    # ---- entrada / salida
    def start(self, mode):
        self.ctl = self.app.ctl
        self.ctl.set_mode(mode)
        auto = mode == "auto"
        self.search_row.height = 0 if auto else 48
        self.search_row.opacity = 0 if auto else 1
        self.demo_btn.opacity = 1 if auto else 0
        self.demo_btn.disabled = not auto
        self.results.clear_widgets()
        self.results.height = 0
        self.search_in.text = ""
        self.asr = None
        if auto:
            self.asr, why = asrmod.make_asr(self.app.index.vocab)
            if self.asr is None:
                popup("Microfono / reconocimiento no disponible",
                      why + "\n\nPuede probar el modo automatico con el boton 'Demo' "
                      "(un cantante simulado) o usar el modo manual.")
            elif not self.asr.start():
                popup("No se pudo iniciar el microfono", self.asr.error or "Error desconocido")
                self.asr = None
        self.refresh()

    def on_enter(self, *a):
        self._ev = Clock.schedule_interval(self.update, 0.1)

    def on_leave(self, *a):
        if getattr(self, "_ev", None):
            self._ev.cancel()
        self.stop_asr()

    def stop_asr(self):
        if self.asr is not None:
            try:
                self.asr.stop()
            except Exception:
                pass
            self.asr = None

    # ---- ciclo
    def update(self, dt):
        if self.ctl is None:
            return
        if self.asr is not None:
            for texto, final in self.asr.poll():
                self.ctl.feed(texto, final)
            if self.asr.error:
                self.ctl.message = self.asr.error
        self.ctl.tick()
        self.refresh()

    def refresh(self):
        v = self.ctl.view()
        estado = {"escuchando": "ESCUCHANDO", "siguiendo": "SIGUIENDO", "capturando": "CAPTURANDO CANCION NUEVA",
                  "espera": "EN ESPERA", "manual": "MANUAL"}.get(v["estado"], v["estado"])
        if v["pausa"]:
            estado = "EN PAUSA (g)"
        sig = self.app.db.next_pending()
        prog = ("   |   Sigue en PROGRAMA: %s" % sig["texto"]) if sig else ""
        self.top_l.text = "Modo %s: %s   |   Canciones cantadas: %d%s" % (
            v["modo"].upper(), estado, v["cantadas"], prog)
        self.title_l.text = v["titulo"] + (("   (linea %d de %d)" % (v["idx"] + 1, v["total"])) if v["total"] else "")
        if v["captura"] or v["estado"] == "capturando":
            self.prev_l.text = ""
            self.cur_l.text = v["live"] or (v["captura"][-1] if v["captura"] else "")
            self.sig1_l.text = ""
            self.sig2_l.text = ""
            self.title_l.text = "Cancion nueva (se guarda en pendientes)"
        elif v["total"]:
            if v["fin"]:
                self.prev_l.text = v["cur"]
                self.cur_l.text = "- FIN DE LA CANCION -"
                self.sig1_l.text = self.sig2_l.text = ""
            else:
                self.prev_l.text = v["prev"]
                self.cur_l.text = v["cur"]
                self.sig1_l.text = v["sig"][0] if v["sig"] else ""
                self.sig2_l.text = v["sig"][1] if len(v["sig"]) > 1 else ""
        else:
            self.prev_l.text = self.sig1_l.text = self.sig2_l.text = ""
            self.cur_l.text = ("Escuchando..." if v["modo"] == "auto"
                               else "Escriba unas palabras de la cancion y pulse Enter")
        for l, lines in ((self.prev_l, 2), (self.cur_l, 2), (self.sig1_l, 2), (self.sig2_l, 2)):
            tam = fit_font(l.text, l.width, l.height, lines)
            l.font_size = tam if l is self.cur_l else max(14, tam * 0.6)
        self.live_l.text = ("Oigo: " + v["live"]) if (v["modo"] == "auto" and v["live"]) else ""
        self.msg_l.text = v["mensaje"]
        if v["flash"] != self._flash_seen:
            self._flash_seen = v["flash"]
            self.cur_l.color = ACCENT
            Clock.schedule_once(lambda dt: setattr(self.cur_l, "color", FG), 0.4)

    # ---- manual: busqueda
    def do_search(self):
        if self.ctl.mode != "manual":
            return
        texto = self.search_in.text.strip()
        self.results.clear_widgets()
        self.results.height = 0
        if not texto:
            return
        self.unfocus()
        res = self.ctl.manual_search(texto)
        self._res = res
        if not res:
            self.ctl.message = "Sin coincidencias para '%s'. Pruebe con otras palabras." % texto
            return
        for i, r in enumerate(res, 1):
            self.results.add_widget(btn("%d. %s   -   \"%s\"" % (i, r["nombre"], r["linea"][:70]),
                                        lambda r=r: self.pick(r), size_hint_y=None, height=40,
                                        font_size="14sp", halign="left"))
        self.results.height = 43 * len(res)

    def pick(self, r):
        self.ctl.manual_select(r["codigo"], r["num_linea"])
        self.results.clear_widgets()
        self.results.height = 0
        self.search_in.text = ""
        self.refresh()

    # ---- acciones (teclas o botones)
    def act(self, k):
        c = self.ctl
        if k == "c":
            c.key_c()
        elif k == "r":
            c.key_r()
        elif k == "i":
            c.key_igual()
        elif k == "g":
            c.key_ignorar()
        elif k == "s":
            c.key_seguir()
        elif k == "p":
            if c.mode == "manual":
                c.manual_program_next()
            else:
                c.message = "En modo automatico el PROGRAMA se usa como pista; cargue con (p) en el menu"
        elif k == "f":
            self.finish()
        self.refresh()

    def key(self, ch, keycode, mods):
        if ch == "/" and self.ctl.mode == "manual":
            self.search_in.focus = True
            return True
        if ch == " ":
            ch = "c"
        if ch in ("c", "r", "i", "g", "s", "p", "f"):
            self.act(ch)
            return True
        if ch.isdigit() and getattr(self, "_res", None) and self.results.children:
            n = int(ch)
            if 1 <= n <= len(self._res):
                self.pick(self._res[n - 1])
                return True
        return False

    def on_escape(self):
        self.finish()

    def finish(self):
        r = self.ctl.finish()
        self.stop_asr()
        nombres = "\n".join("  - %s" % n for _, n in r["nombres"]) or "  (ninguna)"
        txt = "Canciones cantadas en la sesion: %d\n%s" % (r["canciones"], nombres)
        if r["nuevas"]:
            txt += "\n\nSe capturaron %d cancion(es) nueva(s). Revisela(s) en el menu con (n)." % len(r["nuevas"])
        self.app.go("menu")
        popup("Fin de la sesion", txt)

    # ---- demo sin microfono
    def demo(self):
        db = self.app.db
        songs = db.all_song_names()
        if not songs:
            popup("Demo", "No hay canciones en la base. Importe canciones primero (opcion f).")
            return
        codigo, nombre = random.choice(songs)
        self.stop_asr()
        self.ctl.set_mode("auto")
        self.asr = asrmod.DemoASR(db.get_lines(codigo))
        self.asr.start()
        self.ctl.message = "DEMO: un cantante simulado interpreta una cancion al azar..."


# ------------------------------------------------------------- alimentacion
class FeedScreen(Base):
    def build_ui(self):
        self.header("Alimentar la base de datos")
        self.box.add_widget(lbl(
            "(t) Leer un archivo de texto:  NOMBRE en la primera linea y la letra debajo,\n"
            "     canciones separadas por una linea en blanco (o por ---).\n"
            "(e) Escribir una cancion a mano, linea por linea.",
            wrap=True, color=DIM))
        row = BoxLayout(size_hint_y=None, height=52, spacing=8)
        row.add_widget(btn("(t) Elegir archivo de texto", self.choose_file))
        row.add_widget(btn("Importar canciones de ejemplo", self.import_example))
        row.add_widget(btn("(e) Escribir a mano", self.start_manual))
        self.box.add_widget(row)
        self.box.add_widget(lbl("O pegue aqui el texto de varias canciones y pulse 'Importar texto pegado':",
                                size_hint_y=None, height=28, halign="left"))
        self.paste = TextInput(hint_text="NOMBRE DE LA CANCION\nlinea 1\nlinea 2\n...\n\nOTRA CANCION\n...")
        self.box.add_widget(self.paste)
        self.box.add_widget(btn("Importar texto pegado", self.import_paste, size_hint_y=None, height=48))
        self.out = lbl("", wrap=True)
        self.box.add_widget(self.out)

        # entrada manual
        self.fase = None
        self.song_name = ""
        self.lines_in = []

    def on_pre_enter(self, *a):
        self.fase = None
        self.out.text = ""

    def key(self, ch, keycode, mods):
        if ch == "t":
            self.choose_file()
        elif ch == "e":
            self.start_manual()
        else:
            return False
        return True

    def _report(self, rep):
        t = "Agregadas: %d" % len(rep["agregadas"])
        for c, n in rep["agregadas"]:
            t += "\n   %d  %s" % (c, n)
        if rep["existentes"]:
            t += "\nYa existian (omitidas): " + "; ".join(rep["existentes"])
        for a in rep["avisos"]:
            t += "\nAviso: " + a
        self.out.text = t

    def choose_file(self):
        start = "/storage/emulated/0/Download" if asrmod.is_android() and os.path.isdir(
            "/storage/emulated/0/Download") else (config.DATA_DIR)
        fc = FileChooserListView(path=start, filters=["*.txt", "*"])
        box = BoxLayout(orientation="vertical", spacing=8)
        box.add_widget(fc)
        row = BoxLayout(size_hint_y=None, height=48, spacing=8)
        p = Popup(title="Elija el archivo de canciones", content=box, size_hint=(0.95, 0.9))

        def ok(*_):
            if fc.selection:
                p.dismiss()
                try:
                    self._report(importer.import_songs_file(self.app.db, fc.selection[0]))
                except Exception as e:
                    self.out.text = "No se pudo leer el archivo: %s" % e
        row.add_widget(btn("Importar", lambda: ok()))
        row.add_widget(btn("Cancelar", p.dismiss))
        box.add_widget(row)
        p.open()

    def import_example(self):
        ruta = os.path.join(config.APP_DIR, "canciones_ejemplo.txt")
        if not os.path.exists(ruta):
            self.out.text = "No se encontro canciones_ejemplo.txt"
            return
        self._report(importer.import_songs_file(self.app.db, ruta))

    def import_paste(self):
        if not self.paste.text.strip():
            self.out.text = "No hay texto pegado."
            return
        self._report(importer.import_songs(self.app.db, self.paste.text))

    # ---- (e) manual
    def start_manual(self):
        self.fase = "nombre"
        self.song_name, self.lines_in = "", []
        self.ask("Nombre de la cancion (vacio = cancelar):")

    def ask(self, prompt):
        box = BoxLayout(orientation="vertical", padding=8, spacing=8)
        self.q_label = lbl(prompt, wrap=True)
        box.add_widget(self.q_label)
        self.ti = TextInput(multiline=False, size_hint_y=None, height=48, write_tab=False)
        self.ti.bind(on_text_validate=lambda *_: self.entered())
        box.add_widget(self.ti)
        self.log = lbl("", wrap=True, color=DIM)
        sv = ScrollView()
        sv.add_widget(self.log)
        box.add_widget(sv)
        row = BoxLayout(size_hint_y=None, height=48, spacing=8)
        row.add_widget(btn("Aceptar (Enter)", self.entered))
        row.add_widget(btn("Cancelar", self.cancel_manual))
        box.add_widget(row)
        self.pop = Popup(title="Alimentacion manual", content=box, size_hint=(0.92, 0.85),
                         auto_dismiss=False)
        self.pop.open()
        Clock.schedule_once(lambda dt: setattr(self.ti, "focus", True), 0.2)

    def cancel_manual(self):
        self.pop.dismiss()
        self.fase = None
        self.out.text = "Entrada manual cancelada."

    def entered(self):
        t = self.ti.text.strip()
        self.ti.text = ""
        if self.fase == "nombre":
            if not t:
                return self.cancel_manual()
            if self.app.db.song_exists_by_name(t):
                self.q_label.text = "Ya existe una cancion con ese nombre. Escriba otro nombre (vacio = cancelar):"
                return self._refocus()
            self.song_name = t
            self.fase = "lineas"
        else:
            if not t:                                   # linea vacia = fin de la cancion
                if not self.lines_in:
                    self.q_label.text = "La cancion no tiene letra. Escriba la linea 1 (o Cancelar):"
                    return self._refocus()
                codigo = self.app.db.add_song(self.song_name, self.lines_in)
                self.pop.dismiss()
                self.fase = None
                self.out.text = "Cancion guardada con el codigo %d: %s (%d lineas)" % (
                    codigo, self.song_name, len(self.lines_in))
                return
            if len(t) > config.LIMITE_AVISO_LINEA:
                self.log.text += "\n(aviso: linea de %d caracteres, mas larga de lo normal)" % len(t)
            self.lines_in.append(t)
        n = len(self.lines_in) + 1
        self.q_label.text = ("Cancion: %s\nEscriba la linea %d (deje vacia y Enter para terminar):"
                             % (self.song_name, n))
        self.log.text = "\n".join("%2d. %s" % (i, l) for i, l in enumerate(self.lines_in, 1))
        self._refocus()

    def _refocus(self):
        Clock.schedule_once(lambda dt: setattr(self.ti, "focus", True), 0.1)


# ----------------------------------------------------------------- PROGRAMA
class ProgramaScreen(Base):
    def build_ui(self):
        self.header("PROGRAMA del cantante")
        self.box.add_widget(lbl("Un nombre de cancion por linea, en el orden planeado "
                                "(se ignoran lineas vacias y las que empiezan con #).",
                                wrap=True, color=DIM))
        row = BoxLayout(size_hint_y=None, height=52, spacing=8)
        row.add_widget(btn("Cargar archivo PROGRAMA", self.load_file))
        row.add_widget(btn("Guardar texto y cargar", self.load_text))
        self.box.add_widget(row)
        self.ti = TextInput(hint_text="1. Noche estrellada\n2. Mi pueblo bonito\n...")
        self.box.add_widget(self.ti)
        self.out = lbl("", wrap=True)
        sv = ScrollView(size_hint_y=0.6)
        sv.add_widget(self.out)
        self.box.add_widget(sv)

    def on_pre_enter(self, *a):
        ruta = config.programa_path()
        if os.path.exists(ruta) and not self.ti.text:
            self.ti.text = importer.leer_texto(ruta)
        self.show()

    def show(self):
        prog = self.app.db.get_program()
        if not prog:
            self.out.text = "(el PROGRAMA esta vacio)"
            return
        marca = {"pendiente": "[ ]", "cantada": "[x]", "no_encontrada": "[?]"}
        self.out.text = "\n".join("%2d. %s %s%s" % (
            p["orden"], marca.get(p["estado"], "[ ]"), p["texto"],
            "" if p["codigo"] else "   <-- NO esta en la base de datos") for p in prog)

    def load_file(self):
        ruta = config.programa_path()
        if not os.path.exists(ruta):
            self.out.text = "No existe el archivo %s\n(cree PROGRAMA.txt junto al programa o use el cuadro de texto)" % ruta
            return
        self.ti.text = importer.leer_texto(ruta)
        importer.load_program(self.app.db, self.ti.text)
        self.show()

    def load_text(self):
        texto = self.ti.text
        try:
            with open(os.path.join(config.DATA_DIR, config.NOMBRES_PROGRAMA[0]), "w", encoding="utf-8") as f:
                f.write(texto)
        except OSError:
            pass
        importer.load_program(self.app.db, texto)
        self.show()


# ---------------------------------------------------- listar (w) / ver (x)
class ListScreen(Base):
    def build_ui(self):
        self.header("Canciones en la base de datos")
        self.g = self.scroll_list()
        self.info = lbl("", size_hint_y=None, height=28, color=DIM)
        self.box.add_widget(self.info)
        row = BoxLayout(size_hint_y=None, height=52, spacing=8)
        row.add_widget(btn("<  Anteriores (p)", lambda: self.page(-1)))
        row.add_widget(btn("Siguientes (n / espacio)  >", lambda: self.page(1)))
        self.box.add_widget(row)
        self.off = 0

    def on_pre_enter(self, *a):
        self.off = 0
        self.draw()

    def draw(self):
        db = self.app.db
        total = db.count_songs()
        self.g.clear_widgets()
        for codigo, nombre in db.list_songs(self.off, config.PAGINA):
            self.g.add_widget(lbl("%4d   %s" % (codigo, nombre), size_hint_y=None, height=40,
                                  font_size="20sp", halign="left",
                                  text_size=(None, None)))
        self.info.text = ("Canciones %d a %d de %d" % (self.off + 1, min(self.off + config.PAGINA, total), total)
                          if total else "No hay canciones en la base de datos.")

    def page(self, d):
        total = self.app.db.count_songs()
        nuevo = self.off + d * config.PAGINA
        if 0 <= nuevo < total:
            self.off = nuevo
            self.draw()
        else:
            self.info.text = "Fin de la lista" if d > 0 else "Inicio de la lista"

    def key(self, ch, keycode, mods):
        if ch in ("n", " "):
            self.page(1)
        elif ch == "p":
            self.page(-1)
        else:
            return False
        return True


class ViewScreen(FinderMixin, Base):
    def build_ui(self):
        self.header("Ver letra de una cancion")
        self.make_finder(self.show_song)
        self.title_l = lbl("", font_size="20sp", bold=True, color=ACCENT, size_hint_y=None, height=32)
        self.box.add_widget(self.title_l)
        self.g = self.scroll_list()
        row = BoxLayout(size_hint_y=None, height=52, spacing=8)
        row.add_widget(btn("<  Anteriores 10 (p)", lambda: self.page(-1)))
        row.add_widget(btn("Siguientes 10 (n / espacio)  >", lambda: self.page(1)))
        self.box.add_widget(row)
        self.lines, self.off = [], 0

    def on_pre_enter(self, *a):
        self.reset_finder()
        self.g.clear_widgets()
        self.title_l.text = ""
        self.lines = []

    def show_song(self, codigo):
        s = self.app.db.get_song(codigo)
        self.lines = self.app.db.get_lines(codigo)
        self.off = 0
        self.find_list.clear_widgets()
        self.find_list.height = 0
        self.title_l.text = "%d - %s  (%d lineas)" % (codigo, s["nombre_cancion"], len(self.lines))
        self.draw()

    def draw(self):
        self.g.clear_widgets()
        for i, l in enumerate(self.lines[self.off:self.off + config.PAGINA], self.off + 1):
            self.g.add_widget(lbl("%2d.  %s" % (i, l), wrap=True))

    def page(self, d):
        nuevo = self.off + d * config.PAGINA
        if self.lines and 0 <= nuevo < len(self.lines):
            self.off = nuevo
            self.draw()

    def key(self, ch, keycode, mods):
        if ch in ("n", " "):
            self.page(1)
        elif ch == "p":
            self.page(-1)
        else:
            return False
        return True


# --------------------------------------------------- corregir (u) / borrar (b)
class EditScreen(FinderMixin, Base):
    def build_ui(self):
        self.header("Corregir la letra de una cancion")
        self.make_finder(self.load_song)
        self.name_in = TextInput(multiline=False, hint_text="Nombre", size_hint_y=None, height=44)
        self.lyr_in = TextInput(hint_text="Una linea de letra por renglon")
        self.box.add_widget(self.name_in)
        self.box.add_widget(self.lyr_in)
        self.msg = lbl("", wrap=True)
        self.box.add_widget(self.msg)
        self.box.add_widget(btn("Guardar cambios", self.save, size_hint_y=None, height=52))
        self.codigo = None

    def on_pre_enter(self, *a):
        self.reset_finder()
        self.name_in.text = self.lyr_in.text = self.msg.text = ""
        self.codigo = None

    def load_song(self, codigo):
        s = self.app.db.get_song(codigo)
        self.codigo = codigo
        self.find_list.clear_widgets()
        self.find_list.height = 0
        self.name_in.text = s["nombre_cancion"]
        self.lyr_in.text = "\n".join(self.app.db.get_lines(codigo))
        self.msg.color = DIM
        self.msg.text = "Editando la cancion %d" % codigo

    def save(self):
        if self.codigo is None:
            self.msg.color = BAD
            self.msg.text = "Primero busque una cancion."
            return
        otro = self.app.db.song_exists_by_name(self.name_in.text)
        if otro and otro != self.codigo:
            self.msg.color = BAD
            self.msg.text = "Ya existe otra cancion con ese nombre (codigo %d)." % otro
            return
        try:
            self.app.db.update_song(self.codigo, self.name_in.text, self.lyr_in.text.split("\n"))
        except ValueError as e:
            self.msg.color = BAD
            self.msg.text = str(e)
            return
        self.msg.color = OK
        self.msg.text = "Cambios guardados."


class DeleteScreen(FinderMixin, Base):
    def build_ui(self):
        self.header("Borrar una cancion")
        self.make_finder(self.ask_delete)
        self.msg = lbl("", wrap=True)
        self.box.add_widget(self.msg)
        self.box.add_widget(BoxLayout())

    def on_pre_enter(self, *a):
        self.reset_finder()
        self.msg.text = ""

    def ask_delete(self, codigo):
        s = self.app.db.get_song(codigo)
        lineas = self.app.db.get_lines(codigo)
        self.find_list.clear_widgets()
        self.find_list.height = 0
        popup("Confirmar borrado",
              "¿Esta SEGURO de borrar la cancion %d - \"%s\" (%d lineas) y toda su letra?\n\n"
              "Esta accion no se puede deshacer." % (codigo, s["nombre_cancion"], len(lineas)),
              [("SI, borrar", lambda: self.do_delete(codigo, s["nombre_cancion"])),
               ("No, cancelar", lambda: setattr(self.msg, "text", "Borrado cancelado."))])

    def do_delete(self, codigo, nombre):
        self.app.db.delete_song(codigo)
        self.msg.color = OK
        self.msg.text = "Cancion %d (%s) borrada." % (codigo, nombre)
        self.find_in.text = ""


# ----------------------------------------------- canciones nuevas capturadas
class NuevasScreen(Base):
    def build_ui(self):
        self.header("Canciones nuevas capturadas (pendientes)")
        self.box.add_widget(lbl("Las canciones que el modo automatico no conocia se transcribieron aqui. "
                                "Corrija la letra, ponga el nombre real y guardela en la base de datos.",
                                wrap=True, color=DIM))
        self.g = self.scroll_list()
        self.name_in = TextInput(multiline=False, hint_text="Nombre real de la cancion",
                                 size_hint_y=None, height=44)
        self.lyr_in = TextInput(hint_text="Letra transcrita (editable)")
        self.msg = lbl("", wrap=True)
        row = BoxLayout(size_hint_y=None, height=52, spacing=8)
        row.add_widget(btn("Guardar en la base de datos", self.commit))
        row.add_widget(btn("Descartar", self.discard))
        for w in (self.name_in, self.lyr_in, self.msg, row):
            self.box.add_widget(w)
        self.tmp_id = None

    def on_pre_enter(self, *a):
        self.name_in.text = self.lyr_in.text = ""
        self.tmp_id = None
        self.draw()

    def draw(self):
        self.g.clear_widgets()
        lst = self.app.db.tmp_list()
        if not lst:
            self.g.add_widget(lbl("No hay canciones pendientes.", size_hint_y=None, height=36))
        for t in lst:
            self.g.add_widget(btn("#%d  %s  (%d lineas, %s)" % (t["tmp_id"], t["nombre_provisional"],
                                                                 t["lineas"], t["fecha"][:16]),
                                  lambda i=t["tmp_id"]: self.pick(i), size_hint_y=None, height=44))

    def pick(self, tmp_id):
        d = self.app.db.tmp_get(tmp_id)
        self.tmp_id = tmp_id
        self.name_in.text = ""
        self.lyr_in.text = "\n".join(d["lineas"])
        self.msg.color = DIM
        self.msg.text = "Escriba el nombre real y revise la letra."

    def commit(self):
        if self.tmp_id is None:
            return
        nombre = self.name_in.text.strip()
        if not nombre:
            self.msg.color = BAD
            self.msg.text = "Falta el nombre de la cancion."
            return
        if self.app.db.song_exists_by_name(nombre):
            self.msg.color = BAD
            self.msg.text = "Ya existe una cancion con ese nombre."
            return
        try:
            c = self.app.db.tmp_commit(self.tmp_id, nombre, self.lyr_in.text.split("\n"))
        except ValueError as e:
            self.msg.color = BAD
            self.msg.text = str(e)
            return
        self.msg.color = OK
        self.msg.text = "Guardada con el codigo %d." % c
        self.tmp_id = None
        self.name_in.text = self.lyr_in.text = ""
        self.draw()

    def discard(self):
        if self.tmp_id is None:
            return
        tid = self.tmp_id
        popup("Descartar", "¿Descartar esta captura? No se podra recuperar.",
              [("Si, descartar", lambda: (self.app.db.tmp_discard(tid), self.on_pre_enter())),
               ("No", None)])


# ---------------------------------------------------------------------- app
class KaraokeApp(App):
    title = "Karaoke Inteligente"

    def build(self):
        if asrmod.is_android():
            config.set_data_dir(self.user_data_dir)
        Window.clearcolor = BG
        self.db = Database(config.db_path())
        self.index = LyricsIndex(self.db)
        self.ctl = Controller(self.db, self.index)
        self.sm = ScreenManager()
        self.screens = {
            "menu": MenuScreen(self, name="menu"),
            "karaoke": KaraokeScreen(self, name="karaoke"),
            "feed": FeedScreen(self, name="feed"),
            "programa": ProgramaScreen(self, name="programa"),
            "listar": ListScreen(self, name="listar"),
            "ver": ViewScreen(self, name="ver"),
            "editar": EditScreen(self, name="editar"),
            "borrar": DeleteScreen(self, name="borrar"),
            "nuevas": NuevasScreen(self, name="nuevas"),
        }
        for s in self.screens.values():
            self.sm.add_widget(s)
        Window.bind(on_key_down=self._on_key)
        # PROGRAMA: si existe el archivo, se carga al abrir
        try:
            ruta = config.programa_path()
            if os.path.exists(ruta):
                importer.load_program_file(self.db, ruta)
        except Exception:
            pass
        return self.sm

    def go(self, name):
        self.sm.current = name

    def start_karaoke(self, mode):
        if self.db.count_songs() == 0:
            popup("Base de datos vacia", "Aun no hay canciones. Use la opcion (f) para importar "
                  "canciones (hay un archivo de ejemplo).")
            return
        self.screens["karaoke"].start(mode)
        self.go("karaoke")

    def _on_key(self, window, key, scancode, codepoint, modifier):
        scr = self.sm.current_screen
        if key == 27:                          # Esc / boton atras de Android
            if scr.typing():
                scr.unfocus()
            else:
                scr.on_escape()
            return True
        if scr.typing():
            return False
        ch = (codepoint or "").lower()
        return bool(scr.key(ch, key, modifier))

    def on_pause(self):
        return True

    def on_stop(self):
        try:
            self.screens["karaoke"].stop_asr()
            self.db.close()
        except Exception:
            pass


if __name__ == "__main__":
    KaraokeApp().run()
