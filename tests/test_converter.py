"""Tests rápidos del generador de charts (sin audio real)."""

import re

import numpy as np

from clone_hero_converter.charting import (
    DIFICULTADES, FUERZA_STRUM_FORZADO, HOPO_TICKS, RESOLUCION, MapaTempo,
    Nota, _asignar_carriles, _reducir, clasificar_tempo, construir_mapa_tempo,
    generar_pista_bateria, generar_pista_melodica, generar_star_power,
    nombres_de_seccion, segundos_a_ticks,
)
from clone_hero_converter.chartfile import generar_chart, generar_song_ini


def _onsets_de_ejemplo(n=100, paso=0.2):
    # Espaciado con jitter (no exactamente uniforme): un paso perfectamente
    # regular colisiona por casualidad con cualquier sep_min por encima de
    # `paso`, dando el mismo resultado a dos dificultades distintas sin que
    # eso signifique nada real sobre su densidad relativa (ver commit que
    # ajustó Hard). Onsets reales nunca caen exactamente cada X segundos.
    rng = np.random.default_rng(42)
    jitter = rng.uniform(-paso * 0.3, paso * 0.3, n)
    onsets = np.cumsum(np.full(n, paso) + jitter - jitter.mean())
    fuerzas = rng.uniform(0.2, 1.0, n)
    tonos = rng.integers(0, 12, n)
    return onsets, fuerzas, tonos


def _mapa_fijo(bpm=120.0, n_beats=400):
    """Mapa de tempo equivalente a un BPM constante, para tests que no
    quieren variación de tempo (comportamiento anterior)."""
    beats = np.arange(n_beats) * (60.0 / bpm)
    return MapaTempo(beats)


def test_ticks():
    # A 120 BPM, un segundo son 2 negras = 384 ticks
    assert segundos_a_ticks(1.0, 120.0) == 384


def test_mapa_tempo_constante_equivale_a_bpm_fijo():
    mapa = _mapa_fijo(120.0)
    # A tempo constante, a_ticks debe coincidir (tras el snap) con la
    # conversión simple de toda la vida.
    assert mapa.a_ticks(1.0) == 384


def test_mapa_tempo_variable_sigue_el_tempo_local():
    # Tramo 1: 60 BPM (1 beat/segundo) durante 4 beats, luego 120 BPM.
    beats = np.array([0.0, 1.0, 2.0, 3.0, 3.5, 4.0, 4.5])
    mapa = construir_mapa_tempo(beats, bpm_global=90.0)
    sync = mapa.sync_track()
    bpms = [round(b) for _, b in sync]
    # sync_track() fusiona tramos consecutivos de BPM parecido (ver
    # TOLERANCIA_BPM): los 3 tramos a 60 dan un único evento, igual que
    # los 3 tramos a 120, así que solo deben quedar 2 cambios reales.
    assert bpms == [60, 120]
    # El tick del beat 3 (tick=576) debe seguir siendo tick 576 exacto
    assert mapa.a_ticks(3.0) == 576


def test_a_ticks_nunca_es_negativo_antes_del_primer_beat():
    # Si el primer beat detectado no cae en t=0 (lo habitual: la detección
    # de tempo rara vez marca un beat exacto en el instante 0), un evento o
    # nota anterior a ese primer beat interpolaría a un tick negativo si no
    # se acotara. Un tick negativo en notes.chart hace que Clone Hero
    # descarte la canción entera al escanear la carpeta Songs.
    beats = np.array([7.0, 7.5, 8.0, 8.5, 9.0])   # primer beat detectado a los 7s
    mapa = construir_mapa_tempo(beats, bpm_global=120.0)
    assert mapa.a_ticks(0.0) == 0
    assert mapa.a_ticks(3.5) == 0   # bastante antes del primer beat también


