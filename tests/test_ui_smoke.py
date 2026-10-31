import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..")); sys.path.insert(0, os.path.join(HERE, "kivy_stub"))
import stubs; stubs.install()
import config
config.set_data_dir(tempfile.mkdtemp())
import main
app = main.KaraokeApp()
app.build()
app.sm.current_screen = app.screens["menu"]
app.db.count_songs()
# importar ejemplo desde la pantalla de alimentacion
f = app.screens["feed"]; f.import_example(); print(f.out.text.splitlines()[0])
assert app.db.count_songs() >= 6
# manual
k = app.screens["karaoke"]; app.start_karaoke("manual")
k.search_in.text = "bajo la lluvia"; k.do_search(); k.pick(k._res[0])
for ch in "c c c i r g s p".split(): k.act(ch if ch != "" else "c")
k.refresh(); print("manual:", k.title_l.text)
# automatico demo
app.start_karaoke("auto"); k.demo(); import time
for _ in range(60):
    time.sleep(0.15); k.update(0)
print("auto:", k.top.text, "|", k.title_l.text)
k.finish()
# resto de pantallas
for name in ("programa","listar","ver","editar","borrar","nuevas","feed","menu"):
    s = app.screens[name]; s.on_pre_enter()
app.screens["listar"].page(1)
v = app.screens["ver"]; v.find_in.text = "1"; v.do_find(); print("ver:", v.title_l.text)
e = app.screens["editar"]; e.find_in.text = "2"; e.do_find(); e.save(); print("editar:", e.msg.text)
d = app.screens["borrar"]; d.find_in.text = "99"; d.do_find(); print("borrar:", d.find_msg.text)
# alimentacion manual (e)
f.start_manual(); 
for t in ["Mi cancion de prueba", "linea uno", "linea dos", ""]:
    f.ti.text = t; f.entered()
print("e:", f.out.text)
print("UI SMOKE OK")
