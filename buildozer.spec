[app]
title = Karaoke Inteligente
package.name = karaokeinteligente
package.domain = org.karaoke
source.dir = .
source.include_exts = py,txt
source.exclude_dirs = tests,models,venv,__pycache__
source.exclude_patterns = *.db,descargar_modelo.py,iniciar_windows.bat
version = 1.0

# En Android NO se usa vosk/numpy/sounddevice: el reconocimiento es el
# SpeechRecognizer nativo del telefono (via pyjnius).
requirements = python3,kivy==2.3.0,pyjnius,android

orientation = landscape
fullscreen = 0
android.permissions = RECORD_AUDIO,INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
