# KARAOKE INTELIGENTE — Manual del usuario

Auxiliar para cantantes y su público: muestra en pantalla la letra de la canción, línea por línea, al ritmo del cantante.
Funciona en **Windows**.

---

## 1. ¿Qué hace?

* Guarda canciones y letras en una base de datos SQLite llamada **CANCIONES**.
* **Modo manual:** una persona escucha 2 o 3 palabras, las teclea, el programa encuentra la canción y la persona avanza línea por línea con una tecla.
* **Modo automático:** el programa escucha por el micrófono, identifica la canción solo y avanza al ritmo del cantante. Si la canción no está en la base, la transcribe y la deja guardada como *pendiente* para corregirla.
* Puede seguir una lista planeada de canciones (archivo **PROGRAMA**), pero el cantante puede salirse del orden cuando quiera.

---

## 2. Instalación y arranque en Windows

Requisitos: Windows 10/11, **Python 3.10, 3.11 o 3.12** (de python.org; marque *Add Python to PATH*), un micrófono e internet **solo la primera vez** (para instalar paquetes y bajar el modelo de voz, ~40 MB).

**Forma fácil:** doble clic en `iniciar_windows.bat`. La primera vez crea un entorno, instala las dependencias y descarga el modelo de voz; las siguientes veces solo abre el programa.

**Forma manual** (en una consola, dentro de la carpeta del programa):

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python descargar_modelo.py
python main.py
```

Sin micrófono o sin modelo de voz el programa **sí funciona**: el modo manual no los necesita y el modo automático ofrece el botón **Demo** (un cantante simulado).

**Primer uso:** pulse `f` y luego **Importar canciones de ejemplo** (carga 6 canciones originales de prueba).

---

## 3. Android

Se pretendía usar Kivy para hacer una aplicacion multiplataforma, sin embargo, no pude empaquetar la aplicacion en un apk, asi que solo tiene funcionalidad en windows.



---

## 4. Menú principal

Cada opción tiene su tecla (en Windows) o su botón (en cualquier plataforma).

| Tecla | Opción | Para qué sirve |
|---|---|---|
| `m` | Modo manual | Busca la canción con 2–3 palabras y avanza con `c`. |
| `a` | Modo automático | Escucha por el micrófono, identifica y sigue al cantante. |
| `f` | Alimentación | Agrega canciones a la base de datos. |
| `p` | PROGRAMA | Carga la lista planeada de canciones del cantante. |
| `w` | Listar | Muestra códigos y nombres de las canciones, de 10 en 10. |
| `x` | Ver letra | Pide un código (o nombre) y muestra la letra de 10 en 10 líneas. Si no existe, lo indica. |
| `u` | Corregir letra | Edita nombre y letra de una canción (por nombre o código). |
| `b` | Borrar | Borra una canción y su letra, **pidiendo confirmación**. |
| `n` | Canciones nuevas | *(agregada)* Revisa las canciones capturadas por el modo automático y las guarda en la base. |
| `q` | Salir | Cierra el programa. |

`Esc` (o «atrás» en Android) regresa al menú desde cualquier pantalla.

---

## 5. Alimentar la base de datos (`f`)

### (t) Desde un archivo de texto
Formato: **la primera línea es el nombre**; debajo, la letra, una línea por renglón. Las canciones se separan con **una línea en blanco**.

```
NOMBRE DE LA CANCION
primera linea de la letra
segunda linea de la letra

