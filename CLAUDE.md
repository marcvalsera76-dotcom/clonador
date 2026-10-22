# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python tool that converts an MP3/WAV or video file into a playable Clone
Hero song: it analyzes the audio (tempo, beats, note onsets, pitch, drum
hits) with librosa and generates `notes.chart` + `song.ini` + `song.ogg`
across four difficulties (Easy/Medium/Hard/Expert). Has both a Tkinter GUI
(default) and a terminal/scriptable CLI. See `README.md` for end-user usage.

## Commands

```bash
pip install -r requirements.txt   # pygame is only needed for guitar-controller calibration
pip install pytest                # not in requirements.txt, needed to run tests

python -m pytest tests/                                   # all tests
python -m pytest tests/test_converter.py::test_ticks -v   # a single test

python -m clone_hero_converter song.mp3                   # GUI (default)
python -m clone_hero_converter song.mp3 --terminal --si   # terminal, no prompts
python -m clone_hero_converter.calibrar                   # latency calibration tool

python build_exe.py   # builds dist/CloneHeroConverter.exe via PyInstaller (see BUILD_EXE.md)
```

There is no linter configured. Bump `__version__` in
`clone_hero_converter/__init__.py` with every user-facing change — users of
this tool check it (e.g. via `ComprobarVersion.bat`) to confirm which build
they're running.

## Architecture

Conversion is a straight pipeline, one module per stage:

```
audio.py (analizar) -> charting.py (generar_instrumento, MapaTempo) -> chartfile.py (generar_chart/generar_song_ini) -> cli.py (convertir, orchestrates + writes files)
```

- **`audio.py`** — `analizar()` loads the file (extracting audio from video
  via ffmpeg if needed), runs librosa beat/onset detection, splits
  harmonic/percussive components, and returns an `AnalisisCancion` with
  onsets+strength+pitch per source (melody, bass, drums) plus detected beat
  times and section boundaries. `_onsets_con_fuerza()` normalizes onset
  strength to `[0, 1]` — this clipping matters, see gotchas below.
- **`charting.py`** — turns analysis into playable `Nota` objects.
  - `MapaTempo` maps real time -> tick using **variable tempo** (one BPM
    segment per detected beat, not a single fixed BPM for the whole song) so
    notes stay in sync even when the recording's tempo drifts slightly, as
    any non-click-tracked performance does.
  - `PARAMETROS[dificultad]` controls density/chords/lane-count per
    difficulty; tuned empirically against real songs (see gotchas).
  - `generar_pista_melodica`/`generar_pista_bateria` turn onsets into notes,
    deciding chords, forced HOPO/strum, sustains, lane assignment.
  - `generar_star_power` places a handful of energy phrases over the
    densest/most eventful passages.
- **`chartfile.py`** — pure text formatting: turns `Nota` lists + tempo map
  + section/Star Power data into the literal `.chart`/`.ini` file contents.
- **`cli.py`** — `convertir()` is the single entry point both the GUI and
  the terminal mode call; it runs the whole pipeline, prints progress, and
  writes the output folder. `main()` is the argparse CLI; it opens the GUI
  by default unless `--terminal` or `--si` is passed.
- **`gui.py`** — Tkinter window; calls `cli.convertir()` in a background
  thread and streams its `print()` output into the window's log widget via
  `_print_a_ventana`. Also auto-detects the user's Clone Hero `Songs/`
  folder (including portable "Standalone" installs anywhere under
  Desktop/Downloads, not just the usual fixed install paths) and copies the
  converted song there.
- **`config.py`** — tiny shared JSON config at `~/.clone_hero_converter.json`
  (Songs folder path, calibrated offset). Used by `gui.py`, `cli.py` and
  `calibrar.py`; kept dependency-free (no tkinter) so `cli.py`/`calibrar.py`
  can import it without pulling in GUI deps.
- **`calibrar.py`** — standalone latency calibration: plays click rounds via
  a synthesized WAV (`winsound.PlaySound`, not `winsound.Beep` — see
  gotchas) and times the player's response, via a detected game
  controller/guitar (`pygame`) if present, else the keyboard. Saves a
  median offset to the shared config; `cli.py` applies it automatically as
  the chart's `Offset` on future conversions unless one is passed
  explicitly.

## Important invariants

These came from real bugs that stopped Clone Hero from listing or loading
converted songs — easy to reintroduce if touched carelessly:

- **Tick positions must never go negative.** `MapaTempo.a_ticks()` clamps
  to 0. A note/event timestamped before the first detected beat
  extrapolates backwards into a negative tick, and Clone Hero silently
  discards the whole song on scan if it finds one in `notes.chart`. Onsets
  before the first beat are filtered out entirely in
  `_excluir_antes_del_primer_beat` rather than clamped to 0, to avoid
  piling up dozens of notes on the same tick.
- **`[SyncTrack]` must not emit one `B` (tempo) event per beat.** Raw
  per-beat BPM is noisy — it can swing by tens of BPM beat-to-beat from
  detector jitter even when the real tempo is stable — so `sync_track()`
  median-smooths before deciding whether the tempo actually changed
  (`TOLERANCIA_BPM`). An unsmoothed one-event-per-beat sync track was a
  likely cause of Clone Hero hanging on load for longer songs.
- **Chroma (pitch class 0-11) is circular**, not a line: `_asignar_carriles`
  has to unwrap it at its largest actual gap before mapping pitch to lane,
  or a melody that straddles the 11->0 boundary gets its lanes bunched up
  for no musical reason.
- **`PARAMETROS[...]["acordes"]` compares against onset strength clipped to
  `[0, 1]`.** A threshold above 1.0 makes that difficulty mathematically
  incapable of ever producing a chord — this happened to Hard/Medium/Easy
  at one point.
- Within one difficulty's note list, chart-file events (notes + forced
  HOPO/strum + Star Power `S` events) must stay in ascending tick order in
  the written file, or Clone Hero can reject the section.
- `requirements.txt` isn't synced with `setup.py`'s version pin — keep both
  updated together when adding a dependency.

## Working across sessions

Other Claude sessions may be working on this same branch concurrently.
`git push` getting rejected with diverged branches is expected, not an
error to work around some other way — `git pull --no-rebase origin
<branch>`, resolve conflicts (favor combining both sides' fixes rather than
picking one over the other when they touch the same function), rerun
tests, and push again. The remote also reports it "moved" to
`marcvalsera76-dotcom/clonador` on push; that's informational, pushes to
the configured `origin` still succeed.

The repository root has a few unrelated files (`index.html`,
`28133920729.htm`) from stray uploads — not part of this project, ignore
them.
