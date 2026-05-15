"""
Tela principal — console operacional de lançamento CIV.

Arquitetura visual:
  - Header: título + badge "LICENÇA ATIVA" pulsante
  - Layout 68/32: zona operacional dominante (esquerda) + telemetria (direita)
  - Ambient glow azul Iter atrás do card hero
  - 3 estados do hero: vazio (dropzone) -> armado (planilha carregada) ->
    em execução (progress + status SACI)

Bot logic (CDP + civ_bot + classificação de dialogs) preservado integralmente
em _executar_batch / thread_target.
"""
import asyncio
import shutil
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, List

import flet as ft
from playwright.async_api import async_playwright

from app.core import browser as br_mod
from app.core import config
from app.core.civ_bot import lancar_voo, CanceladoPeloUsuario
from app.core.excel_reader import validar_planilha
from app.core.logger import set_ui_callback, get_logger
from app.core.popup_inspector import instalar_dialog_handler
from app.state.planilha_hash import (
    buscar_processamento_anterior,
    registrar_sessao,
)
from app.ui.componentes import iter_wordmark_footer

log = get_logger()


# ── Paleta operacional — Brand Iter ───────────────────────────────────────────
COR_BG          = "#0b0b0e"   # background quase-preto frio
COR_CARD        = "#121218"   # card principal
COR_CARD_ALT    = "#1a1a22"   # card secundário / telemetria
COR_BORDER      = "#262630"
COR_DIM         = "#3a3a48"   # bordas mais discretas
COR_FG          = "#f5ecd8"   # off-white quente
COR_FG_MUTED    = "#8a8482"
COR_FG_DIM      = "#5a565a"
COR_PRIMARY     = "#2b6bff"   # azul elétrico Iter (oficial Brand Kit 2026)
COR_WARMTH      = "#d4b48c"
COR_SUCCESS     = "#22c55e"
COR_WARNING     = "#d4b48c"
COR_ERROR       = "#ef4444"


# ── Helpers visuais ───────────────────────────────────────────────────────────


def _label_secao(texto: str) -> ft.Text:
    return ft.Text(
        texto.upper(),
        size=11,
        weight=ft.FontWeight.W_700,
        color=COR_FG_MUTED,
        style=ft.TextStyle(letter_spacing=1.6),
    )


def _label_telemetria(label: str, valor: ft.Control) -> ft.Column:
    return ft.Column(
        spacing=4,
        controls=[
            ft.Text(
                label.upper(),
                size=9,
                weight=ft.FontWeight.W_700,
                color=COR_FG_DIM,
                style=ft.TextStyle(letter_spacing=1.4),
            ),
            valor,
        ],
    )


def _glow_azul(left=None, right=None, top=None, bottom=None,
               width: int = 520, height: int = 520) -> ft.Container:
    """Disco azul translúcido para ambient. Usar dentro de Stack absoluto."""
    return ft.Container(
        left=left, right=right, top=top, bottom=bottom,
        width=width, height=height,
        bgcolor=COR_PRIMARY,
        opacity=0.06,
        border_radius=width // 2,
    )


def _classificar_dialogs(dialogs: list) -> tuple[str, str]:
    """
    Classifica o resultado de um lançamento baseado nos dialogs/alerts capturados.
    Retorna (classificacao, msg_normalizada).

    Política CONSERVADORA: só retorna "sucesso" se houver prova POSITIVA
    explícita no alert do SACI. Qualquer ambiguidade é tratada como
    "desconhecido" e a UI marca como FALHA (não como sucesso silencioso).
    """
    alerts = [d for d in dialogs if d.get("type") == "alert"]
    if not alerts:
        return ("desconhecido", "")
    msg = alerts[-1].get("message", "")
    msg_norm = msg.lower()

    # Prova positiva de sucesso: alert com palavras inequívocas.
    # IMPORTANTE: "salvo" sozinho é forte ("Registro salvo com sucesso");
    # "registrado" idem. "efetuado" cobre "Lançamento efetuado".
    PROVAS_SUCESSO = (
        "salvo com sucesso", "salvo!",
        "registrado com sucesso", "registrado!",
        "efetuado com sucesso", "efetuado!",
        "operacao efetuada", "operação efetuada",
        "incluido com sucesso", "incluído com sucesso",
        "cadastrado com sucesso",
    )
    if any(t in msg_norm for t in PROVAS_SUCESSO):
        return ("sucesso", msg)

    PROVAS_ERRO = (
        "obrigat", "invalid", "erro", "incorret", "falha",
        "ja existe", "já existe", "duplicado",
    )
    if any(t in msg_norm for t in PROVAS_ERRO):
        return ("erro_validacao", msg)

    return ("desconhecido", msg)


async def _salvar_screenshot_forensics(page_pw, linha_planilha: int, motivo: str) -> str:
    """
    Tira screenshot da tela do SACI no estado atual e salva em
    %APPDATA%/Iter/AppAnac/diagnostico/<data>-linha-N-<motivo>.png.

    Retorna o caminho do arquivo (ou string vazia se falhar).
    Usado quando o desfecho do lançamento é ambíguo — permite o suporte
    pedir o arquivo pro cliente e ver exatamente o que o SACI mostrou.
    """
    import os as _os
    from datetime import datetime as _dt
    try:
        base = Path(_os.environ.get("APPDATA", str(Path.home() / ".iter")))
        pasta = base / "Iter" / "AppAnac" / "diagnostico"
        pasta.mkdir(parents=True, exist_ok=True)
        stamp = _dt.now().strftime("%Y%m%d-%H%M%S")
        nome = f"{stamp}-linha-{linha_planilha}-{motivo}.png"
        destino = pasta / nome
        await page_pw.screenshot(path=str(destino), full_page=True)
        return str(destino)
    except Exception as exc:
        log.warning(f"Falha ao salvar screenshot forensics: {exc}")
        return ""


