"""Calibración manual de latencia: mide tu offset personal tocando al
ritmo de varias rondas de clics, para usarlo como punto de partida del
`Offset` en los charts que generes.

Pensado para ser más riguroso que el calibrador integrado de Clone Hero
(Settings > Gameplay > Calibration):
- Varias rondas independientes en vez de una sola pasada: una ronda mala
  (te despistas, pierdes el pulso) no arruina el resultado, se descarta
  sola si se aparta demasiado de las demás.
- Descarta los primeros golpes de cada ronda ("calentamiento"): al
  principio de cualquier serie rítmica se tiende a llegar tarde hasta
  "engancharse" al tempo; incluirlos sesga la medida hacia offsets más
  positivos de lo real.
- Recorta el 10% de valores más extremos (trimmed mean) en vez de una
  media/mediana simple sobre todo, para que un par de golpes fallados no
  descentren el resultado.
- Te enseña la dispersión de cada pulsación (una tira de texto, como el
  gráfico "bueno/malo" de Clone Hero) para que puedas juzgar tú mismo si
  la medida es de fiar o conviene repetir.
- Usa tu guitarra de Clone Hero si `pygame` la detecta como mando (mejor
  que teclado: mides exactamente el dispositivo con el que vas a jugar,
  no una tecla que da igual). Si no hay pygame o no detecta ningún
  mando, cae a la barra espaciadora.

Sigue sin sustituir al calibrador de Clone Hero: ese mide contra el
audio y el vídeo reales del motor del juego, la referencia final para
jugar. Esto es para tener un número de partida sin abrir el juego cada
vez que generas un chart.

Uso:
    python -m clone_hero_converter.calibrar
"""

from __future__ import annotations

import math
import statistics
import struct
import threading
import time
from typing import Callable

from .config import cargar_config, guardar_config

BPM_POR_DEFECTO = 100.0
BEATS_POR_RONDA = 16
N_RONDAS = 3
BEATS_CALENTAMIENTO = 4     # primeros golpes de cada ronda, se descartan
RECORTE = 0.10              # fracción de valores extremos que se recorta


def _generar_clic_wav(frecuencia: float = 1000.0, duracion_ms: int = 60,
                      muestreo: int = 44100) -> bytes:
    """Genera un WAV corto en memoria (tono seno con fade-out) para
    reproducir con winsound.PlaySound.

    Más fiable que winsound.Beep(): Beep() suena por el "dispositivo de
    pitido" del sistema, que en muchos PCs modernos está deshabilitado o
    no está conectado al altavoz/auriculares principal — puede no sonar
    nunca aunque el volumen normal esté bien. PlaySound con un WAV real
    sale por el dispositivo de audio por defecto, el mismo que usa
    cualquier otro programa (incluido Clone Hero).
    """
    n_muestras = int(muestreo * duracion_ms / 1000)
    muestras = bytearray()
    for i in range(n_muestras):
        t = i / muestreo
        progreso = i / n_muestras
        fade = 1.0 if progreso <= 0.7 else max(0.0, 1.0 - (progreso - 0.7) / 0.3)
        valor = int(32767 * 0.6 * fade * math.sin(2 * math.pi * frecuencia * t))
        muestras += struct.pack('<h', valor)

    bloque_fmt = struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, 1, muestreo,
                             muestreo * 2, 2, 16)
    bloque_data = struct.pack('<4sI', b'data', len(muestras)) + bytes(muestras)
    riff = struct.pack('<4sI4s', b'RIFF',
                       4 + len(bloque_fmt) + len(bloque_data), b'WAVE')
    return riff + bloque_fmt + bloque_data


