"""Pasos del workflow publicar.yml, separados para poder probarlos sin red.

1. preparar: busca la pieza en el paquete descargado y deja los JPEG en una carpeta.
2. (bash) esa carpeta se sube a la rama `publicaciones` para tener URLs públicas
   (Instagram y Threads descargan de ahí; a X se le suben los archivos).
3. publicar_redes: publica en cada red pedida (i, t, x) y avisar_resultados lo cuenta en
   Telegram: edita el mismo mensaje si ya no quedan redes en su menú, o responde abajo si
   quedan. Las redes que fallaron traen su botón de reintentar.
4. avisar_fallo: si algo falló antes de publicar, lo mismo con el motivo.
"""
from __future__ import annotations

import json
from pathlib import Path

from dataclasses import dataclass

from bpt.notificar import telegram
from bpt.publicar import instagram, piezas, redes
from bpt.publicar import threads as th
from bpt.publicar import x as xx


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
                 motivo: str, titular: str | None = None, url_run: str | None = None,
                 destino: str = "i", quedan: str = "i") -> None:
    icono = "📲" if titular and titular.startswith("Historia") else "📸"
    base = f"{icono} {titular}" if titular else "📸 Publicación"
    destino, quedan = redes.normalizar(destino) or "i", redes.normalizar(quedan) or "i"
    texto = f"{base}\n\n❌ No se publicó en {redes.nombres(destino)}: {motivo}"
    if url_run:
        texto += f"\nDetalle: {url_run}"
    filas = [[{"text": "🔁 Reintentar",
               "callback_data": telegram.callback_publicar(run_id, pieza_id, destino, destino)}]]
    if redes.menos(quedan, destino):
        tg.botones(texto, filas, responder_a=message_id)   # el menú de las otras redes sigue
    else:
        tg.editar(message_id, texto, filas)


# --- Varias redes -------------------------------------------------------------------

@dataclass
class Resultado:
    red: str                    # i, t o x
    ok: bool
    permalink: str = ""
    motivo: str = ""
    parcial: bool = False       # hilo a medias: no se ofrece reintentar (saldría repetido)
    duplicado: bool = False
    media_id: str = ""          # id de la publicación en la red (para las métricas)

    def linea(self, historia: bool = False) -> str:
        nombre = redes.NOMBRES[self.red]
        if self.ok:
            que = ("historia publicada (dura 24 h)" if historia and self.red == "i"
                   else "ya estaba publicado" if self.duplicado else "publicado")
            return f"✅ {nombre}: {que}\n{self.permalink}".rstrip()
        if self.parcial:
            return f"⚠️ {nombre}: {self.motivo}\n{self.permalink}".rstrip()
        return f"❌ {nombre}: {self.motivo}"


ERRORES = (instagram.InstagramError, th.ThreadsError, xx.XError, OSError, KeyError)


def publicar_redes(plan: dict, destino: str, base_url: str | None, carpeta_jpeg: Path,
                   clientes: dict) -> list[Resultado]:
    """Publica la pieza en cada red de `destino`. `clientes` = {letra: función que devuelve
    el cliente}; se llama recién al publicar, así una red sin secretos no frena a las otras."""
    archivos = plan.get("archivos", [])
    urls = [base_url.rstrip("/") + "/" + rel for rel in archivos] if base_url else []
    historia = plan.get("tipo") == piezas.HISTORIA
    reel = plan.get("tipo") == piezas.REEL
    salida: list[Resultado] = []
    for red in redes.normalizar(destino):
        try:
            if red in "it" and not (base_url or "").startswith("https://"):
                raise instagram.InstagramError("la URL base de las imágenes debe ser https")
            cliente = clientes[red]()
            if red == "i":
                hecho = (cliente.publicar_historia(urls[0]) if historia
                         else cliente.publicar_reel(urls[0], plan["caption"]) if reel
                         else cliente.publicar(urls, plan["caption"]))
            elif historia:
                raise th.ThreadsError("las historias solo existen en Instagram")
            elif reel:
                raise th.ThreadsError("los Reels por ahora solo van a Instagram")
            elif red == "t":
                hecho = cliente.publicar_hilo(urls, plan.get("hilo") or [])
            else:
                hecho = cliente.publicar_hilo([Path(carpeta_jpeg) / a for a in archivos],
                                              plan.get("hilo") or [])
            salida.append(Resultado(red, True, hecho.permalink, duplicado=hecho.duplicado,
                                    media_id=str(hecho.media_id or "")))
        except (th.PublicacionParcial, xx.PublicacionParcial) as e:
            salida.append(Resultado(red, False, e.permalink, str(e), parcial=True))
        except ERRORES as e:
            salida.append(Resultado(red, False, motivo=str(e)))
    return salida


def registro(plan: dict, resultados: list[Resultado], run_id: str,
             ahora: str | None = None) -> list[dict]:
    """Una fila por red publicada, para la rama `metricas` (publicaciones.jsonl). Los
    duplicados no se registran (ya se registraron la primera vez)."""
    from datetime import datetime, timezone
    ahora = ahora or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return [{"fecha_utc": ahora, "run_id": str(run_id), "pieza": plan.get("pieza"),
             "titular": plan.get("titular"), "tipo": plan.get("tipo", "post"),
             "formato": plan.get("formato", "resultado"), "red": r.red,
             "media_id": r.media_id, "permalink": r.permalink,
             "laminas": len(plan.get("archivos", []))}
            for r in resultados if r.ok and not r.duplicado and r.media_id]


def avisar_resultados(tg: telegram.Telegram, plan: dict, resultados: list[Resultado],
                      run_id: str, message_id: str, destino: str, quedan: str) -> None:
    historia = plan.get("tipo") == piezas.HISTORIA
    texto = _base(plan) + "\n\n" + "\n".join(r.linea(historia) for r in resultados)
    fallidas = "".join(r.red for r in resultados if not r.ok and not r.parcial)
    filas = []
    if fallidas:
        filas = [[{"text": f"🔁 Reintentar en {redes.nombres(fallidas)}",
                   "callback_data": telegram.callback_publicar(run_id, plan["pieza"],
                                                               fallidas, fallidas)}]]
    if redes.menos(quedan, destino):
        tg.botones(texto, filas, responder_a=message_id)
    else:
        tg.editar(message_id, texto, filas)
