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
    bpt llave                                     # probar la llave de la API (sin gastar)
    bpt telegram-chat                             # ver tu TELEGRAM_CHAT_ID
    bpt notificar --fecha 2026-10-11              # mandar el paquete del día a Telegram
    bpt lvbp-resultados --redactar                # jornada LVBP de ayer (hora de Venezuela)
    bpt telegram-webhook --url https://mbp-telegram-relay.<cuenta>.workers.dev   # conectar el relé
    bpt instagram-prueba                          # revisar el token de Instagram (no publica)
    bpt publicar-piezas --carpeta output/resultados/lvbp/2026-10-15   # qué se puede publicar
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
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
    try:
        f = date.fromisoformat(fecha)
    except ValueError:
        print(f"[error] Fecha inválida: {fecha}. Formato AAAA-MM-DD (año-mes-día)",
              file=sys.stderr)
        return 1
    hoy = datetime.now(resultados.TZ_MLB).date()
    if f > hoy:
        print(f"[error] {fecha} es una fecha futura. El formato es AAAA-MM-DD: "
              f"el 11 de octubre es {f.year}-10-11, no {fecha}", file=sys.stderr)
        return 1
    r = resultados.generar(fecha, temporada=args.temporada, tipo=tipo, salida=Path(args.salida),
                           handle=args.handle, refresh=not args.cache)
    carpeta = Path(args.salida) / fecha
    for j in r["juegos"]:
        serie = j["estado_serie"]["texto"] if j["estado_serie"] else ""
        print(f"[ok] {j['serie_corto']} J{j['juego_n']}: {j['titular']}  ({serie})")
    for p in r["pendientes"]:
        print(f"[--] {p['serie']} J{p['juego_n']} {p['partido']}: {p['estado']}")
    if not r["juegos"] and not r["pendientes"]:
        if r.get("otras_fases"):
            fases = ", ".join(f"--fase {k} ({v})" for k, v in r["otras_fases"].items())
            print(f"[!!] No hubo juegos de {r['fase']} el {fecha}, pero sí de otra fase: "
                  f"usa {fases}")
            return 2
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
    except Exception as e:  # noqa: BLE001 - errores de la API de Claude, sin traceback
        if type(e).__module__.startswith("anthropic"):
            detalle = getattr(e, "message", str(e))
            print(f"[error] La API de Claude respondió {type(e).__name__}: {detalle}",
                  file=sys.stderr)
            return 1
        raise
    for r in res:
        marca = "ok" if r["validacion"]["ok"] else "!!"
        print(f"[{marca}] {r['partido']}: {r['estado']} (intentos: {r['intentos']})")
        for c in r["validacion"]["cifras_sin_respaldo"]:
            print(f"     cifra sin respaldo: {c}")
        for a in r["validacion"]["alertas"]:
            print(f"     {a}")
    if res:
        u = agente.resumen_uso(res)
        costo = f" · ~US$ {u['costo_usd']:.4f}" if u["costo_usd"] is not None else ""
        print(f"Uso: {u['entrada'] + u['cache_escrito'] + u['cache_leido']} tokens de entrada "
              f"({u['cache_leido']} leídos del caché, {u['cache_escrito']} escritos), "
              f"{u['salida']} de salida{costo}")
        print(f"Textos: {carpeta / 'textos.md'}")
    else:
        print("[--] No hay juegos terminados para redactar")
    return 0


def cmd_llave(args: argparse.Namespace) -> int:
    from bpt.redactor import agente
    try:
        print(f"[ok] {agente.verificar_llave()}")
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1
    return 0


def _carpeta_mlb(args: argparse.Namespace) -> Path:
    from bpt import resultados
    if getattr(args, "carpeta", None):
        return Path(args.carpeta)
    return Path(args.salida) / (args.fecha or resultados.ayer_mlb())


