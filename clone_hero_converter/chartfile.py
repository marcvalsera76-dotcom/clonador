"""Escritura del archivo notes.chart y song.ini de Clone Hero."""

from __future__ import annotations

from .charting import Nota, RESOLUCION

# Nombres de sección del formato .chart por instrumento
SECCION_INSTRUMENTO = {
    "guitar": "Single",
    "bass": "DoubleBass",
    "drums": "Drums",
    "keys": "Keyboard",
}

NOMBRE_INSTRUMENTO = {
    "guitar": "Guitarra",
    "bass": "Bajo",
    "drums": "Batería",
    "keys": "Teclado",
}


def _seccion(nombre: str, lineas: list[str]) -> str:
    cuerpo = "\n".join(f"  {l}" for l in lineas)
    return f"[{nombre}]\n{{\n{cuerpo}\n}}\n"


def generar_chart(titulo: str, artista: str, album: str, generador: str,
                  sync_track: list[tuple[int, float]], offset: float,
                  pistas: dict[tuple[str, str], list[Nota]]) -> str:
    """Genera el contenido completo de notes.chart.

    `sync_track` es la lista (tick, bpm) de MapaTempo.sync_track() — un
    evento B por cada tramo de tempo detectado, no un único BPM fijo para
    toda la canción (así es como lo hacen los charts de referencia reales).
    `pistas` mapea (instrumento, dificultad) -> lista de notas.
    """
    partes = []

    partes.append(_seccion("Song", [
        f'Name = "{titulo}"',
        f'Artist = "{artista}"',
        f'Album = "{album}"',
        f'Charter = "{generador}"',
        f"Offset = {offset}",
        f"Resolution = {RESOLUCION}",
        "Player2 = bass",
        "Difficulty = 0",
        "PreviewStart = 0",
        "PreviewEnd = 0",
        'Genre = "rock"',
        'MediaType = "cd"',
        'MusicStream = "song.ogg"',
    ]))

    if not sync_track:
        sync_track = [(0, 120.0)]
    lineas_sync = ["0 = TS 4"]
    for tick, bpm in sync_track:
        lineas_sync.append(f"{tick} = B {int(round(bpm * 1000))}")
    partes.append(_seccion("SyncTrack", lineas_sync))

    partes.append(_seccion("Events", [
        '0 = E "section Inicio"',
    ]))

    for (instrumento, dificultad), notas in sorted(pistas.items()):
        if not notas:
            continue
        lineas = []
        for nota in sorted(notas, key=lambda n: n.tick):
            for carril in nota.carriles:
                lineas.append(f"{nota.tick} = N {carril} {nota.longitud}")
        nombre = f"{dificultad}{SECCION_INSTRUMENTO[instrumento]}"
        partes.append(_seccion(nombre, lineas))

    return "\n".join(partes)


def generar_song_ini(titulo: str, artista: str, album: str, generador: str,
                     duracion_s: float, instrumentos: list[str]) -> str:
    """Genera el song.ini con las dificultades marcadas por instrumento."""
    lineas = [
        "[song]",
        f"name = {titulo}",
        f"artist = {artista}",
        f"album = {album}",
        "genre = rock",
        "year = ",
        f"charter = {generador}",
        f"song_length = {int(duracion_s * 1000)}",
        "delay = 0",
        "preview_start_time = 0",
        "diff_band = 3",
    ]
    clave_diff = {
        "guitar": "diff_guitar",
        "bass": "diff_bass",
        "drums": "diff_drums",
        "keys": "diff_keys",
    }
    for inst, clave in clave_diff.items():
        lineas.append(f"{clave} = {6 if inst in instrumentos else -1}")
    lineas.append("icon = ")
    lineas.append("loading_phrase = Generado automáticamente a partir del audio")
    return "\n".join(lineas) + "\n"
