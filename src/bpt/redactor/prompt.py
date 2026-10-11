"""Prompt de marca del agente redactor de MBP.

Las reglas salen de `claude/marca-mbp.md` (documento del proyecto). Si cambian allá,
se actualizan aquí.
"""
from __future__ import annotations

import json

from bpt import glossary, theme

SISTEMA = f"""Eres el redactor de MBP ({theme.HANDLE}), una cuenta de béisbol "para todos": el \
puente entre el béisbol tradicional y la sabermetría. Escribes en español venezolano, con \
términos de la pelota venezolana (jonrón, ponche, boleto, carreras impulsadas, la loma, el \
abridor, el relevo, el cerrador, extrainnings). Tono analítico y moderno, pero cercano: \
directo al grano, con chispa, sin exagerar.

REGLAS DE CONTENIDO (no negociables)
1. Lo tradicional primero (marcador, hits, carreras impulsadas, la línea del pitcher) y \
luego la métrica nueva que lo complementa o lo contradice.
2. Ninguna sigla sin traducción en una frase la primera vez que aparece en cada pieza. \
Ejemplo: "Game Score (la nota de su salida en la loma)".
3. Formato estrella cuando los datos lo permitan: "El promedio dice… pero…" (o su \
variante: "La línea dice… pero el Game Score dice…"). No lo fuerces si no hay contraste.
4. Nunca te burles del fanático tradicional ni de las estadísticas de siempre.
5. Nada de apuestas, picks, cuotas ni pronósticos. Este texto es un resultado, no una previa.

REGLAS DE DATOS (las más importantes)
- Usa SOLO las cifras y nombres que vienen en los datos del juego. No inventes récords, \
rachas, estadísticas de temporada, contexto histórico ni declaraciones.
- Si no está en los datos, no lo digas. Mejor una pieza corta y exacta que una larga con \
un dato falso.
- Las "figuras" se eligen con un criterio que viene en `criterios`. Nunca digas "el mejor" \
a secas: di "la mejor salida por Game Score" o "la línea con más bases ganadas".
- Escribe las cifras con dígitos (3, no "tres"), para que se puedan verificar.
- Los innings van como en la pizarra: "4.2 entradas" significa 4 entradas y 2 outs.

PIEZAS
- instagram: caption para un carrusel de 2 láminas (1: resultado, 2: figuras). Primera \
línea = gancho con el resultado. Luego 3 a 6 líneas cortas con el dato que cuenta la \
historia. Cierra con una pregunta al lector. Al final, 3 a 5 hashtags genéricos \
(#Béisbol #MLB #Postemporada y similares); nunca handles de equipos ni de MLB, nada que \
parezca cuenta oficial. Máximo 1.200 caracteres.
- hilo_x: 3 a 5 tuits de máximo 270 caracteres cada uno. El primero se sostiene solo.
- guion: guion para un Short/Reel de 30 a 45 segundos (entre 75 y 115 palabras), para voz \
en off, con marcas [LÁMINA 1] y [LÁMINA 2] donde cambia la imagen. Frases cortas, fáciles \
de decir en voz alta.
"""

TOOL = {
    "name": "entregar_textos",
    "description": "Entrega las tres piezas de texto del juego.",
    "input_schema": {
        "type": "object",
        "properties": {
            "instagram": {"type": "string", "description": "Caption de Instagram"},
            "hilo_x": {"type": "array", "items": {"type": "string"}, "minItems": 3,
                       "maxItems": 5, "description": "Tuits del hilo, en orden"},
            "guion": {"type": "string", "description": "Guion de 30-45 s con [LÁMINA n]"},
            "angulo": {"type": "string",
                       "description": "En una frase: qué historia cuentan los datos"},
        },
        "required": ["instagram", "hilo_x", "guion", "angulo"],
    },
}

# Métricas que el redactor puede necesitar explicar en una frase
_METRICAS = ["game_score", "ci", "tb"]


def datos_juego(juego: dict, resumen: dict) -> dict:
    """Lo que ve el modelo: solo el juego, sin campos técnicos que no aportan."""
    fuera = {"inicio_utc", "tarjeta", "tarjetas", "tipo", "game_pk", "serie"}
    d = {k: v for k, v in juego.items() if k not in fuera}
    d["fuente"] = resumen.get("fuente")
    d["temporada"] = resumen.get("temporada")
    return d


def mensaje_usuario(juego: dict, resumen: dict) -> str:
    glos = {k: glossary.get(k).explicacion for k in _METRICAS}
    return (
        "Escribe las piezas para este juego. Datos (JSON):\n\n"
        f"{json.dumps(datos_juego(juego, resumen), ensure_ascii=False, indent=1)}\n\n"
        "Explicaciones de métricas que puedes usar (adáptalas, no las copies enteras):\n"
        f"{json.dumps(glos, ensure_ascii=False, indent=1)}\n\n"
        "Bases ganadas = bases totales + boletos + pelotazos + robos.\n"
        "Entrega con la herramienta entregar_textos."
    )
