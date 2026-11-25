@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Primero ejecuta Preparar_Windows.cmd para instalar las dependencias.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -B iniciar_instalada.py
if errorlevel 1 pause
