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

TOLERANCIA_BPM = 2.0  # variación de BPM entre tramos por debajo de la cual
                      # se considera el mismo tempo (ver MapaTempo.sync_track)

DIFICULTADES = ["Easy", "Medium", "Hard", "Expert"]

# Parámetros de reducción por dificultad:
#   sep_min: separación mínima entre notas (en segundos)
#   carriles: número de carriles usados (desde el verde)
#   umbral: fuerza mínima del onset para conservar la nota
#   acordes: probabilidad-fuerza a partir de la cual una nota se vuelve acorde
#
# El número de carriles sigue la convención estándar de Guitar Hero/Clone
# Hero: Easy usa 3 (verde/rojo/amarillo), Medium 4 (+ azul), y Hard ya usa
# los 5 igual que Expert (+ naranja) — Hard NO es "Expert con un carril
# menos", es Expert con menos densidad de notas. Antes Hard tenía
# carriles=4 y Medium carriles=3, así que el naranja nunca aparecía en
# Hard (y el azul casi nunca en Medium).
#
# `acordes` se compara contra la fuerza normalizada de cada onset
# (_onsets_con_fuerza en audio.py), que se recorta explícitamente al rango
# [0, 1] — 1.0 es el máximo físicamente alcanzable. Con Hard/Medium/Easy en
# 1.05-1.10 (por encima de ese máximo) era MATEMÁTICAMENTE IMPOSIBLE que
# esas tres dificultades generasen nunca un acorde; solo Expert (0.95)
# podía, y solo en el puñado de onsets más fuertes de toda la canción. En
# Guitar Hero/Clone Hero real los acordes existen en las 4 dificultades,
# solo que cada vez menos frecuentes cuanto más fácil (Wiki oficial: "los
# acordes rara vez aparecen en Easy", no "nunca").
PARAMETROS = {
    "Expert": dict(sep_min=0.100, carriles=5, umbral=0.07, acordes=0.95),
    "Hard":   dict(sep_min=0.170, carriles=5, umbral=0.18, acordes=0.97),
    "Medium": dict(sep_min=0.280, carriles=4, umbral=0.28, acordes=0.985),
    "Easy":   dict(sep_min=0.500, carriles=3, umbral=0.40, acordes=0.998),
}

SUSTAIN_MINIMO = 0.45   # hueco (s) a partir del cual la nota anterior se alarga
SUSTAIN_MARGEN = 0.15   # margen (s) que se deja antes de la siguiente nota

# --- HOPO / strum forzado ---------------------------------------------------
# Calibrado con las 4 referencias reales analizadas (Mayonaise, Treasure,
# Cantina Band, Shape of my Heart):
#   - HOPO forzado (N 5): notas sueltas, de traste distinto a la anterior,
#     separadas por poco tiempo (paso melódico rápido, "legato"). Mayonaise
#     tenía 102 de 1632 notas así (~6%, rock de tempo medio).
#   - Strum forzado (N 6): ataques marcados/percusivos (acordes, o notas
#     sueltas con onset fuerte tipo "stab"), para que suenen tocadas y no
#     "ligadas" aunque caigan dentro de la ventana de HOPO natural. Cantina
#     Band (swing con metales staccato) tenía 834 de 1668 así (~50%).
HOPO_TICKS = RESOLUCION // 3       # ventana de "paso rápido" (~1/12 negra)
FUERZA_STRUM_FORZADO = 0.75        # onset por encima de esto = ataque percusivo


