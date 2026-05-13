"""
Tela de relatório — histórico das sessões executadas.

Lista uma linha por sessão (lote rodado), em ordem decrescente de data:
  nome do arquivo · data/hora · N identificados · M realizados · badge status

Lê do histórico persistente em %APPDATA%/Iter/AppAnac/planilhas_processadas.json
via `app.state.planilha_hash.listar_sessoes()`.
"""
import os
from pathlib import Path

import flet as ft

from app.state.planilha_hash import HistoricoEntrada, listar_sessoes
from app.ui.componentes import (
    COR_BG, COR_FG, COR_MUTED_FG, COR_SUCCESS, COR_ERROR,
    botao_primario, botao_secundario, eyebrow, iter_wordmark_footer,
    titulo, texto,
)

# Tokens visuais coerentes com tela_principal
COR_CARD       = "#121218"
COR_CARD_ALT   = "#1a1a22"
COR_BORDER     = "#262630"
COR_DIM        = "#3a3a48"
COR_FG_DIM     = "#5a565a"
COR_WARMTH     = "#d4b48c"


def _badge(status: str) -> ft.Container:
    """Pílula de status colorida."""
    cor_map = {
        "OK":         (COR_SUCCESS, "#0e2418", "#1a3d28"),
        "Parcial":    (COR_WARMTH,  "#241a0e", "#3d2f15"),
        "Cancelado":  (COR_FG_DIM,  COR_CARD_ALT, COR_DIM),
        "Falha":      (COR_ERROR,   "#2a0e10", "#4a1f23"),
    }
    fg, bg, border = cor_map.get(status, (COR_FG_DIM, COR_CARD_ALT, COR_BORDER))
    return ft.Container(
        bgcolor=bg,
        border=ft.Border.all(1, border),
        border_radius=999,
        padding=ft.Padding(10, 4, 10, 4),
        content=ft.Text(
            status.upper(),
            size=10,
            weight=ft.FontWeight.W_700,
            color=fg,
            style=ft.TextStyle(letter_spacing=1.2),
        ),
    )


def _classificar(e: HistoricoEntrada) -> str:
    if e.cancelado:
        return "Cancelado"
    if e.sucessos == 0 and e.identificados > 0:
        return "Falha"
    if 0 < e.sucessos < e.identificados:
        return "Parcial"
    return "OK"


def _linha_sessao(e: HistoricoEntrada) -> ft.Container:
    """Uma linha do histórico, estilizada."""
    quando_local = e.quando.astimezone()
    quando_str = quando_local.strftime("%d/%m/%Y · %H:%M")
    status = _classificar(e)

    return ft.Container(
        bgcolor=COR_CARD_ALT,
        border=ft.Border.all(1, COR_BORDER),
        border_radius=12,
        padding=ft.Padding(16, 12, 16, 12),
        content=ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
            controls=[
                ft.Column(
                    spacing=4,
                    expand=True,
                    controls=[
                        ft.Text(
                            e.nome_arquivo,
                            size=14,
                            weight=ft.FontWeight.W_600,
                            color=COR_FG,
                            no_wrap=True,
                        ),
                        ft.Text(
                            f"{quando_str}     {e.identificados} identificados · "
                            f"{e.sucessos} realizados",
                            size=11,
                            color=COR_MUTED_FG,
                            font_family="Consolas",
                        ),
                    ],
                ),
                _badge(status),
            ],
        ),
    )


def _estado_vazio() -> ft.Container:
    return ft.Container(
        bgcolor=COR_CARD_ALT,
        border=ft.Border.all(1, COR_BORDER),
        border_radius=12,
        padding=ft.Padding(24, 32, 24, 32),
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.HISTORY_TOGGLE_OFF, size=32, color=COR_FG_DIM),
                ft.Text(
                    "Nenhuma sessão executada ainda.",
                    size=13,
                    color=COR_FG_DIM,
                ),
            ],
        ),
    )


def construir(page: ft.Page, ao_voltar, *_legacy_args, **_legacy_kw) -> ft.Control:
    """
    Constrói a tela de histórico de sessões.

    `*_legacy_args, **_legacy_kw` absorvem args legacy (sucessos/falhas/
    duracao_seg) que chamadas antigas (test_uis, etc) ainda passam.
    """
    def abrir_log(_):
        base = Path(os.environ.get("APPDATA", Path.home() / ".iter"))
        log_file = base / "Iter" / "AppAnac" / "logs" / "execucao.log"
        if log_file.exists():
            os.startfile(str(log_file))  # type: ignore[attr-defined]

    sessoes = listar_sessoes(limite=50)

    # Lista (ou estado vazio)
    if sessoes:
        lista_view = ft.ListView(
            spacing=8,
            expand=True,
            controls=[_linha_sessao(e) for e in sessoes],
        )
    else:
        lista_view = ft.Column(
            controls=[_estado_vazio()],
            alignment=ft.MainAxisAlignment.START,
        )

    container_lista = ft.Container(
        expand=True,
        content=lista_view,
    )

    # Barra de ações acima da lista — fica visível mesmo com a pílula DEV
    # sobrepondo o rodapé. Operação fica acessível direto pelo topo.
    barra_acoes = ft.Row(
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=12,
        controls=[
            botao_secundario("Abrir log completo", abrir_log),
            botao_primario("Voltar ao início", ao_voltar),
        ],
    )

    return ft.Container(
        padding=ft.Padding(40, 36, 40, 72),  # 72px bottom: respira sobre a DEV pill
        expand=True,
        content=ft.Column(
            spacing=18,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                eyebrow("Relatório"),
                titulo(
                    "Sessões executadas",
                    size=28,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    f"{len(sessoes)} sessão(ões) no histórico"
                    if sessoes else "Histórico vazio",
                    size=12,
                    color=COR_FG_DIM,
                ),
                barra_acoes,
                ft.Container(height=4),
                ft.Container(
                    expand=True,
                    width=720,
                    content=container_lista,
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[iter_wordmark_footer(height=14, opacity=0.30)],
                ),
            ],
        ),
    )