def cmd_lvbp_results(args: argparse.Namespace) -> int:
    from bpt import lvbp_resultados as L
    fecha = args.fecha or L.ayer_ven()
    try:
        f = date.fromisoformat(fecha)
    except ValueError:
        print(f"[error] Fecha inválida: {fecha}. Formato AAAA-MM-DD", file=sys.stderr)
        return 1
    if f > datetime.now(L.TZ_VEN).date():
        print(f"[error] {fecha} es una fecha futura (formato AAAA-MM-DD)", file=sys.stderr)
        return 1
    r = L.generar(fecha, salida=Path(args.salida), handle=args.handle, refresh=not args.cache)
    carpeta = Path(args.salida) / fecha
    for j in r["juegos"]:
        v, lo = j["visitante"], j["local"]
        print(f"[ok] {j['titular']}  ({v['abrev']} {v['record']}, {lo['abrev']} {lo['record']})")
    for p in r["pendientes"]:
        print(f"[--] {p['partido']}: {p['estado']}")
    if not r["juegos"] and not r["pendientes"]:
        print(f"[--] No hubo juegos de la LVBP el {fecha}")
    d = r["destacados"]
    print(f"Destacados: {len(d['bateo'])} al bate, {len(d['pitcheo'])} en la loma, "
          f"{len(d['jonrones'])} jonrón(es) · Láminas: {', '.join(r['tarjetas']) or '-'}")
    print(f"Resumen: {carpeta / 'resumen.json'}")
    if args.redactar and r["juegos"]:
        return _redactar(carpeta, args.modelo)
    return 0


def cmd_historia(args: argparse.Namespace) -> int:
    from bpt import historia
    fecha = args.fecha or historia.hoy_ven()
    try:
        date.fromisoformat(fecha)
    except ValueError:
        print(f"[error] Fecha inválida: {fecha}. Formato AAAA-MM-DD", file=sys.stderr)
        return 1
    r = historia.generar(fecha, salida=Path(args.salida), handle=args.handle)
    carpeta = Path(args.salida) / fecha
    if not r["total"]:
        print(f"[--] {fecha}: no hay juegos de MLB ni de LVBP. No se genera historia.")
    for liga, datos in r["ligas"].items():
        fase = f" ({datos['fase']})" if datos["fase"] else ""
        print(f"{liga}{fase}: {len(datos['juegos'])} juego(s)")
        for j in datos["juegos"]:
            extra = f" · {j['abridores']}" if j["abridores"] else ""
            print(f"  {j['hora']:>12}  {j['visitante']} @ {j['local']}{extra}")
    if r["tarjetas"]:
        print(f"[ok] Historia: {carpeta / r['tarjetas'][0]}")
    print(f"Resumen: {carpeta / 'resumen.json'}")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            f.write(f"carpeta={carpeta}\ntotal={r['total']}\n")
    return 0


def cmd_especial(args: argparse.Namespace) -> int:
    from bpt import especial
    try:
        r = especial.generar(Path(args.archivo), salida=Path(args.salida), handle=args.handle)
    except (especial.EspecialError, FileNotFoundError, KeyError) as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1
    print(f"[ok] {r['titular']}")
    print(f"     Láminas: {', '.join(r['tarjetas'])}")
    if r.get("verificacion"):
        print(f"     {r['verificacion']['resumen']}")
    for a in r["alertas"]:
        print(f"  ⚠️ {a}")
    print(f"Carpeta: {r['carpeta']}")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            f.write(f"carpeta={r['carpeta']}\n")
    return 0


