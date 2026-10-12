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
**Nada se publica solo:** todo sale "para revisar". Modelo por defecto: `claude-sonnet-5-5`
(`--modelo` o la variable `BPT_MODELO` para cambiarlo).

**Automático:** `.github/workflows/resultados-mlb.yml` corre cada mañana de octubre y noviembre
(≈10:47 en Santiago) con `--fase todas`: genera las 3 láminas por juego, el `resumen.json` y, si
el repo tiene el secreto `ANTHROPIC_API_KEY`, los textos. Todo queda como artefacto del run
(Actions → el run → *Artifacts*) y los textos se leen directo en el resumen del run. También se
puede lanzar a mano con **Run workflow**, eligiendo fecha y fase. El cron solo vive en `main`.

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
  resultados.py          # pipeline de resultados MLB: tarjetas + resumen.json
  redactor/              # agente redactor: prompt de marca, llamada a Claude y validador de cifras
  glossary.py            # glosario de métricas: sigla, nombre en español, pista y explicación
  data/savant.py         # extracción de percentiles (pybaseball) + caché + búsqueda de jugador
  data/lvbp.py           # ingesta stats.lvbp.com: paginación, parseo, caché y percentiles vs. liga
  viz/percentile_card.py # tarjeta de percentiles por jugador
  viz/team_card.py       # tarjeta de equipo (dot strip vs. los 8 equipos)
  cli.py                 # comando `bpt`
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
- [ ] Job diario de extracción

Datos: Baseball Savant, FanGraphs, Baseball-Reference vía [pybaseball](https://github.com/jldbc/pybaseball).
