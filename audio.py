"""
audio.py - Limpieza de sonido en tiempo real (solo numpy).

Cadena aplicada a cada bloque de microfono antes de transcribir:
  1. Filtro pasa-altas (HP_CUTOFF_HZ): quita golpes de microfono y ruido grave.
  2. Reduccion de ruido por sustraccion espectral: el ruido de fondo se estima
     como el minimo (suavizado) de la potencia de cada frecuencia y se resta.
     Sirve para ventiladores, aire acondicionado, hiss del microfono y el
     "cuarto" constante.  No elimina musica ni otras voces (eso no se puede
     separar sin modelos pesados).
  3. Ganancia automatica (AGC): sube la voz cuando el cantante esta lejos del
     microfono, sin amplificar el silencio.

Los parametros estan en config.py.
"""
import numpy as np

import config

N = 512            # tamano de ventana (32 ms a 16 kHz)
HOP = N // 2
NOISE_BIAS = 2.0   # compensa que el minimo suavizado queda por debajo del ruido medio


class AudioCleaner:
    def __init__(self, rate=None):
        self.rate = rate or config.SAMPLE_RATE
        # ventana raiz-de-Hann: analisis y sintesis suman 1 con 50% de traslape
        self.win = np.sqrt(np.hanning(N + 1)[:-1]).astype(np.float32)
        freqs = np.fft.rfftfreq(N, 1.0 / self.rate)
        cut = float(config.HP_CUTOFF_HZ)
        self.hp = np.clip((freqs - cut * 0.5) / (cut * 0.5), 0.0, 1.0).astype(np.float32)
        self.inbuf = np.zeros(0, np.float32)
        self.ola = np.zeros(N, np.float32)
        self.noise = None
        self.smooth = None
        self.floor = None      # nivel RMS minimo (ruido de fondo) para decidir cuando hay voz
        self.prev_gain = None
        self.agc = 1.0
        self.frames = 0
        self.warm = 12         # primeros cuadros: se asume que son solo ruido

    def reset(self):
        self.__init__(self.rate)

    def _frame(self, x):
        spec = np.fft.rfft(x * self.win)
        raw = (spec.real ** 2 + spec.imag ** 2).astype(np.float32)
        pw = raw if self.smooth is None else 0.6 * self.smooth + 0.4 * raw
        self.smooth = pw
        if self.noise is None:
            self.noise = pw.copy() + 1e-9
        if self.frames < self.warm:
            self.noise = 0.7 * self.noise + 0.3 * pw
        else:
            # el ruido baja de inmediato y sube lentamente (minimo estadistico)
            self.noise = np.where(pw < self.noise, pw, self.noise * 1.002)
        self.frames += 1
        # el minimo subestima el ruido real: se compensa con NOISE_BIAS
        gain = 1.0 - config.DENOISE_OVERSUB * NOISE_BIAS * self.noise / (pw + 1e-12)
        gain = np.clip(gain, config.DENOISE_FLOOR, 1.0).astype(np.float32)
        if self.prev_gain is not None:             # suaviza para evitar "ruido musical"
            gain = 0.6 * gain + 0.4 * self.prev_gain
        self.prev_gain = gain
        out = np.fft.irfft(spec * gain * self.hp, N).astype(np.float32)
        return out * self.win

    def process(self, block):
        """block: float32 en [-1, 1].  Devuelve float32 de la misma longitud
        (con ~16 ms de retardo por el traslape)."""
        block = np.asarray(block, np.float32)
        n = len(block)
        self.inbuf = np.concatenate([self.inbuf, block])
        out = np.zeros(0, np.float32)
        while len(self.inbuf) >= N:
            y = self._frame(self.inbuf[:N])
            self.ola += y
            out = np.concatenate([out, self.ola[:HOP]])
            self.ola = np.concatenate([self.ola[HOP:], np.zeros(HOP, np.float32)])
            self.inbuf = self.inbuf[HOP:]
        if len(out) < n:                           # relleno inicial para conservar la longitud
            out = np.concatenate([np.zeros(n - len(out), np.float32), out])
        out = out[:n]
        # ganancia automatica: solo si hay senal clara
        rin = float(np.sqrt(np.mean(block ** 2) + 1e-12))
        self.floor = rin if self.floor is None else min(rin, self.floor * 1.003)
        rms = float(np.sqrt(np.mean(out ** 2) + 1e-12))
        if rin > 2.5 * self.floor and rms > 0.004:          # hay voz, no solo ruido
            objetivo = min(config.AGC_MAX_GAIN, config.AGC_TARGET_RMS / rms)
            self.agc += 0.15 * (objetivo - self.agc)
        elif rin <= 1.5 * self.floor:                       # solo ruido: volver a ganancia 1
            self.agc += 0.05 * (1.0 - self.agc)
        return np.clip(out * self.agc, -1.0, 1.0)


def to_pcm16(x):
    return (np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def from_pcm16(b):
    return np.frombuffer(b, dtype="<i2").astype(np.float32) / 32768.0
