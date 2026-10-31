# KARAOKE INTELIGENTE — Manual técnico

## 1. Resumen de decisiones

| Tema | Decisión | Motivo |
|---|---|---|
| Framework | **Python + Kivy** | Un solo código para Windows y Android; SQLite viene incluido. |
| Base de datos | SQLite `CANCIONES.db` | Lo pide el enunciado; sin servidor. |
| Reconocimiento (Windows) | **Vosk** offline, modelo `vosk-model-small-es-0.42` | Gratuito, sin internet, **entrega resultados parciales en streaming** (imprescindible para ir al ritmo del cantante), poco consumo. |
| Reconocimiento (Android) | **`SpeechRecognizer` nativo** vía pyjnius | Gratuito, ya está en el teléfono, da parciales; Vosk/Whisper no compilan de forma práctica con python-for-android. |
| Identificación de canción | Coincidencia **aproximada por palabras** contra `LETRAS` | Tolera los errores típicos del reconocedor. |
| Whisper | **No** se usa en vivo | Procesa por bloques (latencia de 1–5 s por frase) y es pesado; para karaoke se necesita la palabra *mientras* se canta. |

---

## 2. Cómo ejecutarlo (para el docente)

```
cd karaoke
python -m venv venv && venv\Scripts\activate          (Windows)
pip install -r requirements.txt
python tests/test_core.py        # prueba del motor (no necesita Kivy ni micrófono)
python tests/test_audio.py       # prueba de la limpieza de audio (solo numpy)
python descargar_modelo.py       # solo para modo automático con micrófono
python main.py
```

* Menú → `f` → *Importar canciones de ejemplo* → ya se puede probar todo.
* Modo automático sin micrófono: `a` → botón **Demo**.
* Android: ver `MANUAL_USUARIO.md` §3 y `buildozer.spec`.
* La base de datos y `PROGRAMA.txt` se crean/leen en la carpeta del programa (en Android: la carpeta de datos de la app). Variable de entorno `KARAOKE_DATA` para cambiarla.

---

## 3. Módulos

```
main.py        Interfaz Kivy: menú y 9 pantallas, teclado y botones.
engine.py      Controller: modo manual, modo automático (máquina de estados), vista.
matcher.py     Coincidencia aproximada palabra a palabra + índice invertido de LETRAS.
db.py          SQLite: esquema, CRUD, programa, historial, tablas temporales.
importer.py    Lectura de archivos de canciones (opción t) y del PROGRAMA.
asr.py         Motores de voz: VoskASR, AndroidASR, DemoASR.
audio.py       Limpieza de audio: pasa-altas + reducción de ruido + AGC (numpy).
textutil.py    Normalización (minúsculas, sin tildes ni signos).
config.py      TODOS los parámetros ajustables.
descargar_modelo.py   Descarga el modelo Vosk.
tests/         test_core.py, test_audio.py, test_ui_smoke.py (+ stub de Kivy).
```

`engine.py`, `matcher.py`, `db.py`, `importer.py` no dependen de Kivy ni del audio: se prueban solos y se pueden reutilizar con otra interfaz.

---

## 4. Base de datos

Si `CANCIONES.db` **no existe** se crean todas las tablas; si existe se abre y se ejecuta `CREATE TABLE IF NOT EXISTS`, de modo que se completan las tablas que falten (`db.Database._preparar`).

### Tablas pedidas
| Tabla | Campos |
|---|---|
| `NOMBRES` | `codigo` (entero, **autonumérico**), `nombre_cancion` |
| `LETRAS` | `codigo` (enlaza con NOMBRES), `linea` |

### Campos y tablas agregados
| Tabla / campo | Para qué |
|---|---|
| `NOMBRES.nombre_norm` | Nombre normalizado (sin tildes/mayúsculas) para buscar y detectar duplicados. |
| `NOMBRES.artista`, `fecha_alta`, `veces_cantada` | Datos extra; `veces_cantada` se incrementa en cada interpretación. |
| `LETRAS.num_linea` | Orden de la línea dentro de la canción (SQL no garantiza orden sin él). |
| `LETRAS.linea_norm` | Línea normalizada, base de la búsqueda. |
| `PROGRAMA(orden, texto, codigo, estado)` | Lista planeada ya resuelta contra la base. `estado`: pendiente / cantada / no_encontrada. |
| `HISTORIAL(codigo, fecha, modo)` | Registro de lo cantado (manual, automático o programa). |
| **`TMP_CANCIONES(tmp_id, nombre_provisional, fecha)`** y **`TMP_LETRAS(tmp_id, num_linea, linea)`** | **Tablas temporales** del modo automático para canciones desconocidas (§7). |

