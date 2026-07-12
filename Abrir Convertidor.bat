@echo off
chcp 65001 >nul
title Convertidor de canciones
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python convertidor.py %*
    goto fin
)

where py >nul 2>nul
if %errorlevel%==0 (
    py convertidor.py %*
    goto fin
)

echo No se encontro Python instalado en este equipo.
echo Descargalo desde https://www.python.org/downloads/
pause
exit /b 1

:fin
echo.
pause
