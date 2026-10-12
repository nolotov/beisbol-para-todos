"""País de nacimiento de los peloteros (MLB Stats API, endpoint /people) y quién es latino.

El box score no trae el país, así que lo pedimos aparte en lotes y lo cacheamos para
siempre en data/raw/mlb/people.json (el lugar de nacimiento no cambia).

"Latino" aquí = nacido en Latinoamérica o el Caribe hispano, incluido Puerto Rico. Aruba y
Curazao van en una lista aparte (CARIBE_NEERLANDES) porque se suelen contar con los latinos
en el béisbol, pero es una decisión editorial: se activa con `incluir_caribe_neerlandes`.
"""
from __future__ import annotations

import json
from pathlib import Path

from bpt.data.mlb_stats import CACHE_DIR, _get

# birthCountry de la API -> (código de 3 letras, nombre en español)
LATAM = {
    "Venezuela": ("VEN", "Venezuela"),
    "Dominican Republic": ("DOM", "República Dominicana"),
    "Puerto Rico": ("PUR", "Puerto Rico"),
    "Cuba": ("CUB", "Cuba"),
    "Mexico": ("MEX", "México"),
    "Colombia": ("COL", "Colombia"),
    "Panama": ("PAN", "Panamá"),
    "Nicaragua": ("NCA", "Nicaragua"),
    "Honduras": ("HON", "Honduras"),
    "Guatemala": ("GUA", "Guatemala"),
    "El Salvador": ("ESA", "El Salvador"),
    "Costa Rica": ("CRC", "Costa Rica"),
    "Brazil": ("BRA", "Brasil"),
    "Peru": ("PER", "Perú"),
    "Ecuador": ("ECU", "Ecuador"),
    "Argentina": ("ARG", "Argentina"),
    "Chile": ("CHI", "Chile"),
    "Bolivia": ("BOL", "Bolivia"),
    "Uruguay": ("URU", "Uruguay"),
    "Paraguay": ("PAR", "Paraguay"),
}
CARIBE_NEERLANDES = {
    "Aruba": ("ARU", "Aruba"),
    "Curacao": ("CUW", "Curazao"),
    "Curaçao": ("CUW", "Curazao"),
}

PEOPLE_CACHE = CACHE_DIR / "people.json"
LOTE = 50


def _cargar(cache: Path) -> dict[str, dict]:
    return json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}


def fetch_people(ids: list[int], cache: Path = PEOPLE_CACHE) -> dict[int, dict]:
    """id -> {nombre, pais_api, ciudad}. Solo pide a la API los que no están en caché."""
    datos = _cargar(cache)
    faltan = [i for i in dict.fromkeys(ids) if str(i) not in datos]
    for k in range(0, len(faltan), LOTE):
        lote = faltan[k:k + LOTE]
        r = _get("people", {"personIds": ",".join(map(str, lote))})
        for p in r.get("people", []):
            datos[str(p["id"])] = {
                "nombre": p.get("fullName"),
                "pais_api": p.get("birthCountry"),
                "ciudad": p.get("birthCity"),
            }
    if faltan:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    return {int(k): v for k, v in datos.items()}


def pais_latino(pais_api: str | None, incluir_caribe_neerlandes: bool = True) -> tuple[str, str] | None:
    if not pais_api:
        return None
    if pais_api in LATAM:
        return LATAM[pais_api]
    if incluir_caribe_neerlandes and pais_api in CARIBE_NEERLANDES:
        return CARIBE_NEERLANDES[pais_api]
    return None