def _detectar_entrada() -> tuple[Callable[[], bool], str]:
    """Devuelve (hay_pulsacion, descripcion): una función que, llamada a
    menudo, dice si hubo una pulsación nueva desde la última vez, y una
    descripción de qué dispositivo se está usando.

    Prioriza un mando/guitarra detectado por pygame (cualquier botón,
    incluido cualquier traste, cuenta como pulsación) y cae a la barra
    espaciadora si pygame no está instalado o no hay ningún mando
    conectado.
    """
    try:
        import pygame
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            joy = pygame.joystick.Joystick(0)
            joy.init()
            nombre = joy.get_name()

            def hay_pulsacion_mando() -> bool:
                pulso = False
                for evento in pygame.event.get():
                    if evento.type == pygame.JOYBUTTONDOWN:
                        pulso = True
                return pulso

            return hay_pulsacion_mando, f'tu mando ("{nombre}", cualquier traste)'
    except ImportError:
        pass
    except Exception:
        pass  # cualquier fallo al inicializar el mando: caer a teclado

    try:
        import msvcrt
    except ImportError:
        def hay_pulsacion_nunca() -> bool:
            return False
        return hay_pulsacion_nunca, "(sin entrada disponible)"

    def hay_pulsacion_teclado() -> bool:
        pulso = False
        while msvcrt.kbhit():
            msvcrt.getch()
            pulso = True
        return pulso

    return hay_pulsacion_teclado, "la barra espaciadora"


def _reproducir_clic(clic_wav: bytes) -> None:
    import winsound
    winsound.PlaySound(clic_wav, winsound.SND_MEMORY | winsound.SND_ASYNC)


def _ronda_de_clics(bpm: float, n_beats: int, clic_wav: bytes,
                    hay_pulsacion: Callable[[], bool]
                    ) -> tuple[list[float], list[float]]:
    """Reproduce una ronda de `n_beats` clics y registra las pulsaciones.

    Devuelve (tiempos_clic, tiempos_pulsacion) en segundos de reloj
    monotónico (time.perf_counter).
    """
    intervalo = 60.0 / bpm
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
            _reproducir_clic(clic_wav)

    hilo = threading.Thread(target=hilo_clics, daemon=True)
    hilo.start()
    fin = time.perf_counter() + intervalo * n_beats + 1.0
    while time.perf_counter() < fin:
        if hay_pulsacion():
            pulsaciones.append(time.perf_counter())
        time.sleep(0.002)  # sondeo fino sin saturar la CPU
    hilo.join()
    return clics, pulsaciones


def _emparejar(clics: list[float], pulsaciones: list[float],
              intervalo: float, descartar_antes_de: int = 0) -> list[float]:
    """Empareja cada pulsación con el clic más cercano y devuelve las
    diferencias en ms, descartando las que no corresponden a ningún clic
    real (a más de medio compás) o caen en los primeros clics de
    calentamiento."""
    umbral_calentamiento = clics[descartar_antes_de] if descartar_antes_de < len(clics) else 0.0
    offsets_ms = []
    for p in pulsaciones:
        if p < umbral_calentamiento:
            continue
        clic_mas_cercano = min(clics, key=lambda c: abs(c - p))
        diferencia_ms = (p - clic_mas_cercano) * 1000
        if abs(diferencia_ms) < intervalo * 1000 / 2:
            offsets_ms.append(diferencia_ms)
    return offsets_ms


def _media_recortada(valores: list[float], recorte: float = RECORTE) -> float:
    """Media tras descartar el `recorte` de valores más altos y más bajos
    (p.ej. recorte=0.10 descarta el 10% más alto y el 10% más bajo)."""
    ordenados = sorted(valores)
    n_descarte = int(len(ordenados) * recorte)
    recortados = ordenados[n_descarte: len(ordenados) - n_descarte] or ordenados
    return statistics.mean(recortados)


def _barra_dispersion(valores: list[float], ancho: int = 41) -> str:
    """Tira de texto tipo '....|..*.....' que sitúa cada offset en una
    escala de -100 a +100 ms alrededor del centro, para ver de un vistazo
    si las pulsaciones están apretadas (buena consistencia) o dispersas
    (mala consistencia) — el equivalente en texto al gráfico bueno/malo
    de la calibración de Clone Hero."""
    limite = 100.0
    celdas = ["·"] * ancho
    centro = ancho // 2
    celdas[centro] = "|"
    for v in valores:
        pos = centro + int(round(v / limite * centro))
        pos = max(0, min(ancho - 1, pos))
        celdas[pos] = "*"
    return "".join(celdas)


