"""
Script para compilar Clone Hero Converter a .exe con PyInstaller
Ejecutar en Windows: python build_exe.py
"""

import PyInstaller.__main__
import os
import sys

def build():
    # Rutas
    main_py = os.path.join("clone_hero_converter", "__main__.py")
    icon = None  # Opcional: path a un .ico si lo tienes

    print("📦 Compilando Clone Hero Converter a .exe...")
    print("   Esto puede tardar 2-3 minutos...")

    PyInstaller.__main__.run([
        main_py,
        '--name=CloneHeroConverter',
        '--onefile',  # Un solo .exe (más lento pero más simple)
        '--windowed',  # Sin consola
        '--add-data=clone_hero_converter:clone_hero_converter',
        '--hidden-import=librosa',
        '--hidden-import=soundfile',
        '--hidden-import=scipy',
        '--hidden-import=numpy',
        '--collect-all=librosa',
        '--collect-all=scipy',
        '-y',  # Sobrescribir sin preguntar
    ])

    print("\n✅ ¡Hecho!")
    print("   El .exe está en: dist/CloneHeroConverter.exe")
    print("   Cópialo donde quieras y ejecuta haciendo doble clic")

if __name__ == "__main__":
    build()
