"""Las láminas del carrusel ajustan solas los textos largos: nombres de equipo y titulares
nunca se salen de la lámina ni se pisan (caso real: la propuesta del editor "¿Serie pareja?
Lo que dicen las carreras", 23-oct-2026, que llegó con 5 alertas de diseño)."""
import pytest

from bpt.viz import carrusel_card as C

EQUIPOS = {
    "A": {"nombre": "Rays de Tampa Bay", "liga": "Liga Americana", "color": "#3B82C4"},
    "B": {"nombre": "Cerveceros de Milwaukee", "liga": "Liga Nacional", "color": "#E3B23C"},
}

LAMINAS = [
    {"tipo": "portada", "titulo": "¿SERIE\nPAREJA?", "subtitulo": "Lo que dicen las carreras",
     "datos": {"A": [{"cifra": "+105", "texto": "diferencial de carreras"}],
               "B": [{"cifra": "+128", "texto": "diferencial de carreras"}]}},
    {"tipo": "cara_a_cara", "titulo": "CARA A CARA",
     "filas": [{"stat": "Carreras anotadas", "A": "780", "B": "801", "mejor": "B"},
               {"stat": "Carreras permitidas", "A": "675", "B": "673", "mejor": "B"}]},
    {"tipo": "cifras", "titulo": "¿MUCHAS O POCAS CARRERAS?",
     "items": [{"cifra": "4,8", "texto": "carreras por juego de los Rays"},
               {"cifra": "4,9", "texto": "carreras por juego de los Cerveceros"}]},
    {"tipo": "cifras", "titulo": "PERO LAS CARRERAS DICEN OTRA",
     "items": [{"cifra": "95", "texto": "victorias esperadas"}]},
    {"tipo": "camino", "titulo": "CÓMO LLEGAN",
     "equipos": {k: {"record": "95-67", "record_nota": "temporada regular",
                     "series": [{"ronda": "Serie de Campeonato", "rival": "Guardianes",
                                 "resultado": "4-2"}]} for k in "AB"}},
    {"tipo": "figuras", "titulo": "A QUIÉN SEGUIR",
     "jugadores": {k: [{"rol": "Bate", "nombre": "Jugador", "linea": ".280 / 30 HR"}]
                   for k in "AB"}},
]


@pytest.mark.parametrize("i", range(len(LAMINAS)))
def test_textos_largos_no_se_salen_ni_se_pisan(i, tmp_path):
    problemas: list[str] = []
    C.render_lamina(LAMINAS[i], EQUIPOS, tmp_path / f"{i}.png", pagina=f"{i + 1}/6",
                    problemas=problemas)
    assert problemas == []


def test_nombre_corto_de_equipo():
    assert C._corto("Cerveceros de Milwaukee") == "Cerveceros"
    assert C._corto("Rays de Tampa Bay") == "Rays"
    assert C._corto("Leones del Caracas") == "Leones del Caracas"
    assert C._corto("Tiburones") == "Tiburones"


def test_corto_explicito_manda(tmp_path):
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(C.W, C.H))
    t = C._nombre_equipo(fig, 0.5, 0.5, {"nombre": "Navegantes del Magallanes",
                                         "corto": "Magallanes"}, 0.12, 30, weight="bold")
    assert t.get_text() == "MAGALLANES"
    plt.close(fig)


def test_titulo_corto_queda_igual(tmp_path):
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(C.W, C.H))
    t, tam, lineas = C._titular(fig, C.X0, 0.9, "CARA A CARA", C.ANCHO, 44, weight="bold")
    assert (t.get_text(), tam, lineas) == ("CARA A CARA", 44, 1)
    plt.close(fig)


def test_si_uno_va_corto_los_dos_van_cortos():
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(C.W, C.H))
    assert not C._completos_caben(fig, EQUIPOS, 0.22, 17, weight="bold")
    assert C._completos_caben(fig, {"A": {"nombre": "Rays"}, "B": {"nombre": "Mets"}}, 0.22, 17)
    plt.close(fig)
