"""Normalizacion de texto: minusculas, sin tildes ni signos, espacios simples.

Se aplica por igual a la letra guardada y a lo que transcribe el reconocedor,
de modo que "Corazón," y "corazon" sean comparables.
"""
import re
import unicodedata

_NO_ALNUM = re.compile(r"[^a-z0-9\s]")


def normalize(texto):
    if not texto:
        return ""
    s = unicodedata.normalize("NFKD", texto.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _NO_ALNUM.sub(" ", s)
    return " ".join(s.split())


def tokens(texto):
    n = normalize(texto)
    return n.split() if n else []
