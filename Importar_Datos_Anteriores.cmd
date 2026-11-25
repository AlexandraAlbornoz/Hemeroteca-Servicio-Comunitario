@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PERRI_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PERRI_PYTHON%" set "PERRI_PYTHON=%LOCALAPPDATA%\Programs\Hemeroteca-Perri\.venv\Scripts\python.exe"
if not exist "%PERRI_PYTHON%" (
    echo Primero abre Preparar_Windows.cmd.
    pause
    exit /b 1
)
echo Importa una COPIA de la base anterior. No modifica la original.
echo Cierra Hemeroteca antes de continuar. El destino debe estar vacio.
"%PERRI_PYTHON%" -B importar_datos.py
pause
