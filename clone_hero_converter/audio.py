"""Carga y análisis de audio.

Acepta MP3, WAV, OGG, FLAC, M4A y también vídeo (MP4, MKV, AVI, WEBM, MOV):
si el archivo es un vídeo, se extrae la pista de audio con ffmpeg antes de
analizarla.
"""

from __future__ import annotations

import gc
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field

import numpy as np
import librosa

SAMPLE_RATE = 22050

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".webm", ".mov", ".flv", ".wmv", ".m4v"}


@contextmanager
def _gc_hibrido(deshabilitar: bool = True, colectar_salida: bool = False):
    """Context manager que desactiva el GC durante tramos críticos de memoria.

    Evita interrupciones del recolector durante análisis intensivo, permitiendo
    que Python maneje la liberación de forma natural. Solo colecta al salir si
    es necesario.
    """
    previo = gc.isenabled()
    if deshabilitar and previo:
        gc.disable()
    try:
        yield
    finally:
        if deshabilitar and previo:
            gc.enable()
        if colectar_salida:
            gc.collect()


class AudioError(RuntimeError):
    pass


def es_video(ruta: str) -> bool:
    return os.path.splitext(ruta)[1].lower() in VIDEO_EXTENSIONS


def es_formato_soportado(ruta: str) -> bool:
    ext = os.path.splitext(ruta)[1].lower()
    return ext in AUDIO_EXTENSIONS or ext in VIDEO_EXTENSIONS


_RUTA_FFMPEG_CACHE: str | None = None

# Ubicaciones fijas donde buscar un ffmpeg instalado manualmente, sin tocar
# el PATH del sistema (editar el PATH en Windows falla a menudo: hace falta
# reiniciar la terminal, hay líos de usuario/sistema, permisos...). Si el
# usuario copia la carpeta que descarga de gyan.dev a C:\ffmpeg tal cual,
# el ejecutable cae en una de estas rutas y el programa lo encuentra solo.
_RUTAS_FFMPEG_MANUAL = [
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\ffmpeg\ffmpeg.exe",
    os.path.join(os.path.expanduser("~"), "ffmpeg", "bin", "ffmpeg.exe"),
]


def _ruta_ffmpeg() -> str:
    """Ruta absoluta al ejecutable de ffmpeg.

    `static_ffmpeg.add_paths()` solo añade la carpeta al PATH del proceso,
    y en algunos Windows (usuario sin permisos de escritura en el PATH del
    sistema, hilos secundarios, antivirus interceptando la descarga) ese
    PATH modificado no llega a `subprocess.run(["ffmpeg", ...])`, que
    entonces falla con WinError 2 aunque el binario ya esté descargado.
    Pedir la ruta absoluta directamente evita depender del PATH.

    Orden de búsqueda:
    1. Variable de entorno CLONE_HERO_FFMPEG (ruta directa al .exe).
    2. `ffmpeg` ya en el PATH del sistema.
    3. Ubicaciones fijas típicas (C:\\ffmpeg\\bin\\ffmpeg.exe...): evita
       pedirle al usuario que edite el PATH, un paso que falla mucho.
    4. Descarga automática vía static-ffmpeg; si falla, se lanza el error
       real en vez de esconderlo detrás de un "ffmpeg" que fallará igual.
    """
    global _RUTA_FFMPEG_CACHE
    if _RUTA_FFMPEG_CACHE:
        return _RUTA_FFMPEG_CACHE

    manual = os.environ.get("CLONE_HERO_FFMPEG")
    if manual and os.path.exists(manual):
        _RUTA_FFMPEG_CACHE = manual
        return manual

    encontrado = shutil.which("ffmpeg")
    if encontrado:
        _RUTA_FFMPEG_CACHE = encontrado
        return encontrado

    for candidata in _RUTAS_FFMPEG_MANUAL:
        if os.path.exists(candidata):
            _RUTA_FFMPEG_CACHE = candidata
            return candidata

    try:
        import static_ffmpeg.run
        ffmpeg_path, _ = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
    except Exception as e:
        raise AudioError(
            "No se encontró ffmpeg y no se pudo descargar automáticamente "
            f"({type(e).__name__}: {e}).\n"
            "Descarga ffmpeg de https://www.gyan.dev/ffmpeg/builds/ "
            "('ffmpeg-release-essentials.zip'), extráelo y renombra o mueve "
            r"la carpeta extraída para que quede como C:\ffmpeg (de modo que "
            r"exista C:\ffmpeg\bin\ffmpeg.exe). El programa lo detectará "
            "solo, sin tocar el PATH."
        )
    if not ffmpeg_path or not os.path.exists(ffmpeg_path):
        raise AudioError(
            f"static-ffmpeg indicó la ruta {ffmpeg_path!r} pero el archivo no "
            "existe. Borra la carpeta static_ffmpeg de "
            "%LOCALAPPDATA%\\...\\site-packages\\static_ffmpeg y vuelve a "
            "intentarlo para forzar una descarga limpia."
        )
    _RUTA_FFMPEG_CACHE = ffmpeg_path
    return ffmpeg_path


