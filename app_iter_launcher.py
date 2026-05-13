"""Launcher do App Iter (entry point do PyInstaller).

Sit ao lado do pacote `app/` para que o import `from app.X import Y` resolva
corretamente quando empacotado em .exe (--onedir).

Carrega o `.env` a partir do diretório do executável (no bundle) ou do
diretório do script (em dev). Isso é importante porque `app/main_app.py`
resolve o `.env` via `__file__.parent.parent`, que dentro do bundle aponta
pra `_internal/` e não pra pasta onde o usuário tem o `.env`.
"""
import os
import sys
from pathlib import Path


def _resolver_dir_base() -> Path:
    """Retorna o diretório onde o .env e os logs devem viver.

    - PyInstaller bundle: ao lado do .exe (sys.executable).
    - Execução normal: raiz do projeto (parent deste script).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


_DIR_BASE = _resolver_dir_base()

# Carrega .env ANTES de qualquer import que dependa de env vars (supabase,
# DEV_MODE, etc.).
try:
    from dotenv import load_dotenv

    _env_path = _DIR_BASE / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
except ImportError:
    pass

# Faz o pacote `app` resolvível (em dev e no bundle).
if str(_DIR_BASE) not in sys.path:
    sys.path.insert(0, str(_DIR_BASE))

# Em bundle, o pacote `app` é instalado em _internal/. PyInstaller adiciona
# _internal ao sys.path automaticamente, então `import app` funciona.
from app import main_app  # noqa: E402
import flet as ft  # noqa: E402


def _assets_dir() -> str:
    if getattr(sys, "frozen", False):
        # No bundle, assets ficam em _internal/app/assets
        cand = Path(sys._MEIPASS) / "app" / "assets"  # type: ignore[attr-defined]
        if cand.exists():
            return str(cand)
    return str(Path(__file__).resolve().parent / "app" / "assets")


if __name__ == "__main__":
    ft.run(
        main_app.main,
        assets_dir=_assets_dir(),
    )
