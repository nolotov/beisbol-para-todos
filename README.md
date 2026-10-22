# Beisbol Para Todos ⚾📊

Toolkit de datos y visualización de **@mbp.deportes**: análisis sabermétrico de MLB y LVBP.

## Setup (Windows)

```powershell
cd $HOME\Documents\workspace\beisbol-para-todos
.\scripts\setup.ps1          # crea .venv, instala dependencias y corre los tests
.\.venv\Scripts\Activate.ps1
```

> Si PowerShell bloquea el script: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Uso

> En Windows, si **Smart App Control** bloquea `bpt.exe`, usa `python -m bpt` en su lugar
> (por ejemplo `python -m bpt lvbp-equipos --temporada 2025`). No desactives Smart App Control:
> una vez apagado no se puede volver a encender sin reinstalar Windows.

```powershell
# Tarjeta de percentiles Statcast (1080x1350, lista para IG/X)
bpt card "Tarik Skubal" --tipo pitcher --anio 2025
bpt card "Ronald Acuna" --tipo batter --anio 2025

# Forzar re-descarga (ignora la caché en data/raw/savant)
bpt card "Pablo Lopez" --refresh

# Modo offline con un CSV propio
bpt card "Nombre" --csv ruta\al\archivo.csv
```

### LVBP

```powershell
# Descargar bateo y pitcheo de la zafra (2025 = 2025-26). Se cachea en data/raw/lvbp/
bpt lvbp-sync --temporada 2025

# Tarjeta de percentiles vs. la liga (mínimo 100 AL / 20 IP para entrar al pool)
bpt lvbp-card "Gorkys Hernandez" --temporada 2025
bpt lvbp-card "Bryan Mata" --tipo pitcheo --temporada 2025

# Tarjetas por equipo: récord, diferencial, récord pitagórico y bateo/pitcheo vs. la liga
bpt lvbp-equipos --temporada 2025            # portada del carrusel + las 8
bpt lvbp-equipos --temporada 2025 --equipo MAG

# Previas de temporada: números de la anterior + contenido editorial (content/previas_2026-27.json)
bpt lvbp-previas

# Filtros: --equipo MAG, --fase final, --refresh
# Logos: si existe assets/logos/{codigo}.png (agu, bra, car, anz, leo, mag, tib, tig),
# la tarjeta de equipo lo muestra arriba a la derecha. Fuente: lvbp.com. La carpeta no se
# versiona porque son marcas de los equipos.
```

Fuente: `stats.lvbp.com` (datos de TuJonrón). Una petición por segundo y caché local; cita siempre la fuente.

> ⚠️ En las tablas de pitcheo de la LVBP, la columna "K%" es el **% de strikes** (S/NP). El K% real
> lo calculamos con `K/AL`. Está cubierto por un test.

### MLB: resultados de postemporada

```powershell
# Juegos de ayer (hora del Este) de las Series de Campeonato: tarjetas + resumen.json
bpt mlb-resultados

# Una fecha concreta, o toda la postemporada
bpt mlb-resultados --fecha 2026-10-11
bpt mlb-resultados --fecha 2026-10-11 --fase todas      # L, D, F, W o todas
```

Sale en `output/resultados/mlb/AAAA-MM-DD/`, dos láminas de carrusel por juego finalizado:

1. `*_1_resultado.png`: marcador, pizarra por entradas, decisiones de pitcheo y estado de la serie.
2. `*_2_figuras.png`: por equipo, la mejor salida en la loma (**Game Score** v2 de Tango) y la
   mejor línea al bate (**bases ganadas** = bases totales + boletos + pelotazos + robos), más los
   jonrones del juego. El criterio va impreso en la tarjeta y en el JSON.
3. `*_3_latinos.png` (si jugó algún latino): todos los latinos que vieron acción, en la loma y
   al bate, con su país. Los destacados (jonrón, figura del equipo, Game Score 60+, 2+ hits o
   2+ CI, victoria o salvado) van arriba con el motivo; los venezolanos en verde. El país sale
   del endpoint `/people` de la API y se cachea en `data/raw/mlb/people.json`. Aruba y Curazao
   cuentan como latinos (`mlb_people.CARIBE_NEERLANDES`, se puede desactivar).

