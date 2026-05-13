"""
Entry point do App Iter.

Fluxo de inicialização:
  1. Init do logger
  2. Check de licença (cache local + revalidação online)
  3. Se não tem licença válida -> tela_licenca
  4. Se primeiro uso (sem flag onboarding_visto) -> tela_onboarding
  5. Senão -> tela_principal
  6. Após o lote -> tela_relatorio

DEV BYPASS:
  Quando DEV_MODE=True (default agora — ainda não temos gateway definido),
  o roteamento sempre começa na tela principal e mostra um overlay
  centralizado embaixo com 4 botões para navegar entre todas as telas.
  Desligar trocando DEV_MODE=False (ou setando env APP_ANAC_DEV=0) antes
  do release.
"""
import os
from pathlib import Path

# Carrega .env ANTES de qualquer outra coisa — o DEV_MODE e as keys do
# Supabase dependem disso.
try:
    from dotenv import load_dotenv
    _root_env = Path(__file__).resolve().parent.parent / ".env"
    if _root_env.exists():
        load_dotenv(_root_env, override=False)
except ImportError:
    pass

import flet as ft

from app.core.logger import get_logger
from app.licensing.cache import limpar_sessao
from app.licensing.verificador import checar_acesso
from app.ui import tela_licenca, tela_onboarding, tela_principal, tela_relatorio
from app.ui.componentes import (
    COR_BG, COR_FG, COR_BORDER, COR_MUTED, COR_PRIMARY, COR_ERROR,
)
from app.ui.fundo import camadas_ambient

VERSAO = "0.1.0"

# Flip para False antes do release. Env var APP_ANAC_DEV=0 também desliga.
# Default agora é 0 (produção) — exige opt-in explícito pra DEV.
DEV_MODE = os.environ.get("APP_ANAC_DEV", "0") == "1"

log = get_logger()


def _flag_onboarding_visto() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / ".iter"))
    p = base / "Iter" / "AppAnac"
    p.mkdir(parents=True, exist_ok=True)
    return p / "onboarding_visto"


def _dev_nav(ir_para_principal, ir_para_licenca, ir_para_relatorio_demo,
             ir_para_onboarding):
    """
    Overlay centralizado na base com 4 botões para pular entre telas.
    Ordem (request do usuário): Principal · Licença · Relatório · Onboarding.
    Aparece somente em DEV_MODE.
    """
    def botao(label: str, on_click) -> ft.Control:
        return ft.TextButton(
            content=label,
            on_click=lambda _: on_click(),
            style=ft.ButtonStyle(
                color=COR_FG,
                padding=ft.Padding(12, 6, 12, 6),
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        )

    pilula = ft.Container(
        padding=ft.Padding(6, 4, 6, 4),
        bgcolor=COR_MUTED,
        border=ft.Border.all(1, COR_BORDER),
        border_radius=10,
        content=ft.Row(
            tight=True,
            spacing=2,
            controls=[
                ft.Container(
                    content=ft.Text(
                        "DEV", size=10, color=COR_PRIMARY,
                        weight=ft.FontWeight.W_700,
                    ),
                    padding=ft.Padding(8, 0, 8, 0),
                ),
                botao("Principal",  ir_para_principal),
                botao("Licença",    ir_para_licenca),
                botao("Relatório",  ir_para_relatorio_demo),
                botao("Onboarding", ir_para_onboarding),
            ],
        ),
    )

    # Wrapper centralizado horizontalmente na base do Stack
    return ft.Container(
        left=0, right=0, bottom=16,
        alignment=ft.Alignment.BOTTOM_CENTER,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[pilula],
        ),
    )


