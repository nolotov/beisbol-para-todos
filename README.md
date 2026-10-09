# Beisbol Para Todos ⚾📊

Toolkit de datos y visualización para la cuenta faceless de análisis sabermétrico (MLB + LVBP).

## Setup (Windows)

```powershell
cd $HOME\Documents\workspace\beisbol-para-todos
.\scripts\setup.ps1          # crea .venv, instala dependencias y corre los tests
.\.venv\Scripts\Activate.ps1
```

> Si PowerShell bloquea el script: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Uso

```powershell
# Tarjeta de percentiles Statcast (1080x1350, lista para IG/X)
bpt card "Tarik Skubal" --tipo pitcher --anio 2025
bpt card "Ronald Acuna" --tipo batter --anio 2025

# Forzar re-descarga (ignora la caché en data/raw/savant)
bpt card "Pablo Lopez" --refresh

# Modo offline con un CSV propio
bpt card "Nombre" --csv ruta\al\archivo.csv
```

Las tarjetas salen en `output/cards/`. Los datos crudos se cachean en `data/raw/` (ambos fuera de git).

## Estructura

```
src/bpt/
  theme.py               # paleta "Dashboard de dugout" + estilo matplotlib
  data/savant.py         # extracción de percentiles (pybaseball) + caché + búsqueda de jugador
  viz/percentile_card.py # render de la tarjeta
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
- [ ] Ingesta LVBP (Pelota Binaria / LVBP.com, respetando términos de uso)
- [ ] Modelo de pronóstico (log5 + bullpen + park factor) con track record público
- [ ] Job diario de extracción

Datos: Baseball Savant, FanGraphs, Baseball-Reference vía [pybaseball](https://github.com/jldbc/pybaseball).
