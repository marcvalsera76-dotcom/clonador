@echo off
title Clone Hero Converter
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python -m clone_hero_converter %*
    if errorlevel 1 (
        echo.
        echo Hubo un problema al abrir el programa ^(el error debe verse arriba^).
        echo Si menciona un modulo que falta ^(ModuleNotFoundError^), abre una
        echo terminal en esta carpeta y ejecuta:
        echo     pip install -r requirements.txt
        echo.
        pause
    )
    exit /b
)

echo No se encuentra Python en este ordenador.
echo Instalalo desde https://www.python.org/downloads/
echo y marca la casilla "Add Python to PATH" al instalarlo.
pause
