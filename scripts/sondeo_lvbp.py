"""Sondeo: ¿la MLB Stats API trae la LVBP (liga 135) con pizarra, box score y países?

Uso:  python scripts/sondeo_lvbp.py
Guarda las respuestas crudas en data/raw/sondeo_lvbp/ y muestra un resumen.
"""
import json
from pathlib import Path

import requests

BASE = "https://statsapi.mlb.com/api/v1"
OUT = Path("data/raw/sondeo_lvbp")
OUT.mkdir(parents=True, exist_ok=True)


def get(nombre, path, **params):
    r = requests.get(f"{BASE}/{path}", params=params, timeout=30,
                     headers={"User-Agent": "beisbol-para-todos (@mbp.deportes)"})
    (OUT / f"{nombre}.json").write_text(r.text, encoding="utf-8")
    print(f"{nombre:<22} HTTP {r.status_code}  {len(r.content):>8} bytes")
    return r.json() if r.ok else {}


def juegos(d):
    return [g for x in d.get("dates", []) for g in x.get("games", [])]


hoy = get("calendario_2026", "schedule", sportId=17, leagueId=135,
          startDate="2026-10-08", endDate="2026-10-20", hydrate="linescore,decisions,team")
pasada = get("calendario_2025", "schedule", sportId=17, leagueId=135,
             startDate="2025-10-14", endDate="2025-10-20", hydrate="linescore,decisions,team")

for nombre, d in [("2026-27", hoy), ("2025-26", pasada)]:
    js = juegos(d)
    ligas = {(g["teams"]["home"]["team"].get("league") or {}).get("id") for g in js}
    print(f"\nZafra {nombre}: {len(js)} juegos, ligas en el calendario: {ligas}")
    for g in js[:12]:
        t = g["teams"]
        print(f"  {g['officialDate']} {g['gamePk']} {g.get('gameType')} "
              f"{t['away']['team']['name']} {t['away'].get('score', '-')} @ "
              f"{t['home']['team']['name']} {t['home'].get('score', '-')}  "
              f"[{g['status']['detailedState']}] entradas={len((g.get('linescore') or {}).get('innings', []))} "
              f"decisiones={'si' if g.get('decisions') else 'no'}")

finales = [g for g in juegos(pasada) + juegos(hoy) if g["status"]["abstractGameState"] == "Final"]
if finales:
    pk = finales[0]["gamePk"]
    box = get("boxscore", f"game/{pk}/boxscore")
    for lado in ("away", "home"):
        t = box.get("teams", {}).get(lado, {})
        print(f"\nBox {pk} {lado}: {t.get('team', {}).get('name')} "
              f"bateadores={len(t.get('batters', []))} pitchers={len(t.get('pitchers', []))}")
    ids = (box.get("teams", {}).get("home", {}).get("batters", []) or [])[:15]
    if ids:
        p = get("people", "people", personIds=",".join(map(str, ids)))
        for x in p.get("people", []):
            print(f"  {x.get('fullName'):<28} {x.get('birthCountry')}")
else:
    print("\nNo encontré juegos finalizados para probar el box score.")
print(f"\nListo. Archivos en {OUT}/")
