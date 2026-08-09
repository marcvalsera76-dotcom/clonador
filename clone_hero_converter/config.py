"""Configuración persistente del usuario (~/.clone_hero_converter.json).

Compartida entre gui.py, cli.py y calibrar.py para no duplicar la lectura
y escritura del archivo de configuración en cada sitio.
"""

from __future__ import annotations

import json
import os

RUTA_CONFIG = os.path.join(os.path.expanduser("~"), ".clone_hero_converter.json")


def cargar_config() -> dict:
    try:
        with open(RUTA_CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def guardar_config(config: dict) -> None:
    try:
        with open(RUTA_CONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError:
        pass
