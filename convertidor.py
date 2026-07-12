from pathlib import Path
import argparse
import shutil
import logging

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "canciones"
OUTPUT_DIR = BASE_DIR / "salida"
LOG_FILE = BASE_DIR / "convertidor.log"

def setup_logging() -> logging.Logger:
    logger = logging.getLogger("convertidor")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
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
        logger.info(f"Salida limpiada: {salida}")

    salida.mkdir(parents=True, exist_ok=True)

    total = 0
    for archivo in entrada.rglob("*"):
        if archivo.is_file():
            relativo = archivo.relative_to(entrada)
            destino = salida / relativo
            try:
                convertir_archivo(archivo, destino, logger)
                total += 1
            except Exception:
                logger.exception(f"Error al procesar {archivo}")

    return total

def main() -> int:
    parser = argparse.ArgumentParser(description="Convierte y copia archivos desde canciones/ a salida/")
    parser.add_argument("-i", "--input", type=Path, default=SOURCE_DIR)
    parser.add_argument("-o", "--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    logger = setup_logging()

    try:
        total = procesar_canciones(args.input, args.output, logger, args.clean)
        logger.info(f"Proceso terminado: {total} archivo(s)")
        return 0
    except Exception:
        logger.exception("Fallo general del proceso")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