def cmd_editor(args: argparse.Namespace) -> int:
    """Agente editor: busca la historia, consulta los datos y arma un especial verificado."""
    from bpt import editor
    from bpt.editor.agente import EditorError
    from bpt.historia import hoy_ven
    from bpt.redactor.agente import LlaveInvalida

    fecha = args.fecha or hoy_ven()
    aprendizajes = None
    if args.aprendizajes and Path(args.aprendizajes).exists():
        aprendizajes = Path(args.aprendizajes).read_text(encoding="utf-8").strip() or None
    tema = (args.tema or "").strip() or None
    print(f"🧠 Editor MBP · {fecha}" + (f" · tema: {tema}" if tema else " · tema libre"))
    try:
        r = editor.ejecutar(fecha, tema, salida=Path(args.salida), handle=args.handle,
                            aprendizajes=aprendizajes)
    except (EditorError, LlaveInvalida, RuntimeError) as e:
        print(f"[error] Editor: {e}", file=sys.stderr)
        return 1
    ed = r["editor"]
    print(f"[ok] {r['titular']}")
    print(f"     Por qué: {ed['por_que']}")
    print(f"     Láminas: {', '.join(r['tarjetas'])}")
    print(f"     {r['verificacion']['resumen']}")
    for a in r["alertas"]:
        print(f"  ⚠️ {a}")
    costo = ed.get("costo_usd")
    print(f"     {ed['consultas']} consultas · {ed['vueltas']} vueltas · "
          f"{ed['correcciones']} correcciones" + (f" · ~US$ {costo:.3f}" if costo else ""))
    for i in ed["otras_ideas"]:
        print(f"     💡 {i}")
    print(f"Carpeta: {r['carpeta']}")
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            f.write(f"carpeta={r['carpeta']}\n")
    return 0


def cmd_verificar(args: argparse.Namespace) -> int:
    """Verifica un especial sin dibujarlo: cifras, evidencia, hechos y reglas de marca."""
    import json

    from bpt import especial, verificador
    try:
        datos = especial.cargar(Path(args.archivo))
    except (especial.EspecialError, FileNotFoundError, KeyError, ValueError) as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1
    evidencia = (json.loads(Path(args.evidencia).read_text(encoding="utf-8"))
                 if args.evidencia else None)
    v = verificador.verificar(datos, evidencia=evidencia, hechos=not args.sin_hechos)
    print(v.resumen())
    if v.cifras_sin_respaldo:
        print("  ❌ Cifras sin respaldo: " + ", ".join(v.cifras_sin_respaldo))
    for a in v.alertas:
        print(f"  ⚠️ {a}")
    if v.ok:
        print("  ✅ Todo en orden")
    return 0 if v.ok else 2


def cmd_notificar(args: argparse.Namespace) -> int:
    from bpt.notificar import telegram
    carpeta = _carpeta_mlb(args)
    if not (carpeta / "resumen.json").exists():
        print(f"[error] No existe {carpeta / 'resumen.json'}", file=sys.stderr)
        return 1
    try:
        n = telegram.enviar_dia(carpeta, originales=not args.sin_originales)
    except telegram.TelegramError as e:
        print(f"[error] Telegram: {e}", file=sys.stderr)
        return 1
    print(f"[ok] Telegram: {n} juego(s) enviado(s)")
    return 0


def cmd_telegram_chat(args: argparse.Namespace) -> int:
    from bpt.notificar import telegram
    from bpt.redactor.agente import cargar_env
    import os
    cargar_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not telegram.es_token_valido(token):
        print("[error] TELEGRAM_BOT_TOKEN falta o no tiene la forma 123456789:ABC... "
              "(cópialo completo de @BotFather al .env)", file=sys.stderr)
        return 1
    try:
        chats = telegram.chats_recientes(token)
    except telegram.TelegramError as e:
        print(f"[error] Telegram: {e}", file=sys.stderr)
        if "webhook" in str(e).lower():
            print("       El relé de botones está conectado: 'bpt telegram-webhook --quitar', "
                  "busca el chat y vuelve a conectarlo", file=sys.stderr)
        return 1
    if not chats:
        print("[--] Nadie le ha escrito al bot todavía: ábrelo en Telegram, mándale /start "
              "y vuelve a correr este comando")
        return 1
    for c in chats:
        quien = c["nombre"] + (f" (@{c['usuario']})" if c["usuario"] else "")
        print(f"[ok] TELEGRAM_CHAT_ID={c['id']}   <- {c['tipo']}: {quien}")
    print("Copia esa línea al .env (y como secreto en GitHub)")
    return 0


