@echo off
title Clone Hero Converter
cd /d "%~dp0"
where pythonw >nul 2>nul && (
    start "" pythonw -m clone_hero_converter %*
    exit /b
)
where python >nul 2>nul && (
    start "" python -m clone_hero_converter %*
    exit /b
)
echo No se encuentra Python en este ordenador.
echo Instalalo desde https://www.python.org/downloads/
echo y marca la casilla "Add Python to PATH" al instalarlo.
pause