Y un `resumen.json` con las cifras del día, que es la entrada del agente redactor. Los juegos pospuestos o sin terminar quedan en
`pendientes`. Fuente: MLB Stats API (`statsapi.mlb.com`), sin logos ni gráfica de MLB.

#### Agente redactor

```powershell
# Una sola vez: crea el archivo .env en la raíz (está en .gitignore, no se sube a GitHub)
Copy-Item .env.example .env ; notepad .env    # pega tu llave: ANTHROPIC_API_KEY=sk-ant-...
bpt mlb-resultados --fecha 2026-10-12 --redactar
bpt redactar --fecha 2026-10-12                # solo textos, sobre un resumen.json existente
```

Por cada juego escribe el caption de Instagram, un hilo de X de 3-5 tuits y un guion de
30-45 s con marcas `[LÁMINA 1]`/`[LÁMINA 2]`, en `textos.md` (para leer) y `textos.json`.
Las reglas de marca están en `src/bpt/redactor/prompt.py`.

El **validador** revisa que toda cifra del texto esté en los datos del juego; si el modelo
inventa una, se la devuelve para que corrija (1 reintento) y, si insiste, la pieza queda
"con alertas". También marca lenguaje de apuestas, "el mejor" sin criterio y largos.
**Nada se publica solo:** todo sale "para revisar".

**Uso y costo:** cada pieza guarda en `textos.json` los tokens de entrada, salida y caché y el
costo estimado con precios de lista; el total del día queda en `uso.json`. **Prompt caching:**
el prompt de sistema (~1.400 tokens) se cachea solo si la corrida hará 2 o más llamadas
(`BPT_CACHE=auto`; `si` / `no` para forzarlo). Con una sola llamada, escribir el caché (1,25x)
sale más caro que no usarlo. Modelo por defecto: `claude-sonnet-5-5`
(`--modelo` o la variable `BPT_MODELO` para cambiarlo).

**Automático:** `.github/workflows/resultados-mlb.yml` corre cada mañana de octubre y noviembre
(06:17 en Santiago) con `--fase todas`: genera las 3 láminas por juego, el `resumen.json` y, si
el repo tiene el secreto `ANTHROPIC_API_KEY`, los textos. Todo queda como artefacto del run
(Actions → el run → *Artifacts*) y los textos se leen directo en el resumen del run. También se
puede lanzar a mano con **Run workflow**, eligiendo fecha y fase. El cron solo vive en `main`.

