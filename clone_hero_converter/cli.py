"""Interfaz de línea de comandos del conversor.

Uso interactivo:
    python -m clone_hero_converter cancion.mp3

Uso sin preguntas (automatizable):
    python -m clone_hero_converter cancion.mp3 \
        --instrumentos guitar,bass,drums --si
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from . import __version__
from .audio import (
    AudioError, analizar, convertir_a_ogg, es_formato_soportado,
    verificar_ffmpeg,
)
from .chartfile import NOMBRE_INSTRUMENTO, generar_chart, generar_song_ini
from .charting import (
    DIFICULTADES, clasificar_tempo, construir_mapa_tempo, estadisticas_pista,
    generar_instrumento, generar_star_power, nombres_de_seccion,
)

INSTRUMENTOS = ["guitar", "bass", "drums", "keys"]
INSTRUMENTOS_POR_DEFECTO = ["guitar", "bass", "keys"]  # sin batería por defecto
GENERADOR = "Clone Hero Converter"


def _limpiar_nombre(texto: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", texto).strip() or "Cancion"


def _mmss(segundos: float) -> str:
    m, s = divmod(max(0, int(round(segundos))), 60)
    return f"{m}:{s:02d}"


def _titulo_y_artista_por_defecto(ruta: str) -> tuple[str, str]:
    base = os.path.splitext(os.path.basename(ruta))[0]
    # Convención habitual "Artista - Título"
    if " - " in base:
        artista, titulo = base.split(" - ", 1)
        return titulo.strip(), artista.strip()
    return base.strip(), "Desconocido"


def preguntar_instrumentos() -> list[str]:
    print("\n🎸 ¿Qué instrumentos quieres que sean jugables?")
    for i, inst in enumerate(INSTRUMENTOS, 1):
        print(f"  {i}. {NOMBRE_INSTRUMENTO[inst]}")
    print("Escribe los números separados por comas "
          "(Enter = guitarra, bajo y teclado, sin batería):")
    respuesta = input("> ").strip()
    if not respuesta:
        return list(INSTRUMENTOS_POR_DEFECTO)
    elegidos = []
    for token in re.split(r"[,\s]+", respuesta):
        if token.isdigit() and 1 <= int(token) <= len(INSTRUMENTOS):
            elegidos.append(INSTRUMENTOS[int(token) - 1])
    return elegidos or list(INSTRUMENTOS_POR_DEFECTO)


def preguntar_dificultades() -> list[str]:
    print("\n⭐ ¿Qué dificultades quieres generar?")
    for i, dif in enumerate(DIFICULTADES, 1):
        print(f"  {i}. {dif}")
    print("Escribe los números separados por comas (Enter = todas):")
    respuesta = input("> ").strip()
    if not respuesta:
        return list(DIFICULTADES)
    elegidas = []
    for token in re.split(r"[,\s]+", respuesta):
        if token.isdigit() and 1 <= int(token) <= len(DIFICULTADES):
            elegidas.append(DIFICULTADES[int(token) - 1])
    return elegidas or list(DIFICULTADES)


def preguntar_texto(pregunta: str, por_defecto: str) -> str:
    respuesta = input(f"{pregunta} [{por_defecto}]: ").strip()
    return respuesta or por_defecto


def convertir(ruta: str, titulo: str, artista: str, album: str,
              instrumentos: list[str], dificultades: list[str],
              salida: str) -> str:
    """Ejecuta la conversión completa y devuelve la carpeta generada."""
    print("🔧 Comprobando ffmpeg...")
    verificar_ffmpeg()  # falla rápido y con mensaje claro si no está disponible

    print(f"\n🔎 Analizando «{titulo}» — esto puede tardar un poco...")
    analisis = analizar(ruta)
    print(f"   ✔ Duración: {analisis.duracion:.1f} s · Tempo: {analisis.bpm:.1f} BPM")

    # Mapa de tempo VARIABLE (un tramo de BPM por cada beat detectado) en
    # vez de un único BPM fijo para toda la canción: evita que las notas se
    # desincronicen progresivamente cuando el tempo real de la grabación
    # fluctúa, aunque sea ligeramente (lo normal en cualquier grabación no
    # cuantizada a click).
    mapa = construir_mapa_tempo(analisis.tiempos_beat, analisis.bpm)
    print(f"   ✔ Tempo: {clasificar_tempo(mapa.bpms_por_tramo())}")

    pistas = {}
    star_power = {}
    # La más alta de las seleccionadas, según el orden real Easy..Expert
    # (no se puede asumir que `dificultades` venga ya ordenada: en el modo
    # interactivo de terminal el usuario escribe los números en cualquier
    # orden).
    dif_alta = next((d for d in reversed(DIFICULTADES) if d in dificultades),
                    dificultades[-1])
    for instrumento in instrumentos:
        for dificultad in dificultades:
            notas = generar_instrumento(analisis, instrumento, dificultad, mapa)
            pistas[(instrumento, dificultad)] = notas
            star_power[(instrumento, dificultad)] = generar_star_power(notas)
        stats = estadisticas_pista(pistas[(instrumento, dif_alta)])
        print(f"   ✔ {NOMBRE_INSTRUMENTO[instrumento]} ({dif_alta}): "
              f"{stats['total']} notas · {stats['acordes']} acordes · "
              f"{stats['hopo']} HOPO · {stats['strum']} strum forzado · "
              f"{stats['sustains']} sustains")

    # Estructura de la canción (Intro/Verse/Chorus/.../Outro): navegable
    # desde el editor y punto de referencia visual para el jugador.
    #
    # analisis.limites_secciones son PUNTOS frontera (incluye 0.0 al
    # principio y la duración total al final), no nombres de sección: el
    # último punto (duracion) solo marca el final del último tramo, no el
    # inicio de uno nuevo. Nombrar uno por cada punto (como se hacía antes)
    # ponía "Outro" en un evento sin duración justo al final de la canción,
    # y el tramo real final se quedaba con el nombre "Verse"/"Chorus" que
    # le tocara en el ciclo, en vez de "Outro".
    limites_inicio = analisis.limites_secciones[:-1]
    nombres = nombres_de_seccion(len(limites_inicio))
    # Dos límites detectados por separado (p.ej. 0.0s y un límite espurio
    # a 0.02s justo detrás) pueden convertirse al MISMO tick al redondear
    # (mapa.a_ticks() ajusta a la subdivisión más fina de la rejilla), y
    # sin esta comprobación quedarían dos eventos "E" distintos en el
    # mismo instante exacto (p.ej. "0 = E section Intro" seguido de
    # "0 = E section Verse"): redundante, aunque no rompe el archivo. Se
    # descarta cualquier límite que caiga en un tick ya usado.
    secciones = []
    ticks_vistos = set()
    for t, nombre in zip(limites_inicio, nombres):
        tick = mapa.a_ticks(t)
        if tick in ticks_vistos:
            continue
        ticks_vistos.add(tick)
        secciones.append((tick, nombre))
    # Evita mostrar dos límites que redondeen al mismo mm:ss (p.ej. un
    # límite espurio a 0.02s justo detrás del inicio en 0.0s).
    vistos = set()
    etiquetas_seccion = []
    for t, nombre in zip(limites_inicio, nombres):
        marca = _mmss(t)
        if marca in vistos:
            continue
        vistos.add(marca)
        etiquetas_seccion.append(f"{nombre} ({marca})")
    print("   ✔ Estructura: " + " → ".join(etiquetas_seccion))

    for instrumento in instrumentos:
        frases = star_power.get((instrumento, dif_alta), [])
        if frases:
            posiciones = ", ".join(_mmss(mapa.a_segundos(tick)) for tick, _ in frases)
            print(f"   ✔ Star Power {NOMBRE_INSTRUMENTO[instrumento]}: "
                  f"{len(frases)} frases en {posiciones}")

    carpeta = os.path.join(salida, _limpiar_nombre(f"{artista} - {titulo}"))
    os.makedirs(carpeta, exist_ok=True)

    print("📝 Escribiendo notes.chart y song.ini...")
    chart = generar_chart(titulo, artista, album, GENERADOR,
                          mapa.sync_track(), 0.0, pistas,
                          secciones=secciones, star_power=star_power)
    with open(os.path.join(carpeta, "notes.chart"), "w", encoding="utf-8") as f:
        f.write(chart)
    ini = generar_song_ini(titulo, artista, album, GENERADOR,
                           analisis.duracion, instrumentos)
    with open(os.path.join(carpeta, "song.ini"), "w", encoding="utf-8") as f:
        f.write(ini)

    print("🎵 Convirtiendo el audio a song.ogg...")
    convertir_a_ogg(ruta, os.path.join(carpeta, "song.ogg"))

    return carpeta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clone_hero_converter",
        description="Convierte un MP3 o vídeo en una canción jugable de Clone Hero.",
    )
    parser.add_argument("archivo", nargs="?", default=None,
                        help="Archivo de audio (mp3, wav, ogg...) o vídeo (mp4, mkv...). "
                             "Sin archivo se abre la ventana gráfica.")
    parser.add_argument("--terminal", action="store_true",
                        help="Forzar el modo de terminal (no abrir la ventana)")
    parser.add_argument("--titulo", help="Título de la canción")
    parser.add_argument("--artista", help="Artista")
    parser.add_argument("--album", default="", help="Álbum")
    parser.add_argument("--instrumentos",
                        help="Lista separada por comas: guitar,bass,drums,keys")
    parser.add_argument("--dificultades",
                        help="Lista separada por comas: Easy,Medium,Hard,Expert")
    parser.add_argument("--salida", default="canciones",
                        help="Carpeta de salida (por defecto: canciones/)")
    parser.add_argument("--si", "-y", action="store_true",
                        help="No preguntar nada: usar valores por defecto")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    # Sin archivo (o con archivo pero sin --terminal/--si): abrir la ventana
    if not args.terminal and not args.si:
        try:
            from .gui import main as gui_main
            return gui_main(args.archivo)
        except Exception:
            if args.archivo is None:
                raise
            # sin entorno gráfico: continuar en modo terminal

    if args.archivo is None:
        parser.error("falta el archivo (o ejecuta sin --terminal para abrir la ventana)")

    print(f"🎮 Clone Hero Converter v{__version__}")

    if not os.path.exists(args.archivo):
        print(f"❌ No existe el archivo: {args.archivo}", file=sys.stderr)
        return 1
    if not es_formato_soportado(args.archivo):
        print("❌ Formato no soportado. Usa MP3/WAV/OGG/FLAC/M4A o vídeo MP4/MKV/AVI/WEBM.",
              file=sys.stderr)
        return 1

    titulo_def, artista_def = _titulo_y_artista_por_defecto(args.archivo)
    interactivo = not args.si and sys.stdin.isatty()

    titulo = args.titulo
    artista = args.artista
    if interactivo:
        if titulo is None:
            titulo = preguntar_texto("📀 Título", titulo_def)
        if artista is None:
            artista = preguntar_texto("🎤 Artista", artista_def)
    titulo = titulo or titulo_def
    artista = artista or artista_def

    if args.instrumentos:
        instrumentos = [i.strip().lower() for i in args.instrumentos.split(",")]
        desconocidos = [i for i in instrumentos if i not in INSTRUMENTOS]
        if desconocidos:
            print(f"❌ Instrumentos desconocidos: {', '.join(desconocidos)}. "
                  f"Válidos: {', '.join(INSTRUMENTOS)}", file=sys.stderr)
            return 1
    elif interactivo:
        instrumentos = preguntar_instrumentos()
    else:
        instrumentos = list(INSTRUMENTOS_POR_DEFECTO)

    if args.dificultades:
        mapa = {d.lower(): d for d in DIFICULTADES}
        dificultades = []
        for d in args.dificultades.split(","):
            clave = d.strip().lower()
            if clave not in mapa:
                print(f"❌ Dificultad desconocida: {d}. "
                      f"Válidas: {', '.join(DIFICULTADES)}", file=sys.stderr)
                return 1
            dificultades.append(mapa[clave])
    elif interactivo:
        dificultades = preguntar_dificultades()
    else:
        dificultades = list(DIFICULTADES)

    try:
        carpeta = convertir(args.archivo, titulo, artista, args.album,
                            instrumentos, dificultades, args.salida)
    except AudioError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    print(f"\n✅ ¡Listo! Canción generada en: {carpeta}")
    print("   Copia esa carpeta dentro de la carpeta «Songs» de Clone Hero")
    print("   y actualiza la lista de canciones desde el propio juego.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
