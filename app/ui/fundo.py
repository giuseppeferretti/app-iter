"""
Background ambient global — aplicado atrás de todas as telas via main_app.

Composição: 2 discos azul-Iter translúcidos (~5-7% opacity) posicionados em
cantos opostos do viewport. Cria sensação de profundidade e iluminação sutil
sem competir com o conteúdo. Reusa o vocabulário visual do Visual.pdf (páginas
4 e 7 — hero institucional com sphere blue ambient).
"""
import flet as ft

from app.ui.componentes import COR_PRIMARY


def _glow(
    *,
    left: int | None = None,
    right: int | None = None,
    top: int | None = None,
    bottom: int | None = None,
    width: int = 520,
    height: int = 520,
    opacity: float = 0.06,
) -> ft.Container:
    return ft.Container(
        left=left, right=right, top=top, bottom=bottom,
        width=width, height=height,
        bgcolor=COR_PRIMARY,
        opacity=opacity,
        border_radius=width // 2,
    )


def camadas_ambient() -> list[ft.Control]:
    """
    Retorna as camadas (containers) do background global. Lista pronta pra
    spread dentro de um Stack na main_app: `Stack(controls=[*camadas_ambient(),
    conteudo, dev_pill])`.
    """
    return [
        _glow(left=-180, top=80,  width=540, height=540, opacity=0.07),
        _glow(right=-200, bottom=-100, width=480, height=480, opacity=0.05),
        _glow(left=320, top=-160, width=260, height=260, opacity=0.04),
    ]
