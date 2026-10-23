"""Agente editor de MBP: propone y arma especiales con datos verificados.

`ejecutar` corre el agente, deja en la carpeta el especial (especial.json), la evidencia
(evidencia.json) y las láminas, igual que `bpt especial`; desde ahí el envío a Telegram y
el botón de publicar funcionan como con cualquier especial.
"""
from __future__ import annotations

import json
from pathlib import Path

from bpt import especial as E
from bpt import theme

SALIDA = Path("output/editor")
CONTENIDO = Path("content/especiales")


def ya_publicados(carpeta: Path = CONTENIDO) -> list[str]:
    salida = []
    for f in sorted(Path(carpeta).glob("*.json")):
        if f.name.endswith(".evidencia.json"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        salida.append(f"{d.get('fecha', '')} · {d.get('titular', f.stem)}")
    return salida


def _conteo(nombres: list[str]) -> str:
    from collections import Counter
    return ", ".join(f"{n} ×{k}" if k > 1 else n for n, k in Counter(nombres).items())


def ejecutar(fecha: str, tema: str | None = None, salida: Path = SALIDA,
             handle: str = theme.HANDLE, aprendizajes: str | None = None, client=None,
             caja=None, log=print) -> dict:
    from bpt.editor.agente import editar

    r = editar(fecha, tema, client=client, caja=caja, ya_publicados=ya_publicados(),
               aprendizajes=aprendizajes, log=log)
    e = r.especial
    e["editor"] = {"por_que": r.por_que, "otras_ideas": r.otras_ideas, "tema": tema,
                   "modelo": r.uso.get("modelo"), "costo_usd": r.uso.get("costo_usd"),
                   "vueltas": r.vueltas, "correcciones": r.correcciones,
                   "consultas": len(r.evidencia),
                   "herramientas": _conteo([x["herramienta"] for x in r.evidencia])}
    resumen = E.generar_datos(e, salida, handle, evidencia=r.evidencia)
    carpeta = Path(resumen["carpeta"])
    # Con estos dos archivos copiados a content/especiales/ el especial queda en el repo con
    # su evidencia, y "Especial MBP" lo puede regenerar igual.
    e_guardar = {**e, "evidencia_archivo": f"{e['slug']}.evidencia.json"}
    (carpeta / f"{e['slug']}.json").write_text(json.dumps(e_guardar, ensure_ascii=False,
                                                          indent=1), encoding="utf-8")
    (carpeta / f"{e['slug']}.evidencia.json").write_text(json.dumps(r.evidencia, ensure_ascii=False,
                                                       indent=1, default=str),
                                            encoding="utf-8")
    (carpeta / "uso.json").write_text(json.dumps(r.uso, indent=1), encoding="utf-8")
    resumen["editor"] = e["editor"]
    return resumen
