"""Stub minimo de Kivy: permite importar main.py y recorrer el codigo de las
pantallas SIN Kivy (solo para detectar errores de nombres/logica en este
entorno; no valida el dibujo real)."""
import sys, types

class W:
    def __init__(self, *a, **k):
        self.__dict__.update(k); self.children = []; self.text = k.get("text", ""); self.focus = False
        self.width = 800; self.height = 100; self.opacity = 1; self.disabled = False
    def __getattr__(self, n):
        if n.startswith("__"): raise AttributeError(n)
        return W()
    def __call__(self, *a, **k): return W()
    def __iter__(self): return iter([])
    def bind(self, **k): self._b = getattr(self, "_b", {}); self._b.update(k)
    def add_widget(self, w): self.children.append(w)
    def clear_widgets(self): self.children = []
    def walk(self, restrict=False):
        yield self
        for c in self.children:
            if hasattr(c, "walk"): yield from c.walk()
    def open(self): pass
    def dismiss(self): pass
    def setter(self, n): return lambda *a: None

def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m

def install():
    class App(W):
        def run(self): pass
        user_data_dir = "/tmp/kv_user"
    class Screen(W): pass
    class ScreenManager(W):
        current = "menu"; current_screen = None
        def add_widget(self, w):
            super().add_widget(w)
    clock = W()
    clock.schedule_interval = lambda f, t: W()
    clock.schedule_once = lambda f, t=0: None
    mod("kivy"); mod("kivy.app", App=App); mod("kivy.clock", Clock=clock)
    mod("kivy.core"); mod("kivy.core.window", Window=W())
    mod("kivy.uix")
    for n, c in [("boxlayout","BoxLayout"),("button","Button"),("gridlayout","GridLayout"),("label","Label"),
                 ("popup","Popup"),("scrollview","ScrollView"),("textinput","TextInput"),
                 ("filechooser","FileChooserListView")]:
        mod("kivy.uix."+n, **{c: type(c, (W,), {})})
    mod("kivy.uix.screenmanager", Screen=Screen, ScreenManager=ScreenManager)