def test_no_apila_notas_en_tick_0_por_onsets_antes_del_primer_beat():
    # Confirmado en un notes.chart real: una intro sin pulso claro genera
    # varios onsets antes de que librosa detecte el primer beat fiable.
    # Como TODOS esos onsets interpolan a un tick negativo que a_ticks()
    # acota a 0 (ver test anterior), sin filtrarlos antes se apilaban
    # más de 15 notas de la misma pista exactamente en el tick 0 — un
    # caso degenerado que puede colgar el juego.
    beats = np.array([7.0, 7.5, 8.0, 8.5, 9.0])   # primer beat a los 7s
    mapa = construir_mapa_tempo(beats, bpm_global=120.0)
    onsets = np.array([0.5, 1.2, 2.0, 2.8, 3.6, 4.4, 5.2, 6.0, 6.8,  # antes del primer beat
                       7.2, 7.6, 8.0, 8.4])                          # después
    fuerzas = np.full(len(onsets), 0.9)
    tonos = np.tile(np.arange(12), 2)[:len(onsets)]
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Expert")
    en_tick_0 = [n for n in notas if n.tick == 0]
    assert len(en_tick_0) <= 1, "no debe apilar varios onsets tempranos en el mismo tick 0"


def test_clasificar_tempo_usa_bpm_crudo_no_el_ya_fusionado():
    # sync_track() fusiona a propósito el jitter pequeño (para no hinchar
    # el archivo), así que clasificar_tempo() debe recibir siempre
    # bpms_por_tramo() (el BPM crudo), no sync_track(): si se le pasa la
    # versión ya fusionada de una canción con tempo estable, puede colapsar
    # a 1-2 eventos y caer en la rama de "pocos beats detectados", un
    # mensaje sin sentido para una canción de 200 beats.
    dt = 60.0 / 128.0
    jitter = np.random.default_rng(7).normal(0, 0.0012, 200)
    beats = np.cumsum(np.concatenate([[0.0], dt + jitter]))
    mapa = MapaTempo(beats)

    assert len(mapa.sync_track()) < 3, "el tempo casi constante debe fusionarse a pocos eventos"
    assert "estable" in clasificar_tempo(mapa.bpms_por_tramo())


def test_sync_track_fusiona_jitter_de_tempo_casi_constante():
    # Con tempo real constante (120 BPM), el detector de beats siempre
    # tiene algo de temblor: los intervalos no son EXACTAMENTE iguales.
    # Sin fusionar tramos parecidos, esto generaría un evento B distinto
    # en cada beat (miles de líneas en una canción larga). Con jitter de
    # menos de TOLERANCIA_BPM, debe quedar un único evento de tempo.
    beats = 0.5 * np.arange(60) + np.random.default_rng(1).normal(0, 0.001, 60)
    mapa = MapaTempo(np.sort(beats))
    sync = mapa.sync_track()
    assert len(sync) == 1


def test_sync_track_conserva_cambios_de_tempo_reales():
    # Un cambio de tempo genuino (60 -> 150 BPM) no debe fusionarse,
    # aunque esté muy por debajo de TOLERANCIA_BPM en número de tramos.
    beats = np.concatenate([np.arange(10) * 1.0, 9.0 + np.arange(1, 10) * 0.4])
    mapa = MapaTempo(beats)
    sync = mapa.sync_track()
    bpms = [round(b) for _, b in sync]
    assert bpms[0] == 60
    assert bpms[-1] == 150


def test_dificultades_reducen_notas():
    onsets, fuerzas, tonos = _onsets_de_ejemplo()
    mapa = _mapa_fijo(120.0)
    cuentas = {}
    for dif in DIFICULTADES:
        notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, dif)
        cuentas[dif] = len(notas)
        assert all(0 <= c <= 4 for n in notas for c in n.carriles)
        ticks = [n.tick for n in notas]
        assert ticks == sorted(ticks)
    assert cuentas["Easy"] < cuentas["Medium"] < cuentas["Hard"] <= cuentas["Expert"]


def test_acordes_alcanzables_en_todas_las_dificultades():
    # p["acordes"] se compara contra la fuerza normalizada de un onset,
    # que _onsets_con_fuerza() recorta a un máximo de 1.0 — un umbral por
    # encima de 1.0 (el bug: Hard/Medium/Easy tenían 1.05-1.10) hace
    # IMPOSIBLE que esa dificultad genere nunca un acorde. Con la fuerza
    # máxima alcanzable (1.0) en cada onda, las 4 dificultades deben poder
    # producir al menos una nota de 2 carriles.
    onsets = np.arange(30) * 0.5
    fuerzas = np.full(30, 1.0)   # la fuerza máxima físicamente alcanzable
    tonos = np.tile(np.arange(12), 3)[:30]
    mapa = _mapa_fijo(120.0)
    for dif in DIFICULTADES:
        notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, dif)
        acordes = [n for n in notas if len(n.carriles) > 1]
        assert acordes, f"{dif} debería poder generar acordes con fuerza máxima"


