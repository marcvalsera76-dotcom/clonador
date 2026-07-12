from pathlib import Path
import argparse
import shutil
import subprocess
import logging
from logging.handlers import RotatingFileHandler

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "canciones"
OUTPUT_DIR = BASE_DIR / "salida"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "convertidor.log"

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wma"}

CODECS_FFMPEG = {
    "ogg": ["-c:a", "libvorbis", "-q:a", "6"],
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
}

def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("convertidor")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

def convertir_audio_ffmpeg(origen: Path, destino: Path, formato: str, logger: logging.Logger) -> None:
    cmd = ["ffmpeg", "-y", "-i", str(origen), "-vn", *CODECS_FFMPEG.get(formato.lower(), []), str(destino)]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg falló con código {resultado.returncode}: {resultado.stderr[-500:]}")
    logger.debug(f"Convertido: {origen} -> {destino}")

def convertir_archivo(origen: Path, destino: Path, logger: logging.Logger) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if origen.suffix.lower() != destino.suffix.lower():
        convertir_audio_ffmpeg(origen, destino, destino.suffix.lstrip("."), logger)
    else:
        shutil.copy2(origen, destino)
        logger.debug(f"Copiado: {origen} -> {destino}")

def procesar_canciones(
    entrada: Path,
    salida: Path,
    logger: logging.Logger,
    limpiar: bool = False,
    solo_audio: bool = False,
    convertir_audio: bool = False,
    formato: str = "ogg",
) -> int:
    if not entrada.exists():
        raise FileNotFoundError(f"No existe la carpeta de entrada: {entrada}")

    if limpiar and salida.exists():
        shutil.rmtree(salida)
        logger.info(f"Salida eliminada: {salida}")

    salida.mkdir(parents=True, exist_ok=True)

    total = 0
    omitidos = 0
    errores = 0

    for archivo in entrada.rglob("*"):
        if not archivo.is_file():
            continue

        es_audio = archivo.suffix.lower() in AUDIO_EXTENSIONS
        if solo_audio and not es_audio:
            omitidos += 1
            logger.debug(f"Omitido (no es audio): {archivo}")
            continue

        relativo = archivo.relative_to(entrada)
        if convertir_audio and es_audio:
            relativo = relativo.with_suffix(f".{formato}")
        destino = salida / relativo

        try:
            convertir_archivo(archivo, destino, logger)
            total += 1
        except Exception:
            errores += 1
            logger.exception(f"Error al procesar: {archivo}")

    logger.info(f"Procesados: {total} | Omitidos: {omitidos} | Errores: {errores}")
    return total

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copia (y opcionalmente convierte) archivos desde canciones/ a salida/ con logs."
    )
    parser.add_argument(
        "-i", "--input",
        type=Path,
        default=SOURCE_DIR,
        help="Carpeta de entrada"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=OUTPUT_DIR,
        help="Carpeta de salida"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Borra la salida antes de copiar"
    )
    parser.add_argument(
        "--solo-audio",
        action="store_true",
        help=f"Omite archivos que no sean audio ({', '.join(sorted(AUDIO_EXTENSIONS))})"
    )
    parser.add_argument(
        "--convertir-audio",
        action="store_true",
        help="Convierte los archivos de audio al formato de --formato usando ffmpeg (requiere ffmpeg instalado)"
    )
    parser.add_argument(
        "--formato",
        default="ogg",
        help="Formato de audio de destino cuando se usa --convertir-audio (por defecto: ogg)"
    )
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("Inicio del proceso")

    if args.convertir_audio and shutil.which("ffmpeg") is None:
        logger.error("Se pidió --convertir-audio pero no se encontró ffmpeg instalado en el sistema")
        return 1

    try:
        procesar_canciones(
            args.input, args.output, logger, args.clean,
            args.solo_audio, args.convertir_audio, args.formato,
        )
        logger.info("Proceso finalizado correctamente")
        return 0
    except Exception:
        logger.exception("Fallo general del proceso")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