def verificar_ffmpeg() -> str:
    """Comprueba (y descarga si hace falta) ffmpeg antes de empezar.

    Se llama al principio de la conversión para fallar rápido con un
    mensaje claro, en vez de que el usuario espere el análisis completo
    (puede ser bastante largo) y se encuentre el error solo al final, al
    intentar escribir song.ogg.
    """
    return _ruta_ffmpeg()


def extraer_audio_de_video(ruta_video: str, destino: str) -> str:
    """Extrae la pista de audio de un vídeo a un WAV temporal con ffmpeg."""
    cmd = [
        _ruta_ffmpeg(), "-y", "-i", ruta_video,
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        destino,
    ]
    try:
        resultado = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as e:
        raise AudioError(f"No se pudo ejecutar ffmpeg: {e}")
    if resultado.returncode != 0:
        raise AudioError(
            f"ffmpeg no pudo extraer el audio del vídeo:\n{resultado.stderr[-500:]}"
        )
    return destino


def convertir_a_ogg(ruta_audio: str, destino: str) -> str:
    """Convierte el audio original a OGG (formato que usa Clone Hero)."""
    cmd = [
        _ruta_ffmpeg(), "-y", "-i", ruta_audio,
        "-vn", "-c:a", "libvorbis", "-q:a", "6",
        destino,
    ]
    try:
        resultado = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as e:
        raise AudioError(f"No se pudo ejecutar ffmpeg: {e}")
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
    # Estructura de la canción (Intro/Verso/Estribillo/Outro...)
    limites_secciones: np.ndarray = field(default_factory=lambda: np.array([]))
    extra: dict = field(default_factory=dict)


