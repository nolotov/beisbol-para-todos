"""CLI: genera una tarjeta de percentiles para un jugador.

Ejemplos:
    python -m bpt.cli card "Tarik Skubal" --tipo pitcher --anio 2025
    python -m bpt.cli card "Ronald Acuna" --tipo batter --anio 2025 --refresh
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

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
    render_card(name, args.tipo, args.anio, metrics, out, handle=args.handle)
    print(f"[ok] Tarjeta generada: {out}")
    return 0


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
    c.add_argument("--handle", default="@beisbolparatodos")
    c.set_defaults(func=cmd_card)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