def _user_nav(ir_para_principal, ir_para_relatorio, sair):
    """
    Barra de navegação do usuário (não-DEV). Aparece pós-login nas telas
    operacionais (Principal e Relatório). 3 ações:
      - Principal (volta pra tela operacional)
      - Relatório (histórico de sessões)
      - Sair      (logout: limpa sessão + volta pra tela de licença)
    """
    def botao(label: str, on_click, cor=COR_FG) -> ft.Control:
        return ft.TextButton(
            content=label,
            on_click=lambda _: on_click(),
            style=ft.ButtonStyle(
                color=cor,
                padding=ft.Padding(14, 6, 14, 6),
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        )

    pilula = ft.Container(
        padding=ft.Padding(6, 4, 6, 4),
        bgcolor=COR_MUTED,
        border=ft.Border.all(1, COR_BORDER),
        border_radius=10,
        content=ft.Row(
            tight=True,
            spacing=2,
            controls=[
                botao("Principal",  ir_para_principal),
                botao("Relatório",  ir_para_relatorio),
                ft.Container(
                    width=1, height=18, bgcolor=COR_BORDER,
                    margin=ft.Margin(4, 0, 4, 0),
                ),
                botao("Sair", sair, cor=COR_ERROR),
            ],
        ),
    )

    return ft.Container(
        left=0, right=0, bottom=16,
        alignment=ft.Alignment.BOTTOM_CENTER,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[pilula],
        ),
    )


def main(page: ft.Page):
    page.title = f"App Iter v{VERSAO}" + (" [DEV]" if DEV_MODE else "")
    page.bgcolor = COR_BG
    page.padding = 0

    # Ícone da janela (taskbar + title bar) — substitui o default do Flet
    try:
        page.window.icon = str(Path(__file__).resolve().parent / "assets" / "icon.ico")
    except Exception as exc:
        log.warning(f"Falha ao setar ícone da janela: {exc}")

    page.window.min_width = 880
    page.window.min_height = 640
    page.window.width = 1024
    page.window.height = 720

    def _render(controle: ft.Control, with_user_nav: bool = False) -> None:
        """
        Monta a tela com camadas via Stack:
          - Background ambient global (glows azuis sutis)
          - Conteúdo da tela
          - Pílula DEV (se DEV_MODE)  OU  barra do usuário (with_user_nav)

        Nas telas de auth (licenca, onboarding) `with_user_nav` é False.
        Nas telas operacionais (principal, relatorio) é True.
        """
        page.controls.clear()
        camadas: list[ft.Control] = [*camadas_ambient(), controle]
        if DEV_MODE:
            camadas.append(_dev_nav(
                ir_para_principal, ir_para_licenca,
                _ir_para_relatorio_demo, ir_para_onboarding,
            ))
        elif with_user_nav:
            camadas.append(_user_nav(ir_para_principal, ir_para_relatorio, sair))
        page.add(ft.Stack(expand=True, controls=camadas))
        page.update()

    def sair():
        """Logout: limpa sessão local e volta pra tela de licença."""
        try:
            limpar_sessao()
        except Exception as exc:
            log.warning(f"Falha ao limpar sessão: {exc}")
        log.info("Logout realizado pelo usuário.")
        ir_para_licenca()

    def ir_para_onboarding():
        _render(tela_onboarding.construir(
            page, ao_continuar=lambda _: continuar_apos_onboarding(),
        ))

    def continuar_apos_onboarding():
        _flag_onboarding_visto().touch(exist_ok=True)
        roteamento()

    def ir_para_licenca():
        _render(tela_licenca.construir(
            page, ao_ativar=lambda _: ir_para_principal(),
        ))

    def ir_para_principal():
        _render(
            tela_principal.construir(page, ao_concluir=ir_para_relatorio),
            with_user_nav=True,
        )

    def ir_para_relatorio(sucessos: int = 0, falhas: int = 0, duracao: float = 0.0):
        """
        Args mantidos opcionais por compatibilidade com chamadas legadas
        (ao_concluir do tela_principal ainda passa). A tela_relatorio agora
        lê o histórico de sessões direto de planilha_hash.listar_sessoes()
        e ignora esses args.
        """
        _render(
            tela_relatorio.construir(
                page,
                ao_voltar=lambda _: ir_para_principal(),
            ),
            with_user_nav=True,
        )

    def _ir_para_relatorio_demo():
        ir_para_relatorio()

    def roteamento():
        if DEV_MODE:
            log.info("DEV_MODE ativo — pulando onboarding e licença, indo direto para a principal.")
            ir_para_principal()
            return

        if not _flag_onboarding_visto().exists():
            log.info("Primeiro uso — exibindo onboarding.")
            ir_para_onboarding()
            return

        if not checar_acesso():
            log.info("Sem sessão válida — exibindo tela de ativação.")
            ir_para_licenca()
            return

        ir_para_principal()

    roteamento()


if __name__ == "__main__":
    ft.run(
        main,
        assets_dir=str(Path(__file__).resolve().parent / "assets"),
    )
