import os, random, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from db import Database
from engine import Controller
from importer import import_songs, load_program

TXT = open(os.path.join(os.path.dirname(__file__), "..", "canciones_ejemplo.txt"), encoding="utf-8").read() \
    if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "canciones_ejemplo.txt")) else ""

def mkdb():
    d = tempfile.mkdtemp()
    db = Database(os.path.join(d, "CANCIONES.db"))
    rep = import_songs(db, TXT)
    return db, rep

def noisy(words, rng, err=0.12):
    out = []
    for w in words:
        r = rng.random()
        if r < err * 0.4: continue                      # palabra perdida
        if r < err and len(w) > 3: w = w[:-1] if rng.random() < .5 else w + "s"   # variante
        out.append(w)
    return out

def sing(c, lines, rng, per_line_final=True, err=0.12):
    for l in lines:
        ws = noisy(l.lower().replace(",", "").replace("¿","").replace("?","").split(), rng, err)
        for i in range(1, len(ws) + 1):
            c.feed(" ".join(ws[:i]), final=False)
        if per_line_final: c.feed(" ".join(ws), final=True)

def main():
    db, rep = mkdb()
    print("importadas:", len(rep["agregadas"]), "avisos:", rep["avisos"])
    assert len(rep["agregadas"]) >= 5
    c = Controller(db)
    # --- manual
    c.set_mode("manual")
    codes = {n: k for k, n in db.all_song_names()}
    res = c.manual_search("noche estrellada")
    print("manual:", [(r["nombre"], round(r["score"], 2)) for r in res[:3]])
    assert res
    c.manual_select(res[0]["codigo"], res[0]["num_linea"])
    n = len(c.player.lines)
    for _ in range(n + 2): c.key_c()
    assert c.player.ended
    c.key_r(); assert c.player.idx == 0 and not c.player.ended
    c.key_ignorar(); c.key_c(); assert c.player.idx == 0
    c.key_seguir(); c.key_c(); assert c.player.idx == 1
    print("manual OK; cantadas:", c.songs_sung)
    # --- automatico: reconocer y seguir (varias semillas)
    ok = 0; tot = 0
    for seed in range(15):
        rng = random.Random(seed)
        for codigo, nombre in db.all_song_names():
            lines = db.get_lines(codigo)
            c.set_mode("auto")
            start = rng.choice([0, 0, 1, 2])
            # el cantante empieza en `start`; se mide si el motor identifica y sigue
            sing(c, lines[start:], rng)
            tot += 1
            if codigo in c.session and c.session[0] == codigo and c.player.ended:
                ok += 1
            else:
                print("  FALLA seed", seed, nombre, "sesion", c.session, "estado", c.auto.state, c.message)
    print("auto reconocer+seguir hasta el fin: %d/%d" % (ok, tot))
    assert ok / tot >= 0.9
    # --- seguimiento linea por linea: la linea mostrada debe ir 'sobre' la cantada
    rng = random.Random(1)
    codigo = [k for k, n in db.all_song_names()][0]
    lines = db.get_lines(codigo)
    c.set_mode("auto")
    sing(c, lines[:3], rng, err=0)
    assert c.player.codigo == codigo
    # mientras canta la linea 4 muestra la 4 y al terminarla muestra la 5
    ws = lines[3].lower().replace(",", "").split()
    for i in range(1, len(ws) // 2): c.feed(" ".join(ws[:i]), final=False)
    antes = c.player.idx
    for i in range(len(ws) // 2, len(ws) + 1): c.feed(" ".join(ws[:i]), final=False)
    print("idx antes/despues de terminar linea 4:", antes, c.player.idx)
    assert antes == 3 and c.player.idx == 4
    # salto: el cantante se salta a la linea 7
    ws = lines[6].lower().replace(",", "").split()
    for i in range(1, len(ws) + 1): c.feed(" ".join(ws[:i]), final=False)
    print("tras saltar a linea 7 idx =", c.player.idx)
    assert c.player.idx >= 6
    # --- cancion nueva
    c.set_mode("auto")
    nueva = ["la lluvia cae sobre el techo de mi casa", "mientras yo canto una cancion que nadie conoce",
             "los gatos duermen en la ventana vieja", "y el cafe se enfria sobre la mesa",
             "nadie sabe cuando volvera el sol"]
    sing(c, nueva, rng, err=0.05)
    c.tick(c.auto.last_voice + config.CAPTURE_END_SILENCE + 1)
    tmp = db.tmp_list()
    print("capturas:", tmp)
    assert len(tmp) == 1 and tmp[0]["lineas"] >= 4
    cod = db.tmp_commit(tmp[0]["tmp_id"], "La lluvia", db.tmp_get(tmp[0]["tmp_id"])["lineas"])
    c.set_mode("auto"); sing(c, nueva[1:], rng, err=0.05)
    assert c.session and c.session[0] == cod, (c.session, cod)
    print("cancion nueva capturada, guardada y luego reconocida OK")
    # --- programa
    p = load_program(db, "1. Noche estrellada\nCancion que no existe\n")
    print("programa:", [(x["texto"], x["codigo"], x["estado"]) for x in p])
    print("TODO OK")
main()
