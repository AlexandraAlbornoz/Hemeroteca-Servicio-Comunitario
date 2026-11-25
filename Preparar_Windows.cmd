@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Preparar Hemeroteca para Windows

echo Preparacion de Hemeroteca para Windows
echo Este paso requiere internet y Python 3.13 instalado con pip y Tcl/Tk.
echo.
py -3.13 --version >nul 2>nul
if errorlevel 1 goto falta_python

if not exist ".venv\Scripts\python.exe" (
    py -3.13 -m venv .venv
    if errorlevel 1 goto error_preparacion
)
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 13) else 1)"
if errorlevel 1 goto version_incorrecta
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto error_preparacion

echo.
echo Preparacion terminada. Abre Iniciar_Hemeroteca.cmd con doble clic.
echo En una copia nueva, el programa pedira registrar al administrador principal.
echo Si ya existe una base con cuentas, utilizara esas cuentas.
pause
exit /b 0

:falta_python
echo No se encontro Python 3.13 con el lanzador py.
echo Instala Python 3.13 incluyendo pip, Python Launcher y Tcl/Tk.
echo Despues vuelve a abrir este archivo.
pause
exit /b 1

:version_incorrecta
echo El entorno .venv de esta carpeta utiliza otra version de Python.
echo Pide al responsable que prepare un entorno nuevo con Python 3.13.
echo No copies el entorno .venv desde otra computadora.
pause
exit /b 1

:error_preparacion
echo.
echo No se pudo completar la preparacion. Revisa el error mostrado arriba.
echo Comprueba la conexion a internet y los permisos de escritura en esta carpeta.
pause
exit /b 1
