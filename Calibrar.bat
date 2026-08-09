@echo off
title Calibrar offset - Clone Hero Converter
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python -m clone_hero_converter.calibrar
    echo.
    pause
    exit /b
)

echo No se encuentra Python en este ordenador.
echo Instalalo desde https://www.python.org/downloads/
echo y marca la casilla "Add Python to PATH" al instalarlo.
pause
