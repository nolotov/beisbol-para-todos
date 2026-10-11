"""CLI de Beisbol Para Todos.

Ejemplos:
    bpt card "Tarik Skubal" --tipo pitcher --anio 2025
    bpt lvbp-sync --temporada 2025
    bpt lvbp-card "Gorkys Hernandez" --temporada 2025
    bpt lvbp-card "Bryan Mata" --tipo pitcheo --temporada 2025
    bpt lvbp-equipos --temporada 2025            # portada + las 8 tarjetas de equipo
    bpt lvbp-equipos --temporada 2025 --equipo MAG
    bpt lvbp-previas                              # previas 2026-27 (content/previas_2026-27.json)
    bpt mlb-resultados                            # Series de Campeonato: juegos de ayer
    bpt mlb-resultados --fecha 2026-10-11 --fase todas
    bpt mlb-resultados --redactar                 # + caption, hilo y guion (ANTHROPIC_API_KEY)
    bpt redactar --fecha 2026-10-12               # solo textos, sobre un resumen.json ya generado
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from bpt import glossary, theme
from bpt.data import savant
from bpt.viz.percentile_card import render_card


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", savant._normalize(text)).strip("-")


def cmd_card(args: argparse.Namespace) -> int:
    df = savant.load_percentiles(args.tipo, args.anio, refresh=args.refresh,
                                 source_csv=args.csv)
    try:
        row = savant.find_player(df, args.jugador)
    except LookupError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1
    name = savant.display_name(row["player_name"])
    metrics = savant.player_metrics(row, args.tipo)
    out = Path(args.salida) / f"{_slug(name)}_{args.tipo}_{args.anio}.png"
    render_card(name, args.tipo, args.anio, metrics, out, handle=args.handle,
                etiquetas=args.etiquetas)
    print(f"[ok] Tarjeta generada: {out}")
    return 0


def _lvbp_kwargs(args: argparse.Namespace) -> dict:
    return dict(team=args.equipo, game_type=args.fase, refresh=args.refresh)


def cmd_lvbp_sync(args: argparse.Namespace) -> int:
    from bpt.data import lvbp

    for kind in (["bateo", "pitcheo"] if args.tipo == "ambos" else [args.tipo]):
        df = lvbp.fetch_leaders(args.temporada, kind, **_lvbp_kwargs(args))
        print(f"[ok] LVBP {lvbp.season_label(args.temporada)} {kind}: {len(df)} jugadores "
              f"-> data/raw/lvbp/")
    return 0


def cmd_lvbp_card(args: argparse.Namespace) -> int:
    from bpt import theme
    from bpt.data import lvbp

    df = lvbp.fetch_leaders(args.temporada, args.tipo, **_lvbp_kwargs(args))
    key = savant._normalize(args.jugador)
    names = df["jugador"].map(savant._normalize)
    hits = df[names == key]
    if hits.empty:
        hits = df[names.str.contains(key, regex=False)]
    if hits.empty:
        print(f"[error] No encontré a '{args.jugador}' en LVBP {lvbp.season_label(args.temporada)}.",
              file=sys.stderr)
        return 1
    if len(hits) > 1:
        opts = ", ".join(f"{r.jugador} ({r.equipo})" for r in hits.head(8).itertuples())
        print(f"[error] '{args.jugador}' es ambiguo. Opciones: {opts}", file=sys.stderr)
        return 1
    row = hits.iloc[0]

    pool_kw = dict(min_pa=args.min_al, min_ip=args.min_ip)
    if not lvbp.qualified_pool(df, args.tipo, **pool_kw)["jugador"].eq(row["jugador"]).any():
        print("[aviso] El jugador no alcanza el mínimo de muestra; percentiles poco fiables.",
              file=sys.stderr)
    metrics = lvbp.percentiles(df, row, args.tipo, **pool_kw)
    role = "BATEADOR" if args.tipo == "bateo" else "LANZADOR"
    subtitle = (f"{role}  ·  {str(row['equipo']).upper()}  ·  LVBP "
                f"{lvbp.season_label(args.temporada)}  ·  PERCENTIL VS LIGA")
    out = Path(args.salida) / f"lvbp_{_slug(row['jugador'])}_{args.tipo}_{args.temporada}.png"
    render_card(row["jugador"], args.tipo, args.temporada, metrics, out,
                handle=args.handle, source=lvbp.SOURCE_LABEL, subtitle=subtitle,
                accent=theme.LVBP, etiquetas=args.etiquetas)
    print(f"[ok] Tarjeta generada: {out}")
    return 0


def cmd_lvbp_teams(args: argparse.Namespace) -> int:
    from bpt.data import lvbp
    from bpt.viz.team_card import render_team_card

    t = lvbp.fetch_team_stats(args.temporada, game_type=args.fase, refresh=args.refresh)
    if args.equipo:
        code = args.equipo.upper()
        sel = t[t["codigo"] == code]["equipo"].tolist()
        if not sel:
            print(f"[error] Equipo '{args.equipo}' no válido. Usa: {', '.join(lvbp.TEAMS)}",
                  file=sys.stderr)
            return 1
    else:
        sel = t["equipo"].tolist()
    label = lvbp.season_label(args.temporada)
    if not args.equipo:
        from bpt.viz.cover import render_season_cover
        out = Path(args.salida) / f"lvbp_equipo_00_portada_{args.temporada}.png"
        render_season_cover(t, label, out, handle=args.handle)
        print(f"[ok] Portada: {out}")
    for eq in sel:
        code = t.loc[t["equipo"] == eq, "codigo"].iloc[0]
        out = Path(args.salida) / f"lvbp_equipo_{str(code).lower()}_{args.temporada}.png"
        render_team_card(t, eq, label, out, handle=args.handle, etiquetas=args.etiquetas)
        print(f"[ok] {eq}: {out}")
    return 0


def cmd_lvbp_previews(args: argparse.Namespace) -> int:
    import json

    from bpt.data import lvbp
    from bpt.viz.preview_card import render_preview_card

    contenido = json.loads(Path(args.contenido).read_text(encoding="utf-8"))
    anterior = int(contenido["temporada_anterior"])
    t = lvbp.fetch_team_stats(anterior, refresh=args.refresh)
    for code, data in contenido["equipos"].items():
        if args.equipo and code != args.equipo.upper():
            continue
        out = Path(args.salida) / f"lvbp_previa_{code.lower()}_{contenido['temporada']}.png"
        render_preview_card(t, code, data, contenido["temporada"], lvbp.season_label(anterior),
                            out, handle=args.handle)
        print(f"[ok] {code}: {out}")
    return 0


def cmd_mlb_results(args: argparse.Namespace) -> int:
    from bpt import resultados
    fecha = args.fecha or resultados.ayer_mlb()
    tipo = None if args.fase == "todas" else args.fase
    r = resultados.generar(fecha, temporada=args.temporada, tipo=tipo, salida=Path(args.salida),
                           handle=args.handle, refresh=not args.cache)
    carpeta = Path(args.salida) / fecha
    for j in r["juegos"]:
        serie = j["estado_serie"]["texto"] if j["estado_serie"] else ""
        print(f"[ok] {j['serie_corto']} J{j['juego_n']}: {j['titular']}  ({serie})")
    for p in r["pendientes"]:
        print(f"[--] {p['serie']} J{p['juego_n']} {p['partido']}: {p['estado']}")
    if not r["juegos"] and not r["pendientes"]:
        print(f"[--] No hubo juegos de esa fase el {fecha}")
    print(f"Resumen: {carpeta / 'resumen.json'}")
    if args.redactar and r["juegos"]:
        return _redactar(carpeta, args.modelo)
    return 0


def _redactar(carpeta: Path, modelo: str) -> int:
    from bpt.redactor import agente
    try:
        res = agente.redactar_dia(carpeta, modelo=modelo)
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1
    for r in res:
        marca = "ok" if r["validacion"]["ok"] else "!!"
        print(f"[{marca}] {r['partido']}: {r['estado']} (intentos: {r['intentos']})")
        for c in r["validacion"]["cifras_sin_respaldo"]:
            print(f"     cifra sin respaldo: {c}")
        for a in r["validacion"]["alertas"]:
            print(f"     {a}")
    if res:
        print(f"Textos: {carpeta / 'textos.md'}")
    else:
        print("[--] No hay juegos terminados para redactar")
    return 0


def cmd_redactar(args: argparse.Namespace) -> int:
    from bpt import resultados
    carpeta = Path(args.carpeta) if args.carpeta else \
        Path(args.salida) / (args.fecha or resultados.ayer_mlb())
    if not (carpeta / "resumen.json").exists():
        print(f"[error] No existe {carpeta / 'resumen.json'}: corre antes bpt mlb-resultados",
              file=sys.stderr)
        return 1
    return _redactar(carpeta, args.modelo)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bpt", description="Beisbol Para Todos - toolkit de datos")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("card", help="Tarjeta de percentiles Statcast")
    c.add_argument("jugador", help='Nombre, p. ej. "Tarik Skubal"')
    c.add_argument("--tipo", choices=["pitcher", "batter"], default="pitcher")
    c.add_argument("--anio", type=int, default=2025)
    c.add_argument("--refresh", action="store_true", help="Ignorar caché y volver a descargar")
    c.add_argument("--csv", type=Path, default=None, help="Usar un CSV local (modo offline)")
    c.add_argument("--salida", default="output/cards")
    c.add_argument("--handle", default=theme.HANDLE)
    c.add_argument("--etiquetas", choices=glossary.MODES, default="mixto",
                    help="mixto: español + sigla | espanol | siglas")
    c.set_defaults(func=cmd_card)

    def lvbp_common(sp):
        sp.add_argument("--temporada", type=int, default=2025,
                        help="Año de inicio de la zafra (2025 = 2025-26)")
        sp.add_argument("--equipo", default=None, help="AGU, BRA, CAR, ANZ, LEO, MAG, TIB, TIG")
        sp.add_argument("--fase", choices=["regular", "comodin", "semifinal", "final"],
                        default="regular")
        sp.add_argument("--refresh", action="store_true", help="Ignorar caché y volver a descargar")

    s = sub.add_parser("lvbp-sync", help="Descargar estadísticas LVBP (stats.lvbp.com)")
    s.add_argument("--tipo", choices=["bateo", "pitcheo", "ambos"], default="ambos")
    lvbp_common(s)
    s.set_defaults(func=cmd_lvbp_sync)

    lc = sub.add_parser("lvbp-card", help="Tarjeta de percentiles vs. la LVBP")
    lc.add_argument("jugador", help='Nombre, p. ej. "Gorkys Hernandez"')
    lc.add_argument("--tipo", choices=["bateo", "pitcheo"], default="bateo")
    lc.add_argument("--min-al", type=int, default=100, help="Mínimo de apariciones (bateo)")
    lc.add_argument("--min-ip", type=float, default=20.0, help="Mínimo de innings (pitcheo)")
    lc.add_argument("--salida", default="output/cards")
    lc.add_argument("--handle", default=theme.HANDLE)
    lc.add_argument("--etiquetas", choices=glossary.MODES, default="mixto",
                    help="mixto: español + sigla | espanol | siglas")
    lvbp_common(lc)
    lc.set_defaults(func=cmd_lvbp_card)

    te = sub.add_parser("lvbp-equipos", help="Tarjetas de bateo y pitcheo por equipo")
    te.add_argument("--salida", default="output/cards")
    te.add_argument("--handle", default=theme.HANDLE)
    te.add_argument("--etiquetas", choices=glossary.MODES, default="mixto",
                    help="mixto: español + sigla | espanol | siglas")
    lvbp_common(te)
    te.set_defaults(func=cmd_lvbp_teams)

    mr = sub.add_parser("mlb-resultados",
                        help="Tarjetas de resultados de postemporada MLB + resumen.json")
    mr.add_argument("--fecha", default=None,
                    help="YYYY-MM-DD (fecha oficial MLB). Por defecto: ayer en hora del Este")
    mr.add_argument("--fase", choices=["L", "D", "F", "W", "todas"], default="L",
                    help="L=Series de Campeonato (defecto), D=Divisional, F=Comodín, W=Mundial")
    mr.add_argument("--temporada", type=int, default=None)
    mr.add_argument("--salida", default="output/resultados/mlb")
    mr.add_argument("--handle", default=theme.HANDLE)
    mr.add_argument("--cache", action="store_true",
                    help="Usar la caché local en vez de descargar de nuevo")
    mr.add_argument("--redactar", action="store_true",
                    help="Además, redactar caption, hilo y guion con Claude")
    mr.add_argument("--modelo", default=None, help="Modelo de Claude (defecto: claude-sonnet-5-5)")
    mr.set_defaults(func=cmd_mlb_results)

    rd = sub.add_parser("redactar", help="Textos para redes desde un resumen.json")
    rd.add_argument("--fecha", default=None, help="YYYY-MM-DD; por defecto, ayer (hora del Este)")
    rd.add_argument("--carpeta", default=None, help="Carpeta con resumen.json (ignora --fecha)")
    rd.add_argument("--salida", default="output/resultados/mlb")
    rd.add_argument("--modelo", default=None, help="Modelo de Claude (defecto: claude-sonnet-5-5)")
    rd.set_defaults(func=cmd_redactar)

    pv = sub.add_parser("lvbp-previas", help="Tarjetas previas de temporada por equipo")
    pv.add_argument("--contenido", default="content/previas_2026-27.json",
                    help="JSON con mánager, cambios y la pregunta de cada equipo")
    pv.add_argument("--equipo", default=None, help="Solo un equipo (CAR, MAG, ...)")
    pv.add_argument("--salida", default="output/cards")
    pv.add_argument("--handle", default=theme.HANDLE)
    pv.add_argument("--refresh", action="store_true")
    pv.set_defaults(func=cmd_lvbp_previews)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
