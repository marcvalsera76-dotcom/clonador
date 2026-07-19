@echo off
title Comprobar version del conversor
cd /d "%~dp0"
echo.
echo Carpeta donde se esta ejecutando:
echo %cd%
echo.
echo Version instalada:
python -c "from clone_hero_converter import __version__; print('VERSION:', __version__)"
if errorlevel 1 (
    echo.
    echo NO SE PUDO LEER LA VERSION. Puede que falte Python o el modulo.
)
echo.
pause