**Disparo puntual con cron-job.org.** El cron de GitHub se atrasa (hubo días en que corrió a las
14:00). Por eso el arranque real lo da [cron-job.org](https://cron-job.org), que llama a la API
de GitHub (`workflow_dispatch`) a las 06:10 (MLB) y 06:15 (LVBP), zona `America/Santiago`. El
cron de GitHub queda de **respaldo**: si ese día ya hubo un run manual o de cron-job.org, el job
`control` lo detiene y no se repite el paquete en Telegram.

Llamada que hace cron-job.org (una por workflow):

```
POST https://api.github.com/repos/nolotov/beisbol-para-todos/actions/workflows/resultados-mlb.yml/dispatches
Authorization: Bearer <token fine-grained, solo este repo, permiso Actions: Read and write>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json

{"ref":"main"}
```

Respuesta esperada: `204 No Content`. El token vence: renovarlo antes de la fecha que elegiste.

Secreto: *Settings → Secrets and variables → Actions → New repository secret*,
nombre `ANTHROPIC_API_KEY`, valor = la misma llave del `.env`.

#### Telegram: el paquete del día en el celular

Cada mañana el workflow manda por juego: encabezado con estado y alertas, álbum de láminas,
las láminas originales como archivo (calidad completa para Instagram), el caption, cada tuit
por separado y el guion. Si no hubo juegos o falla el workflow, también avisa. **No publica
nada**: tú revisas y publicas.

Configuración (una vez):
1. En Telegram, habla con **@BotFather** → `/newbot` → nombre y usuario del bot. Copia el token.
2. Ponlo en el `.env` como `TELEGRAM_BOT_TOKEN=...`, abre tu bot y mándale `/start`.
3. `bpt telegram-chat` te muestra tu `TELEGRAM_CHAT_ID`: cópialo al `.env`.
4. `bpt telegram-prueba` para confirmar; `bpt notificar --fecha 2026-10-11` para ver un paquete.
5. Crea los secretos `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` en GitHub.

#### Instagram: publicar con un botón (fase 4)

Con la variable de repositorio `PUBLICAR_INSTAGRAM=1`, cada pieza del paquete (un carrusel por
juego de MLB, o el de la jornada LVBP) cierra con **📸 Publicar en Instagram**. Pide
confirmación y, al confirmar, el workflow `publicar.yml` la publica y el mensaje se actualiza
con el enlace. Sin caption no hay botón; las piezas con alertas lo dicen en el mensaje.

```powershell
python -m bpt instagram-prueba          # token, cuenta y cuota de 24 h (no publica)
python -m bpt publicar-piezas --carpeta output/resultados/lvbp/2026-10-15
python -m bpt telegram-webhook          # estado del relé que atiende los botones
```

Requiere el relé `infra/telegram-relay/worker.js` (Cloudflare Worker, gratis), los secretos
`IG_ACCESS_TOKEN`, `IG_USER_ID` (opcional) y `GH_PAT_SECRETOS`, y la renovación semanal del
token (`instagram-token.yml`). Paso a paso, decisiones y fallas habituales en la wiki:
[Publicación en Instagram](https://github.com/nolotov/beisbol-para-todos/wiki/Publicacion-en-Instagram).

#### Threads y X: el mismo botón, una red a la vez

Con `PUBLICAR_THREADS=1` y/o `PUBLICAR_X=1` (variables del repo) el botón de cada pieza pasa a
ser un menú: **📸 Instagram · 🧵 Threads · 𝕏 X · 🚀 Todas**, cada uno con confirmación. Threads
recibe el carrusel con el hilo como respuestas; X, el hilo con hasta 4 láminas en el primer
tuit (X cobra por post y rechazamos los tuits con enlace, que cuestan más).

```powershell
python -m bpt threads-prueba            # token, cuenta y cuota de Threads (no publica)
python -m bpt x-prueba                  # credenciales de X (no publica)
```

Requiere desplegar el `worker.js` nuevo en Cloudflare y los secretos `THREADS_ACCESS_TOKEN`,
`X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN` y `X_ACCESS_SECRET`. Paso a paso en la wiki:
[Publicación en Threads y X](https://github.com/nolotov/beisbol-para-todos/wiki/Publicacion-en-Threads-y-X).

#### Especiales: publicaciones armadas a mano

Un JSON en `content/especiales/` (portada, rosters y textos) se convierte en un paquete igual
al del día: láminas 1080×1350, caption e hilo, y llega a Telegram con el menú de redes.

```powershell
python -m bpt especial --archivo content/especiales/latinos-serie-mundial.json
```

En GitHub: Actions → **Especial MBP** → *Run workflow* con la ruta del archivo.

**Historia especial.** Con `"tipo": "historia"` el JSON no lleva rosters ni textos sino un
bloque `historia` (antetítulo, titular en 1-3 líneas, marcador, figuras, dato y lo que viene) y
sale una sola lámina 1080x1920 para historias de Instagram. Llega a Telegram con el botón
"📲 Publicar historia en Instagram", igual que la historia del día. Ejemplo:
`content/especiales/rays-banderin-2026.json`.

**Carrusel por bloques.** En vez de `rosters`, un especial puede traer `equipos` (A y B, con
nombre y color) y `laminas`: una lista de láminas 1080x1350 de tipo `portada`, `cifras`,
`barras`, `cara_a_cara`, `camino` o `figuras` (ver `src/bpt/viz/carrusel_card.py`). Sirve para
previas y duelos. Ejemplo: `content/especiales/previa-serie-mundial-2026.json` (9 láminas).

**Verificador.** Cada especial pasa por `bpt.verificador` antes de llegar a Telegram: los
números de los textos tienen que estar en las láminas, las láminas en la evidencia (si el JSON
trae `evidencia` o `evidencia_archivo`) y los hechos del bloque `verificar` se comprueban otra
vez contra MLB Stats API (récord, marcador, línea, estadística de temporada). Sin bloquear:
lo que no cuadra deja la pieza "con alertas".

```powershell
python -m bpt verificar --archivo content/especiales/previa-serie-mundial-2026.json
```

#### Agente editor: propuestas de especiales

El editor busca la historia del día (o arma el tema que le pidas), consulta MLB Stats API y
Statcast con herramientas, calcula las cifras derivadas con una calculadora, arma el especial
(carrusel o historia) y lo entrega al verificador: si alguna cifra no salió de una consulta,
se lo devuelve para que corrija. Llega a Telegram como "🧠 Propuesta del editor", con el
porqué, otras ideas y el menú de redes. En el paquete quedan `<slug>.json` y
`<slug>.evidencia.json`: copiados a `content/especiales/`, el especial queda en el repo.

```powershell
python -m bpt editor                                   # tema libre, hoy
python -m bpt editor --tema "el mejor venezolano de la semana en la LVBP"
```

En GitHub: Actions → **Editor MBP** → *Run workflow*. Diario a las 11:43 de Santiago con la
variable de repo `EDITOR_DIARIO = 1`. Modelo: `MODELO_EDITOR` (por defecto Sonnet 5.5).

#### Métricas: qué funcionó

Cada publicación queda anotada en la rama `metricas`. Los lunes, **Métricas MBP** pide los
números de los últimos 28 días a Instagram, Threads y X, manda el informe por Telegram y
escribe `aprendizajes.md`, que el editor lee antes de elegir. Requiere los permisos
`instagram_business_manage_insights` y `threads_manage_insights` en la app de Meta.

```powershell
python -m bpt metricas --registro ruta/publicaciones.jsonl --salida ruta --enviar
```

#### Reels: las láminas con voz

`bpt reel` arma un video vertical por pieza con sus láminas, la voz del guion (edge-tts, voz
venezolana `es-VE-SebastianNeural`; cámbiala con `BPT_VOZ`) y subtítulos. Sin voz sale mudo,
para ponerle música en la app. Con la variable `REELS = 1` se arman solos y llegan a Telegram
con "🎬 Publicar Reel en Instagram".

```powershell
pip install -e ".[video]"
python -m bpt reel --carpeta output/especiales/previa-serie-mundial-2026
```

#### Historia del día: los juegos de hoy

Una historia vertical (1080×1920) con la cartelera de hoy de la MLB y la LVBP en hora de
Venezuela: hora, enfrentamiento, cómo va la serie (postemporada) o los récords (LVBP) y los
abridores probables. Si no hay juegos de ninguna liga no se genera ni se manda nada. Llega a
Telegram con **📲 Publicar historia en Instagram**, por el mismo camino que las publicaciones.

```powershell
python -m bpt historia                    # hoy (hora de Venezuela) -> output/historia/<fecha>/
python -m bpt historia --fecha 2026-10-20
python -m bpt notificar --carpeta output/historia/2026-10-20
```

El workflow `historia.yml` corre solo al terminar el primer workflow de resultados del día
(cron de respaldo a las 07:43 de Santiago) y no repite la historia si ya salió.

### LVBP: resultados de la jornada

```powershell
bpt lvbp-resultados                         # jornada de ayer (hora de Venezuela)
bpt lvbp-resultados --fecha 2026-10-12 --redactar
bpt notificar --salida output/resultados/lvbp --fecha 2026-10-12
```

Un carrusel por jornada en `output/resultados/lvbp/AAAA-MM-DD/`:

1. `lvbp_1_jornada.png`: todos los marcadores, con el récord de cada equipo después del juego
   y las decisiones (G/P/S).
2. `lvbp_2_destacados.png`: lo mejor de la jornada al bate (bases ganadas, mínimo 3) y en la
   loma (Game Score de 50 o más, con 3+ entradas), y los jonrones. Si nadie llega al mínimo,
   la lámina lo dice: no se inventan destacados.
3. Extras para historias: `lvbp_extra_*_resultado.png` y `*_figuras.png` de cada juego.

El redactor escribe **un** caption, hilo y guion para toda la jornada, neutral entre los 8
equipos. Datos: MLB Stats API (liga 135), con nuestras siglas (CAR = Cardenales; la API le dice
CAR a Caracas) y nombres con tilde. Workflow: `.github/workflows/resultados-lvbp.yml`
(octubre a enero, 06:22 en Santiago), con los mismos secretos.

### Etiquetas de métricas

Todas las tarjetas aceptan `--etiquetas`:

| Modo | Ejemplo | Cuándo |
|---|---|---|
| `mixto` (defecto) | **Efectividad** / ERA · **wOBA** / valor de cada turno | Tarjetas completas: puente entre lo tradicional y lo nuevo |
| `espanol` | Efectividad, Embasado, % de ponches | Público tradicional |
| `siglas` | ERA, OBP, K% | Poco espacio, público analítico |

El glosario (`src/bpt/glossary.py`) tiene sigla, nombre, pista y una explicación de una frase por métrica,
para usar en captions y guiones.

Las tarjetas salen en `output/cards/`. Los datos crudos se cachean en `data/raw/` (ambos fuera de git).

## Estructura

```
src/bpt/
  theme.py               # paleta "Dashboard de dugout", estilo matplotlib y firma @mbp.deportes
  lvbp_resultados.py     # pipeline de la jornada LVBP: carrusel + resumen.json
  resultados.py          # pipeline de resultados MLB: tarjetas + resumen.json
  historia.py            # historia del día: cartelera de juegos de hoy (MLB + LVBP)
  especial.py            # especiales armados a mano (content/especiales/*.json)
  verificador.py         # verificador de especiales: cifras, evidencia, hechos y reglas
  editor/                # agente editor: herramientas de datos, bucle con Claude y entrega
  metricas/              # fase 5: insights de cada red, informe y aprendizajes
  video/reel.py          # Reels: láminas + voz del guion + subtítulos (ffmpeg)
  redactor/              # agente redactor: prompt de marca, llamada a Claude y validador de cifras
  notificar/telegram.py  # paquete del día a Telegram + botón de publicar
  publicar/              # fase 4: piezas, JPEG, menú por red y clientes de Instagram, Threads y X
  glossary.py            # glosario de métricas: sigla, nombre en español, pista y explicación
  data/savant.py         # extracción de percentiles (pybaseball) + caché + búsqueda de jugador
  data/lvbp.py           # ingesta stats.lvbp.com: paginación, parseo, caché y percentiles vs. liga
  viz/percentile_card.py # tarjeta de percentiles por jugador
  viz/team_card.py       # tarjeta de equipo (dot strip vs. los 8 equipos)
  cli.py                 # comando `bpt`
infra/telegram-relay/    # relé de los botones (Cloudflare Worker) y sus pruebas (node --test)
tests/                   # tests offline con CSV sintético
scripts/setup.ps1        # bootstrap del entorno en Windows
```

## Flujo de ramas (GitFlow)

- `main`: lo que está en producción (lo que genera contenido publicado)
- `develop`: integración
- `feature/*`: una rama por funcionalidad (ej. `feature/statcast-percentile-card`)

## Roadmap

- [x] Tarjeta de percentiles Statcast
- [ ] Gráfico de movimiento de pitcheos (antes vs. ahora)
- [x] Ingesta LVBP (stats.lvbp.com) + tarjeta de percentiles vs. liga
- [ ] Splits LVBP (vs. zurdos/derechos, por mes) y comparativa MLB vs. LVBP
- [ ] Modelo de pronóstico (log5 + bullpen + park factor) con track record público
- [x] Job diario de extracción (resultados MLB y LVBP)
- [x] Publicación en Instagram desde Telegram
- [x] Historia diaria con los juegos de hoy
- [x] Publicación en Threads y X desde Telegram
- [x] Verificador de especiales y agente editor
- [x] Métricas semanales con aprendizajes para el editor
- [x] Reels con voz venezolana

Datos: Baseball Savant, FanGraphs, Baseball-Reference vía [pybaseball](https://github.com/jldbc/pybaseball).
