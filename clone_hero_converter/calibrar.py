"""Calibración manual de latencia: mide tu offset personal tocando al
ritmo de una serie de clics, para usarlo como punto de partida del
`Offset` en los charts que generes.

Esto NO sustituye al calibrador que ya trae Clone Hero (Settings >
Gameplay > Calibration): ese mide contra el audio y el vídeo reales del
juego, así que sigue siendo la referencia más fiable para jugar. Este
script solo te da un número de partida razonable si notas las notas
sistemáticamente adelantadas o atrasadas al convertir con este programa,
sin tener que abrir el juego para probarlo.

Uso:
    python -m clone_hero_converter.calibrar
"""

from __future__ import annotations

import statistics
import threading
import time

from .config import cargar_config, guardar_config

BPM_POR_DEFECTO = 100.0
BEATS_POR_DEFECTO = 16


def calibrar(bpm: float = BPM_POR_DEFECTO,
            n_beats: int = BEATS_POR_DEFECTO) -> float | None:
    """Mide el offset personal (ms) tocando al ritmo de una serie de clics.

    Reproduce `n_beats` clics a `bpm` y registra cuándo pulsas la barra
    espaciadora respecto a cada uno. Tocar AL RITMO de una serie (en vez
    de reaccionar a un único estímulo sorpresa) cancela la mayor parte del
    tiempo de reacción humano (~150-200 ms), que si no contaminaría la
    medida y la haría inútil como offset de audio.

    Devuelve la mediana en milisegundos (positivo = sueles pulsar tarde
    respecto al clic; negativo = pulsas pronto), o None si no hubo
    suficientes pulsaciones válidas para confiar en el resultado.
    """
    try:
        import msvcrt
        import winsound
    except ImportError:
        print("Esta calibración solo funciona en Windows (usa winsound/msvcrt).")
        print("En otros sistemas, usa el calibrador integrado de Clone Hero.")
        return None

    intervalo = 60.0 / bpm
    print(f"\nVas a oír {n_beats} clics a {bpm:.0f} BPM.")
    print("Pulsa la BARRA ESPACIADORA justo cuando oigas cada clic, como si "
          "tocaras al ritmo (no esperes a reaccionar a cada uno suelto).")
    input("Pulsa Enter cuando estés listo...")
    print("Empezando en 2 segundos...")
    time.sleep(2)

    clics: list[float] = []
    pulsaciones: list[float] = []

    def hilo_clics():
        inicio = time.perf_counter()
        for i in range(n_beats):
            objetivo = inicio + i * intervalo
            espera = objetivo - time.perf_counter()
            if espera > 0:
                time.sleep(espera)
            clics.append(time.perf_counter())
            winsound.Beep(1000, 60)

    hilo = threading.Thread(target=hilo_clics, daemon=True)
    hilo.start()
    fin = time.perf_counter() + intervalo * n_beats + 1.0
    while time.perf_counter() < fin:
        if msvcrt.kbhit():
            msvcrt.getch()
            pulsaciones.append(time.perf_counter())
    hilo.join()

    if not clics or not pulsaciones:
        print("No se registraron suficientes datos. Repite la prueba.")
        return None

    # Empareja cada pulsación con el clic más cercano en el tiempo y
    # descarta las que caen a más de medio compás (pulsaciones sueltas
    # que no corresponden a ningún clic real).
    offsets_ms = []
    for p in pulsaciones:
        clic_mas_cercano = min(clics, key=lambda c: abs(c - p))
        diferencia_ms = (p - clic_mas_cercano) * 1000
        if abs(diferencia_ms) < intervalo * 1000 / 2:
            offsets_ms.append(diferencia_ms)

    minimo_valido = max(3, n_beats // 3)
    if len(offsets_ms) < minimo_valido:
        print(f"Muy pocas pulsaciones cerca de los clics ({len(offsets_ms)} "
              f"de {n_beats}). Repite la prueba intentando ir más al ritmo.")
        return None

    mediana = statistics.median(offsets_ms)
    print(f"\nOffset medido: {mediana:+.0f} ms "
          f"(mediana de {len(offsets_ms)}/{n_beats} pulsaciones válidas)")
    print("Positivo = sueles pulsar tarde. Negativo = pulsas pronto.")
    return mediana


def calibrar_y_guardar() -> None:
    """Ejecuta la calibración y guarda el resultado en la configuración,
    para que `cli.py` lo use automáticamente como Offset por defecto en
    las próximas conversiones."""
    resultado = calibrar()
    if resultado is None:
        return
    config = cargar_config()
    config["offset_calibrado_ms"] = round(resultado, 1)
    guardar_config(config)
    print(f"\nGuardado. Los próximos charts usarán Offset = "
          f"{-resultado / 1000:.3f} s para compensarlo automáticamente.")
    print("Sigue siendo una aproximación: usa el calibrador de Clone Hero "
          "(Settings > Gameplay > Calibration) como referencia final, y "
          "ajusta el audio/video offset del juego si algo no encaja.")


if __name__ == "__main__":
    calibrar_y_guardar()
