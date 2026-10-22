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

## Sonic Youth - Pink Steam (charter: Debugmod12)

Rock alternativo/noise rock (Rather Ripped, 2006), 7 min, solo dificultad
Expert cargada en el chart.

- **SyncTrack**: 200 eventos en 418.9s, ~1 cada 2.1s — mismo orden de
  magnitud que la referencia de Björk, otra confirmación independiente de
  que la densidad de nuestro `sync_track()` fusionado va bien encaminada.
- **Densidad**: 1221 notas en Expert ≈ 2.9 notas/seg.
- **HOPO forzado (`N 5`) real: 105 notas (~8.6%)** — a diferencia de
  Björk, aquí sí se usa, en una proporción moderada.
- **Strum/tap forzado (`N 6`): CERO notas**, igual que en Björk.

**Por qué importa el cruce de datos:** dos referencias reales e
independientes, de estilos distintos (pad electrónico vs. rock ruidoso),
coinciden en **0% de uso de `N 6`**. Eso ya no es un rasgo de un estilo
concreto, es una señal de que el uso que hace `FUERZA_STRUM_FORZADO` /
`forzado = 6` en `charting.py` de la nota tipo 6 puede estar mal
planteado: por especificación del formato `.chart`, el tipo 6 no es
"forzar strum" — es **marcar la nota como Tap Note** (se puede tocar sin
rasgueo), un mecanismo distinto del que el código asume. Esto ya se había
sospechado antes en esta conversación sin confirmarlo con datos reales;
ahora hay dos referencias independientes que lo corroboran. Pendiente de
revisar `FUERZA_STRUM_FORZADO` en `charting.py` (línea ~66) y decidir si
ese caso debería usar otro mecanismo (o ninguno) en vez de `N 6`, **no
tocado todavía** — requiere que el usuario confirme que quiere ese cambio,
ya que afecta a cómo se sienten todas las canciones ya generadas.

