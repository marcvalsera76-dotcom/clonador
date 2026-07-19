# Compilar Clone Hero Converter a .exe

## En tu portátil Windows:

### PASO 1: Instalar dependencias
```bash
pip install -r requirements.txt
pip install pyinstaller
```

### PASO 2: Compilar
```bash
python build_exe.py
```

Espera 2-3 minutos. Verás un progreso de compilación.

### PASO 3: ¡Listo!
El `.exe` estará en: `dist/CloneHeroConverter.exe`

### PASO 4: Usar
- **Opción A:** Doble clic en `CloneHeroConverter.exe` 
- **Opción B:** Copia el `.exe` a donde quieras (Escritorio, etc.)

## ¿Qué hace `build_exe.py`?

1. Empaqueta todo el código Python
2. Incluye todas las librerías necesarias (librosa, numpy, ffmpeg, etc.)
3. Genera un `.exe` independiente
4. No necesitas Python instalado para ejecutarlo

## El .exe resultante:
- **Tamaño:** ~150-200 MB (contiene todo incluido)
- **Velocidad:** Primera ejecución es lenta (~5s), luego es normal
- **Compatibilidad:** Windows 10/11

## Si falla la compilación:

1. Asegúrate de tener Python >=3.9
2. Verifica que todas las dependencias se instalaron:
   ```bash
   pip list | findstr librosa numpy soundfile
   ```
3. Ejecuta en `cmd` como Administrador
4. Si aún falla, comparte el error

---

¿Preguntas? Necesitas cualquier cosa, avísame.
