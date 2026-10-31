@echo off
REM Karaoke Inteligente - arranque en Windows (doble clic)
cd /d "%~dp0"
if not exist venv (
  echo Creando entorno virtual e instalando dependencias, solo la primera vez...
  python -m venv venv
  call venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  python descargar_modelo.py
) else (
  call venv\Scripts\activate.bat
)
python main.py
pause
thin