from pathlib import Path
import argparse
import shutil
import logging
from logging.handlers import RotatingFileHandler

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "canciones"
OUTPUT_DIR = BASE_DIR / "salida"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "convertidor.log"

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

def convertir_archivo(origen: Path, destino: Path, logger: logging.Logger) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origen, destino)
    logger.debug(f"Copiado: {origen} -> {destino}")

def procesar_canciones(entrada: Path, salida: Path, logger: logging.Logger, limpiar: bool = False) -> int:
    if not entrada.exists():
        raise FileNotFoundError(f"No existe la carpeta de entrada: {entrada}")

    if limpiar and salida.exists():
        shutil.rmtree(salida)
        logger.info(f"Salida eliminada: {salida}")

    salida.mkdir(parents=True, exist_ok=True)

    total = 0
    errores = 0

    for archivo in entrada.rglob("*"):
        if archivo.is_file():
            relativo = archivo.relative_to(entrada)
            destino = salida / relativo
            try:
                convertir_archivo(archivo, destino, logger)
                total += 1
            except Exception:
                errores += 1
                logger.exception(f"Error al procesar: {archivo}")

    logger.info(f"Procesados: {total} | Errores: {errores}")
    return total

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copia archivos desde canciones/ a salida/ con logs."
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
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("Inicio del proceso")

    try:
        procesar_canciones(args.input, args.output, logger, args.clean)
        logger.info("Proceso finalizado correctamente")
        return 0
    except Exception:
        logger.exception("Fallo general del proceso")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
