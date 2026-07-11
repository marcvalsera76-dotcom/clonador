"""Carga y análisis de audio.

Acepta MP3, WAV, OGG, FLAC, M4A y también vídeo (MP4, MKV, AVI, WEBM, MOV):
si el archivo es un vídeo, se extrae la pista de audio con ffmpeg antes de
analizarla.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, field

import numpy as np
import librosa

SAMPLE_RATE = 22050

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".webm", ".mov", ".flv", ".wmv", ".m4v"}


class AudioError(RuntimeError):
    pass


def es_video(ruta: str) -> bool:
    return os.path.splitext(ruta)[1].lower() in VIDEO_EXTENSIONS


def es_formato_soportado(ruta: str) -> bool:
    ext = os.path.splitext(ruta)[1].lower()
    return ext in AUDIO_EXTENSIONS or ext in VIDEO_EXTENSIONS


def extraer_audio_de_video(ruta_video: str, destino: str) -> str:
    """Extrae la pista de audio de un vídeo a un WAV temporal con ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-i", ruta_video,
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        destino,
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise AudioError(
            f"ffmpeg no pudo extraer el audio del vídeo:\n{resultado.stderr[-500:]}"
        )
    return destino


def convertir_a_ogg(ruta_audio: str, destino: str) -> str:
    """Convierte el audio original a OGG (formato que usa Clone Hero)."""
    cmd = [
        "ffmpeg", "-y", "-i", ruta_audio,
        "-vn", "-c:a", "libvorbis", "-q:a", "6",
        destino,
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise AudioError(
            f"ffmpeg no pudo convertir el audio a OGG:\n{resultado.stderr[-500:]}"
        )
    return destino


@dataclass
class AnalisisCancion:
    """Resultado del análisis de una canción."""

    duracion: float
    bpm: float
    tiempos_beat: np.ndarray          # instantes (s) de cada beat
    # Instrumento melódico (guitarra / teclado)
    onsets_melodia: np.ndarray        # instantes (s) de ataque
    fuerza_melodia: np.ndarray        # fuerza relativa 0..1 de cada onset
    tono_melodia: np.ndarray          # cromas (0-11) dominante en cada onset
    # Bajo (banda grave)
    onsets_bajo: np.ndarray
    fuerza_bajo: np.ndarray
    tono_bajo: np.ndarray
    # Batería (componente percusivo por bandas)
    onsets_bateria: np.ndarray
    fuerza_bateria: np.ndarray
    banda_bateria: np.ndarray         # 0=grave(bombo) 1=media(caja) 2=aguda(platos)
    extra: dict = field(default_factory=dict)


def _onsets_con_fuerza(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Detecta onsets y devuelve (tiempos, fuerza normalizada 0..1)."""
    envolvente = librosa.onset.onset_strength(y=y, sr=sr)
    frames = librosa.onset.onset_detect(
        onset_envelope=envolvente, sr=sr, backtrack=False, units="frames"
    )
    if len(frames) == 0:
        return np.array([]), np.array([])
    tiempos = librosa.frames_to_time(frames, sr=sr)
    fuerzas = envolvente[np.clip(frames, 0, len(envolvente) - 1)]
    tope = np.percentile(fuerzas, 95) if len(fuerzas) > 3 else fuerzas.max()
    fuerzas = np.clip(fuerzas / max(tope, 1e-9), 0.0, 1.0)
    return tiempos, fuerzas


def _croma_en_onsets(y: np.ndarray, sr: int, tiempos: np.ndarray) -> np.ndarray:
    """Croma dominante (0-11) en cada instante de onset."""
    if len(tiempos) == 0:
        return np.array([], dtype=int)
    croma = librosa.feature.chroma_cqt(y=y, sr=sr)
    frames = librosa.time_to_frames(tiempos, sr=sr)
    frames = np.clip(frames, 0, croma.shape[1] - 1)
    # Media de un par de frames alrededor del ataque para robustez
    tonos = []
    for f in frames:
        ventana = croma[:, f : min(f + 3, croma.shape[1])]
        tonos.append(int(np.argmax(ventana.mean(axis=1))))
    return np.array(tonos, dtype=int)


def _pitch_en_onsets(y: np.ndarray, sr: int, tiempos: np.ndarray,
                     fmin: float = 77.0, fmax: float = 1300.0) -> np.ndarray:
    """Tono (0-11) siguiendo el pitch fundamental (pyin) en cada onset.

    Más robusto que el croma de banda ancha para una línea melódica
    monofónica (p.ej. un riff de guitarra), porque sigue una única
    frecuencia dominante en vez de sumar energía de todas las notas
    presentes (lo que arrastra armónicos de voz u otros instrumentos).
    Si el frame no tiene un pitch fiable (silencio, ruido), recurre al
    croma de banda ancha como respaldo.
    """
    if len(tiempos) == 0:
        return np.array([], dtype=int)

    f0, voiced_flag, _ = librosa.pyin(y, fmin=fmin, fmax=fmax, sr=sr)
    croma_respaldo = _croma_en_onsets(y, sr, tiempos)

    frames = np.clip(librosa.time_to_frames(tiempos, sr=sr), 0, len(f0) - 1)
    tonos = []
    for i, f in enumerate(frames):
        ventana = slice(f, min(f + 3, len(f0)))
        f0_ventana = f0[ventana]
        voz_ventana = voiced_flag[ventana]
        validos = f0_ventana[voz_ventana & ~np.isnan(f0_ventana)]
        if len(validos) > 0:
            midi = librosa.hz_to_midi(np.median(validos))
            tonos.append(int(round(midi)) % 12)
        else:
            tonos.append(int(croma_respaldo[i]))
    return np.array(tonos, dtype=int)


def _filtrar_banda(y: np.ndarray, sr: int, f_max: float | None = None,
                   f_min: float | None = None) -> np.ndarray:
    """Filtro de banda sencillo vía STFT (suficiente para detección de onsets)."""
    stft = librosa.stft(y)
    freqs = librosa.fft_frequencies(sr=sr)
    mascara = np.ones(len(freqs), dtype=bool)
    if f_max is not None:
        mascara &= freqs <= f_max
    if f_min is not None:
        mascara &= freqs >= f_min
    stft_filtrado = stft * mascara[:, None]
    return librosa.istft(stft_filtrado, length=len(y))


def _analizar_bateria(y_perc: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Detecta golpes percusivos y los clasifica por banda de frecuencia."""
    tiempos, fuerzas = _onsets_con_fuerza(y_perc, sr)
    if len(tiempos) == 0:
        return tiempos, fuerzas, np.array([], dtype=int)

    stft = np.abs(librosa.stft(y_perc))
    freqs = librosa.fft_frequencies(sr=sr)
    frames = np.clip(librosa.time_to_frames(tiempos, sr=sr), 0, stft.shape[1] - 1)

    grave = freqs < 120
    media = (freqs >= 120) & (freqs < 2000)
    aguda = freqs >= 2000

    bandas = []
    for f in frames:
        ventana = stft[:, f : min(f + 3, stft.shape[1])].mean(axis=1)
        energias = np.array([
            ventana[grave].sum(),
            ventana[media].sum() * 0.6,   # la banda media es ancha; compensar
            ventana[aguda].sum() * 0.8,
        ])
        bandas.append(int(np.argmax(energias)))
    return tiempos, fuerzas, np.array(bandas, dtype=int)


def analizar(ruta: str, verbose: bool = True) -> AnalisisCancion:
    """Analiza un archivo de audio o vídeo y extrae los eventos musicales."""
    if not os.path.exists(ruta):
        raise AudioError(f"No existe el archivo: {ruta}")
    if not es_formato_soportado(ruta):
        raise AudioError(
            f"Formato no soportado: {os.path.splitext(ruta)[1]}. "
            f"Usa MP3/WAV/OGG/FLAC/M4A o un vídeo MP4/MKV/AVI/WEBM."
        )

    ruta_audio = ruta
    tmp = None
    if es_video(ruta):
        if verbose:
            print("🎬 Es un vídeo: extrayendo la pista de audio con ffmpeg...")
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        ruta_audio = extraer_audio_de_video(ruta, tmp.name)

    try:
        if verbose:
            print("🎧 Cargando audio...")
        y, sr = librosa.load(ruta_audio, sr=SAMPLE_RATE, mono=True)
        duracion = float(len(y) / sr)
        if duracion < 5:
            raise AudioError("El audio es demasiado corto (mínimo 5 segundos).")

        if verbose:
            print("🥁 Detectando tempo y beats...")
        tempo, frames_beat = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(np.atleast_1d(tempo)[0])
        if bpm < 40:
            bpm *= 2
        if bpm > 250:
            bpm /= 2
        tiempos_beat = librosa.frames_to_time(frames_beat, sr=sr)

        if verbose:
            print("🎸 Separando componentes armónico y percusivo...")
        # Margen alto para una separación más agresiva: reduce que platos/palmas
        # se cuelen en el componente armónico y viceversa.
        y_harm, y_perc = librosa.effects.hpss(y, margin=(1.0, 5.0))

        if verbose:
            print("🎼 Detectando notas de melodía (guitarra/teclado)...")
        # Banda típica de guitarra (E2-E6 aprox.): reduce la interferencia de
        # graves de bajo/voz muy grave y de sibilancias/armónicos muy agudos.
        y_guitarra = _filtrar_banda(y_harm, sr, f_min=80.0, f_max=1300.0)
        onsets_mel, fuerza_mel = _onsets_con_fuerza(y_guitarra, sr)
        tono_mel = _pitch_en_onsets(y_guitarra, sr, onsets_mel)

        if verbose:
            print("🎻 Detectando línea de bajo...")
        # Banda típica de bajo (E1-G3 aprox., con margen): el bajo suele ser
        # una línea monofónica, así que el seguimiento de pitch fundamental
        # es más fiable aquí que el croma de banda ancha.
        y_bajo = _filtrar_banda(y_harm, sr, f_max=300.0)
        onsets_bajo, fuerza_bajo = _onsets_con_fuerza(y_bajo, sr)
        tono_bajo = _pitch_en_onsets(y_bajo, sr, onsets_bajo, fmin=41.0, fmax=300.0)

        if verbose:
            print("🥁 Detectando golpes de batería...")
        onsets_bat, fuerza_bat, banda_bat = _analizar_bateria(y_perc, sr)

        return AnalisisCancion(
            duracion=duracion,
            bpm=bpm,
            tiempos_beat=tiempos_beat,
            onsets_melodia=onsets_mel,
            fuerza_melodia=fuerza_mel,
            tono_melodia=tono_mel,
            onsets_bajo=onsets_bajo,
            fuerza_bajo=fuerza_bajo,
            tono_bajo=tono_bajo,
            onsets_bateria=onsets_bat,
            fuerza_bateria=fuerza_bat,
            banda_bateria=banda_bat,
        )
    finally:
        if tmp is not None and os.path.exists(tmp.name):
            os.unlink(tmp.name)
