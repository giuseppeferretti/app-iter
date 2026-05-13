"""
Boot real em FLET_APP_HIDDEN: renderiza cada tela em sequencia e captura
erros de runtime/serializacao que o test_uis.py mockado nao pega.

Importante: ft.run precisa rodar na main thread. Usamos threading.Timer
pra disparar transicoes e fechar a janela no fim.

Uso: `python scripts/boot_test.py`
"""
import asyncio
import os
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ["APP_ANAC_DEV"] = "1"

import flet as ft

from app.main_app import _dev_nav
from app.ui import tela_onboarding, tela_licenca, tela_principal, tela_relatorio
from app.ui.componentes import COR_BG

DELAY_POR_TELA = 1.2
ERROS: list[str] = []


def _capture(label: str, fn) -> None:
    try:
        fn()
    except Exception as exc:
        msg = f"[{label}] {type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        ERROS.append(msg)
        print(msg, file=sys.stderr)


def _main(page: ft.Page):
    page.title = "Boot test — App Iter"
    page.bgcolor = COR_BG
    page.padding = 0
    page.window.width = 1024
    page.window.height = 720

    telas = [
        ("tela_onboarding", lambda: tela_onboarding.construir(page, lambda _: None)),
        ("tela_licenca",    lambda: tela_licenca.construir(page, lambda _: None)),
        ("tela_principal",  lambda: tela_principal.construir(page, lambda *a, **kw: None)),
        ("tela_relatorio",  lambda: tela_relatorio.construir(page, lambda _: None, 12, 1, 87.5)),
    ]

    def _renderiza_proxima(idx: int) -> None:
        if idx >= len(telas):
            print(f"\n--- Renderizadas {len(telas)} telas, encerrando ---")
            print(f"Erros capturados: {len(ERROS)}")
            for e in ERROS:
                print(e, file=sys.stderr)
            # Encerra processo
            os._exit(1 if ERROS else 0)

        nome, builder = telas[idx]
        print(f"  Renderizando {nome}...", flush=True)

        def _faz():
            page.controls.clear()
            # Replica o padrao real do main_app: Stack(tela, dev_nav)
            controle = builder()
            stack = ft.Stack(
                expand=True,
                controls=[
                    controle,
                    _dev_nav(lambda: None, lambda: None, lambda: None, lambda: None),
                ],
            )
            page.add(stack)
            page.update()
            print(f"  OK   {nome}", flush=True)

        _capture(nome, _faz)

        # Proxima tela
        threading.Timer(DELAY_POR_TELA, _renderiza_proxima, args=[idx + 1]).start()

    threading.Timer(0.4, _renderiza_proxima, args=[0]).start()


if __name__ == "__main__":
    assets_dir = ROOT / "app" / "assets"
    ft.run(
        _main,
        view=ft.AppView.FLET_APP_HIDDEN,
        assets_dir=str(assets_dir),
    )
