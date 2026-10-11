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

Sale en `output/resultados/mlb/AAAA-MM-DD/`: una tarjeta por juego finalizado (marcador, pizarra
por entradas, decisiones de pitcheo y estado de la serie) y un `resumen.json` con las cifras del
día, que es la entrada del agente redactor. Los juegos pospuestos o sin terminar quedan en
`pendientes`. Fuente: MLB Stats API (`statsapi.mlb.com`), sin logos ni gráfica de MLB.

**Automático:** `.github/workflows/resultados-mlb.yml` lo corre cada mañana de octubre y noviembre
y deja la carpeta del día como artefacto del run. El cron solo se activa cuando el workflow está
en `main`; antes se puede lanzar a mano desde Actions.

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