Los nombres de campo van **sin tildes** (`codigo`, `linea`) para evitar problemas de codificación entre sistemas.

---

## 5. Búsqueda: cómo se identifica una canción (`matcher.py`)

El reconocedor se equivoca ("corazón"→"corazones", palabras comidas), así que **no se compara texto exacto**:

1. **Normalizar** todo: minúsculas, sin tildes ni signos.
2. **Igualdad de palabras tolerante** (`tok_eq`): iguales, o con similitud ≥ `FUZZY_TOKEN` (0.80) si miden ≥ 4 letras.
3. **Alineación** (`align`): de las palabras escuchadas, cuántas aparecen en una línea de la letra, en orden (usa `difflib.SequenceMatcher` sobre palabras ya «canonizadas»).
4. **Índice invertido** palabra→líneas: sólo se evalúan las líneas que comparten al menos 1–2 palabras con lo escuchado. Las palabras muy comunes (en > 3 % de las líneas, p. ej. «de», «la») no generan candidatos salvo que sean todo lo que hay → escala a miles de canciones.
5. **Puntaje por línea** = `(0.8·coincidentes + 0.2·bloque_más_largo)/palabras_escuchadas`; por canción se toma su mejor línea. Las canciones pendientes del PROGRAMA suman +0.05.

El mismo mecanismo sirve a la búsqueda manual (2–3 palabras tecleadas) y al modo automático. En manual también se busca por nombre de canción.

---

## 6. Modo automático — cómo se resolvió

### 6.1 Cadena
```
micrófono ─► limpieza (audio.py) ─► Vosk (parciales + finales) ─► Controller.feed()
                                                                      │
                          ┌───────────────────────────────────────────┘
                          ▼
   ESCUCHANDO ──identifica──► SIGUIENDO ──pierde el hilo──► ESCUCHANDO
        │                                            ▲
        └─ palabras sin match ─► CAPTURANDO ─silencio─┘ (queda en TMP_*)
```
Una *frase parcial* de Vosk llega cada ~0.1–0.3 s con todo lo dicho desde el último silencio; una *final* cierra la frase. La interfaz las consulta cada 100 ms (`KaraokeScreen.update`).

### 6.2 Limpieza del sonido (`audio.py`)
Trabaja por bloques de 100 ms, en tiempo real, solo con numpy:
1. **Pasa-altas** a `HP_CUTOFF_HZ` (90 Hz): golpes de micrófono, zumbido grave.
2. **Sustracción espectral**: el ruido de fondo se estima por frecuencia como el *mínimo suavizado* de la potencia (baja de inmediato, sube lento) y se resta con factor `DENOISE_OVERSUB` y piso `DENOISE_FLOOR` (evita sonido «metálico»). En una prueba sintética redujo el ruido ≈ 11 dB conservando la voz (`tests/test_audio.py`).
3. **AGC**: sube la voz de cantantes lejanos (hasta ×`AGC_MAX_GAIN`) **solo si detecta voz** (nivel > 2.5× el piso de ruido), nunca amplifica el silencio.

No separa voz de música ni de otras voces: eso requeriría modelos pesados. En Android el sistema operativo aplica su propia supresión de ruido y no se expone el audio crudo, por eso `audio.py` solo se usa en Windows.

### 6.3 ESCUCHANDO → identificar
* Se acumulan las palabras del «episodio» (se olvida tras `EPISODE_TIMEOUT` = 20 s sin voz).
* Con ≥ `SEARCH_MIN_TOKENS` (3) palabras se busca la **cola** de las últimas `SEARCH_TAIL` palabras (≈ 0.8 líneas).
* Se fija la canción si su puntaje ≥ `SEARCH_THRESHOLD` (0.75) **y** supera a la segunda por `SEARCH_AMBIGUITY` (0.05); si hay empate (estribillos repetidos entre canciones), **se sigue escuchando** y la siguiente palabra desempata.
* Si pasan `UNKNOWN_TOKENS` palabras y el mejor puntaje está entre 0.50 y 0.75, se fija igual (mejor suposición).
* Se vuelve a aplicar la búsqueda en cada parcial, así que la identificación ocurre **a mitad de la primera línea**.

### 6.4 SIGUIENDO → sincronizar con la velocidad del cantante (`Controller._track`)
La pantalla muestra la **línea que se está cantando** (más la anterior y las dos siguientes). En cada parcial se calcula qué fracción de la línea actual ya se reconoció (`progress`):

