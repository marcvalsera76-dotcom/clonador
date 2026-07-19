"""Tests rápidos del generador de charts (sin audio real)."""

import re

import numpy as np

from clone_hero_converter.charting import (
    DIFICULTADES, FUERZA_STRUM_FORZADO, HOPO_TICKS, MapaTempo, Nota,
    construir_mapa_tempo, generar_pista_bateria, generar_pista_melodica,
    segundos_a_ticks,
)
from clone_hero_converter.chartfile import generar_chart, generar_song_ini


def _onsets_de_ejemplo(n=100, paso=0.2):
    rng = np.random.default_rng(42)
    onsets = np.arange(n) * paso
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
    assert bpms[:3] == [60, 60, 60]   # tramos lentos
    assert bpms[-1] == 120            # tramo rápido al final
    # El tick del beat 3 (tick=576) debe seguir siendo tick 576 exacto
    assert mapa.a_ticks(3.0) == 576


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


def test_easy_usa_pocos_carriles():
    onsets, fuerzas, tonos = _onsets_de_ejemplo()
    mapa = _mapa_fijo(120.0)
    notas = generar_pista_melodica(onsets, fuerzas, tonos, mapa, "Easy")
    carriles = {c for n in notas for c in n.carriles}
    assert carriles <= {0, 1, 2}


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


def test_song_ini():
    ini = generar_song_ini("T", "A", "", "Test", 65.4, ["guitar", "drums"])
    assert "song_length = 65400" in ini
    assert "diff_guitar = 6" in ini
    assert "diff_bass = -1" in ini
