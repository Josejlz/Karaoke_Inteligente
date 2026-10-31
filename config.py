"""
config.py - PARAMETROS CONFIGURABLES DEL KARAOKE INTELIGENTE
=============================================================

Todo lo que se pueda querer ajustar esta aqui.  Ningun otro modulo tiene
numeros "magicos" de comportamiento.

--- Donde cambiar la longitud promedio de las canciones y de las lineas ---
    LINEAS_PROMEDIO        (enunciado: ~10 lineas por cancion)
    CARACTERES_POR_LINEA   (enunciado: ~80 caracteres por linea)

Estos dos valores NO limitan lo que se puede guardar (la base de datos acepta
canciones y lineas de cualquier tamano).  Se usan para:
  * el tamano de letra con que se dibuja la linea actual (lineas largas ->
    letra mas pequena, lineas cortas -> letra mas grande),
  * avisar al importar/editar si una linea es mucho mas larga de lo normal
    (LIMITE_AVISO_LINEA),
  * calibrar el modo automatico: cuantas palabras se esperan por linea
    (TOKENS_POR_LINEA), ventana de busqueda, minimo de lineas para aceptar
    una cancion nueva capturada, etc.
Si sus letras tienen lineas de ~40 caracteres o de ~120, cambie
CARACTERES_POR_LINEA y todo lo derivado se recalcula solo.
"""
import os

# ----------------------------------------------------------------- ubicaciones
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("KARAOKE_DATA", APP_DIR)

NOMBRE_BD = "CANCIONES.db"            # base de datos SQLite
NOMBRES_PROGRAMA = ("PROGRAMA.txt", "PROGRAMA")   # se acepta con o sin extension
NOMBRE_MODELO_VOSK = "vosk-model-small-es-0.42"   # carpeta dentro de models/


def set_data_dir(path):
    """Cambia la carpeta de datos (en Android se usa user_data_dir)."""
    global DATA_DIR
    os.makedirs(path, exist_ok=True)
    DATA_DIR = path


def db_path():
    return os.path.join(DATA_DIR, NOMBRE_BD)


def programa_path():
    """Ruta del archivo PROGRAMA (con o sin .txt). Si no existe ninguno,
    devuelve la ruta con extension .txt."""
    for nombre in NOMBRES_PROGRAMA:
        ruta = os.path.join(DATA_DIR, nombre)
        if os.path.exists(ruta):
            return ruta
    return os.path.join(DATA_DIR, NOMBRES_PROGRAMA[0])


def modelo_vosk_path():
    for base in (DATA_DIR, APP_DIR):
        ruta = os.path.join(base, "models", NOMBRE_MODELO_VOSK)
        if os.path.isdir(ruta):
            return ruta
    return os.path.join(DATA_DIR, "models", NOMBRE_MODELO_VOSK)


# ---------------------------------------------- tamano esperado de las letras
LINEAS_PROMEDIO = 10
CARACTERES_POR_LINEA = 80
LIMITE_AVISO_LINEA = CARACTERES_POR_LINEA * 2      # avisar si una linea pasa de esto
PAGINA = 10                                        # listados "de 10 en 10"

# palabras promedio por linea (palabra promedio ~5 letras + 1 espacio)
TOKENS_POR_LINEA = max(3.0, CARACTERES_POR_LINEA / 6.0)

# ------------------------------------------------------ comparacion de textos
FUZZY_TOKEN = 0.80        # similitud minima para considerar iguales dos palabras
                          # (absorbe errores tipicos del reconocedor de voz)

# --------------------------------------------------------------- modo manual
BUSQUEDA_MAX_RESULTADOS = 8
PALABRA_COMUN_FRACCION = 0.03   # palabra en mas del 3% de las lineas = comun (de, la, que...): no se usa para acotar candidatos

# ------------------------------------------------------------ modo automatico
SEARCH_MIN_TOKENS = 3                                  # palabras minimas para intentar identificar
SEARCH_TAIL = max(4, int(TOKENS_POR_LINEA * 0.8))      # ventana de palabras recientes usada al buscar
SEARCH_THRESHOLD = 0.75                                # puntaje minimo para fijar una cancion
SEARCH_AMBIGUITY = 0.05                                # si dos canciones empatan, seguir escuchando
UNKNOWN_TOKENS = max(10, int(TOKENS_POR_LINEA * 1.5))  # palabras sin identificar -> posible cancion nueva
UNKNOWN_MIN_FINALS = 2                                 # frases completas minimas para sospechar cancion nueva
UNKNOWN_BEST_GUESS = 0.50                              # entre esto y SEARCH_THRESHOLD se fija igual (mejor suposicion)
EPISODE_TIMEOUT = 20.0                                 # seg sin voz: se olvida lo escuchado al buscar

ADVANCE_PROGRESS = 0.70    # fraccion de la linea reconocida para pasar a la siguiente
FINAL_ADVANCE = 0.50       # si el cantante hace pausa, basta esta fraccion
MIN_PROGRESS = 0.34        # fraccion minima para decir "ya esta cantando esta linea"
JUMP_THRESHOLD = 0.70      # para saltar hacia adelante (el cantante se salto lineas)
BACK_THRESHOLD = 0.50      # para volver atras (el cantante repite una linea anterior)
DELTA_MOVE = 0.30          # ventaja minima sobre la linea actual para saltar o volver
MAX_JUMP = 4               # cuantas lineas adelante se vigilan
MAX_BACK = 2               # cuantas lineas atras se vigilan
LOST_TOKENS = 12           # palabras sin coincidir -> buscar la cancion de nuevo
TRACK_IDLE_TIMEOUT = 30.0  # seg sin voz siguiendo una cancion -> volver a escuchar

CAPTURE_END_SILENCE = 10.0                         # seg de silencio que cierran una captura
MIN_CAPTURE_LINES = max(3, LINEAS_PROMEDIO // 3)   # menos lineas = ruido, se descarta

# --------------------------------------------------------------------- audio
SAMPLE_RATE = 16000
BLOCK_MS = 100
CLEAN_AUDIO = True               # limpiar sonido antes de transcribir
HP_CUTOFF_HZ = 90                # filtro pasa-altas (quita ruido grave / golpes de microfono)
DENOISE_OVERSUB = 1.6            # agresividad de la reduccion de ruido (1.0 suave - 2.5 fuerte)
DENOISE_FLOOR = 0.12             # piso espectral (evita sonido "metalico")
AGC_TARGET_RMS = 0.07            # volumen objetivo de la voz tras la ganancia automatica
AGC_MAX_GAIN = 8.0
USAR_VOCABULARIO_RESTRINGIDO = False   # Vosk: limitar palabras a las de la BD (mas preciso, pero
                                       # impide capturar canciones nuevas)
LENGUAJE_ANDROID = "es-ES"       # idioma del reconocedor nativo de Android