def calibrar(bpm: float = BPM_POR_DEFECTO, n_rondas: int = N_RONDAS,
            beats_por_ronda: int = BEATS_POR_RONDA) -> float | None:
    """Mide el offset personal (ms) en varias rondas de clics.

    Devuelve la media recortada en milisegundos (positivo = sueles pulsar
    tarde respecto al clic; negativo = pulsas pronto), o None si no hubo
    suficientes datos de fiar.
    """
    try:
        import winsound  # noqa: F401
    except ImportError:
        print("Esta calibración solo funciona en Windows (usa winsound).")
        print("En otros sistemas, usa el calibrador integrado de Clone Hero.")
        return None

    hay_pulsacion, descripcion_entrada = _detectar_entrada()
    if descripcion_entrada == "(sin entrada disponible)":
        print("No se encontró ni teclado ni mando utilizable. Cancelado.")
        return None

    clic_wav = _generar_clic_wav()
    intervalo = 60.0 / bpm
    print(f"\nVamos a hacer {n_rondas} rondas de {beats_por_ronda} clics a "
          f"{bpm:.0f} BPM cada una.")
    print(f"Pulsa {descripcion_entrada} al ritmo de cada clic (no reacciones "
          f"a uno suelto: engánchate al pulso, como si tocaras).")
    print("Ignora los primeros golpes de cada ronda mientras coges el tempo, "
          "esos no cuentan.")
    input("Pulsa Enter cuando estés listo...")

    medianas_por_ronda: list[float] = []

    for ronda in range(1, n_rondas + 1):
        print(f"\n— Ronda {ronda}/{n_rondas} — empezando en 2 segundos...")
        time.sleep(2)
        clics, pulsaciones = _ronda_de_clics(bpm, beats_por_ronda, clic_wav,
                                             hay_pulsacion)
        offsets_ms = _emparejar(clics, pulsaciones, intervalo,
                                descartar_antes_de=BEATS_CALENTAMIENTO)
        minimo_valido = max(3, (beats_por_ronda - BEATS_CALENTAMIENTO) // 2)
        if len(offsets_ms) < minimo_valido:
            print(f"  Ronda descartada: solo {len(offsets_ms)} pulsaciones "
                  f"válidas de fiar. (No pasa nada, sigue con las siguientes.)")
            continue
        mediana_ronda = statistics.median(offsets_ms)
        spread = statistics.pstdev(offsets_ms) if len(offsets_ms) > 1 else 0.0
        print(f"  Offset de esta ronda: {mediana_ronda:+.0f} ms "
              f"(±{spread:.0f} ms de dispersión, {len(offsets_ms)} golpes)")
        print(f"  [{_barra_dispersion(offsets_ms)}]  (-100ms{'':>27}+100ms)")
        medianas_por_ronda.append(mediana_ronda)

    if len(medianas_por_ronda) < 2:
        print("\nNo hubo suficientes rondas válidas. Repite la prueba — "
              "procura mantener el pulso constante desde el 5º golpe.")
        return None

    # Una ronda entera muy distinta de las demás (te despistaste, perdiste
    # el pulso a mitad) se descarta antes de promediar, en vez de dejar
    # que arrastre el resultado final.
    mediana_global = statistics.median(medianas_por_ronda)
    rondas_coherentes = [m for m in medianas_por_ronda
                         if abs(m - mediana_global) < 60.0] or medianas_por_ronda
    if len(rondas_coherentes) < len(medianas_por_ronda):
        print(f"\n({len(medianas_por_ronda) - len(rondas_coherentes)} ronda(s) "
              f"muy distinta(s) del resto, descartada(s) del resultado final)")

    resultado = _media_recortada(rondas_coherentes) if len(rondas_coherentes) >= 3 \
        else statistics.mean(rondas_coherentes)
    dispersion_entre_rondas = (statistics.pstdev(rondas_coherentes)
                               if len(rondas_coherentes) > 1 else 0.0)

    print(f"\n=== Resultado: {resultado:+.0f} ms "
          f"(de {len(rondas_coherentes)} rondas válidas) ===")
    if dispersion_entre_rondas > 25:
        print(f"⚠ Las rondas variaron bastante entre sí (±{dispersion_entre_rondas:.0f} "
              f"ms). El resultado es utilizable pero no muy fino; repite la "
              f"prueba en algún momento si puedes para afinarlo.")
    else:
        print(f"Consistencia buena entre rondas (±{dispersion_entre_rondas:.0f} ms).")
    print("Positivo = sueles pulsar tarde. Negativo = pulsas pronto.")
    return resultado


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
