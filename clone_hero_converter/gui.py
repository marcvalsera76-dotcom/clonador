"""Interfaz gráfica del conversor (sin terminal).

Se abre con:
    python -m clone_hero_converter          (sin argumentos)
o haciendo doble clic en AbrirConverter.bat.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .chartfile import NOMBRE_INSTRUMENTO

RUTA_CONFIG = os.path.join(os.path.expanduser("~"), ".clone_hero_converter.json")

INSTRUMENTOS = ["guitar", "bass", "keys", "drums"]
MARCADOS_POR_DEFECTO = {"guitar", "bass", "keys"}
DIFICULTADES = ["Easy", "Medium", "Hard", "Expert"]


def cargar_config() -> dict:
    try:
        with open(RUTA_CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def guardar_config(config: dict) -> None:
    try:
        with open(RUTA_CONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError:
        pass


def detectar_carpeta_songs() -> str:
    """Busca la carpeta Songs de Clone Hero en las ubicaciones habituales."""
    inicio = os.path.expanduser("~")
    candidatas = []
    for docs in ("Documents", "Documentos", os.path.join("OneDrive", "Documents"),
                 os.path.join("OneDrive", "Documentos")):
        candidatas.append(os.path.join(inicio, docs, "Clone Hero", "Songs"))
    candidatas.append(os.path.join(inicio, "Clone Hero", "Songs"))
    for ruta in candidatas:
        if os.path.isdir(ruta):
            return ruta
    return ""


def _titulo_y_artista(ruta: str) -> tuple[str, str]:
    base = os.path.splitext(os.path.basename(ruta))[0]
    if " - " in base:
        artista, titulo = base.split(" - ", 1)
        return titulo.strip(), artista.strip()
    return base.strip(), ""


# Cola a la que _print_a_ventana envía los mensajes mientras dura una
# conversión. Es una función con nombre a nivel de módulo (nunca una lambda
# ni un método ligado a la ventana): así sigue siendo válida aunque alguna
# librería intente serializar builtins.print en Windows.
_COLA_ACTIVA: queue.Queue | None = None


def _print_a_ventana(*args, **kwargs):
    cola = _COLA_ACTIVA
    if cola is not None:
        cola.put(" ".join(str(x) for x in args))


class VentanaConverter(tk.Tk):
    def __init__(self, archivo_inicial: str | None = None):
        super().__init__()
        self.title(f"Clone Hero Converter v{__version__}")
        self.geometry("560x560")
        self.resizable(False, False)

        self.config_app = cargar_config()
        self.cola_mensajes: queue.Queue = queue.Queue()
        self.convirtiendo = False

        cuerpo = ttk.Frame(self, padding=12)
        cuerpo.pack(fill="both", expand=True)

        # --- Canción ---
        ttk.Label(cuerpo, text="1. Canción (MP3 o vídeo):",
                  font=("", 10, "bold")).pack(anchor="w")
        fila_archivo = ttk.Frame(cuerpo)
        fila_archivo.pack(fill="x", pady=(2, 8))
        self.var_archivo = tk.StringVar(value=archivo_inicial or "")
        ttk.Entry(fila_archivo, textvariable=self.var_archivo).pack(
            side="left", fill="x", expand=True)
        ttk.Button(fila_archivo, text="Elegir...",
                   command=self.elegir_archivo).pack(side="left", padx=(6, 0))

        # --- Título y artista ---
        fila_meta = ttk.Frame(cuerpo)
        fila_meta.pack(fill="x", pady=(0, 8))
        ttk.Label(fila_meta, text="Título:").grid(row=0, column=0, sticky="w")
        self.var_titulo = tk.StringVar()
        ttk.Entry(fila_meta, textvariable=self.var_titulo, width=28).grid(
            row=0, column=1, sticky="we", padx=(4, 12))
        ttk.Label(fila_meta, text="Artista:").grid(row=0, column=2, sticky="w")
        self.var_artista = tk.StringVar()
        ttk.Entry(fila_meta, textvariable=self.var_artista, width=20).grid(
            row=0, column=3, sticky="we", padx=(4, 0))
        fila_meta.columnconfigure(1, weight=1)
        fila_meta.columnconfigure(3, weight=1)

        # --- Instrumentos ---
        ttk.Label(cuerpo, text="2. Instrumentos:",
                  font=("", 10, "bold")).pack(anchor="w")
        fila_inst = ttk.Frame(cuerpo)
        fila_inst.pack(fill="x", pady=(2, 8))
        self.vars_instrumentos: dict[str, tk.BooleanVar] = {}
        for i, inst in enumerate(INSTRUMENTOS):
            var = tk.BooleanVar(value=inst in MARCADOS_POR_DEFECTO)
            self.vars_instrumentos[inst] = var
            ttk.Checkbutton(fila_inst, text=NOMBRE_INSTRUMENTO[inst],
                            variable=var).grid(row=0, column=i, padx=(0, 14))

        # --- Dificultades ---
        ttk.Label(cuerpo, text="3. Dificultades:",
                  font=("", 10, "bold")).pack(anchor="w")
        fila_dif = ttk.Frame(cuerpo)
        fila_dif.pack(fill="x", pady=(2, 8))
        self.vars_dificultades: dict[str, tk.BooleanVar] = {}
        for i, dif in enumerate(DIFICULTADES):
            var = tk.BooleanVar(value=True)
            self.vars_dificultades[dif] = var
            ttk.Checkbutton(fila_dif, text=dif, variable=var).grid(
                row=0, column=i, padx=(0, 14))

        # --- Carpeta Songs de Clone Hero ---
        ttk.Label(cuerpo, text="4. Carpeta «Songs» de Clone Hero "
                              "(se copia ahí automáticamente):",
                  font=("", 10, "bold")).pack(anchor="w")
        fila_songs = ttk.Frame(cuerpo)
        fila_songs.pack(fill="x", pady=(2, 10))
        songs_inicial = self.config_app.get("carpeta_songs") or detectar_carpeta_songs()
        self.var_songs = tk.StringVar(value=songs_inicial)
        ttk.Entry(fila_songs, textvariable=self.var_songs).pack(
            side="left", fill="x", expand=True)
        ttk.Button(fila_songs, text="Buscar...",
                   command=self.elegir_songs).pack(side="left", padx=(6, 0))

        # --- Botón convertir ---
        self.boton = ttk.Button(cuerpo, text="🎸 CONVERTIR",
                                command=self.iniciar_conversion)
        self.boton.pack(fill="x", ipady=6, pady=(2, 8))

        # --- Registro de progreso ---
        self.registro = tk.Text(cuerpo, height=11, state="disabled",
                                font=("Consolas", 9))
        self.registro.pack(fill="both", expand=True)

        if archivo_inicial:
            self.rellenar_meta(archivo_inicial)

        self.after(150, self.procesar_cola)

    # ------------------------------------------------------------------
    def elegir_archivo(self):
        ruta = filedialog.askopenfilename(
            title="Elige una canción o vídeo",
            filetypes=[("Audio y vídeo",
                        "*.mp3 *.wav *.ogg *.flac *.m4a *.mp4 *.mkv *.avi *.webm *.mov"),
                       ("Todos los archivos", "*.*")])
        if ruta:
            self.var_archivo.set(ruta)
            self.rellenar_meta(ruta)

    def rellenar_meta(self, ruta: str):
        titulo, artista = _titulo_y_artista(ruta)
        if not self.var_titulo.get():
            self.var_titulo.set(titulo)
        if not self.var_artista.get() and artista:
            self.var_artista.set(artista)

    def elegir_songs(self):
        ruta = filedialog.askdirectory(title="Carpeta Songs de Clone Hero")
        if ruta:
            self.var_songs.set(ruta)

    def escribir(self, texto: str):
        self.cola_mensajes.put(texto)

    def _resetear_boton(self):
        self.boton.configure(state="normal", text="🎸 CONVERTIR")

    def procesar_cola(self):
        try:
            while True:
                texto = self.cola_mensajes.get_nowait()
                self.registro.configure(state="normal")
                self.registro.insert("end", texto + "\n")
                self.registro.see("end")
                self.registro.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(150, self.procesar_cola)

    # ------------------------------------------------------------------
    def iniciar_conversion(self):
        if self.convirtiendo:
            return
        archivo = self.var_archivo.get().strip()
        if not archivo or not os.path.exists(archivo):
            messagebox.showerror("Falta la canción",
                                 "Elige primero un archivo de audio o vídeo válido.")
            return
        instrumentos = [i for i, v in self.vars_instrumentos.items() if v.get()]
        if not instrumentos:
            messagebox.showerror("Faltan instrumentos",
                                 "Marca al menos un instrumento.")
            return
        dificultades = [d for d, v in self.vars_dificultades.items() if v.get()]
        if not dificultades:
            messagebox.showerror("Faltan dificultades",
                                 "Marca al menos una dificultad.")
            return

        self.config_app["carpeta_songs"] = self.var_songs.get().strip()
        guardar_config(self.config_app)

        self.convirtiendo = True
        self.boton.configure(state="disabled", text="Convirtiendo...")
        hilo = threading.Thread(target=self.convertir_en_hilo,
                                args=(archivo, instrumentos, dificultades),
                                daemon=True)
        hilo.start()

    def convertir_en_hilo(self, archivo: str, instrumentos: list[str],
                          dificultades: list[str]):
        global _COLA_ACTIVA
        import builtins
        from .cli import convertir

        print_original = builtins.print
        _COLA_ACTIVA = self.cola_mensajes
        builtins.print = _print_a_ventana
        try:
            titulo = self.var_titulo.get().strip() or "Cancion"
            artista = self.var_artista.get().strip() or "Desconocido"
            salida = os.path.join(os.path.dirname(os.path.abspath(archivo)),
                                  "canciones_clone_hero")
            carpeta = convertir(archivo, titulo, artista, "",
                                instrumentos, dificultades, salida)

            songs = self.var_songs.get().strip()
            if songs and os.path.isdir(songs):
                destino = os.path.join(songs, os.path.basename(carpeta))
                if os.path.abspath(destino) != os.path.abspath(carpeta):
                    if os.path.isdir(destino):
                        shutil.rmtree(destino)
                    shutil.copytree(carpeta, destino)
                self.escribir(f"📂 Copiada a Clone Hero: {destino}")
                self.escribir("✅ ¡Lista! Abre Clone Hero (o dale a Scan Songs) y a tocar 🎸")
            else:
                self.escribir(f"📂 Guardada en: {carpeta}")
                self.escribir("⚠ No se copió a Clone Hero (carpeta Songs no configurada).")
        except Exception as e:  # mostrar el error en la ventana, no en consola
            self.escribir(f"❌ Error: {e}")
        finally:
            builtins.print = print_original
            _COLA_ACTIVA = None
            self.convirtiendo = False
            self.boton.after(0, self._resetear_boton)


def main(archivo: str | None = None) -> int:
    ventana = VentanaConverter(archivo)
    ventana.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
