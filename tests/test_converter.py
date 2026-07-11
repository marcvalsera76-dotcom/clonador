"""Tests rápidos del generador de charts (sin audio real)."""

import re

import numpy as np

from clone_hero_converter.charting import (
    DIFICULTADES, Nota, generar_pista_bateria, generar_pista_melodica,
    segundos_a_ticks,
)
from clone_hero_converter.chartfile import generar_chart, generar_song_ini


def _onsets_de_ejemplo(n=100, paso=0.2):
    rng = np.random.default_rng(42)
    onsets = np.arange(n) * paso
    fuerzas = rng.uniform(0.2, 1.0, n)
    tonos = rng.integers(0, 12, n)
    return onsets, fuerzas, tonos


def test_ticks():
    # A 120 BPM, un segundo son 2 negras = 384 ticks
    assert segundos_a_ticks(1.0, 120.0) == 384


def test_dificultades_reducen_notas():
    onsets, fuerzas, tonos = _onsets_de_ejemplo()
    cuentas = {}
    for dif in DIFICULTADES:
        notas = generar_pista_melodica(onsets, fuerzas, tonos, 120.0, dif)
        cuentas[dif] = len(notas)
        assert all(0 <= c <= 4 for n in notas for c in n.carriles)
        ticks = [n.tick for n in notas]
        assert ticks == sorted(ticks)
    assert cuentas["Easy"] < cuentas["Medium"] < cuentas["Hard"] <= cuentas["Expert"]


def test_easy_usa_pocos_carriles():
    onsets, fuerzas, tonos = _onsets_de_ejemplo()
    notas = generar_pista_melodica(onsets, fuerzas, tonos, 120.0, "Easy")
    carriles = {c for n in notas for c in n.carriles}
    assert carriles <= {0, 1, 2}


def test_bateria_bandas():
    onsets = np.arange(40) * 0.25
    fuerzas = np.full(40, 0.6)
    bandas = np.tile([0, 2, 1, 2], 10)
    notas = generar_pista_bateria(onsets, fuerzas, bandas, 120.0, "Expert")
    assert notas, "la batería debe generar notas"
    carriles = {c for n in notas for c in n.carriles}
    assert 0 in carriles and 1 in carriles and 2 in carriles


def test_formato_chart():
    pistas = {
        ("guitar", "Expert"): [Nota(0, [0]), Nota(192, [1, 2], 96)],
        ("drums", "Easy"): [Nota(0, [0])],
    }
    chart = generar_chart("Titulo", "Artista", "", "Test", 120.0, 0.0, pistas)
    assert '[Song]' in chart
    assert '0 = B 120000' in chart
    assert '[ExpertSingle]' in chart
    assert '[EasyDrums]' in chart
    assert re.search(r'192 = N 1 96', chart)
    assert re.search(r'192 = N 2 96', chart)


def test_song_ini():
    ini = generar_song_ini("T", "A", "", "Test", 65.4, ["guitar", "drums"])
    assert "song_length = 65400" in ini
    assert "diff_guitar = 6" in ini
    assert "diff_bass = -1" in ini