* ≥ `ADVANCE_PROGRESS` (70 %) → pasa a la línea siguiente. Si Vosk cerró la frase (pausa del cantante) basta `FINAL_ADVANCE` (50 %).
* Un puntero `consumed` marca las palabras de la frase ya asignadas a líneas anteriores, de modo que una frase continua que abarca varias líneas se reparte correctamente.
* **Salto adelante:** si una de las `MAX_JUMP` (4) líneas siguientes coincide ≥ 70 % y supera a la actual por `DELTA_MOVE`, la pantalla salta allí.
* **Repetición atrás:** igual con las `MAX_BACK` (2) líneas anteriores (≥ 50 %).
* **Perdido:** si se acumulan `LOST_TOKENS` (12) palabras sin coincidir → vuelve a ESCUCHANDO y busca en toda la base (esto cubre también «el cantante cambió de canción»).
* `TRACK_IDLE_TIMEOUT` (30 s) de silencio → vuelve a ESCUCHANDO.
* Líneas sin palabras (p. ej. «...») se saltan solas.
* Al completar la última línea → «FIN», se contabiliza la canción y se queda escuchando la siguiente. No hace falta ninguna tecla.

Por qué funciona «a la velocidad del cantante»: el avance depende de **lo que se oye**, no de un reloj; si el cantante alarga o se detiene, la pantalla espera.

### 6.5 Canción desconocida: tablas temporales y nombre
Si se acumulan ≥ `UNKNOWN_TOKENS` (20) palabras en ≥ 2 frases y nada coincide (< 0.50):
1. Se crea una fila en `TMP_CANCIONES` y cada frase final se guarda en `TMP_LETRAS` (con la primera letra en mayúscula).
2. Durante la captura se sigue **comprobando** cada frase contra la base: si resulta que la canción sí existía (las primeras palabras se oyeron mal), se descarta la captura y se pasa a SIGUIENDO.
3. Tras `CAPTURE_END_SILENCE` (10 s) la captura se cierra. Si tiene menos de `MIN_CAPTURE_LINES` (3) líneas se descarta por ser ruido.
4. En el menú `n` el usuario corrige la letra, escribe el **nombre** y se pasa a `NOMBRES/LETRAS` con `tmp_commit`.

**Suposición sobre el nombre:** un reconocedor de voz transcribe palabras cantadas, pero no sabe cómo se llama la canción, y no se usa internet para buscarlo (el programa debe funcionar sin conexión). Por eso el nombre provisional es «Nueva: <primeras palabras>» y la persona lo confirma.

### 6.6 Funciones del modo manual automatizadas
| Manual | En automático |
|---|---|
| Buscar con 2–3 palabras | Identificación automática (§6.3) |
| `c` continuar | Avance por progreso de línea (§6.4); `c` sigue disponible como forzado |
| `r` repetir canción | Se detecta como «repetición atrás»/«perdido→re-identificar»; `r` forzado |
| `i` igual | La línea no avanza hasta que se canta; `i` fuerza mantenerla |
| `g` / `s` ignorar / seguir | Igual, a mano (`g` ignora todo audio hasta `s`) |
| `f` fin | Igual; cierra además capturas abiertas |
| PROGRAMA | Las canciones pendientes desempatan la identificación |

---

## 7. Parámetros ajustables (`config.py`)

### ¿Dónde y cómo cambiar el tamaño de canciones y líneas?
| Parámetro | Valor | Efecto |
|---|---|---|
| `LINEAS_PROMEDIO` | 10 | Líneas por canción esperadas. Deriva `MIN_CAPTURE_LINES` (mín. de líneas para aceptar una canción nueva capturada). |
| `CARACTERES_POR_LINEA` | 80 | Caracteres por línea esperados. Deriva: palabras por línea (`TOKENS_POR_LINEA` ≈ 13), tamaño de la ventana de búsqueda (`SEARCH_TAIL`), umbral de «cancion nueva» (`UNKNOWN_TOKENS`), umbral de aviso de línea larga (`LIMITE_AVISO_LINEA` = el doble) y tamaño mínimo de letra en pantalla. |

La base **no limita** ni líneas por canción ni largo de línea. Para letras con líneas de ~40 caracteres, cambie `CARACTERES_POR_LINEA = 40`; para ~120, `= 120`. El tamaño de letra en pantalla se calcula con el largo real de cada línea (líneas largas = letra más pequeña, hasta 2 renglones).

Otros parámetros sensibles (ver comentarios en el archivo): `FUZZY_TOKEN`, `SEARCH_THRESHOLD`, `ADVANCE_PROGRESS` (más bajo = la pantalla se adelanta más al cantante), `LOST_TOKENS`, `HP_CUTOFF_HZ`, `DENOISE_OVERSUB`, `USAR_VOCABULARIO_RESTRINGIDO` (Vosk limitado al vocabulario de la base: más preciso pero **impide capturar canciones nuevas**), `PAGINA` (10).

---


