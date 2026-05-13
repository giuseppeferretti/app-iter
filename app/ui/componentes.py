"""
Widgets Flet reutilizáveis (botões, cards, badges, logo) com a identidade Iter.
"""
from typing import Optional

import flet as ft

# Cores Iter (mesma paleta da landing — dark-first)
COR_BG          = "#0b0b0e"      # background quase-preto frio
COR_FG          = "#f5ecd8"      # foreground bege quente
COR_MUTED       = "#1f1f29"
COR_MUTED_FG    = "#8a8482"
COR_PRIMARY     = "#2b6bff"      # azul elétrico — brand Iter oficial
COR_PRIMARY_FG  = "#f5ecd8"
COR_WARMTH      = "#d4b48c"      # bege quente acento
COR_BORDER      = "#262630"
COR_SUCCESS     = "#22c55e"
COR_ERROR       = "#ef4444"


def botao_primario(texto: str, on_click) -> ft.ElevatedButton:
    return ft.ElevatedButton(
        content=texto,
        on_click=on_click,
        bgcolor=COR_PRIMARY,
        color=COR_PRIMARY_FG,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding(20, 14, 20, 14),
        ),
    )


def botao_secundario(texto: str, on_click) -> ft.OutlinedButton:
    return ft.OutlinedButton(
        content=texto,
        on_click=on_click,
        style=ft.ButtonStyle(
            color=COR_FG,
            side=ft.BorderSide(1, COR_BORDER),
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding(20, 14, 20, 14),
        ),
    )


def card(conteudo: ft.Control, padding: int = 24) -> ft.Container:
    return ft.Container(
        content=conteudo,
        padding=padding,
        bgcolor=COR_MUTED,
        border=ft.Border.all(1, COR_BORDER),
        border_radius=12,
    )


def eyebrow(texto: str) -> ft.Text:
    return ft.Text(
        texto.upper(),
        size=11,
        weight=ft.FontWeight.W_600,
        color=COR_WARMTH,
        style=ft.TextStyle(letter_spacing=3),
    )


def titulo(
    texto: str,
    size: int = 28,
    text_align: Optional[ft.TextAlign] = None,
) -> ft.Text:
    return ft.Text(
        texto,
        size=size,
        weight=ft.FontWeight.W_500,
        color=COR_FG,
        text_align=text_align,
    )


def iter_wordmark(height: int = 56) -> ft.Image:
    """
    Wordmark Iter completo: "iTER" (i oficial com dot azul + glow + stem,
    seguido de TER em Segoe UI Black off-white). Fundo transparente.

    Para uso destacado no onboarding (tela de entrada do app).
    Lê de `iter-wordmark.png` no assets_dir.
    """
    return ft.Image(
        src="iter-wordmark.png",
        height=height,
        fit=ft.BoxFit.CONTAIN,
    )


def iter_wordmark_footer(
    height: int = 18,
    opacity: float = 0.35,
) -> ft.Container:
    """
    Wordmark Iter pequeno e fade para uso no rodapé das telas operacionais.
    Marca presença sem competir com a UI principal.
    """
    return ft.Container(
        content=ft.Image(
            src="iter-wordmark.png",
            height=height,
            fit=ft.BoxFit.CONTAIN,
        ),
        opacity=opacity,
    )


def texto(conteudo: str, color: str = COR_FG, size: int = 14) -> ft.Text:
    return ft.Text(conteudo, size=size, color=color)
