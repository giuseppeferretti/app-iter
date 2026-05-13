"""
Tela de boas-vindas (1º uso).

Layout:
  - Wordmark "iTER" centralizado no topo
  - Título centralizado
  - Linha com 2 colunas:
      esquerda: GIF de demonstração
      direita:  bullets explicando o que o app faz
  - Botão "Continuar" centralizado no fim

Compacto, sem scroll. Cabe num 880x640 sem precisar rolar.
"""
import flet as ft

from app.ui.componentes import (
    COR_BG, COR_FG, COR_MUTED_FG,
    botao_primario, iter_wordmark, titulo, texto,
)


def construir(page: ft.Page, ao_continuar) -> ft.Control:
    """Retorna o controle Flet da tela de onboarding."""

    gif_placeholder = ft.Container(
        width=420, height=240,
        bgcolor="#1f1f29",
        border_radius=12,
        content=ft.Text(
            "[ GIF de demonstração será exibido aqui ]",
            color=COR_MUTED_FG, size=12,
        ),
        alignment=ft.Alignment.CENTER,
    )

    bullets = ft.Column(
        spacing=14,
        horizontal_alignment=ft.CrossAxisAlignment.START,
        alignment=ft.MainAxisAlignment.CENTER,
        expand=True,
        controls=[
            texto("✓  Sua planilha .xlsx vira rascunhos no SACI", size=15),
            texto("✓  Funciona no Chrome, Brave, Edge ou Opera", size=15),
            texto("✓  Sem instalar Python ou outra coisa técnica", size=15),
        ],
    )

    return ft.Container(
        bgcolor=COR_BG,
        padding=ft.Padding(40, 40, 40, 40),
        alignment=ft.Alignment.TOP_CENTER,
        expand=True,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=22,
            controls=[
                iter_wordmark(height=64),
                titulo(
                    "Lance suas horas no SACI\nem minutos, não em tardes.",
                    size=32,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=32,
                    controls=[
                        gif_placeholder,
                        ft.Container(width=280, content=bullets),
                    ],
                ),
                botao_primario("Continuar", ao_continuar),
            ],
        ),
    )
