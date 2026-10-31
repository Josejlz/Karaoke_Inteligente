"""
asr.py - Transcripcion de voz en tiempo real.  Entrega eventos (texto, final).

Tres motores con la misma interfaz (start / stop / poll):

  VoskASR      Windows/Linux/Mac.  Microfono con `sounddevice`, limpieza de
               audio (audio.py) y reconocimiento OFFLINE con Vosk (gratuito).
  AndroidASR   Android.  SpeechRecognizer nativo del telefono via pyjnius
               (gratis; usa el motor de Google instalado; funciona sin
               internet si el paquete de voz en espanol esta descargado).
  DemoASR      Sin microfono: "canta" una letra con errores simulados. Sirve
               para probar y demostrar el modo automatico sin audio.

poll() devuelve la lista de (texto, es_final) recibidos desde la ultima
llamada; la interfaz la consulta con un Clock cada ~100 ms y se lo pasa al
Controller.feed().  Los motores corren en hilos propios.
"""
import json
import os
import queue
import random
import threading
import time

import config


def is_android():
    return "ANDROID_ARGUMENT" in os.environ or "ANDROID_STORAGE" in os.environ


class BaseASR:
    name = "base"

    def __init__(self):
        self.q = queue.Queue()
        self.error = None
        self.running = False

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                return out

    def start(self):
        raise NotImplementedError

    def stop(self):
        self.running = False


# --------------------------------------------------------------------- Vosk
class VoskASR(BaseASR):
    name = "Vosk (offline)"

    def __init__(self, vocabulario=None):
        super().__init__()
        self.vocabulario = vocabulario
        self.thread = None

    @staticmethod
    def disponible():
        """(True, '') o (False, motivo)."""
        try:
            import numpy  # noqa
            import sounddevice  # noqa
            import vosk  # noqa
        except Exception as e:
            return False, "Falta instalar: %s (pip install vosk sounddevice numpy)" % e
        if not os.path.isdir(config.modelo_vosk_path()):
            return False, ("No se encontro el modelo de voz en %s. "
                           "Ejecute: python descargar_modelo.py" % config.modelo_vosk_path())
        return True, ""

    def start(self):
        ok, why = self.disponible()
        if not ok:
            self.error = why
            return False
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return True

    def _run(self):
        try:
            import sounddevice as sd
            import vosk
            from audio import AudioCleaner, to_pcm16
            vosk.SetLogLevel(-1)
            model = vosk.Model(config.modelo_vosk_path())
            if self.vocabulario and config.USAR_VOCABULARIO_RESTRINGIDO:
                rec = vosk.KaldiRecognizer(model, config.SAMPLE_RATE,
                                           json.dumps(list(self.vocabulario) + ["[unk]"]))
            else:
                rec = vosk.KaldiRecognizer(model, config.SAMPLE_RATE)
            cleaner = AudioCleaner() if config.CLEAN_AUDIO else None
            block = int(config.SAMPLE_RATE * config.BLOCK_MS / 1000)
            audio_q = queue.Queue()

            def cb(indata, frames, t, status):
                audio_q.put(indata[:, 0].copy())

            last_partial = ""
            with sd.InputStream(samplerate=config.SAMPLE_RATE, blocksize=block, channels=1,
                                dtype="float32", callback=cb):
                while self.running:
                    try:
                        x = audio_q.get(timeout=0.3)
                    except queue.Empty:
                        continue
                    if cleaner is not None:
                        x = cleaner.process(x)
                    if rec.AcceptWaveform(to_pcm16(x)):
                        txt = json.loads(rec.Result()).get("text", "")
                        last_partial = ""
                        if txt:
                            self.q.put((txt, True))
                    else:
                        p = json.loads(rec.PartialResult()).get("partial", "")
                        if p and p != last_partial:
                            last_partial = p
                            self.q.put((p, False))
        except Exception as e:                      # microfono ocupado, sin permiso, etc.
            self.error = "Error de audio: %s" % e
        finally:
            self.running = False


