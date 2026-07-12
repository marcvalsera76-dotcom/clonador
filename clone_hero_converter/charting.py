"""Generación de notas jugables a partir del análisis de audio.

Convierte los onsets detectados en notas de 5 carriles (verde, rojo,
amarillo, azul, naranja) con cuatro niveles de dificultad, aplicando
reducción de densidad y de carriles según el nivel.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .audio import AnalisisCancion

RESOLUCION = 192  # ticks por negra (estándar de .chart)

DIFICULTADES = ["Easy", "Medium", "Hard", "Expert"]

# Parámetros de reducción por dificultad:
#   sep_min: separación mínima entre notas (en segundos)
#   carriles: número de carriles usados (desde el verde)
#   umbral: fuerza mínima del onset para conservar la nota
#   acordes: probabilidad-fuerza a partir de la cual una nota se vuelve acorde
PARAMETROS = {
    "Expert": dict(sep_min=0.085, carriles=5, umbral=0.05, acordes=0.80),
    "Hard":   dict(sep_min=0.150, carriles=4, umbral=0.15, acordes=0.90),
    "Medium": dict(sep_min=0.280, carriles=3, umbral=0.28, acordes=1.10),
    "Easy":   dict(sep_min=0.500, carriles=3, umbral=0.40, acordes=1.10),
}

SUSTAIN_MINIMO = 0.45   # hueco (s) a partir del cual la nota anterior se alarga
SUSTAIN_MARGEN = 0.15   # margen (s) que se deja antes de la siguiente nota


@dataclass
class Nota:
    tick: int
    carriles: list[int]   # 0=verde .. 4=naranja (batería: 0=bombo .. 4=verde)
    longitud: int = 0     # ticks de sustain (0 = nota corta)


def segundos_a_ticks(t: float, bpm: float) -> int:
    return int(round(t * (bpm / 60.0) * RESOLUCION))


def _mejor_snap(tick: float, resolucion: int = RESOLUCION) -> int:
    """Ajusta un tick al punto más cercano de dos rejillas finas: 32ª nota
    recta (resolucion/8) o 32ª de tresillo (resolucion/12). Evita dejar
    valores de tick "crudos" (arbitrarios) como hace la conversión ingenua
    segundo->tick; los charts hechos a mano (referencia: Mayonaise, Treasure,
    Cantina Band, Shape of my Heart) caen siempre en una de estas dos
    subdivisiones, nunca en ticks sueltos."""
    paso_recta = max(1, resolucion // 8)
    paso_tresillo = max(1, resolucion // 12)
    cand_recta = round(tick / paso_recta) * paso_recta
    cand_tresillo = round(tick / paso_tresillo) * paso_tresillo
    if abs(cand_recta - tick) <= abs(cand_tresillo - tick):
        return int(cand_recta)
    return int(cand_tresillo)


@dataclass
class MapaTempo:
    """Convierte tiempo real (segundos) a ticks usando tempo VARIABLE.

    En vez de asumir un único BPM fijo para toda la canción (lo que hacía
    que las notas se desincronizaran progresivamente en cuanto el tempo
    real de la grabación fluctuaba, aunque fuese ligeramente), cada
    intervalo entre dos beats detectados consecutivos se trata como su
    propio tramo de BPM instantáneo. Es exactamente la técnica que usan
    los charters humanos (ver [SyncTrack] de cualquier referencia real:
    un evento `B` nuevo cada 1-4 tiempos, nunca uno solo para toda la
    canción).
    """

    tiempos_beat: np.ndarray
    resolucion: int = RESOLUCION

    def __post_init__(self) -> None:
        if len(self.tiempos_beat) < 2:
            raise ValueError("Se necesitan al menos 2 beats para un mapa de tempo")
        self._ticks_beat = np.arange(len(self.tiempos_beat)) * self.resolucion

    def sync_track(self) -> list[tuple[int, float]]:
        """Lista (tick, bpm) — un evento B por cada tramo entre beats,
        lista para escribirse tal cual en [SyncTrack]."""
        eventos = []
        for i in range(len(self.tiempos_beat) - 1):
            dt = self.tiempos_beat[i + 1] - self.tiempos_beat[i]
            bpm = 60.0 / dt if dt > 1e-6 else 120.0
            eventos.append((int(self._ticks_beat[i]), bpm))
        return eventos

    def a_ticks(self, t: float) -> int:
        """Tiempo real (s) -> tick, interpolando dentro del tramo de beat
        correspondiente y ajustando a la subdivisión más cercana."""
        tb = self.tiempos_beat
        if t <= tb[0]:
            i = 0
        elif t >= tb[-1]:
            i = len(tb) - 2
        else:
            i = int(np.searchsorted(tb, t, side="right") - 1)
            i = max(0, min(i, len(tb) - 2))
        dt = tb[i + 1] - tb[i]
        frac = (t - tb[i]) / dt if dt > 1e-6 else 0.0
        tick_crudo = self._ticks_beat[i] + frac * self.resolucion
        return _mejor_snap(tick_crudo, self.resolucion)


def construir_mapa_tempo(tiempos_beat: np.ndarray, bpm_global: float,
                         resolucion: int = RESOLUCION) -> MapaTempo:
    """Construye el MapaTempo a partir de los beats detectados por librosa.

    Si por lo que sea hay menos de 2 beats (canción rarísima o detección
    fallida), recurre a un mapa sintético de tempo fijo con `bpm_global`
    para no romper la conversión.
    """
    if tiempos_beat is not None and len(tiempos_beat) >= 2:
        return MapaTempo(np.asarray(tiempos_beat, dtype=float), resolucion)
    # Fallback: tempo fijo sintético (mismo comportamiento que antes)
    duracion_beat = 60.0 / max(bpm_global, 1.0)
    beats_sinteticos = np.arange(0, 600.0, duracion_beat)  # cubre hasta 10 min
    return MapaTempo(beats_sinteticos, resolucion)


def _asignar_carriles(tonos: np.ndarray, n_carriles: int) -> np.ndarray:
    """Reparte los cromas (0-11) entre los carriles disponibles.

    Se ordenan los cromas presentes en la canción por altura y se dividen en
    n_carriles grupos de uso equilibrado, de modo que notas más graves caigan
    en carriles más a la izquierda.
    """
    if len(tonos) == 0:
        return np.array([], dtype=int)
    valores, cuentas = np.unique(tonos, return_counts=True)
    orden = np.argsort(valores)          # por altura de croma
    valores, cuentas = valores[orden], cuentas[orden]
    acumulado = np.cumsum(cuentas) / cuentas.sum()
    inicio = acumulado - cuentas / cuentas.sum()
    mapa = {}
    for v, ini, fin in zip(valores, inicio, acumulado):
        centro = (ini + fin) / 2          # punto medio del intervalo del tono
        mapa[int(v)] = min(int(centro * n_carriles), n_carriles - 1)
    return np.array([mapa[int(t)] for t in tonos], dtype=int)


def _reducir(onsets: np.ndarray, fuerzas: np.ndarray, extras: np.ndarray,
             sep_min: float, umbral: float):
    """Filtra onsets débiles y demasiado próximos entre sí."""
    seleccion_t, seleccion_f, seleccion_e = [], [], []
    ultimo = -1e9
    for t, f, e in zip(onsets, fuerzas, extras):
        if f < umbral:
            continue
        if t - ultimo < sep_min:
            # Si el nuevo onset es claramente más fuerte, sustituye al anterior
            if seleccion_f and f > seleccion_f[-1] * 1.5:
                seleccion_t[-1], seleccion_f[-1], seleccion_e[-1] = t, f, e
                ultimo = t
            continue
        seleccion_t.append(t)
        seleccion_f.append(f)
        seleccion_e.append(e)
        ultimo = t
    return (np.array(seleccion_t), np.array(seleccion_f),
            np.array(seleccion_e, dtype=int))


def _evitar_repeticion(carriles: np.ndarray, n_carriles: int) -> np.ndarray:
    """Rompe rachas largas del mismo carril alternando con un vecino."""
    resultado = carriles.copy()
    racha = 1
    for i in range(1, len(resultado)):
        if resultado[i] == resultado[i - 1]:
            racha += 1
            if racha > 3:
                vecino = resultado[i] + (1 if resultado[i] < n_carriles - 1 else -1)
                resultado[i] = vecino
                racha = 1
        else:
            racha = 1
    return resultado


def generar_pista_melodica(onsets: np.ndarray, fuerzas: np.ndarray,
                           tonos: np.ndarray, mapa: MapaTempo,
                           dificultad: str) -> list[Nota]:
    """Genera una pista de guitarra/bajo/teclado para una dificultad."""
    p = PARAMETROS[dificultad]
    t, f, tono = _reducir(onsets, fuerzas, tonos, p["sep_min"], p["umbral"])
    if len(t) == 0:
        return []

    carriles = _asignar_carriles(tono, p["carriles"])
    carriles = _evitar_repeticion(carriles, p["carriles"])

    notas: list[Nota] = []
    for i in range(len(t)):
        lanes = [int(carriles[i])]
        # Acorde de dos notas en los ataques más fuertes (solo Expert/Hard)
        if f[i] >= p["acordes"]:
            vecino = lanes[0] + (1 if lanes[0] < p["carriles"] - 1 else -1)
            lanes.append(vecino)

        tick_inicio = mapa.a_ticks(t[i])
        longitud = 0
        hueco = (t[i + 1] - t[i]) if i + 1 < len(t) else 0.0
        if hueco > SUSTAIN_MINIMO:
            # Duración en ticks = diferencia entre los ticks de inicio y fin
            # convertidos con el tempo local de cada instante, no una
            # multiplicación por un BPM fijo (eso desincroniza el final del
            # sustain si el tempo real varía dentro del hueco).
            tick_fin = mapa.a_ticks(t[i] + hueco - SUSTAIN_MARGEN)
            longitud = max(0, tick_fin - tick_inicio)

        notas.append(Nota(tick=tick_inicio,
                          carriles=sorted(set(lanes)), longitud=longitud))
    return notas


def generar_pista_bateria(onsets: np.ndarray, fuerzas: np.ndarray,
                          bandas: np.ndarray, mapa: MapaTempo,
                          dificultad: str) -> list[Nota]:
    """Genera la pista de batería.

    Carriles de batería en Clone Hero: 0=bombo, 1=rojo (caja),
    2=amarillo (charles), 3=azul (tom), 4=verde (crash).
    """
    p = PARAMETROS[dificultad]
    t, f, banda = _reducir(onsets, fuerzas, bandas, p["sep_min"], p["umbral"])
    if len(t) == 0:
        return []

    notas: list[Nota] = []
    for i in range(len(t)):
        if banda[i] == 0:                       # grave → bombo
            lanes = [0]
            if f[i] >= p["acordes"]:            # bombo + crash en golpes fuertes
                lanes.append(4 if dificultad in ("Expert", "Hard") else 1)
        elif banda[i] == 1:                     # media → caja
            lanes = [1]
        else:                                   # aguda → charles/platos
            lanes = [2] if dificultad != "Easy" else [1]
        notas.append(Nota(tick=mapa.a_ticks(t[i]),
                          carriles=sorted(set(lanes))))
    return notas


def generar_instrumento(analisis: AnalisisCancion, instrumento: str,
                        dificultad: str, mapa: MapaTempo | None = None) -> list[Nota]:
    """Genera la lista de notas de un instrumento y dificultad concretos.

    `mapa` es opcional para no romper llamadas existentes: si no se pasa,
    se construye aquí mismo a partir de `analisis.tiempos_beat` (con
    fallback a tempo fijo si la detección de beats no dio suficientes).
    Para convertir varios instrumentos/dificultades de la misma canción es
    más eficiente construirlo una vez fuera y pasarlo.
    """
    if mapa is None:
        mapa = construir_mapa_tempo(analisis.tiempos_beat, analisis.bpm)
    if instrumento == "guitar":
        return generar_pista_melodica(analisis.onsets_melodia,
                                      analisis.fuerza_melodia,
                                      analisis.tono_melodia, mapa, dificultad)
    if instrumento == "bass":
        return generar_pista_melodica(analisis.onsets_bajo,
                                      analisis.fuerza_bajo,
                                      analisis.tono_bajo, mapa, dificultad)
    if instrumento == "keys":
        # El teclado reutiliza la parte armónica con reducción algo mayor
        notas = generar_pista_melodica(analisis.onsets_melodia,
                                       analisis.fuerza_melodia,
                                       analisis.tono_melodia, mapa, dificultad)
        return notas
    if instrumento == "drums":
        return generar_pista_bateria(analisis.onsets_bateria,
                                     analisis.fuerza_bateria,
                                     analisis.banda_bateria, mapa, dificultad)
    raise ValueError(f"Instrumento desconocido: {instrumento}")
