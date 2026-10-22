# Referencias reales de charts hechos a mano

Charts reales descargados/compartidos por el usuario, para comparar contra
lo que genera `clone_hero_converter` y calibrar parámetros (densidad,
HOPO/strum forzado, SyncTrack, etc.). Cada subcarpeta es un chart completo
(`notes.chart` + `song.ini` + audio) tal como se usaría en Clone Hero.

## Björk - Human Behavior (charter: TheSheepQueen)

Pop electrónico (Debut, 1993). Pista `guitar.ogg` — en esta canción es más
un sintetizador/pad sostenido que una guitarra tocada, y el chart lo
refleja:

- **SyncTrack**: 107 eventos de tempo en 4:30 (resolución 480 ticks/negra),
  ~1 cada 2.5s — confirma que nuestro `sync_track()` ya fusionado (ver
  `charting.py`) está en el orden de magnitud correcto, no la densidad de
  un evento por beat.
- **Sin HOPO ni strum forzados en absoluto** (ningún `N 5`/`N 6` en
  `ExpertSingle`/`HardSingle`/etc.): el charter deja que el estado natural
  HOPO/strum del juego decida siempre, sin forzar nada. Contrasta con
  nuestro generador, que marca HOPO/strum forzado en una fracción
  significativa de las notas en casi todas las canciones probadas — para
  este estilo de canción (pads sostenidos) forzar poco o nada encaja mejor;
  no está claro que generalice igual a riffs de guitarra percutidos.
- **Casi todas las notas son acordes de 2 carriles con sustain** (nunca
  notas sueltas de longitud 0 en el fragmento revisado): refleja que la
  fuente es un pad sintético sostenido, no un patrón atribuible a "así
  deben ser los charts" en general.
- **Hard casi tan denso como Expert** (420 vs 456 notas, ~8% menos): para
  una canción poco exigente técnicamente, la diferenciación entre
  dificultades puede ser mínima sin que eso sea un defecto del chart.

**Conclusión al guardarla (2026):** útil como dato real, pero es un estilo
de canción atípico (pad electrónico, no guitarra rítmica/riff percutido)
comparado con las canciones de rock con las que se ha calibrado
`PARAMETROS`/`FUERZA_STRUM_FORZADO` hasta ahora. Antes de usarla para
tocar esos parámetros, convendría contrastarla con más referencias del
mismo estilo (electrónica/pop con pads) o tratarla como caso aparte en vez
de generalizar sus proporciones a todo el conversor.