OTRA CANCION
primera linea...
```

Si la letra tiene líneas en blanco entre estrofas, separe las canciones con una línea `---`; en ese caso las líneas en blanco se ignoran.
Si una canción ya existe (mismo nombre) se omite y se avisa. Se aceptan archivos UTF-8 o ANSI de Windows. El archivo `canciones_ejemplo.txt` sirve de modelo.

También puede **pegar** el texto directamente en el cuadro de la pantalla y pulsar *Importar texto pegado*.

### (e) A mano
Escriba el nombre y pulse Enter; luego la línea 1, Enter, la línea 2, Enter… **Una línea vacía + Enter termina la canción.** El **código se genera solo** y se le muestra al terminar.

---

## 6. El PROGRAMA del cantante (`p`)

Archivo de texto `PROGRAMA.txt` (o `PROGRAMA` sin extensión) junto al programa, **un nombre por línea**:

```
# comentario (se ignora)
1. Noche estrellada
2. Mi pueblo bonito
```

Se carga solo al abrir el programa y también con la opción `p` (donde además puede editarlo y guardarlo). Los nombres no tienen que ser exactos: «noche estrellada» encuentra «Noche estrellada en el camino». Cada nombre se marca como `[ ]` pendiente, `[x]` cantada o `[?]` si **no está en la base**.

**El orden no es obligatorio:** en cualquier momento puede buscar otra canción, repetir una o terminar. El PROGRAMA solo ayuda:

* En manual, la tecla `p` carga la siguiente canción *pendiente* del PROGRAMA sin teclear nada.
* En manual y automático, las canciones pendientes del PROGRAMA tienen una pequeña ventaja al buscar (desempatan).

---

## 7. Modo manual (`m`)

1. Escriba 2 o 3 palabras que oyó (`/` para colocarse en el cuadro de búsqueda) y pulse **Enter**. También se busca por nombre.
2. Aparece una lista numerada con la canción y la línea donde coinciden. Pulse el **número** o toque el botón.
3. La pantalla muestra la línea actual en grande, la anterior atenuada y las dos siguientes. Esa es la línea que **toca cantar**.
4. Cuando el cantante termina (o está por terminar) la línea, pulse `c` o **Espacio**.
5. Al terminar la última línea aparece «FIN DE LA CANCIÓN». Busque la siguiente canción y repita; puede cantar tantas como quiera.

### Teclas durante la sesión

| Tecla | Acción |
|---|---|
| `c` / Espacio | Continuar con la **siguiente línea** |
| `r` | **Repetir** la misma canción desde el inicio |
| `i` | **Igual**: el cantante repite la línea actual, no avanza (la línea parpadea para confirmarlo) |
| `g` | **Ignorar** (pausa): se suspende todo mientras el cantante afina o hace ejercicios |
| `s` | **Seguir**: reanuda tras `g` |
| `p` | Cargar la siguiente canción del PROGRAMA *(agregada)* |
| `f` | **Finalizar** la sesión (muestra las canciones cantadas) |
| `/` | Ir al cuadro de búsqueda |
| 1–8 | Elegir un resultado de la búsqueda |

> **Nota:** el enunciado original usaba `i` dos veces (línea «igual» e «ignorar»). Aquí `i` = *igual* y **`g` = ignorar**.

---

## 8. Modo automático (`a`)

1. Pulse `a`. Arriba aparece **ESCUCHANDO**. Acerque el micrófono (o el teléfono) al cantante.
2. Cuando el cantante canta unas palabras, el programa identifica la canción y pasa a **SIGUIENDO**: muestra la línea que se está cantando y, al reconocer que ya se cantó (~70 %), muestra la siguiente.
3. Si el cantante **se salta líneas** o **repite líneas anteriores**, la pantalla lo sigue. Si se pierde (cambia de canción, improvisa), el programa **vuelve a escuchar y busca de nuevo**.
4. Si la canción **no está en la base**, pasa a **CAPTURANDO CANCIÓN NUEVA**: lo que oye se muestra como subtítulos y se guarda en pendientes. Tras ~10 s de silencio se cierra la captura. Revísela con `n` (ponga el nombre real, corrija la letra y guárdela).
5. Siguen disponibles las teclas de manual: `c` (forzar avance), `r`, `i`, `g` (ignorar/pausa), `s` (seguir), `f` (terminar).
6. **Consejos para mejores resultados:** micrófono cerca de la voz, poco ruido de fondo, y si hay música muy fuerte considere el modo manual. El modo automático funciona mejor con voz clara; con instrumental fuerte puede fallar.

**Botón Demo:** simula a un cantante con errores de reconocimiento. Sirve para probar el modo automático sin micrófono.

---

## 9. Corregir y borrar

* `u` Corregir: busque por código o nombre; se cargan nombre y letra (un renglón por línea); edite y **Guardar cambios**.
* `b` Borrar: busque por código o nombre; el programa muestra el nombre y pregunta **«¿Está seguro?»** antes de borrar. No se puede deshacer.

---

## 10. Problemas frecuentes

| Problema | Solución |
|---|---|
| «No se encontró el modelo de voz» | Ejecute `python descargar_modelo.py` (necesita internet una vez). |
| El modo automático no identifica la canción | Acérquese al micrófono; compruebe que la canción está en la base (`w`); cante/habla al menos 4–5 palabras seguidas. Use el modo manual como respaldo. |
| La letra va adelantada o atrasada | Use `c` para avanzar a mano o `i` para mantener la línea; ajuste `ADVANCE_PROGRESS` (ver manual técnico). |
| Una letra con líneas muy largas se ve pequeña | Es automático. Ver `CARACTERES_POR_LINEA` en `config.py`. |
| Android: no reconoce voz | Compruebe permiso de micrófono, que exista el paquete de voz en español y, si no hay internet, que esté descargado para uso sin conexión. |
