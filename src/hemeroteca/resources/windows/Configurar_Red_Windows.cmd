@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Permitir Hemeroteca en la red privada
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0Configurar_Red_Windows.ps1"
if errorlevel 1 (
    echo Windows no pudo configurar la red. Pide ayuda al responsable de esta PC.
    pause
)