def _onsets_con_fuerza(y: np.ndarray, sr: int, delta: float = 0.035,
                       wait: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Detecta onsets y devuelve (tiempos, fuerza normalizada 0..1).

    Los valores por defecto de librosa (delta=0.07) son demasiado
    conservadores para instrumentos con pasajes rápidos (p.ej. rasgueado de
    guitarra): apenas detectan ~2 notas/s. Bajar delta y wait recupera notas
    reales que de otro modo se pierden; el filtrado por dificultad
    (sep_min/umbral en charting.py) ya se encarga de curar la densidad final.
    """
    envolvente = librosa.onset.onset_strength(y=y, sr=sr)
    frames = librosa.onset.onset_detect(
        onset_envelope=envolvente, sr=sr, backtrack=False, units="frames",
        delta=delta, wait=wait,
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
    croma = librosa.feature.chroma_stft(y=y, sr=sr)
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
    """Tono (0-11) del pico espectral dominante (piptrack) en cada onset.

    Sigue la frecuencia dominante en vez de sumar energía de todas las
    notas presentes, lo que reduce el arrastre de armónicos de voz u
    otros instrumentos. piptrack calcula un solo STFT, así que es dos
    órdenes de magnitud más rápido que un rastreador tipo pyin con
    resultados comparables para asignar carriles. Si el frame no tiene
    pico fiable, recurre al croma de banda ancha como respaldo.
    """
    if len(tiempos) == 0:
        return np.array([], dtype=int)

    pitches, mags = librosa.piptrack(y=y, sr=sr, fmin=fmin, fmax=fmax)
    croma_respaldo = _croma_en_onsets(y, sr, tiempos)

    frames = np.clip(librosa.time_to_frames(tiempos, sr=sr),
                     0, pitches.shape[1] - 1)
    tonos = []
    for i, f in enumerate(frames):
        fin = min(f + 3, mags.shape[1])
        ventana_mag = mags[:, f:fin]
        if ventana_mag.size and ventana_mag.max() > 0:
            idx = np.unravel_index(np.argmax(ventana_mag), ventana_mag.shape)
            hz = pitches[:, f:fin][idx]
            if hz > 0:
                tonos.append(int(round(librosa.hz_to_midi(hz))) % 12)
                continue
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


def _detectar_secciones(y: np.ndarray, sr: int, duracion: float) -> np.ndarray:
    """Detecta límites de sección (tiempos, s) mediante segmentación
    estructural (auto-similitud de timbre + armonía), la misma técnica que
    usan las herramientas de análisis de estructura musical.

    No sabe distinguir semánticamente "estribillo" de "verso" (eso exigiría
    letra o metadatos), pero sí encuentra los puntos donde el carácter de la
    canción cambia de forma clara, que es justo donde un charter humano
    coloca los marcadores de sección.
    """
    # Una sección por cada ~35s de canción, con un mínimo de 3 (intro/
    # cuerpo/outro) y un máximo razonable para no saturar de eventos.
    n_secciones = int(np.clip(round(duracion / 35), 3, 10))
    try:
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        n = min(mfcc.shape[1], chroma.shape[1])
        rasgos = np.vstack([mfcc[:, :n], chroma[:, :n]])
        limites_frames = librosa.segment.agglomerative(rasgos, n_secciones)
        limites = librosa.frames_to_time(limites_frames, sr=sr)
        limites = np.unique(np.concatenate([[0.0], limites, [duracion]]))
        return limites
    except Exception:
        return np.array([0.0, duracion])


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


def _analizar_con_sr(ruta_audio: str, sr_objetivo: int,
                     logger: callable) -> AnalisisCancion:
    """Análisis completo optimizado con liberación selectiva de memoria.

    Mantiene referencias explícitas a variables grandes para que el garbage
    collector las libere cuando salgan del scope. No fuerza recolección
    de basura aquí; eso es un anti-patrón en Python.
    """
    logger("🎧 Cargando audio...")
    y, sr = librosa.load(ruta_audio, sr=sr_objetivo, mono=True)
    duracion = float(len(y) / sr)
    if duracion < 5:
        raise AudioError("El audio es demasiado corto (mínimo 5 segundos).")

    logger("🥁 Detectando tempo y beats...")
    tempo, frames_beat = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])
    if bpm < 40:
        bpm *= 2
    if bpm > 250:
        bpm /= 2
    tiempos_beat = librosa.frames_to_time(frames_beat, sr=sr)

    logger("🗺️ Detectando estructura de la canción...")
    limites_secciones = _detectar_secciones(y, sr, duracion)

    logger("🎸 Separando componentes armónico y percusivo...")
    y_harm, y_perc = librosa.effects.hpss(y, margin=(1.0, 5.0))
    del y

    logger("🎼 Detectando notas de melodía (guitarra/teclado)...")
    y_guitarra = _filtrar_banda(y_harm, sr, f_min=80.0, f_max=1300.0)
    onsets_mel, fuerza_mel = _onsets_con_fuerza(y_guitarra, sr)
    tono_mel = _pitch_en_onsets(y_guitarra, sr, onsets_mel)
    del y_guitarra

    logger("🎻 Detectando línea de bajo...")
    y_bajo = _filtrar_banda(y_harm, sr, f_max=300.0)
    del y_harm
    onsets_bajo, fuerza_bajo = _onsets_con_fuerza(y_bajo, sr)
    tono_bajo = _pitch_en_onsets(y_bajo, sr, onsets_bajo, fmin=41.0, fmax=300.0)
    del y_bajo

    logger("🥁 Detectando golpes de batería...")
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
        limites_secciones=limites_secciones,
    )


def analizar(ruta: str, logger: callable = print) -> AnalisisCancion:
    """Analiza un archivo delegando los mensajes al logger provisto."""
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
        logger("🎬 Es un vídeo: extrayendo la pista de audio con ffmpeg...")
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        ruta_audio = extraer_audio_de_video(ruta, tmp.name)

    try:
        try:
            dur_estimada = float(librosa.get_duration(path=ruta_audio))
        except Exception:
            dur_estimada = 0.0

        sr_inicial = SAMPLE_RATE if dur_estimada <= 900 else SAMPLE_RATE // 2
        candidatos = [c for c in (sr_inicial, sr_inicial // 2, sr_inicial // 4)
                      if c >= 5512]

        for i, sr_objetivo in enumerate(candidatos):
            try:
                with _gc_hibrido(deshabilitar=True, colectar_salida=False):
                    return _analizar_con_sr(ruta_audio, sr_objetivo, logger)
            except MemoryError:
                gc.collect()
                if i == len(candidatos) - 1:
                    break
                logger("⚠ Poca memoria: reintentando con calidad reducida...")
        raise AudioError(
            "No hay memoria suficiente para analizar esta canción. "
            "Cierra otros programas (navegador, juegos...) y vuelve a "
            "intentarlo, o usa un archivo más corto."
        )
    finally:
        if tmp is not None and os.path.exists(tmp.name):
            os.unlink(tmp.name)