def test_favorecer_cambio_tono_deja_ganar_a_una_nota_melodica_mas_floja():
    # Patrón típico "pam pam pam pam": un onset fuerte y repetitivo (mismo
    # tono) puede enterrar una nota melódica algo más floja pero con
    # movimiento real de tono. Sin favorecer_cambio_tono, solo gana el más
    # fuerte (comportamiento de batería, sin cambiar).
    onsets = np.array([0.0, 0.05])
    fuerzas = np.array([1.0, 0.9])   # la segunda es un 10% más floja
    tonos = np.array([5, 7])         # pero cambia de tono

    t, f, e = _reducir(onsets, fuerzas, tonos, sep_min=0.1, umbral=0.05,
                       favorecer_cambio_tono=False)
    assert list(e) == [5], "sin el favor, debe ganar el más fuerte (el repetitivo)"

    t, f, e = _reducir(onsets, fuerzas, tonos, sep_min=0.1, umbral=0.05,
                       favorecer_cambio_tono=True)
    assert list(e) == [7], "con el favor, la nota que cambia de tono debe ganar aunque sea algo más floja"
    assert f[0] == 0.9, "la fuerza guardada debe ser la real, no la bonificada"


def test_favorecer_cambio_tono_no_deja_ganar_a_algo_mucho_mas_flojo():
    # El favor no debe convertirse en "cualquier cambio de tono gana": si
    # la nota más floja es MUCHO más floja (por debajo del margen
    # reducido), sigue perdiendo.
    onsets = np.array([0.0, 0.05])
    fuerzas = np.array([1.0, 0.5])   # mitad de fuerte
    tonos = np.array([5, 7])
    t, f, e = _reducir(onsets, fuerzas, tonos, sep_min=0.1, umbral=0.05,
                       favorecer_cambio_tono=True)
    assert list(e) == [5]


def test_favorecer_cambio_tono_no_afecta_a_bateria():
    # generar_pista_bateria llama a _reducir sin favorecer_cambio_tono: un
    # patrón repetitivo de la misma banda (p.ej. bombo a tempo) no debe
    # verse alterado por este cambio.
    onsets = np.arange(20) * 0.15
    fuerzas = np.full(20, 0.8)
    bandas = np.zeros(20, dtype=int)   # siempre la misma banda (bombo)
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_bateria(onsets, fuerzas, bandas, mapa, "Expert")
    assert notas, "debe seguir generando notas de bombo repetidas con normalidad"


def test_easy_usa_pocos_carriles():
    onsets, fuerzas, tonos = _onsets_de_ejemplo()
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Easy")
    carriles = {c for n in notas for c in n.carriles}
    assert carriles <= {0, 1, 2}


def test_carril_agudo_usa_todos_los_carriles():
    # Tonos que cubren de forma pareja todo el rango grave->agudo (0-11):
    # el más agudo debe caer en el ÚLTIMO carril (naranja en Expert), no
    # solo cuando sea la nota menos frecuente de la canción.
    onsets = np.arange(60) * 0.15
    fuerzas = np.full(60, 0.5)
    tonos = np.tile(np.arange(12), 5)   # reparto uniforme de tonos 0-11
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Expert")
    carriles_usados = {c for n in notas for c in n.carriles}
    assert carriles_usados == {0, 1, 2, 3, 4}, "debe usar los 5 carriles, incluido el naranja"


def test_asignar_carriles_respeta_la_circularidad_del_croma():
    # Melodía que usa 10, 11, 0, 1 (cuatro semitonos seguidos, cruzando la
    # frontera 11->0): son cuatro tonos vecinos de verdad, no deberían
    # amontonarse en un único carril solo porque numéricamente 0 y 1 son
    # "bajos" y 10 y 11 son "altos" en una recta 0-11.
    tonos = np.array([10, 11, 0, 1] * 3)
    carriles = _asignar_carriles(tonos, 5)
    valores_unicos = sorted(set(int(c) for t, c in zip(tonos, carriles)))
    # Deben repartirse en al menos 3 carriles distintos, no amontonarse
    # todos (o casi todos) en uno solo.
    carriles_por_tono = {int(t): int(c) for t, c in zip(tonos, carriles)}
    assert len(set(carriles_por_tono.values())) >= 3


