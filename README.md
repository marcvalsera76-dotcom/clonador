# 🎮 Clone Hero Converter

Convierte canciones en **MP3** (o vídeos **MP4/MKV/AVI/WEBM**) en canciones
**jugables para Clone Hero**. La app analiza el audio automáticamente
(tempo, beats, ataques de notas, tonos y golpes de batería) y genera las
notas con **cuatro niveles de dificultad** (Easy, Medium, Hard, Expert).
Al ejecutarla te pregunta **qué instrumentos quieres que sean jugables**:
guitarra, bajo, batería y/o teclado.

## Requisitos

- Python 3.10 o superior
- [ffmpeg](https://ffmpeg.org/) instalado en el sistema (para vídeos y para
  convertir el audio a OGG)

```bash
pip install -r requirements.txt
```

## Uso

### Modo interactivo (recomendado)

```bash
python -m clone_hero_converter "Mi Artista - Mi Cancion.mp3"
```

La app te irá preguntando:

1. 📀 **Título** y 🎤 **artista** (propone los del nombre del archivo)
2. 🎸 **Instrumentos** que quieres tocar: guitarra, bajo, batería, teclado
3. ⭐ **Dificultades** a generar: Easy, Medium, Hard, Expert

### Modo automático (sin preguntas)

```bash
python -m clone_hero_converter cancion.mp3 --si
```

### Opciones

| Opción | Descripción |
|---|---|
| `--titulo` / `--artista` / `--album` | Metadatos de la canción |
| `--instrumentos guitar,bass,drums,keys` | Instrumentos a generar |
| `--dificultades Easy,Medium,Hard,Expert` | Dificultades a generar |
| `--salida CARPETA` | Carpeta de salida (por defecto `canciones/`) |
| `--si` / `-y` | Aceptar todos los valores por defecto sin preguntar |

### Ejemplo con vídeo

```bash
python -m clone_hero_converter concierto.mp4 --instrumentos guitar,drums --si
```

## Resultado

Se crea una carpeta lista para el juego:

```
canciones/
└── Mi Artista - Mi Cancion/
    ├── notes.chart   ← las notas de todos los instrumentos y dificultades
    ├── song.ogg      ← el audio convertido
    └── song.ini      ← metadatos para Clone Hero
```

**Cópiala dentro de la carpeta `Songs` de tu instalación de Clone Hero** y
actualiza la lista de canciones desde el menú del juego.

## Cómo funciona

1. Si el archivo es un vídeo, se extrae la pista de audio con ffmpeg.
2. Con [librosa](https://librosa.org/) se detectan el **tempo**, los
   **beats** y los **onsets** (ataques de nota).
3. El audio se separa en componente **armónico** (melodía y bajo) y
   **percusivo** (batería):
   - **Guitarra/teclado**: onsets del componente armónico; el tono
     dominante (croma) decide el carril (verde→naranja, de grave a agudo).
   - **Bajo**: igual pero sobre la banda grave (< 250 Hz).
   - **Batería**: los golpes se clasifican por banda de frecuencia en
     bombo (graves), caja (medios) y charles/platos (agudos).
4. Cada dificultad aplica una **reducción** distinta: menos notas por
   segundo, menos carriles, sin acordes en las fáciles y notas largas
   (sustains) donde hay huecos.

## Limitaciones

Es una transcripción automática: no será tan precisa como un chart hecho a
mano, pero genera canciones jugables al momento a partir de cualquier
audio. Los mejores resultados se obtienen con canciones de ritmo claro.