def cmd_telegram_prueba(args: argparse.Namespace) -> int:
    from bpt.notificar import telegram
    try:
        telegram.Telegram(*telegram.credenciales()).texto(args.texto)
    except telegram.TelegramError as e:
        print(f"[error] Telegram: {e}", file=sys.stderr)
        return 1
    print("[ok] Mensaje enviado")
    return 0


def cmd_telegram_webhook(args: argparse.Namespace) -> int:
    import os
    import secrets as _secrets
    from bpt.notificar import telegram
    from bpt.redactor.agente import cargar_env
    cargar_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not telegram.es_token_valido(token):
        print("[error] TELEGRAM_BOT_TOKEN falta o no es válido", file=sys.stderr)
        return 1
    try:
        if args.quitar:
            telegram.quitar_webhook(token)
            print("[ok] Relé desconectado: los botones dejan de responder y "
                  "'bpt telegram-chat' vuelve a funcionar")
            return 0
        if not args.url:
            info = telegram.info_webhook(token)
            if info.get("url"):
                print(f"[ok] Relé conectado: {info['url']}")
                print(f"     Pendientes: {info.get('pending_update_count', 0)}"
                      + (f" · Último error: {info['last_error_message']}"
                         if info.get("last_error_message") else ""))
            else:
                print("[--] Sin relé: usa --url https://<tu-worker>.workers.dev")
            return 0
        secreto = args.secreto or _secrets.token_urlsafe(32)
        telegram.poner_webhook(token, args.url, secreto)
    except telegram.TelegramError as e:
        print(f"[error] Telegram: {e}", file=sys.stderr)
        return 1
    print(f"[ok] Telegram ya le avisa al relé: {args.url}")
    if not args.secreto:
        print("Guarda este valor en el Worker como secreto TELEGRAM_WEBHOOK_SECRET:")
        print(secreto)
    return 0


def cmd_instagram_prueba(args: argparse.Namespace) -> int:
    from bpt.publicar import instagram
    try:
        ig = instagram.Instagram(*instagram.credenciales())
        c = ig.cuenta()
        lim = ig.limite()
    except instagram.InstagramError as e:
        print(f"[error] Instagram: {e}", file=sys.stderr)
        return 1
    uso = lim.get("quota_usage", "?")
    tope = (lim.get("config") or {}).get("quota_total", "?")
    print(f"[ok] Cuenta @{c.get('username')} ({c.get('account_type')}) · IG_USER_ID={c.get('user_id')}")
    print(f"[ok] Publicaciones por API en las últimas 24 h: {uso} de {tope}")
    return 0


def cmd_publicar_piezas(args: argparse.Namespace) -> int:
    from bpt.publicar import piezas
    try:
        lista = piezas.piezas(Path(args.carpeta))
    except FileNotFoundError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1
    if not lista:
        print("[--] Nada publicable: hacen falta láminas y caption (textos.json)")
        return 1
    for p in lista:
        marca = "⚠️" if p.tiene_alertas else "✅"
        print(f"{marca} pieza {p.id}: {p.titular} · {len(p.imagenes)} lámina(s) · "
              f"{len(p.caption)} caracteres")
    return 0


def cmd_publicar_preparar(args: argparse.Namespace) -> int:
    from bpt.publicar import flujo, piezas
    try:
        plan = flujo.preparar(Path(args.carpeta), args.pieza, Path(args.destino), args.prefijo,
                              Path(args.plan))
    except (piezas.PiezaError, FileNotFoundError) as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1
    print(f"[ok] Pieza {plan['pieza']} · {plan['titular']} · {len(plan['archivos'])} JPEG")
    for a in plan["alertas"]:
        print(f"  ⚠️ {a}")
    return 0


def _tg_opcional():
    from bpt.notificar import telegram
    try:
        return telegram.Telegram(*telegram.credenciales())
    except telegram.TelegramError:
        return None