def test_hard_usa_los_5_carriles_igual_que_expert():
    # Convención estándar Guitar Hero/Clone Hero: Hard NO es "Expert menos
    # un carril" — usa los mismos 5 carriles que Expert (incluido el
    # naranja), solo con menos densidad de notas. Solo Easy (3) y Medium
    # (4) recortan carriles.
    onsets = np.arange(60) * 0.3
    fuerzas = np.full(60, 0.9)
    tonos = np.tile(np.arange(12), 5)
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Hard")
    carriles_usados = {c for n in notas for c in n.carriles}
    assert 4 in carriles_usados, "el naranja debe poder aparecer en Hard"


def test_medium_usa_hasta_el_carril_azul():
    onsets = np.arange(60) * 0.4
    fuerzas = np.full(60, 0.9)
    tonos = np.tile(np.arange(12), 5)
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Medium")
    carriles_usados = {c for n in notas for c in n.carriles}
    assert carriles_usados <= {0, 1, 2, 3}
    assert 3 in carriles_usados, "el azul debe poder aparecer en Medium"


def test_bateria_bandas():
    onsets = np.arange(40) * 0.25
    fuerzas = np.full(40, 0.6)
    bandas = np.tile([0, 2, 1, 2], 10)
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_bateria(onsets, fuerzas, bandas, mapa, "Expert")
    assert notas, "la batería debe generar notas"
    carriles = {c for n in notas for c in n.carriles}
    assert 0 in carriles and 1 in carriles and 2 in carriles


def test_hopo_forzado_en_paso_rapido_de_traste():
    # Notas sueltas, dentro de la ventana de HOPO (64 ticks ≈ 0.167s a 120
    # BPM) pero por encima del sep_min de Expert (0.085s) para que
    # _reducir no las descarte. Fuerza baja para no disparar strum forzado.
    onsets = np.array([0.0, 0.12, 0.24, 0.9])
    fuerzas = np.array([0.3, 0.3, 0.3, 0.3])
    tonos = np.array([0, 4, 8, 0])   # cromas distintos -> carriles distintos
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Expert")
    assert len(notas) == 4
    # La 2ª y 3ª nota deben quedar marcadas HOPO (traste distinto + rápido)
    assert notas[1].forzado == 5
    assert notas[2].forzado == 5
    # La 1ª no tiene nota anterior -> nunca forzada
    assert notas[0].forzado is None


def test_strum_forzado_en_ataque_percusivo():
    onsets = np.array([0.0, 0.12])
    fuerzas = np.array([0.3, 0.78])   # 2ª nota: fuerte pero sin llegar a acorde (umbral 0.95)
    tonos = np.array([0, 4])
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Expert")
    assert len(notas) == 2
    assert len(notas[1].carriles) == 1   # nota suelta, no acorde
    assert notas[1].forzado == 6


def test_acorde_nunca_es_hopo():
    onsets = np.array([0.0, 0.12])
    fuerzas = np.array([0.3, 0.97])   # 2ª nota por encima del umbral "acordes" Expert (0.95)
    tonos = np.array([0, 4])
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Expert")
    assert len(notas) == 2
    assert len(notas[1].carriles) == 2   # es acorde
    assert notas[1].forzado != 5         # nunca HOPO


def test_sustain_no_se_solapa_con_siguiente_nota():
    # Hueco largo entre nota 0 y 1, pero la nota 1 llega justo después del
    # final "ideal" del sustain: el clamp debe recortarlo.
    onsets = np.array([0.0, 0.9, 1.0])
    fuerzas = np.array([0.3, 0.3, 0.3])
    tonos = np.array([0, 4, 8])
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Expert")
    assert notas[0].tick + notas[0].longitud < notas[1].tick