# ------------------------------------------------------------------ Android
class AndroidASR(BaseASR):
    """SpeechRecognizer nativo.  Se reinicia solo al terminar cada frase.
    Necesita el permiso RECORD_AUDIO (se solicita al iniciar)."""
    name = "Android SpeechRecognizer"

    def __init__(self):
        super().__init__()
        self._sr = None
        self._intent = None
        self._listener = None
        self._restart_at = 0

    @staticmethod
    def disponible():
        if not is_android():
            return False, "No es Android"
        return True, ""

    def start(self):
        try:
            from android.permissions import Permission, request_permissions  # type: ignore
            request_permissions([Permission.RECORD_AUDIO], self._after_perm)
        except Exception as e:
            self.error = "No se pudo pedir el permiso de microfono: %s" % e
            return False
        self.running = True
        return True

    def _after_perm(self, permisos, resultados):
        if not all(resultados):
            self.error = "Sin permiso de microfono"
            self.running = False
            return
        from android.runnable import run_on_ui_thread  # type: ignore

        @run_on_ui_thread
        def init():
            try:
                self._init_java()
                self._listen()
            except Exception as e:
                self.error = "Error iniciando reconocimiento: %s" % e
                self.running = False
        init()

    def _init_java(self):
        from jnius import PythonJavaClass, autoclass, java_method  # type: ignore
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        SpeechRecognizer = autoclass("android.speech.SpeechRecognizer")
        RecognizerIntent = autoclass("android.speech.RecognizerIntent")
        Intent = autoclass("android.content.Intent")
        outer = self

        class Listener(PythonJavaClass):
            __javainterfaces__ = ["android/speech/RecognitionListener"]
            __javacontext__ = "app"

            @java_method("(Landroid/os/Bundle;)V")
            def onResults(self, bundle):
                outer._emit(bundle, True)
                outer._relisten()

            @java_method("(Landroid/os/Bundle;)V")
            def onPartialResults(self, bundle):
                outer._emit(bundle, False)

            @java_method("(I)V")
            def onError(self, code):
                outer._relisten(delay=0.4 if code in (6, 7) else 1.0)   # sin voz / sin coincidencia

            @java_method("(Landroid/os/Bundle;)V")
            def onReadyForSpeech(self, b): pass
            @java_method("()V")
            def onBeginningOfSpeech(self): pass
            @java_method("(F)V")
            def onRmsChanged(self, v): pass
            @java_method("([B)V")
            def onBufferReceived(self, b): pass
            @java_method("()V")
            def onEndOfSpeech(self): pass
            @java_method("(ILandroid/os/Bundle;)V")
            def onEvent(self, t, b): pass

        self._listener = Listener()
        ctx = PythonActivity.mActivity
        self._sr = SpeechRecognizer.createSpeechRecognizer(ctx)
        self._sr.setRecognitionListener(self._listener)
        it = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
        it.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        it.putExtra(RecognizerIntent.EXTRA_LANGUAGE, config.LENGUAJE_ANDROID)
        it.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, True)
        it.putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, True)
        self._intent = it

    def _emit(self, bundle, final):
        from jnius import autoclass  # type: ignore
        key = "results_recognition" if final else "android.speech.extra.UNSTABLE_TEXT"
        lst = bundle.getStringArrayList("results_recognition")
        texto = ""
        if not final:
            un = bundle.getStringArrayList(key)
            texto = (str(lst.get(0)) if lst is not None and lst.size() else "") + \
                    (" " + str(un.get(0)) if un is not None and un.size() else "")
        elif lst is not None and lst.size():
            texto = str(lst.get(0))
        texto = texto.strip()
        if texto:
            self.q.put((texto, final))

    def _listen(self):
        if self.running and self._sr is not None:
            self._sr.startListening(self._intent)

    def _relisten(self, delay=0.1):
        from kivy.clock import Clock  # type: ignore
        Clock.schedule_once(lambda dt: self._run_listen(), delay)

    def _run_listen(self):
        from android.runnable import run_on_ui_thread  # type: ignore

        @run_on_ui_thread
        def go():
            try:
                self._sr.cancel()
                self._listen()
            except Exception as e:
                self.error = str(e)
        go()

    def stop(self):
        self.running = False
        try:
            from android.runnable import run_on_ui_thread  # type: ignore

            @run_on_ui_thread
            def bye():
                if self._sr is not None:
                    self._sr.cancel()
                    self._sr.destroy()
                    self._sr = None
            bye()
        except Exception:
            pass


# --------------------------------------------------------------------- Demo
class DemoASR(BaseASR):
    """Simula a un cantante: emite palabra por palabra (parciales) y cierra
    cada frase como final.  errores = probabilidad de que el reconocedor falle."""
    name = "Demostracion (sin microfono)"

    def __init__(self, lineas, palabras_por_seg=2.5, errores=0.10, pausa_linea=0.8, seed=None):
        super().__init__()
        self.lineas = list(lineas)
        self.pps = palabras_por_seg
        self.errores = errores
        self.pausa = pausa_linea
        self.rng = random.Random(seed)
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return True

    def _sucio(self, w):
        r = self.rng.random()
        if r < self.errores * 0.4:
            return None
        if r < self.errores and len(w) > 3:
            return w[:-1] if self.rng.random() < .5 else w + "s"
        return w

    def _run(self):
        from textutil import normalize
        time.sleep(1.0)
        for linea in self.lineas:
            if not self.running:
                return
            ws = [x for x in (self._sucio(w) for w in normalize(linea).split()) if x]
            for i in range(1, len(ws) + 1):
                if not self.running:
                    return
                time.sleep(1.0 / self.pps)
                self.q.put((" ".join(ws[:i]), False))
            self.q.put((" ".join(ws), True))
            time.sleep(self.pausa)
        self.running = False


def make_asr(vocabulario=None):
    """Elige el motor segun la plataforma.  Devuelve (asr_o_None, mensaje)."""
    if is_android():
        return AndroidASR(), ""
    ok, why = VoskASR.disponible()
    if ok:
        return VoskASR(vocabulario), ""
    return None, why
