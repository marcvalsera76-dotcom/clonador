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
ahora hay dos referencias independientes que lo corroboran.

**Actualización: corregido en v2.0.0.** Se confirmó además que la nota
tipo 5 es un TOGGLE del estado HOPO/strum natural, no un "activar HOPO":
el 93% de los `N 5` de esta referencia están en posiciones donde el
estado natural ya sería *strum* (mismo traste, o traste distinto pero
separado), y el charter las fuerza A HOPO — justo lo contrario de lo que
hacía nuestro generador. `generar_pista_melodica()` ya no usa la nota
tipo 6 en absoluto, y solo usa el toggle (tipo 5) para forzar *strum*
sobre una posición que saldría HOPO natural (ataque percusivo). Ver el
comentario sobre `HOPO_TICKS`/`FUERZA_STRUM_FORZADO` en `charting.py`.

## King Gizzard & The Lizard Wizard - Iron Lung (charter: oivalian)

Funk/jazz fusion/psicodelia (*Ice, Death, Planets, Lungs, Mushrooms and
Lava*, 2022), 9:06, las 4 dificultades cargadas.

- **SyncTrack**: 77 eventos en 546.5s, ~1 cada 7s — tempo más estable que
  las dos referencias anteriores (banda de estudio con click, probablemente).
- **Densidad Expert**: 2259 notas ≈ 4.1 notas/seg (bastante más técnica
  que Björk o Sonic Youth).
- **`N 5` (toggle HOPO/strum)**: Expert 35/2259 (1.5%), Hard 23/1789
  (1.3%), Medium 85/1300 (6.5%), Easy 55/849 (6.5%) — curioso que las
  dificultades más fáciles usan el toggle proporcionalmente MÁS que
  Expert/Hard, probablemente porque al simplificar la pista se rompen
  relaciones de traste que había que restaurar a mano; dato para tener en
  cuenta si en el futuro se afina el forzado por dificultad, no accionado
  todavía.
- **`N 6`: CERO notas, tercera referencia seguida.** Confirma de nuevo el
  fix de v2.0.0: ya son tres charts reales e independientes (pop
  electrónico, noise rock, funk/jazz fusion) sin un solo uso de tipo 6.
- De los 35 `N 5` en Expert: 32 (91%) en posiciones que naturalmente
  serían *strum* (forzadas A HOPO), igual patrón que Sonic Youth (93%) —
  confirma el sentido del toggle con un tercer dato independiente.