@dataclass
class Nota:
    tick: int
    carriles: list[int]   # 0=verde .. 4=naranja (batería: 0=bombo .. 4=verde)
    longitud: int = 0     # ticks de sustain (0 = nota corta)
    forzado: int | None = None   # 5=HOPO forzado, 6=strum forzado, None=natural


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
        """Lista (tick, bpm) — un evento B por cada tramo en que el tempo
        cambia de verdad, lista para escribirse tal cual en [SyncTrack].

        Cada BPM se acota a un rango razonable (20-400): un tramo con un
        hueco anómalo entre beats (silencio, sección sin pulso claro que
        confunde al detector) puede dar un BPM casi 0 o disparatadamente
        alto. Un evento B así de extremo no es solo "feo": algunos charts
        con BPM degenerados no llegan a listarse en Clone Hero al
        escanear la carpeta de Songs.

        No se emite un evento por cada beat: la detección de tempo tiene
        "temblor" (jitter) de un beat a otro incluso en una canción de
        tempo constante, así que escribir el BPM crudo de cada tramo deja
        un SyncTrack con miles de eventos casi idénticos (p.ej. 143.5,
        143.6, 143.4...) para una sola canción larga. Eso hincha mucho el
        archivo y puede ser parte de por qué Clone Hero se atasca al
        cargarlo. Solo se escribe un evento nuevo cuando el BPM se aparta
        más de TOLERANCIA_BPM del último escrito; el resto del tramo
        queda cubierto por ese mismo tempo, igual que en los charts de
        referencia hechos a mano.

        Antes de comparar contra TOLERANCIA_BPM, el BPM crudo se suaviza
        con una mediana móvil. Comprobado con canciones reales: el BPM
        instantáneo no solo tiembla un poco, sino que puede OSCILAR entre
        valores bastante distintos de un beat al siguiente por simple
        imprecisión de frame (143→161→152→161→172... con el tempo real de
        la zona estable en torno a 155-160). Comparar cada tramo solo con
        el último ESCRITO no basta ahí: el ruido "salta" en vez de
        cambiar gradualmente, así que sigue disparando un evento nuevo en
        casi cada beat aunque la tolerancia sea generosa. La mediana en
        una ventana de unos pocos compases da el tempo real de la zona
        sin ese ruido (581 tramos -> 13 eventos en una canción de prueba,
        frente a ~340 sin suavizar).
        """
        bpms = self._bpms_suavizados()
        eventos = []
        bpm_anterior = None
        for i, bpm in enumerate(bpms):
            if bpm_anterior is None or abs(bpm - bpm_anterior) > TOLERANCIA_BPM:
                eventos.append((int(self._ticks_beat[i]), bpm))
                bpm_anterior = bpm
        return eventos

    def _bpms_suavizados(self, ventana: int = 4) -> np.ndarray:
        """bpms_por_tramo() pasado por una mediana móvil de `ventana` beats.

        Solo para sync_track(): clasificar_tempo() necesita el BPM crudo
        (bpms_por_tramo) para medir la variación real de la grabación, no
        esta versión ya aplanada.
        """
        crudos = self.bpms_por_tramo()
        n = len(crudos)
        medio = max(1, ventana // 2)
        return np.array([
            np.median(crudos[max(0, i - medio):min(n, i + medio + 1)])
            for i in range(n)
        ])

    def bpms_por_tramo(self) -> np.ndarray:
        """BPM real de cada tramo entre beats consecutivos, SIN fusionar
        tramos parecidos (a diferencia de sync_track()). clasificar_tempo()
        necesita esta versión cruda: mide la variación real del tempo para
        distinguir una grabación con click de una interpretación en vivo,
        y sync_track() ya ha colapsado el jitter menor que TOLERANCIA_BPM
        para no hinchar el archivo — medir la variación sobre esa versión
        ya aplanada haría parecer "estable" casi cualquier canción."""
        tb = self.tiempos_beat
        dt = np.diff(tb)
        bpm = np.where(dt > 1e-6, 60.0 / np.where(dt > 1e-6, dt, 1.0), 120.0)
        return np.clip(bpm, 20.0, 400.0)

    def a_ticks(self, t: float) -> int:
        """Tiempo real (s) -> tick, interpolando dentro del tramo de beat
        correspondiente y ajustando a la subdivisión más cercana.

        Se acota a un mínimo de 0: un evento o nota anterior al primer beat
        detectado (`t < tiempos_beat[0]`, típico de una entrada/pickup antes
        del primer pulso claro) interpolaría a un tick NEGATIVO. El formato
        .chart no admite ticks negativos — varios parsers (incluido Clone
        Hero) descartan el archivo entero, sin aviso, si aparece uno.
        """
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
        return max(0, _mejor_snap(tick_crudo, self.resolucion))

    def a_segundos(self, tick: float) -> float:
        """Inversa de `a_ticks`: tick -> tiempo real (s). Se usa para poder
        mostrarle al usuario en segundos dónde caen eventos que internamente
        se manejan en ticks (p.ej. las frases de Star Power)."""
        tb, tks = self.tiempos_beat, self._ticks_beat
        if tick <= tks[0]:
            i = 0
        elif tick >= tks[-1]:
            i = len(tks) - 2
        else:
            i = int(np.searchsorted(tks, tick, side="right") - 1)
            i = max(0, min(i, len(tks) - 2))
        dt_ticks = tks[i + 1] - tks[i]
        frac = (tick - tks[i]) / dt_ticks if dt_ticks > 1e-6 else 0.0
        dt_tiempo = tb[i + 1] - tb[i]
        return float(tb[i] + frac * dt_tiempo)


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
    """Reparte los cromas (0-11) entre los carriles disponibles por ALTURA.

    Antes se repartía por percentil de frecuencia (cuántas veces sonaba
    cada tono), no por su altura real: el carril más agudo (naranja en
    Expert) solo recibía el tono menos frecuente de toda la canción, así
    que si esa nota apenas sonaba, el naranja casi no aparecía en el
    chart. Ahora la posición se calcula directamente por altura dentro
    del rango de tonos presentes en la canción (el más grave -> carril 0,
    el más agudo -> el último carril), que es como se reparten los
    carriles en un chart hecho a mano: los agudos van a la derecha.
    """
    if len(tonos) == 0:
        return np.array([], dtype=int)
    valores = np.unique(tonos)
    if len(valores) == 1:
        return np.zeros(len(tonos), dtype=int)
    minimo, maximo = int(valores.min()), int(valores.max())
    rango = maximo - minimo
    mapa = {
        int(v): min(int((v - minimo) / rango * n_carriles), n_carriles - 1)
        for v in valores
    }
    return np.array([mapa[int(t)] for t in tonos], dtype=int)


MARGEN_REEMPLAZO = 1.5        # normal: el retador debe sonar bastante más fuerte
MARGEN_REEMPLAZO_CON_CAMBIO = 0.85  # con cambio de tono: puede ser algo más flojo


def _reducir(onsets: np.ndarray, fuerzas: np.ndarray, extras: np.ndarray,
             sep_min: float, umbral: float,
             favorecer_cambio_tono: bool = False):
    """Filtra onsets débiles y demasiado próximos entre sí.

    `favorecer_cambio_tono` (solo tiene sentido si `extras` son tonos, no
    bandas de batería): cuando dos onsets caen dentro de la misma ventana
    `sep_min`, un patrón rítmico fuerte y repetitivo (siempre la misma
    nota — p.ej. una guitarra rítmica marcando el mismo acorde una y otra
    vez) suena más fuerte y regular que una línea melódica con movimiento,
    así que por pura intensidad el rítmico siempre gana la competición y
    la melodía real queda enterrada. Con esto activado, un onset que
    cambia de tono respecto al último conservado solo necesita superar
    MARGEN_REEMPLAZO_CON_CAMBIO (puede sonar hasta un poco más flojo y aun
    así quedarse con la plaza) en vez del margen normal, mucho más
    exigente, que sí sigue aplicando entre dos onsets de la misma altura.
    """
    seleccion_t, seleccion_f, seleccion_e = [], [], []
    ultimo = -1e9
    for t, f, e in zip(onsets, fuerzas, extras):
        if f < umbral:
            continue
        if t - ultimo < sep_min:
            if seleccion_f:
                cambia_tono = (favorecer_cambio_tono
                               and seleccion_e and e != seleccion_e[-1])
                margen = MARGEN_REEMPLAZO_CON_CAMBIO if cambia_tono else MARGEN_REEMPLAZO
                if f > seleccion_f[-1] * margen:
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


def _excluir_antes_del_primer_beat(onsets: np.ndarray, fuerzas: np.ndarray,
                                   extra: np.ndarray, mapa: MapaTempo):
    """Descarta los onsets anteriores al primer beat detectado.

    MapaTempo no tiene una referencia de tempo fiable antes de
    tiempos_beat[0]: mapa.a_ticks() interpola ahí con un tramo
    extrapolado hacia atrás que da un tick crudo NEGATIVO, y ese
    negativo se acota a 0 (ver a_ticks) para que el .chart no lo
    rechace. El problema es que TODOS los onsets antes del primer beat
    acotan al mismo 0, sin importar lo separados que estén entre sí en
    tiempo real — se ha confirmado un caso real con más de 15 notas de
    una misma pista apiladas exactamente en el tick 0, un caso
    degenerado (decenas de "notas" simultáneas en el mismo instante)
    que puede colgar el juego al intentar mostrarlas todas de golpe.
    Sin una referencia de tempo fiable ahí de todos modos, es mejor
    perder ese puñado de onsets tempranos que arriesgarse a la pila.
    """
    valido = onsets >= mapa.tiempos_beat[0]
    return onsets[valido], fuerzas[valido], extra[valido]


def generar_pista_melodica(onsets: np.ndarray, fuerzas: np.ndarray,
                           tonos: np.ndarray, mapa: MapaTempo,
                           dificultad: str) -> list[Nota]:
    """Genera una pista de guitarra/bajo/teclado para una dificultad."""
    p = PARAMETROS[dificultad]
    onsets, fuerzas, tonos = _excluir_antes_del_primer_beat(onsets, fuerzas, tonos, mapa)
    t, f, tono = _reducir(onsets, fuerzas, tonos, p["sep_min"], p["umbral"],
                          favorecer_cambio_tono=True)
    if len(t) == 0:
        return []

    carriles = _asignar_carriles(tono, p["carriles"])
    carriles = _evitar_repeticion(carriles, p["carriles"])

    notas: list[Nota] = []
    anterior_fret: int | None = None
    anterior_tick: int | None = None
    for i in range(len(t)):
        lanes = [int(carriles[i])]
        es_acorde = f[i] >= p["acordes"]
        # Acorde de dos notas en los ataques más fuertes (solo Expert/Hard)
        if es_acorde:
            vecino = lanes[0] + (1 if lanes[0] < p["carriles"] - 1 else -1)
            lanes.append(vecino)

        tick_inicio = mapa.a_ticks(t[i])

        # HOPO / strum forzado: los acordes nunca son HOPO. Un ataque muy
        # marcado (percusivo) fuerza strum aunque quede dentro de la
        # ventana de HOPO; si no, un cambio de traste rápido respecto a la
        # nota anterior se marca como HOPO forzado.
        forzado = None
        if not es_acorde:
            if f[i] >= FUERZA_STRUM_FORZADO:
                forzado = 6
            elif (anterior_fret is not None and lanes[0] != anterior_fret
                  and anterior_tick is not None
                  and tick_inicio - anterior_tick <= HOPO_TICKS):
                forzado = 5

        longitud = 0
        hueco = (t[i + 1] - t[i]) if i + 1 < len(t) else 0.0
        if hueco > SUSTAIN_MINIMO:
            # Duración en ticks = diferencia entre los ticks de inicio y fin
            # convertidos con el tempo local de cada instante, no una
            # multiplicación por un BPM fijo (eso desincroniza el final del
            # sustain si el tempo real varía dentro del hueco).
            tick_fin = mapa.a_ticks(t[i] + hueco - SUSTAIN_MARGEN)
            longitud = max(0, tick_fin - tick_inicio)
            if i + 1 < len(t):
                # Clamp: el snap a subdivisión puede empujar el final del
                # sustain más allá de donde cae (tras su propio snap) la
                # siguiente nota. Sin este tope el sustain se "come" la
                # nota siguiente en el juego.
                tick_siguiente = mapa.a_ticks(t[i + 1])
                longitud = min(longitud, max(0, tick_siguiente - tick_inicio - 1))

        notas.append(Nota(tick=tick_inicio, carriles=sorted(set(lanes)),
                          longitud=longitud, forzado=forzado))

        # Los acordes rompen la cadena de HOPO (no se encadena tras uno).
        anterior_fret = None if es_acorde else lanes[0]
        anterior_tick = tick_inicio
    return notas


def generar_pista_bateria(onsets: np.ndarray, fuerzas: np.ndarray,
                          bandas: np.ndarray, mapa: MapaTempo,
                          dificultad: str) -> list[Nota]:
    """Genera la pista de batería.

    Carriles de batería en Clone Hero: 0=bombo, 1=rojo (caja),
    2=amarillo (charles), 3=azul (tom), 4=verde (crash).
    """
    p = PARAMETROS[dificultad]
    onsets, fuerzas, bandas = _excluir_antes_del_primer_beat(onsets, fuerzas, bandas, mapa)
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


def generar_star_power(notas: list[Nota],
                       n_frases_objetivo: int = 6) -> list[tuple[int, int]]:
    """Coloca frases de Star Power (evento `S 2`) sobre los tramos de mayor
    densidad/dificultad de la pista, como haría un charter humano: pocas
    frases (5-8 en una canción de 3 min), espaciadas para dejar huecos de
    respiro, y cada una cubre una racha de varias notas consecutivas —
    nunca una nota suelta ni el chart entero.
    """
    if len(notas) < 10:
        return []
    notas = sorted(notas, key=lambda n: n.tick)
    ticks = np.array([n.tick for n in notas])
    # Los acordes y las notas forzadas pesan más: son los pasajes que un
    # charter marca como climáticos.
    pesos = np.array([
        (1.5 if len(n.carriles) > 1 else 1.0) * (1.2 if n.forzado else 1.0)
        for n in notas
    ])

    ventana = RESOLUCION * 8   # ~2 compases en 4/4: frase típica de SP
    densidades = np.array([
        pesos[(ticks >= t - ventana / 2) & (ticks <= t + ventana / 2)].sum()
        for t in ticks
    ])

    duracion_ticks = max(1, int(ticks[-1] - ticks[0]))
    separacion_min = max(RESOLUCION * 16,
                         duracion_ticks // max(n_frases_objetivo * 2, 1))

    frases: list[tuple[int, int]] = []
    for idx in np.argsort(densidades)[::-1]:
        if len(frases) >= n_frases_objetivo:
            break
        centro = ticks[idx]
        mascara = (ticks >= centro - ventana / 2) & (ticks <= centro + ventana / 2)
        bloque = np.where(mascara)[0]
        if len(bloque) < 4:                      # una frase necesita cuerpo
            continue
        inicio, fin = int(ticks[bloque[0]]), int(ticks[bloque[-1]])
        if any(not (fin < f_ini - separacion_min or inicio > f_fin + separacion_min)
               for f_ini, f_fin in frases):
            continue                              # se solapa con otra frase
        frases.append((inicio, fin))

    frases.sort()
    return [(inicio, max(RESOLUCION, fin - inicio)) for inicio, fin in frases]


def nombres_de_seccion(n: int) -> list[str]:
    """Etiquetas genéricas Intro/Verse/Chorus/.../Outro para los `n` tramos
    detectados por `_detectar_secciones`. No hay forma de saber qué tramo es
    realmente un estribillo sin letra, pero alternar Verse/Chorus entre
    Intro y Outro es la convención que siguen los auto-charters y ya deja
    la canción navegable por secciones en el editor.
    """
    if n <= 0:
        return []
    if n == 1:
        return ["Song"]
    nombres = ["Intro"]
    ciclo = ["Verse", "Chorus"]
    i = 0
    while len(nombres) < n - 1:
        repeticion = i // 2 + 1
        base = ciclo[i % 2]
        nombres.append(f"{base} {repeticion}" if repeticion > 1 else base)
        i += 1
    nombres.append("Outro")
    return nombres[:n]


def clasificar_tempo(bpms_por_tramo: np.ndarray) -> str:
    """Clasifica la estabilidad del tempo detectado en esta canción concreta:
    grabación con click (BPM prácticamente constante) o interpretación en
    vivo (el tempo real fluctúa y el MapaTempo variable lo sigue tramo a
    tramo, en vez de forzar un único BPM para toda la pista).

    Recibe el BPM crudo de cada tramo (MapaTempo.bpms_por_tramo()), NO la
    lista ya fusionada de sync_track(): esa fusión colapsa a propósito el
    jitter pequeño para no hinchar el archivo, y mediría "casi cero
    variación" en casi cualquier canción.
    """
    bpms = np.asarray(bpms_por_tramo)
    if len(bpms) < 3:
        return "tempo fijo (pocos beats detectados para evaluar variación)"
    variacion = float(np.std(bpms) / max(np.mean(bpms), 1.0))
    if variacion < 0.01:
        return f"grabación con click, tempo estable (~{bpms.mean():.1f} BPM constante)"
    if variacion < 0.04:
        return (f"tempo casi estable (~{bpms.mean():.1f} BPM) con pequeñas "
                f"fluctuaciones típicas de interpretación humana")
    return (f"tempo VARIABLE, sin click (~{bpms.mean():.1f} BPM de media, "
           f"±{bpms.std():.1f}): probable interpretación en vivo — el mapa "
           f"de tempo sigue el ritmo real compás a compás")


def estadisticas_pista(notas: list[Nota]) -> dict:
    """Cuenta acordes, HOPO, strums forzados y sustains de una pista ya
    generada: da una foto real de cómo quedó ESA canción, no una regla
    genérica."""
    if not notas:
        return dict(total=0, acordes=0, hopo=0, strum=0, sustains=0)
    total = len(notas)
    return dict(
        total=total,
        acordes=sum(1 for n in notas if len(n.carriles) > 1),
        hopo=sum(1 for n in notas if n.forzado == 5),
        strum=sum(1 for n in notas if n.forzado == 6),
        sustains=sum(1 for n in notas if n.longitud > 0),
    )


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
