"""Pasos del workflow publicar.yml, separados para poder probarlos sin red.

1. preparar: busca la pieza en el paquete descargado y deja los JPEG en una carpeta.
2. (bash) esa carpeta se sube a la rama `publicaciones` para tener URLs públicas.
3. publicar_instagram: publica con esas URLs y edita el mensaje de Telegram con el enlace.
4. avisar_fallo: si algo falló, el mensaje de Telegram lo dice y ofrece reintentar.
"""
from __future__ import annotations

import json
from pathlib import Path

from bpt.notificar import telegram
from bpt.publicar import instagram, piezas


def preparar(carpeta: Path, pieza_id: str, destino: Path, prefijo: str, plan_path: Path) -> dict:
    pieza = piezas.buscar(carpeta, pieza_id)
    plan = piezas.preparar(pieza, destino, prefijo)
    Path(plan_path).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan


def _base(plan: dict) -> str:
    icono = "📲" if plan.get("tipo") == piezas.HISTORIA else "📸"
    return f"{icono} {plan.get('titular', 'Pieza')}"


def publicar_instagram(plan: dict, base_url: str, ig: instagram.Instagram,
                       tg: telegram.Telegram | None = None,
                       message_id: str | None = None) -> instagram.Publicado:
    if not base_url.startswith("https://"):
        raise instagram.InstagramError("la URL base de las imágenes debe ser https")
    urls = [base_url.rstrip("/") + "/" + rel for rel in plan["archivos"]]
    historia = plan.get("tipo") == piezas.HISTORIA
    hecho = ig.publicar_historia(urls[0]) if historia else ig.publicar(urls, plan["caption"])
    if tg and message_id:
        if historia:
            estado = "✅ Historia publicada en Instagram (dura 24 h)"
        elif hecho.duplicado:
            estado = "✅ Ya estaba publicado en Instagram"
        else:
            estado = "✅ Publicado en Instagram"
        tg.editar(message_id, f"{_base(plan)}\n\n{estado}\n{hecho.permalink}".rstrip())
    return hecho


def avisar_fallo(tg: telegram.Telegram, message_id: str, run_id: str, pieza_id: str,
                 motivo: str, titular: str | None = None, url_run: str | None = None) -> None:
    icono = "📲" if titular and titular.startswith("Historia") else "📸"
    base = f"{icono} {titular}" if titular else "📸 Publicación"
    texto = f"{base}\n\n❌ No se publicó: {motivo}"
    if url_run:
        texto += f"\nDetalle: {url_run}"
    filas = [[{"text": "🔁 Reintentar",
               "callback_data": telegram.callback_publicar(run_id, pieza_id)}]]
    tg.editar(message_id, texto, filas)