def cmd_publicar_instagram(args: argparse.Namespace) -> int:
    import json
    from bpt.notificar import telegram
    from bpt.publicar import flujo, instagram
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    tg = _tg_opcional() if args.message_id else None
    try:
        ig = instagram.Instagram(*instagram.credenciales())
        hecho = flujo.publicar_instagram(plan, args.base_url, ig, tg, args.message_id)
    except (instagram.InstagramError, telegram.TelegramError) as e:
        print(f"[error] {e}", file=sys.stderr)
        Path(args.motivo).write_text(str(e), encoding="utf-8")
        return 1
    tipo = "ya estaba publicado" if hecho.duplicado else "publicado"
    print(f"[ok] Instagram: {tipo} · {hecho.permalink}")
    return 0


def cmd_publicar_fallo(args: argparse.Namespace) -> int:
    from bpt.notificar import telegram
    from bpt.publicar import flujo
    tg = _tg_opcional()
    if tg is None or not args.message_id:
        return 0
    motivo = args.texto or "falló el workflow de publicación"
    if args.motivo and Path(args.motivo).exists():
        motivo = Path(args.motivo).read_text(encoding="utf-8").strip() or motivo
    try:
        flujo.avisar_fallo(tg, args.message_id, args.run_id, args.pieza, motivo[:600],
                           titular=args.titular, url_run=args.url_run,
                           destino=args.destino, quedan=args.quedan or args.destino)
    except telegram.TelegramError as e:
        print(f"[error] Telegram: {e}", file=sys.stderr)
        return 1
    return 0


def _clientes() -> dict:
    """Fábricas de clientes por red: se crean recién al publicar (sin secretos = error de
    esa red, no de todas)."""
    from bpt.publicar import instagram, threads, x
    return {
        "i": lambda: instagram.Instagram(*instagram.credenciales()),
        "t": lambda: threads.Threads(*threads.credenciales()),
        "x": lambda: x.X(x.autenticacion(*x.credenciales()), secretos=x.credenciales()),
    }


def cmd_publicar_redes(args: argparse.Namespace) -> int:
    import json
    from bpt.notificar import telegram
    from bpt.publicar import flujo, redes
    destino = redes.normalizar(args.destino)
    quedan = redes.normalizar(args.quedan or destino)
    if not destino:
        print("[error] destino inválido (letras i, t, x)", file=sys.stderr)
        return 1
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    resultados = flujo.publicar_redes(plan, destino, args.base_url, Path(args.carpeta),
                                      _clientes())
    for r in resultados:
        print(("[ok] " if r.ok else "[error] ") + r.linea(plan.get("tipo") == "historia")
              .replace("\n", " · "))
    tg = _tg_opcional() if args.message_id else None
    if tg:
        try:
            flujo.avisar_resultados(tg, plan, resultados, args.run_id, args.message_id,
                                    destino, quedan)
            Path(args.avisado).write_text("ok", encoding="utf-8")
        except telegram.TelegramError as e:
            print(f"[error] Telegram: {e}", file=sys.stderr)
    malos = [r for r in resultados if not r.ok]
    if malos:
        Path(args.motivo).write_text("; ".join(f"{redes.NOMBRES[r.red]}: {r.motivo}"
                                               for r in malos), encoding="utf-8")
        return 1
    return 0


def cmd_threads_prueba(args: argparse.Namespace) -> int:
    from bpt.publicar import threads
    try:
        t = threads.Threads(*threads.credenciales())
        c = t.cuenta()
        lim = t.limite()
    except threads.ThreadsError as e:
        print(f"[error] Threads: {e}", file=sys.stderr)
        return 1
    uso = lim.get("quota_usage", "?")
    tope = (lim.get("config") or {}).get("quota_total", "?")
    print(f"[ok] Cuenta @{c.get('username')} · THREADS_USER_ID={c.get('id')}")
    print(f"[ok] Posts por API en las últimas 24 h: {uso} de {tope}")
    return 0


