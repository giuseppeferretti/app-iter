"""
Test harness: constroi cada tela do app contra uma Page mockada e reporta
qualquer erro de API (assinatura errada, kwarg invalido, etc.) sem precisar
abrir a janela Flet de fato.

Roda: `python scripts/test_uis.py`
"""
import sys
import traceback
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import flet as ft

from app.ui import tela_onboarding, tela_licenca, tela_principal, tela_relatorio
from app.main_app import _dev_nav


def _fake_page() -> MagicMock:
    """Page mockada — captura .add/.update/.services/.overlay sem precisar de runtime Flet."""
    page = MagicMock(spec=ft.Page)
    page.overlay = []
    page.services = []
    page.controls = []
    page.snack_bar = None
    return page


def _run(nome: str, fn) -> bool:
    try:
        controle = fn()
        # Walk superficial pra forcar lazy-init de algumas propriedades
        _ = str(controle)
        print(f"  OK   {nome}")
        return True
    except Exception as exc:
        print(f"  FAIL {nome}: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return False


def main() -> int:
    print("Test harness — Telas do App Iter")
    print("=" * 50)
    page = _fake_page()
    falhas = 0
    casos = [
        ("tela_onboarding", lambda: tela_onboarding.construir(page, lambda _: None)),
        ("tela_licenca",    lambda: tela_licenca.construir(page, lambda _: None)),
        ("tela_principal",  lambda: tela_principal.construir(page, lambda *a, **kw: None)),
        ("tela_relatorio",  lambda: tela_relatorio.construir(page, lambda _: None, 12, 1, 87.5)),
        ("dev_nav",         lambda: _dev_nav(lambda: None, lambda: None, lambda: None, lambda: None)),
    ]
    for nome, fn in casos:
        if not _run(nome, fn):
            falhas += 1

    print("=" * 50)
    print(f"Resultado: {len(casos) - falhas}/{len(casos)} OK, {falhas} falha(s)")
    return falhas


if __name__ == "__main__":
    sys.exit(main())