def _toast(page: ft.Page, msg: str) -> None:
    """SnackBar transitório (Flet 0.85: via page.show_dialog)."""
    try:
        page.show_dialog(ft.SnackBar(content=ft.Text(msg)))
    except Exception:
        # Fallback silencioso se a UI ainda não estiver pronta
        log.info(f"[toast] {msg}")


# ── Tela principal ────────────────────────────────────────────────────────────


def construir(page: ft.Page, ao_concluir: Callable[[int, int, float], None]) -> ft.Control:
    estado: Dict[str, Any] = {
        "caminho": None,
        "lancamentos": [],
        "erros": [],
        "rodando": False,
    }

    # Event cooperativo: setado quando usuário clica em "CANCELAR".
    # O loop de _executar_batch verifica antes de cada linha e dá break.
    cancelar_event = threading.Event()

    # ───────── Header: badge LICENÇA ATIVA reflete sessão real ─────────
    # Lê do cache local. Se há sessão, mostra "ATIVA · email"; senão "DEV MODE".
    from app.licensing.cache import ler_sessao as _ler_sessao_iter
    _sess_atual = _ler_sessao_iter()
    if _sess_atual:
        _label_badge = "LICENÇA ATIVA"
        _email_badge = _sess_atual.email
        _badge_dot_color = COR_SUCCESS
        _badge_bg = "#0e2418"
        _badge_border = "#1a3d28"
        _badge_fg = COR_SUCCESS
    else:
        _label_badge = "MODO DEV"
        _email_badge = "sem sessão ativa"
        _badge_dot_color = COR_WARMTH
        _badge_bg = "#241a0e"
        _badge_border = "#3d2f15"
        _badge_fg = COR_WARMTH

    dot_licenca = ft.Container(
        width=8, height=8,
        bgcolor=_badge_dot_color,
        border_radius=4,
        animate_opacity=ft.Animation(1400, ft.AnimationCurve.EASE_IN_OUT),
        opacity=1.0,
    )

    def _animar_pulse():
        while True:
            try:
                dot_licenca.opacity = 0.35 if dot_licenca.opacity >= 0.9 else 1.0
                page.update()
            except Exception:
                pass
            time.sleep(1.4)

    threading.Thread(target=_animar_pulse, daemon=True).start()

    badge_licenca = ft.Container(
        bgcolor=_badge_bg,
        border=ft.Border.all(1, _badge_border),
        border_radius=999,
        padding=ft.Padding(12, 6, 14, 6),
        content=ft.Row(
            spacing=8,
            tight=True,
            controls=[
                dot_licenca,
                ft.Text(
                    _label_badge,
                    size=10,
                    weight=ft.FontWeight.W_700,
                    color=_badge_fg,
                    style=ft.TextStyle(letter_spacing=1.4),
                ),
            ],
        ),
    )

    header = ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Column(
                spacing=2,
                controls=[
                    ft.Text(
                        "App Iter",
                        size=22,
                        weight=ft.FontWeight.W_700,
                        color=COR_FG,
                    ),
                    ft.Text(
                        "Automação de lançamentos CIV · SACI",
                        size=11,
                        color=COR_FG_MUTED,
                    ),
                ],
            ),
            ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.END,
                spacing=4,
                controls=[
                    badge_licenca,
                    ft.Text(
                        _email_badge,
                        size=10,
                        color=COR_FG_DIM,
                    ),
                ],
            ),
        ],
    )

    # ───────── Estado VAZIO: card de upload (click-to-pick) ─────────
    # NOTA: drag-and-drop nativo de arquivos da OS não é suportado pelo Flet
    # 0.85 — apenas drag entre controles Flet. Microcopy foca em clique;
    # quando a feature chegar, basta wirar evento no Container.
    dropzone_inner = ft.Column(
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=12,
        controls=[
            ft.Icon(ft.Icons.UPLOAD_FILE, size=36, color=COR_FG_DIM),
            ft.Text(
                "Clique para carregar uma planilha",
                size=15,
                weight=ft.FontWeight.W_600,
                color=COR_FG,
            ),
            ft.Container(height=4),
            ft.Text(
                ".xlsx · compatível com SACI / ANAC",
                size=11,
                weight=ft.FontWeight.W_600,
                color=COR_FG_DIM,
                style=ft.TextStyle(letter_spacing=1.4),
            ),
        ],
    )

    dropzone = ft.Container(
        height=240,
        bgcolor=COR_CARD_ALT,
        border=ft.Border.all(1, COR_DIM),
        border_radius=20,
        alignment=ft.Alignment.CENTER,
        padding=24,
        content=dropzone_inner,
        animate_scale=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
    )

    # Link "Baixar modelo" abaixo do dropzone (substitui o botão que estava
    # na tela de onboarding — contexto é melhor aqui).
    # on_click é setado MAIS ABAIXO, após `baixar_modelo` ser definida.
    link_modelo = ft.TextButton(
        content=ft.Row(
            spacing=6,
            tight=True,
            controls=[
                ft.Icon(ft.Icons.DOWNLOAD_OUTLINED, size=14, color=COR_FG_MUTED),
                ft.Text(
                    "Não tem uma planilha? Baixar modelo",
                    size=12,
                    color=COR_FG_MUTED,
                ),
            ],
        ),
        style=ft.ButtonStyle(
            padding=ft.Padding(8, 6, 8, 6),
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
    )

    # ───────── Estado ARMADO: card com informações da planilha ─────────
    nome_arquivo = ft.Text("", size=15, weight=ft.FontWeight.W_600, color=COR_FG)
    contagem_validos = ft.Text("", size=28, weight=ft.FontWeight.W_700, color=COR_FG)
    contagem_erros = ft.Text("", size=11, color=COR_FG_MUTED)
    aviso_duplicacao = ft.Container(
        visible=False,
        bgcolor="#241a0e",
        border=ft.Border.all(1, "#3d2f15"),
        border_radius=12,
        padding=ft.Padding(12, 10, 12, 10),
        content=ft.Row(
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.WARNING_AMBER, size=14, color=COR_WARNING),
                ft.Text(
                    "",
                    size=12,
                    color=COR_WARNING,
                    expand=True,
                ),
            ],
        ),
    )

    info_planilha_card = ft.Container(
        visible=False,
        bgcolor=COR_CARD_ALT,
        border=ft.Border.all(1, COR_BORDER),
        border_radius=16,
        padding=20,
        content=ft.Column(
            spacing=16,
            controls=[
                _label_secao("Manifesto CIV carregado"),
                nome_arquivo,
                ft.Divider(height=1, color=COR_BORDER),
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    spacing=20,
                    controls=[
                        ft.Column(
                            spacing=2,
                            controls=[
                                contagem_validos,
                                ft.Text(
                                    "lançamentos armados",
                                    size=11,
                                    color=COR_FG_MUTED,
                                ),
                            ],
                        ),
                        ft.Container(expand=True),
                        contagem_erros,
                    ],
                ),
                aviso_duplicacao,
            ],
        ),
    )

    # ───────── Painel de inconsistências (mostra só quando há erros) ──────
    inconsistencias_list = ft.ListView(
        spacing=4,
        height=156,
        auto_scroll=False,
    )

    inconsistencias_panel = ft.Container(
        visible=False,
        bgcolor=COR_CARD_ALT,
        border=ft.Border.all(1, "#3d2520"),
        border_radius=16,
        padding=ft.Padding(20, 16, 20, 16),
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.ERROR_OUTLINE, size=14, color=COR_ERROR),
                        _label_secao("Inconsistências"),
                    ],
                ),
                inconsistencias_list,
            ],
        ),
    )

    # ───────── Botão operacional INICIAR ─────────
    botao_iniciar_label = ft.Text(
        "INICIAR SESSÃO",
        size=13,
        weight=ft.FontWeight.W_700,
        color="#ffffff",
        style=ft.TextStyle(letter_spacing=1.8),
    )

    botao_iniciar = ft.Container(
        visible=False,
        height=56,
        bgcolor=COR_PRIMARY,
        border_radius=14,
        alignment=ft.Alignment.CENTER,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
            controls=[
                ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, color="#ffffff", size=20),
                botao_iniciar_label,
            ],
        ),
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=24,
            color="#2b6bff4d",  # azul Iter 30% alpha glow
            offset=ft.Offset(0, 4),
        ),
        animate_opacity=ft.Animation(900, ft.AnimationCurve.EASE_IN_OUT),
        animate_scale=ft.Animation(160, ft.AnimationCurve.EASE_OUT),
        ink=True,
    )

    # ───────── Hero panel (envolve dropzone OU info+iniciar) ─────────
    hero_panel = ft.Container(
        bgcolor=COR_CARD,
        border=ft.Border.all(1, COR_BORDER),
        border_radius=20,
        padding=28,
        content=ft.Column(
            spacing=16,
            controls=[
                _label_secao("Manifesto"),
                dropzone,
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[link_modelo],
                ),
                info_planilha_card,
                inconsistencias_panel,
                botao_iniciar,
            ],
        ),
    )

    # ───────── Telemetria (lado direito) ─────────
    dot_cdp = ft.Container(
        width=8, height=8,
        bgcolor=COR_FG_DIM,
        border_radius=4,
        animate_opacity=ft.Animation(900, ft.AnimationCurve.EASE_IN_OUT),
        opacity=0.4,
    )

    status_cdp_texto = ft.Text(
        "Aguardando manifesto",
        size=12,
        color=COR_FG_MUTED,
    )

    telemetria_status = ft.Container(
        padding=ft.Padding(0, 0, 0, 16),
        content=_label_telemetria(
            "Sessão SACI",
            ft.Row(
                spacing=8,
                tight=True,
                controls=[dot_cdp, status_cdp_texto],
            ),
        ),
    )

    progresso = ft.ProgressBar(
        value=0,
        bgcolor=COR_CARD_ALT,
        color=COR_PRIMARY,
        bar_height=4,
    )
    progresso_label = ft.Text("0 / 0", size=12, color=COR_FG_MUTED)

    telemetria_progresso = ft.Container(
        padding=ft.Padding(0, 0, 0, 16),
        content=_label_telemetria(
            "Progresso",
            ft.Column(
                spacing=8,
                controls=[
                    progresso,
                    progresso_label,
                ],
            ),
        ),
    )

    eventos_view = ft.ListView(
        expand=True,
        spacing=2,
        auto_scroll=True,
    )

    def adicionar_log_linha(nivel: str, msg: str) -> None:
        cor = {
            "INFO": COR_FG_MUTED,
            "WARNING": COR_WARMTH,
            "ERROR": COR_ERROR,
        }.get(nivel, COR_FG_DIM)
        eventos_view.controls.append(
            ft.Text(
                msg,
                color=cor,
                size=11,
                font_family="Consolas",
                selectable=True,
            )
        )
        if len(eventos_view.controls) > 200:
            eventos_view.controls = eventos_view.controls[-200:]
        try:
            page.update()
        except Exception:
            pass

    set_ui_callback(adicionar_log_linha)

    telemetria_eventos = ft.Container(
        expand=True,
        content=ft.Column(
            spacing=8,
            expand=True,
            controls=[
                _label_telemetria("Eventos", ft.Container(height=0)),
                ft.Container(
                    expand=True,
                    bgcolor=COR_BG,
                    border=ft.Border.all(1, COR_BORDER),
                    border_radius=10,
                    padding=12,
                    content=eventos_view,
                ),
            ],
        ),
    )

    # Botão Cancelar (visível só durante execução do bot)
    botao_cancelar_label = ft.Text(
        "CANCELAR",
        size=11,
        weight=ft.FontWeight.W_700,
        color="#ffffff",
        style=ft.TextStyle(letter_spacing=1.4),
    )
    botao_cancelar = ft.Container(
        visible=False,
        height=40,
        bgcolor=COR_ERROR,
        border_radius=10,
        alignment=ft.Alignment.CENTER,
        margin=ft.Margin(0, 0, 0, 16),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8,
            controls=[
                ft.Icon(ft.Icons.STOP_CIRCLE, color="#ffffff", size=16),
                botao_cancelar_label,
            ],
        ),
        ink=True,
        animate_opacity=ft.Animation(160, ft.AnimationCurve.EASE_OUT),
    )

    telemetria_panel = ft.Container(
        bgcolor=COR_CARD,
        border=ft.Border.all(1, COR_BORDER),
        border_radius=20,
        padding=24,
        expand=True,
        content=ft.Column(
            spacing=0,
            expand=True,
            controls=[
                _label_secao("Telemetria"),
                ft.Container(height=16),
                telemetria_status,
                botao_cancelar,
                telemetria_progresso,
                telemetria_eventos,
            ],
        ),
    )

    # ───────── FilePicker (Service no Flet 0.85: anexa em page.services) ──
    picker = ft.FilePicker()
    page.services.append(picker)

    # ───────── Handlers ─────────
    async def baixar_modelo(_=None):
        """
        Abre Save Dialog para o usuário escolher onde salvar o modelo.
        Copia o template.xlsx oficial pro destino escolhido.

        Estratégia anti-conflito:
          - shutil.copyfile (não copy2) — não preserva metadata; arquivo gerado
            sai com permissões padrão de escrita.
          - Se o destino já existe e está em uso (Excel/OneDrive lock), o erro
            é capturado e mostrado num toast claro. Sugere fechar Excel e
            renomear.
          - Se o destino existir e for substituível, sobrescreve.
        """
        origem = Path(__file__).resolve().parent.parent / "assets" / "template.xlsx"
        if not origem.exists():
            _toast(page, "Modelo de planilha indisponível neste build.")
            return

        destino_str = await picker.save_file(
            dialog_title="Salvar modelo de planilha",
            file_name="modelo-civ-app-iter.xlsx",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx"],
        )
        if not destino_str:
            return  # usuário cancelou

        destino = Path(destino_str)

        # Pré-check: se o destino existe e está em uso, avisa antes de tentar
        if destino.exists():
            try:
                # Tentativa de abertura exclusiva — se outro processo segura o
                # arquivo (Excel aberto, OneDrive sincronizando), falha aqui.
                with open(destino, "a+b"):
                    pass
            except OSError as exc:
                msg = (
                    f"'{destino.name}' está em uso por outro programa "
                    "(Excel aberto, OneDrive sincronizando?). "
                    "Feche-o ou escolha outro nome."
                )
                log.error(f"Destino em uso: {exc}")
                _toast(page, msg)
                return

        try:
            shutil.copyfile(origem, destino)
        except Exception as exc:
            log.error(f"Falha ao salvar modelo em {destino}: {exc}")
            _toast(page, f"Falha ao salvar: {exc}")
            return

        log.info(f"Modelo salvo em {destino}.")
        _toast(page, f"Modelo salvo em {destino.name}")

    async def escolher_planilha(_=None):
        arquivos = await picker.pick_files(
            allowed_extensions=["xlsx"],
            file_type=ft.FilePickerFileType.CUSTOM,
            allow_multiple=False,
        )
        if not arquivos:
            return
        caminho = arquivos[0].path
        estado["caminho"] = caminho

        try:
            lancamentos, erros = validar_planilha(caminho)
            estado["lancamentos"] = lancamentos
            estado["erros"] = erros
        except Exception as exc:
            log.error(f"Falha ao validar planilha: {exc}")
            estado["lancamentos"] = []
            estado["erros"] = []
            return

        dropzone.visible = False
        info_planilha_card.visible = True

        nome_arquivo.value = Path(caminho).name
        contagem_validos.value = str(len(lancamentos))
        if erros:
            contagem_erros.value = f"{len(erros)} inconsistência(s)"
            contagem_erros.color = COR_WARNING
        else:
            contagem_erros.value = "0 inconsistências"
            contagem_erros.color = COR_FG_MUTED

        # Painel detalhado de inconsistências: 1 linha por erro
        inconsistencias_list.controls.clear()
        if erros:
            for er in erros:
                inconsistencias_list.controls.append(
                    ft.Row(
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                f"linha {er.linha}",
                                size=11,
                                color=COR_FG_DIM,
                                weight=ft.FontWeight.W_600,
                                width=64,
                            ),
                            ft.Text(
                                er.coluna,
                                size=11,
                                color=COR_FG_MUTED,
                                font_family="Consolas",
                                width=96,
                            ),
                            ft.Text(
                                f"{er.valor!r}",
                                size=11,
                                color=COR_FG,
                                font_family="Consolas",
                                width=120,
                                no_wrap=True,
                            ),
                            ft.Text(
                                er.motivo,
                                size=11,
                                color=COR_ERROR,
                                expand=True,
                                selectable=True,
                            ),
                        ],
                    )
                )
            inconsistencias_panel.visible = True
        else:
            inconsistencias_panel.visible = False

        # Estado do botão Iniciar: ativo só quando há lançamentos válidos
        botao_iniciar.visible = True
        if lancamentos:
            botao_iniciar.opacity = 1.0
            botao_iniciar.ink = True
            botao_iniciar.on_click = iniciar
            botao_iniciar_label.value = "INICIAR SESSÃO"
        else:
            botao_iniciar.opacity = 0.35
            botao_iniciar.ink = False
            botao_iniciar.on_click = None
            botao_iniciar_label.value = "NENHUM LANÇAMENTO VÁLIDO"

        ja_processada = buscar_processamento_anterior(caminho)
        if ja_processada:
            aviso_duplicacao.visible = True
            aviso_duplicacao.content.controls[1].value = (
                f"Manifesto já processado em "
                f"{ja_processada.quando.strftime('%d/%m/%Y %H:%M')}. "
                f"Iniciar de novo vai duplicar entradas no SACI."
            )
        else:
            aviso_duplicacao.visible = False

        status_cdp_texto.value = "Pronto para acionar"
        page.update()

    dropzone.on_click = escolher_planilha
    link_modelo.on_click = baixar_modelo
    info_planilha_card.on_click = escolher_planilha

    # ───────── Execução real do batch ─────────
    async def _executar_batch() -> tuple[int, int]:
        lancamentos: List[Dict[str, Any]] = estado["lancamentos"]
        total = len(lancamentos)
        sucessos = 0
        falhas = 0

        async with async_playwright() as pw:
            try:
                browser, _context, page_pw = await br_mod.conectar(pw)
            except Exception as exc:
                log.error(f"Não foi possível conectar ao navegador: {exc}")
                return 0, total

            status_cdp_texto.value = "Chrome conectado via CDP"
            status_cdp_texto.color = COR_FG
            dot_cdp.bgcolor = COR_SUCCESS
            try:
                page.update()
            except Exception:
                pass

            capture = instalar_dialog_handler(page_pw)

            try:
                for i, linha in enumerate(lancamentos, 1):
                    # Cancelamento cooperativo: checa antes de iniciar cada linha
                    if cancelar_event.is_set():
                        log.warning(
                            f"Cancelado pelo usuário antes da linha "
                            f"{linha['linha_planilha']}."
                        )
                        break

                    log.info(
                        f"Lançamento {i}/{total} "
                        f"(linha {linha['linha_planilha']} da planilha)"
                    )
                    try:
                        await page_pw.goto(
                            config.URL_CIV,
                            wait_until="domcontentloaded",
                            timeout=config.TIMEOUT_PADRAO,
                        )
                    except Exception as exc:
                        log.error(f"Falha ao navegar para URL_CIV: {exc}")
                        falhas += 1
                        _atualizar_progresso(i, total, sucessos, falhas)
                        continue

                    capture.eventos.clear()

                    try:
                        resposta = await lancar_voo(
                            page_pw, linha, capture, cancel_event=cancelar_event,
                        )
                    except CanceladoPeloUsuario:
                        log.warning(
                            f"Cancelado pelo usuário durante a linha "
                            f"{linha['linha_planilha']}."
                        )
                        break
                    except Exception as exc:
                        log.error(
                            f"Falha no preenchimento da linha "
                            f"{linha['linha_planilha']}: {exc}"
                        )
                        falhas += 1
                        _atualizar_progresso(i, total, sucessos, falhas)
                        continue

                    # Política conservadora: só conta sucesso com PROVA POSITIVA
                    # de que o SACI salvou (alert "salvo com sucesso", redirect
                    # pra listagem, ou modal HTML confirmando). Qualquer
                    # ambiguidade → FALHA + screenshot pra diagnóstico.
                    tipo = resposta.get("tipo")
                    nlinha = linha['linha_planilha']

                    if tipo == "sessao_expirada":
                        log.error(
                            f"Sessão SACI expirada (URL: {resposta.get('url')}). "
                            "Refaça login no navegador e acione novamente. Abortando."
                        )
                        falhas += 1
                        _atualizar_progresso(i, total, sucessos, falhas)
                        break

                    elif tipo == "native_dialog":
                        classificacao, msg = _classificar_dialogs(
                            resposta.get("dialogs", [])
                        )
                        if classificacao == "sucesso":
                            log.info(f"Linha {nlinha} salva: {msg!r}")
                            sucessos += 1
                        elif classificacao == "erro_validacao":
                            screenshot = await _salvar_screenshot_forensics(
                                page_pw, nlinha, "erro-validacao"
                            )
                            log.error(
                                f"Linha {nlinha} REJEITADA pelo SACI: {msg!r}"
                                + (f" — screenshot: {screenshot}" if screenshot else "")
                            )
                            falhas += 1
                        else:
                            screenshot = await _salvar_screenshot_forensics(
                                page_pw, nlinha, "popup-ambiguo"
                            )
                            log.error(
                                f"Linha {nlinha} popup ambíguo (msg: {msg!r}) — "
                                "tratando como FALHA. Confira o SACI manualmente"
                                + (f". Screenshot: {screenshot}" if screenshot else "")
                            )
                            falhas += 1

                    elif tipo == "redirect":
                        # Sucesso apenas se redirecionou pra URL associada a
                        # salvamento (lista de CIVs, confirmação de inclusão).
                        url_dest = (resposta.get("url") or "").lower()
                        SINAIS_SUCESSO = (
                            "listarciv", "consultarciv", "listar_civ",
                            "incluircivok", "sucesso", "confirma",
                        )
                        if any(t in url_dest for t in SINAIS_SUCESSO):
                            log.info(
                                f"Linha {nlinha} salva (redirect: {resposta.get('url')})"
                            )
                            sucessos += 1
                        else:
                            screenshot = await _salvar_screenshot_forensics(
                                page_pw, nlinha, "redirect-inesperado"
                            )
                            log.error(
                                f"Linha {nlinha} redirect inesperado pra "
                                f"{resposta.get('url')} — tratando como FALHA"
                                + (f". Screenshot: {screenshot}" if screenshot else "")
                            )
                            falhas += 1

                    elif tipo == "html_modal":
                        texto_modal = (resposta.get("texto") or "").lower()
                        SINAIS_SUCESSO_MODAL = (
                            "salvo", "salvo!", "sucesso",
                            "registrado", "efetuado", "incluido", "incluído",
                        )
                        SINAIS_ERRO_MODAL = (
                            "erro", "invalid", "obrigat", "falha", "incorret",
                        )
                        if any(t in texto_modal for t in SINAIS_ERRO_MODAL):
                            screenshot = await _salvar_screenshot_forensics(
                                page_pw, nlinha, "modal-erro"
                            )
                            log.error(
                                f"Linha {nlinha} modal de erro: {texto_modal[:120]!r}"
                                + (f" — screenshot: {screenshot}" if screenshot else "")
                            )
                            falhas += 1
                        elif any(t in texto_modal for t in SINAIS_SUCESSO_MODAL):
                            log.info(
                                f"Linha {nlinha} salva (modal: {texto_modal[:80]!r})"
                            )
                            sucessos += 1
                        else:
                            screenshot = await _salvar_screenshot_forensics(
                                page_pw, nlinha, "modal-ambiguo"
                            )
                            log.error(
                                f"Linha {nlinha} modal HTML ambíguo: "
                                f"{texto_modal[:120]!r} — tratando como FALHA"
                                + (f". Screenshot: {screenshot}" if screenshot else "")
                            )
                            falhas += 1

                    else:  # "noop" — nada visível mudou
                        screenshot = await _salvar_screenshot_forensics(
                            page_pw, nlinha, "noop"
                        )
                        log.error(
                            f"Linha {nlinha}: nada mudou após #salvar "
                            f"(URL: {resposta.get('url')}). Tratando como FALHA"
                            + (f". Screenshot: {screenshot}" if screenshot else "")
                        )
                        falhas += 1

                    _atualizar_progresso(i, total, sucessos, falhas)
            finally:
                await br_mod.desconectar(browser)

        return sucessos, falhas

    def _atualizar_progresso(i: int, total: int, sucessos: int, falhas: int) -> None:
        progresso.value = i / total if total else 0
        progresso_label.value = (
            f"Linha {i}/{total} · {sucessos} ok · {falhas} falha(s)"
        )
        try:
            page.update()
        except Exception:
            pass

    def cancelar_lote(_=None):
        """Sinaliza cancelamento. O loop em _executar_batch verifica antes de
        cada linha e dá break — termina a linha em andamento e sai."""
        if not estado["rodando"]:
            return
        cancelar_event.set()
        botao_cancelar_label.value = "CANCELANDO..."
        botao_cancelar.opacity = 0.5
        botao_cancelar.on_click = None
        log.warning("Cancelamento solicitado. Terminando linha atual...")
        try:
            page.update()
        except Exception:
            pass

    botao_cancelar.on_click = cancelar_lote

    def _mostrar_dialog_finalizacao(sucessos: int, falhas: int, duracao: float, cancelado: bool):
        """AlertDialog mostrado quando o lote termina (ou é cancelado)."""
        if cancelado:
            titulo_dlg = "Lote cancelado"
            corpo = (
                f"O lote foi interrompido após {sucessos + falhas} linha(s).\n"
                f"{sucessos} sucesso(s) · {falhas} falha(s) · {duracao:.0f}s"
            )
        else:
            titulo_dlg = "Lançamentos finalizados"
            corpo = (
                f"O lote foi concluído.\n"
                f"{sucessos} sucesso(s) · {falhas} falha(s) · {duracao:.0f}s"
            )

        def _fechar(_):
            page.pop_dialog()
            page.update()

        def _ver_relatorio(_):
            page.pop_dialog()
            page.update()
            ao_concluir(sucessos, falhas, duracao)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(titulo_dlg, size=18, weight=ft.FontWeight.W_700),
            content=ft.Text(corpo, size=13, color=COR_FG_MUTED),
            actions=[
                ft.OutlinedButton(content="Fechar", on_click=_fechar),
                ft.ElevatedButton(
                    content="Ver relatório",
                    on_click=_ver_relatorio,
                    bgcolor=COR_PRIMARY,
                    color="#ffffff",
                ),
            ],
        )
        try:
            page.show_dialog(dlg)
            page.update()
        except Exception as exc:
            log.error(f"Falha ao abrir dialog de finalização: {exc}")
            # Fallback: routea direto pra relatorio
            ao_concluir(sucessos, falhas, duracao)

    def _executar_inicio():
        """Lógica real de início do bot — chamada quando o usuário clica
        'Prosseguir' no pre-flight modal."""
        if not estado["caminho"] or not estado["lancamentos"]:
            return
        if estado["rodando"]:
            return
        estado["rodando"] = True
        cancelar_event.clear()
        eventos_view.controls.clear()
        progresso.value = 0
        progresso_label.value = f"Linha 0/{len(estado['lancamentos'])}"

        botao_iniciar_label.value = "SESSÃO SACI EM EXECUÇÃO"
        botao_iniciar.bgcolor = "#1d4ed8"
        botao_iniciar.opacity = 0.85
        status_cdp_texto.value = "Conectando..."
        status_cdp_texto.color = COR_WARMTH
        dot_cdp.bgcolor = COR_WARMTH
        # Mostrar botão Cancelar (em execução)
        botao_cancelar.visible = True
        botao_cancelar.opacity = 1.0
        botao_cancelar.on_click = cancelar_lote
        botao_cancelar_label.value = "CANCELAR"
        page.update()

        def thread_target():
            inicio = time.monotonic()
            sucessos = 0
            falhas = 0
            cancelado = False
            try:
                sucessos, falhas = asyncio.run(_executar_batch())
                cancelado = cancelar_event.is_set()
                if cancelado:
                    log.info(
                        f"Lote cancelado: {sucessos} sucesso(s), {falhas} falha(s) "
                        f"antes do cancelamento."
                    )
                else:
                    log.info(
                        f"Lote concluído: {sucessos} sucesso(s), {falhas} falha(s)."
                    )
            except Exception as exc:
                log.error(f"Erro inesperado no lote: {exc}")
            finally:
                duracao = time.monotonic() - inicio
                estado["rodando"] = False

                # Registra a sessão SEMPRE — mesmo cancelada ou com 0 sucessos.
                # O relatório precisa mostrar todas as tentativas.
                try:
                    registrar_sessao(
                        caminho=estado["caminho"],
                        identificados=len(estado["lancamentos"]),
                        sucessos=sucessos,
                        falhas=falhas,
                        duracao_seg=duracao,
                        cancelado=cancelado,
                    )
                except Exception as exc:
                    log.warning(f"Falha ao registrar sessão no histórico: {exc}")

                # Reset visual: botão Iniciar volta ao normal, Cancelar some
                botao_iniciar_label.value = "INICIAR SESSÃO"
                botao_iniciar.bgcolor = COR_PRIMARY
                botao_iniciar.opacity = 1.0
                botao_cancelar.visible = False
                botao_cancelar.opacity = 1.0
                botao_cancelar_label.value = "CANCELAR"

                # Log explícito de finalização nos eventos
                msg_final = (
                    "Cancelado pelo usuário"
                    if cancelado
                    else f"Lote finalizado: {sucessos} sucesso(s), {falhas} falha(s) em {duracao:.0f}s"
                )
                adicionar_log_linha("INFO", "═══ " + msg_final + " ═══")

                try:
                    page.update()
                except Exception:
                    pass

                # Dialog modal de finalização
                _mostrar_dialog_finalizacao(sucessos, falhas, duracao, cancelado)

        threading.Thread(target=thread_target, daemon=True).start()

    def iniciar(_=None):
        """Handler do botão 'INICIAR SESSÃO': abre pre-flight modal.

        Fluxo novo (UX explícita):
          - Status "Aguardando você abrir o SACI" + botão "Abrir SACI" ativo
          - Clica "Abrir SACI" → o app detecta o navegador certo (Brave, Chrome
            etc.) e abre na porta CDP com a URL do SACI já carregada
          - Polling em background atualiza o status:
              · "Abrindo navegador..." → "Navegador pronto, faça login..."
              · "SACI detectado" (verde) → habilita "Prosseguir"
          - Botão "Prosseguir" começa DESABILITADO. Só ativa quando o polling
            confirma CDP + aba do SACI carregada.
        """
        if not estado["caminho"] or not estado["lancamentos"]:
            return
        if estado["rodando"]:
            return

        # Estado interno do pre-flight
        preflight = {
            "polling_event": threading.Event(),  # set = pare de pollar
            "saci_pronto": False,
        }

        # Status texto + dot pulsante (refletem estado do polling)
        status_dot = ft.Container(
            width=10, height=10,
            bgcolor=COR_FG_DIM,
            border_radius=5,
        )
        status_label = ft.Text(
            "Aguardando você abrir o SACI",
            size=13,
            color=COR_FG_MUTED,
            weight=ft.FontWeight.W_500,
        )

        botao_abrir = ft.OutlinedButton(content="Abrir SACI")
        botao_prosseguir = ft.ElevatedButton(
            content="Prosseguir",
            bgcolor=COR_FG_DIM,
            color="#ffffff",
            disabled=True,
        )
        botao_cancelar_dlg = ft.TextButton(content="Cancelar")

        def _atualizar_status(texto: str, cor: str, pronto: bool) -> None:
            try:
                status_dot.bgcolor = cor
                status_label.value = texto
                status_label.color = cor if pronto else COR_FG_MUTED
                botao_prosseguir.disabled = not pronto
                botao_prosseguir.bgcolor = COR_PRIMARY if pronto else COR_FG_DIM
                page.update()
            except Exception:
                pass

        def _polling_loop():
            """Roda em thread separada. Atualiza status a cada 1s."""
            while not preflight["polling_event"].is_set():
                try:
                    cdp_ok = br_mod.cdp_disponivel()
                    saci_ok = cdp_ok and br_mod.saci_aberto()
                    if saci_ok and not preflight["saci_pronto"]:
                        preflight["saci_pronto"] = True
                        _atualizar_status(
                            "SACI detectado — pronto para iniciar",
                            COR_SUCCESS, True,
                        )
                    elif cdp_ok and not saci_ok:
                        _atualizar_status(
                            "Navegador pronto — abra o SACI e autentique",
                            COR_WARMTH, False,
                        )
                        preflight["saci_pronto"] = False
                    elif not cdp_ok and preflight["saci_pronto"]:
                        # Navegador foi fechado
                        preflight["saci_pronto"] = False
                        _atualizar_status(
                            "Aguardando você abrir o SACI",
                            COR_FG_DIM, False,
                        )
                except Exception as exc:
                    log.debug(f"polling preflight: {exc}")
                # Espera 1s OU sai imediatamente se o event for setado
                preflight["polling_event"].wait(timeout=1.0)

        # Já tá pronto? Sim → habilita Prosseguir de cara.
        try:
            if br_mod.cdp_disponivel() and br_mod.saci_aberto():
                preflight["saci_pronto"] = True
                _atualizar_status(
                    "SACI detectado — pronto para iniciar", COR_SUCCESS, True,
                )
        except Exception:
            pass

        threading.Thread(target=_polling_loop, daemon=True).start()

        def _abrir_saci(_):
            """Abre o navegador na porta CDP com o SACI já carregado."""
            _atualizar_status("Abrindo navegador...", COR_WARMTH, False)
            def _abrir_em_thread():
                try:
                    nav = br_mod.abrir_navegador_com_cdp()
                    log.info(f"Pre-flight: navegador {nav.nome} aberto via CDP.")
                except Exception as exc:
                    log.error(f"Falha ao abrir navegador via CDP: {exc}")
                    _atualizar_status(f"Erro: {exc}", COR_ERROR, False)
            threading.Thread(target=_abrir_em_thread, daemon=True).start()

        def _prosseguir(_):
            preflight["polling_event"].set()
            page.pop_dialog()
            page.update()
            _executar_inicio()

        def _cancelar(_):
            preflight["polling_event"].set()
            page.pop_dialog()
            page.update()

        botao_abrir.on_click = _abrir_saci
        botao_prosseguir.on_click = _prosseguir
        botao_cancelar_dlg.on_click = _cancelar

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(
                "Sessão SACI",
                size=18, weight=ft.FontWeight.W_700,
            ),
            content=ft.Column(
                tight=True,
                spacing=14,
                controls=[
                    ft.Text(
                        "Antes de iniciar, abra o site da ANAC pelo botão "
                        "abaixo (o app vai usar o navegador que você abrir, "
                        "preservando sua sessão).",
                        size=13, color=COR_FG_MUTED,
                    ),
                    ft.Container(
                        bgcolor=COR_CARD_ALT,
                        border=ft.Border.all(1, COR_BORDER),
                        border_radius=10,
                        padding=ft.Padding(14, 12, 14, 12),
                        content=ft.Row(
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[status_dot, status_label],
                        ),
                    ),
                ],
            ),
            actions=[
                botao_cancelar_dlg,
                botao_abrir,
                botao_prosseguir,
            ],
        )
        try:
            page.show_dialog(dlg)
            page.update()
        except Exception as exc:
            log.error(f"Falha ao abrir pre-flight dialog: {exc}")
            preflight["polling_event"].set()
            _executar_inicio()

    botao_iniciar.on_click = iniciar

    # Footer discreto com wordmark no canto inferior direito
    rodape = ft.Row(
        alignment=ft.MainAxisAlignment.END,
        controls=[iter_wordmark_footer(height=14, opacity=0.30)],
    )

    # ───────── Layout final ─────────
    # O background ambient (glows azuis) é aplicado globalmente em
    # main_app._render, não aqui. Esta tela só monta o conteúdo.
    return ft.Container(
        padding=ft.Padding(28, 24, 28, 16),
        content=ft.Column(
            spacing=16,
            expand=True,
            controls=[
                header,
                ft.Row(
                    expand=True,
                    spacing=20,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        ft.Container(expand=68, content=hero_panel),
                        ft.Container(expand=32, content=telemetria_panel),
                    ],
                ),
                rodape,
            ],
        ),
    )