def cmd_x_prueba(args: argparse.Namespace) -> int:
    from bpt.publicar import x
    try:
        cred = x.credenciales()
        c = x.X(x.autenticacion(*cred), secretos=cred).cuenta()
    except x.XError as e:
        print(f"[error] X: {e}", file=sys.stderr)
        return 1
    print(f"[ok] Cuenta @{c.get('username')} ({c.get('name')}) · id {c.get('id')}")
    print("     Ojo: en X cada llamada se cobra (esta lectura también, aunque poco).")
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

    lr = sub.add_parser("lvbp-resultados",
                        help="Carrusel de la jornada LVBP (marcadores + destacados) y resumen.json")
    lr.add_argument("--fecha", default=None, help="YYYY-MM-DD; por defecto, ayer (hora de Venezuela)")
    lr.add_argument("--salida", default="output/resultados/lvbp")
    lr.add_argument("--handle", default=theme.HANDLE)
    lr.add_argument("--cache", action="store_true", help="Usar la caché local")
    lr.add_argument("--redactar", action="store_true", help="Además, redactar los textos")
    lr.add_argument("--modelo", default=None)
    lr.set_defaults(func=cmd_lvbp_results)

    hi = sub.add_parser("historia", help="Historia de Instagram con los juegos de hoy (MLB y LVBP)")
    hi.add_argument("--fecha", default=None, help="YYYY-MM-DD; por defecto, hoy (hora de Venezuela)")
    hi.add_argument("--salida", default="output/historia")
    hi.add_argument("--handle", default=theme.HANDLE)
    hi.add_argument("--github-output", default=None, help=argparse.SUPPRESS)
    hi.set_defaults(func=cmd_historia)

    es = sub.add_parser("especial", help="Láminas y textos de un especial (content/especiales/*.json)")
    es.add_argument("--archivo", required=True)
    es.add_argument("--salida", default="output/especiales")
    es.add_argument("--handle", default=theme.HANDLE)
    es.add_argument("--github-output", default=None, help=argparse.SUPPRESS)
    es.set_defaults(func=cmd_especial)

    ed = sub.add_parser("editor", help="Agente editor: propone y arma un especial verificado")
    ed.add_argument("--fecha", default=None, help="AAAA-MM-DD; por defecto, hoy (hora de Venezuela)")
    ed.add_argument("--tema", default=None, help="Tema pedido; vacío = el agente elige")
    ed.add_argument("--salida", default="output/editor")
    ed.add_argument("--handle", default=theme.HANDLE)
    ed.add_argument("--aprendizajes", default=None, help="Archivo con lo aprendido de las métricas")
    ed.add_argument("--github-output", default=None, help=argparse.SUPPRESS)
    ed.set_defaults(func=cmd_editor)

    ve = sub.add_parser("verificar", help="Verificar las cifras de un especial (sin dibujarlo)")
    ve.add_argument("--archivo", required=True)
    ve.add_argument("--evidencia", default=None, help="JSON con la evidencia (reemplaza la del especial)")
    ve.add_argument("--sin-hechos", action="store_true", help="No consultar MLB Stats API")
    ve.set_defaults(func=cmd_verificar)

    nt = sub.add_parser("notificar", help="Enviar el paquete del día a Telegram")
    nt.add_argument("--fecha", default=None, help="YYYY-MM-DD; por defecto, ayer (hora del Este)")
    nt.add_argument("--carpeta", default=None, help="Carpeta con resumen.json (ignora --fecha)")
    nt.add_argument("--salida", default="output/resultados/mlb",
                    help="output/resultados/mlb o output/resultados/lvbp")
    nt.add_argument("--sin-originales", action="store_true",
                    help="No mandar las láminas como archivo (solo el álbum de vista previa)")
    nt.set_defaults(func=cmd_notificar)

    tc = sub.add_parser("telegram-chat", help="Mostrar el TELEGRAM_CHAT_ID (tras mandarle /start al bot)")
    tc.set_defaults(func=cmd_telegram_chat)

    tp = sub.add_parser("telegram-prueba", help="Mandarte un mensaje de prueba por Telegram")
    tp.add_argument("texto", nargs="?", default="⚾ Hola Noe, soy el bot de MBP. ¡Funciono!")
    tp.set_defaults(func=cmd_telegram_prueba)

    ll = sub.add_parser("llave", help="Probar la llave de la API (no gasta créditos)")
    ll.set_defaults(func=cmd_llave)

    tw = sub.add_parser("telegram-webhook",
                        help="Conectar (o revisar) el relé que atiende los botones")
    tw.add_argument("--url", default=None, help="URL del Worker (https://...workers.dev)")
    tw.add_argument("--secreto", default=None,
                    help="Secreto compartido con el Worker (si falta, se genera uno)")
    tw.add_argument("--quitar", action="store_true", help="Desconectar el relé")
    tw.set_defaults(func=cmd_telegram_webhook)

    ip = sub.add_parser("instagram-prueba",
                        help="Revisar el token de Instagram y la cuota (no publica nada)")
    ip.set_defaults(func=cmd_instagram_prueba)

    pp = sub.add_parser("publicar-piezas", help="Listar las piezas publicables de un paquete")
    pp.add_argument("--carpeta", required=True)
    pp.set_defaults(func=cmd_publicar_piezas)

    pr = sub.add_parser("publicar-preparar", help="(workflow) JPEG y plan de una pieza")
    pr.add_argument("--carpeta", required=True, help="Paquete del día (con resumen.json)")
    pr.add_argument("--pieza", required=True, help="1, 2... (MLB) o jornada (LVBP)")
    pr.add_argument("--destino", required=True, help="Carpeta que se hará pública")
    pr.add_argument("--prefijo", required=True, help="Subcarpeta dentro de --destino")
    pr.add_argument("--plan", required=True, help="Dónde escribir el plan.json")
    pr.set_defaults(func=cmd_publicar_preparar)

    pi = sub.add_parser("publicar-instagram", help="(workflow) Publicar un plan en Instagram")
    pi.add_argument("--plan", required=True)
    pi.add_argument("--base-url", required=True, help="URL pública donde quedaron los JPEG")
    pi.add_argument("--message-id", default=None, help="Mensaje de Telegram a actualizar")
    pi.add_argument("--motivo", default="motivo.txt", help="Si falla, el motivo queda aquí")
    pi.set_defaults(func=cmd_publicar_instagram)

    pf = sub.add_parser("publicar-fallo", help="(workflow) Avisar el fallo en Telegram")
    pf.add_argument("--message-id", default=None)
    pf.add_argument("--run-id", required=True)
    pf.add_argument("--pieza", required=True)
    pf.add_argument("--titular", default=None)
    pf.add_argument("--motivo", default="motivo.txt")
    pf.add_argument("--texto", default=None)
    pf.add_argument("--url-run", default=None)
    pf.add_argument("--destino", default="i")
    pf.add_argument("--quedan", default=None)
    pf.set_defaults(func=cmd_publicar_fallo)

    pz = sub.add_parser("publicar-redes", help="(workflow) Publicar un plan en Instagram, Threads y/o X")
    pz.add_argument("--plan", required=True)
    pz.add_argument("--destino", default="i", help="Letras de red: i=Instagram, t=Threads, x=X")
    pz.add_argument("--quedan", default=None, help="Redes que tenía el menú (por defecto, destino)")
    pz.add_argument("--base-url", default=None, help="URL pública de los JPEG (Instagram y Threads)")
    pz.add_argument("--carpeta", default="publico", help="Carpeta local de los JPEG (X)")
    pz.add_argument("--run-id", default="0", help="Run del paquete (para el botón de reintentar)")
    pz.add_argument("--message-id", default=None, help="Mensaje de Telegram del botón")
    pz.add_argument("--motivo", default="motivo.txt")
    pz.add_argument("--avisado", default="avisado.txt",
                    help="Se crea si el resultado ya se avisó en Telegram")
    pz.set_defaults(func=cmd_publicar_redes)

    tp2 = sub.add_parser("threads-prueba", help="Probar el token de Threads (no publica)")
    tp2.set_defaults(func=cmd_threads_prueba)

    xp = sub.add_parser("x-prueba", help="Probar las credenciales de X (no publica; cobra una lectura)")
    xp.set_defaults(func=cmd_x_prueba)

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