def test_formato_chart():
    pistas = {
        ("guitar", "Expert"): [Nota(0, [0]), Nota(192, [1, 2], 96),
                                Nota(384, [3], forzado=5)],
        ("drums", "Easy"): [Nota(0, [0])],
    }
    sync_track = [(0, 120.0), (384, 118.5)]
    chart = generar_chart("Titulo", "Artista", "", "Test", sync_track, 0.0, pistas)
    assert '[Song]' in chart
    assert '0 = B 120000' in chart
    assert '384 = B 118500' in chart
    assert '[ExpertSingle]' in chart
    assert '[EasyDrums]' in chart
    assert re.search(r'192 = N 1 96', chart)
    assert re.search(r'192 = N 2 96', chart)
    assert re.search(r'384 = N 5 0', chart)   # marca de HOPO forzado


def test_star_power_cubre_bloques_de_varias_notas():
    # Racha densa de acordes (climax) seguida de un tramo suelto y espaciado.
    onsets = np.concatenate([np.arange(20) * 0.15, np.arange(5) * 2.0 + 5.0])
    fuerzas = np.concatenate([np.full(20, 0.9), np.full(5, 0.3)])
    tonos = np.tile(np.arange(12), 3)[:25]
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Expert")
    frases = generar_star_power(notas, n_frases_objetivo=3)
    assert frases, "debe colocar al menos una frase de Star Power"
    for inicio, longitud in frases:
        assert longitud >= RESOLUCION
        assert inicio >= 0


def test_star_power_no_solapa_frases():
    onsets, fuerzas, tonos = _onsets_de_ejemplo(n=200, paso=0.15)
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Expert")
    frases = generar_star_power(notas, n_frases_objetivo=6)
    frases_ordenadas = sorted(frases)
    for (i1, l1), (i2, l2) in zip(frases_ordenadas, frases_ordenadas[1:]):
        assert i1 + l1 <= i2, "las frases de SP no deben solaparse"


def test_star_power_vacio_con_pocas_notas():
    onsets = np.array([0.0, 0.5, 1.0])
    fuerzas = np.array([0.5, 0.5, 0.5])
    tonos = np.array([0, 4, 8])
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Expert")
    assert generar_star_power(notas) == []


def test_nombres_de_seccion():
    assert nombres_de_seccion(0) == []
    assert nombres_de_seccion(1) == ["Song"]
    nombres = nombres_de_seccion(6)
    assert nombres[0] == "Intro"
    assert nombres[-1] == "Outro"
    assert len(nombres) == 6
    assert len(set(nombres)) == len(nombres)   # sin nombres repetidos


def test_chart_incluye_secciones_y_star_power():
    pistas = {("guitar", "Expert"): [Nota(0, [0]), Nota(192, [1, 2], 96)]}
    secciones = [(0, "Intro"), (384, "Verse"), (768, "Outro")]
    star_power = {("guitar", "Expert"): [(0, 192)]}
    chart = generar_chart("Titulo", "Artista", "", "Test", [(0, 120.0)], 0.0,
                          pistas, secciones=secciones, star_power=star_power)
    assert '0 = E "section Intro"' in chart
    assert '384 = E "section Verse"' in chart
    assert '768 = E "section Outro"' in chart
    assert '0 = S 2 192' in chart


def test_chart_mantiene_orden_ascendente_de_tick_con_star_power():
    # Frase de Star Power con tick menor que las últimas notas: si se
    # escribe después de las notas sin reordenar, la sección queda con
    # ticks no ascendentes (formato que varios lectores de .chart,
    # incluido Clone Hero, rechazan sin avisar).
    pistas = {("guitar", "Expert"): [Nota(0, [0]), Nota(192, [1]), Nota(1000, [2])]}
    star_power = {("guitar", "Expert"): [(100, 50)]}
    chart = generar_chart("T", "A", "", "Test", [(0, 120.0)], 0.0,
                          pistas, star_power=star_power)
    seccion = chart.split("[ExpertSingle]")[1].split("{")[1].split("}")[0]
    ticks = [int(linea.split(" = ")[0]) for linea in seccion.strip().splitlines()]
    assert ticks == sorted(ticks)


def test_song_ini():
    ini = generar_song_ini("T", "A", "", "Test", 65.4, ["guitar", "drums"])
    assert "song_length = 65400" in ini
    assert "diff_guitar = 6" in ini
    assert "diff_bass = -1" in ini
