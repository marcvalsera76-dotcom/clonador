"""Tests de la lógica pura del calibrador (sin winsound/msvcrt, que solo
existen en Windows): las funciones de estadística y emparejado no
dependen del hardware, así que se pueden probar igual en cualquier SO."""

from clone_hero_converter.calibrar import (
    _barra_dispersion, _emparejar, _media_recortada,
)


def test_media_recortada_descarta_extremos():
    valores = [10.0, 11.0, 12.0, 13.0, 14.0, 200.0]  # 200 es un atípico
    # Con recorte=0.10 sobre 6 valores, n_descarte = int(6*0.10) = 0 (no
    # recorta nada): usar un recorte mayor para forzar el descarte en un
    # conjunto tan pequeño.
    resultado = _media_recortada(valores, recorte=0.20)
    assert resultado < 20.0, "el atípico de 200 no debe arrastrar la media"


def test_media_recortada_sin_atipicos_es_similar_a_la_media_normal():
    valores = [10.0, 11.0, 9.0, 10.5, 9.5]
    assert abs(_media_recortada(valores, recorte=0.10) - 10.0) < 1.0


def test_barra_dispersion_marca_centro_sin_valores():
    barra = _barra_dispersion([])
    assert barra[len(barra) // 2] == "|"
    assert set(barra) <= {"·", "|"}


def test_barra_dispersion_marca_valores_dentro_de_rango():
    barra = _barra_dispersion([0.0, 50.0, -50.0])
    assert barra.count("*") == 3


def test_emparejar_descarta_pulsaciones_lejos_de_cualquier_clic():
    intervalo = 0.5  # 120 BPM
    clics = [0.0, 0.5, 1.0, 1.5]
    pulsaciones = [0.02, 0.52, 5.0]  # la última no corresponde a ningún clic
    offsets = _emparejar(clics, pulsaciones, intervalo)
    assert len(offsets) == 2
    assert all(abs(o) < 100 for o in offsets)


def test_emparejar_descarta_pulsaciones_de_calentamiento():
    intervalo = 0.5
    clics = [0.0, 0.5, 1.0, 1.5, 2.0]
    pulsaciones = [0.01, 0.51, 1.02, 1.51]
    # Descartar los 2 primeros clics (calentamiento) debe eliminar las
    # pulsaciones que caen antes de clics[2] = 1.0
    offsets = _emparejar(clics, pulsaciones, intervalo, descartar_antes_de=2)
    assert len(offsets) == 2
